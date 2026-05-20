import asyncio
import io
import os
import re
import time
import json
import random
import sqlite3
import difflib
from datetime import datetime, timezone
from collections import defaultdict
from pathlib import Path

import discord
from discord.ext import commands

from bot.core import bot

from bot.core import _pending_orders
from bot.utils.market import (
    load_catalogue, fuzzy_search, _clean_ghost_items,
    update_catalogue_message, send_notif, _parse_prix_num,
)
from bot.utils.config import cfg_category, cfg_channel, load_config
from bot.utils.permissions import is_staff, is_vendeur
from bot.utils.helpers import now_utc
from bot.utils.logs import send_log

class _GestionConfirmView(discord.ui.View):
    def __init__(self, author_id: int):
        super().__init__(timeout=60)
        self.author_id = author_id
        self.result    = None
    async def interaction_check(self, i): return i.user.id == self.author_id
    @discord.ui.button(label="✅ Confirmer", style=discord.ButtonStyle.green)
    async def confirmer(self, interaction, button):
        self.result = True; self.stop(); await interaction.response.defer()
    @discord.ui.button(label="❌ Annuler", style=discord.ButtonStyle.red)
    async def annuler(self, interaction, button):
        self.result = False; self.stop(); await interaction.response.defer()
class _PrixAlertView(discord.ui.View):
    def __init__(self, author_id):
        super().__init__(timeout=60)
        self.author_id = author_id
        self.result    = None
    async def interaction_check(self, i): return i.user.id == self.author_id
    @discord.ui.button(label="✅ Oui, publier quand même", style=discord.ButtonStyle.green)
    async def oui(self, i, b): self.result = True; self.stop(); await i.response.defer()
    @discord.ui.button(label="❌ Non, annuler", style=discord.ButtonStyle.red)
    async def non(self, i, b): self.result = False; self.stop(); await i.response.defer()
class _SuppAllView(discord.ui.View):
    def __init__(self, author_id):
        super().__init__(timeout=30)
        self.author_id = author_id
        self.result    = None
    async def interaction_check(self, i): return i.user.id == self.author_id
    @discord.ui.button(label="✅ Confirmer — Tout supprimer", style=discord.ButtonStyle.red)
    async def confirmer(self, interaction, button):
        self.result = True; self.stop()
        for child in self.children: child.disabled = True
        await interaction.response.edit_message(view=self)
    @discord.ui.button(label="❌ Annuler", style=discord.ButtonStyle.grey)
    async def annuler(self, interaction, button):
        self.result = False; self.stop()
        for child in self.children: child.disabled = True
        await interaction.response.edit_message(view=self)
class CommandeSelect(discord.ui.Select):
    def __init__(self, guild_id, items):
        self.guild_id = guild_id
        options = []
        for key, item in items.items():
            if item.get("quantite", 0) <= 0: continue
            options.append(discord.SelectOption(
                label=f"{item['nom'][:20]} ({item['prix'][:15]})"[:25],
                value=key,
                description=f"Stock: {item['quantite']} · Vendeur: <@{item['vendeur_id']}>"[:100]
            ))
        if not options:
            options = [discord.SelectOption(label="Aucun article disponible", value="__vide__")]
        super().__init__(placeholder="🔹 Choisis un article…", min_values=1, max_values=1, options=options[:25], custom_id=f"commande_select_{guild_id}")

    async def callback(self, interaction: discord.Interaction):
        nom_key = self.values[0]
        if nom_key == "__vide__":
            await interaction.response.send_message("📭 Aucun article disponible.", ephemeral=True); return
        gid = interaction.guild.id
        uid = interaction.user.id
        pk  = f"{gid}:{uid}"
        if _pending_orders.get(pk):
            await interaction.response.send_message("⏳ Tu as déjà une commande en cours.", ephemeral=True); return
        data  = load_catalogue(gid)
        items = data.get("items", {})
        item  = items.get(nom_key)
        if not item or item.get("quantite", 0) <= 0:
            await interaction.response.send_message("❌ Article indisponible ou épuisé.", ephemeral=True); return
        await interaction.response.defer(ephemeral=True, thinking=True)
        _pending_orders[pk] = True
        try:
            embed_ask = discord.Embed(
                title=f"🛒 Commande — {item['nom']}",
                description=f"📦 **Stock :** {item['quantite']}\n💰 **Prix :** {item['prix']}\n\nÉcris la **quantité** souhaitée dans ce salon.\n*(60 secondes)*",
                color=0x3498DB
            )
            await interaction.followup.send(embed=embed_ask, ephemeral=True)
            def check(m): return m.author.id == uid and m.channel.id == interaction.channel.id
            try: msg = await bot.wait_for("message", check=check, timeout=60)
            except asyncio.TimeoutError:
                await interaction.followup.send("⏰ Temps écoulé. Commande annulée.", ephemeral=True); return
            try: await msg.delete()
            except Exception: pass
            try:
                qty = int(msg.content.strip())
                if qty <= 0: raise ValueError
            except ValueError:
                await interaction.followup.send("❌ Quantité invalide.", ephemeral=True); return
            data  = load_catalogue(gid)
            items = data.get("items", {})
            item  = items.get(nom_key)
            if not item:
                await interaction.followup.send("❌ Article retiré entre-temps.", ephemeral=True); return
            if qty > item["quantite"]:
                await interaction.followup.send(f"❌ Stock insuffisant. Disponible : **{item['quantite']}**", ephemeral=True); return
            guild    = interaction.guild
            acheteur = interaction.user
            vendeur  = guild.get_member(item["vendeur_id"])
            category = cfg_category(guild, "categorie_commandes")
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                acheteur:           discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
                guild.me:           discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True),
            }
            if vendeur:
                overwrites[vendeur] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
            ticket_channel = await guild.create_text_channel(
                name=f"cmd-{acheteur.display_name[:16]}-{item['nom'][:10]}",
                category=category, overwrites=overwrites,
                topic=f"commande|{nom_key}|{qty}|{item['vendeur_id']}"
            )
            nums = re.findall(r"[\d]+(?:[.,][\d]+)?", item["prix"])
            prix_total_str = f"{qty} × {item['prix']}"
            if nums:
                try:
                    unit_val  = float(nums[0].replace(",", "."))
                    total_val = unit_val * qty
                    suffix    = str(int(total_val)) if total_val == int(total_val) else f"{total_val:.2f}"
                    prix_total_str = f"{qty} × {item['prix']} = **{suffix}**"
                except Exception: pass
            embed_ticket = discord.Embed(title="📦 Nouvelle commande", color=0x2ECC71, timestamp=now_utc())
            embed_ticket.add_field(name="🔹 Article",    value=item["nom"],      inline=True)
            embed_ticket.add_field(name="📦 Quantité",   value=str(qty),         inline=True)
            embed_ticket.add_field(name="💰 Prix unit.", value=item["prix"],      inline=True)
            embed_ticket.add_field(name="🧾 Prix total", value=prix_total_str,    inline=False)
            embed_ticket.add_field(name="🛒 Acheteur",  value=acheteur.mention,  inline=True)
            embed_ticket.add_field(name="👤 Vendeur",   value=vendeur.mention if vendeur else f"<@{item['vendeur_id']}>", inline=True)
            embed_ticket.set_footer(text="Vendeur : utilise !vendu pour confirmer ou refuser")
            await ticket_channel.send(content=f"{acheteur.mention} {vendeur.mention if vendeur else ''}", embed=embed_ticket)
            await interaction.followup.send(f"✅ Ticket créé : {ticket_channel.mention}", ephemeral=True)
        finally:
            _pending_orders.pop(pk, None)


class CommandeRechercheModal(discord.ui.Modal, title="🔍 Rechercher un article"):
    terme = discord.ui.TextInput(label="Nom ou mots-clés", placeholder="ex: paladium", max_length=50)
    def __init__(self, guild_id):
        super().__init__()
        self.guild_id = guild_id
    async def on_submit(self, interaction: discord.Interaction):
        data  = load_catalogue(self.guild_id)
        items = data.get("items", {})
        res   = fuzzy_search(str(self.terme), items)
        if not res:
            await interaction.response.send_message("❌ Aucun résultat trouvé.", ephemeral=True); return
        embed = discord.Embed(title=f"🔍 Résultats pour « {self.terme} »", color=0x9B59B6, timestamp=now_utc())
        for key, (item, score) in list(res.items())[:10]:
            vendeur_m = interaction.guild.get_member(item["vendeur_id"])
            vnom      = vendeur_m.display_name if vendeur_m else f"<@{item['vendeur_id']}>"
            embed.add_field(name=f"🔹 {item['nom']} ({int(score*100)}% match)", value=f"📦 {item['quantite']} · 💰 {item['prix']} · 👤 {vnom}", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)


class CommandeView(discord.ui.View):
    def __init__(self, guild_id, items):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.add_item(CommandeSelect(guild_id, _clean_ghost_items(items)))

    @discord.ui.button(label="🔍 Rechercher", style=discord.ButtonStyle.blurple, row=1, custom_id="commande_search")
    async def recherche(self, interaction, button):
        await interaction.response.send_modal(CommandeRechercheModal(interaction.guild.id))


def _build_commande_embed_from_items(guild: discord.Guild, items: dict) -> discord.Embed:
    embed = discord.Embed(title="🛒 Boutique — Passer une commande", color=0x9B59B6, timestamp=now_utc())
    if guild.icon: embed.set_thumbnail(url=guild.icon.url)
    live = _clean_ghost_items(items)
    if not live:
        embed.description = "📭 **Le catalogue est vide pour l'instant.**\nRevenez bientôt !"
    else:
        par_vendeur: dict[int, list] = defaultdict(list)
        for key, item in live.items():
            par_vendeur[item["vendeur_id"]].append(item)
        lignes = []
        for vendeur_id, arts in par_vendeur.items():
            membre = guild.get_member(vendeur_id)
            vnom   = membre.display_name if membre else f"Vendeur #{vendeur_id}"
            lignes.append(f"**🏷️ {vnom}**")
            for art in arts:
                lignes.append(f"  └ 🔹 **{art['nom']}** — 📦 {art['quantite']} · 💰 {art['prix']}")
        embed.description = "\n".join(lignes)
    embed.add_field(name="━━━━━━━━━━━━━━━━━━",
        value="📋 **Menu déroulant** → sélectionner un article\n🔍 **Rechercher** → trouver par nom ou mots-clés\n🔄 Catalogue mis à jour automatiquement",
        inline=False)
    embed.set_footer(text="Embed permanent · Se met à jour automatiquement toutes les 3s")
    return embed
class VenduView(discord.ui.View):
    def __init__(self, guild_id, vendeur_id, nom_key, quantite, ticket_channel_id):
        super().__init__(timeout=600)
        self.guild_id          = guild_id
        self.vendeur_id        = vendeur_id
        self.nom_key           = nom_key
        self.quantite          = quantite
        self.ticket_channel_id = ticket_channel_id
        self.done              = False

    def _disable_all(self):
        for child in self.children: child.disabled = True

    @discord.ui.button(label="✅ Vendu", style=discord.ButtonStyle.green)
    async def vendu(self, interaction, button):
        if interaction.user.id != self.vendeur_id and not is_staff(interaction.user):
            await interaction.response.send_message("❌ Seul le vendeur peut valider.", ephemeral=True); return
        if self.done: await interaction.response.send_message("⚠️ Déjà effectué.", ephemeral=True); return
        self.done = True; self._disable_all(); self.stop()
        await interaction.response.defer()
        guild = interaction.guild
        data  = load_catalogue(self.guild_id)
        items = data.get("items", {})
        nom_affiche = items[self.nom_key]["nom"] if self.nom_key in items else self.nom_key.split(":")[0]
        prix_item   = items[self.nom_key].get("prix", "?") if self.nom_key in items else "?"
        ticket_ch   = guild.get_channel(self.ticket_channel_id)
        acheteur_id = None
        if ticket_ch:
            for target, _ in ticket_ch.overwrites.items():
                if isinstance(target, discord.Member) and target.id != interaction.user.id and not target.bot:
                    acheteur_id = target.id; break
        if self.nom_key in items:
            items[self.nom_key]["quantite"] -= self.quantite
            if items[self.nom_key]["quantite"] <= 0:
                del items[self.nom_key]
                await send_notif(guild, f"📭 **{nom_affiche}** épuisé et retiré du catalogue.")
            items = _clean_ghost_items(items)
            data["items"] = items
            save_catalogue(self.guild_id, data)
            await update_catalogue_message(guild, items)
        await _log_vente(guild=guild, acheteur_id=acheteur_id, vendeur=interaction.user, nom=nom_affiche, quantite=self.quantite, prix_unitaire=prix_item)
        embed = discord.Embed(title="✅ Vente confirmée !", description=f"Article : **{nom_affiche}**\nQuantité : **{self.quantite}**", color=0x2ECC71, timestamp=now_utc())
        embed.set_footer(text="Ticket fermé dans 10 secondes")
        await interaction.followup.edit_message(message_id=interaction.message.id, embed=embed, view=self)
        await asyncio.sleep(10)
        channel = guild.get_channel(self.ticket_channel_id)
        if channel:
            try: await channel.delete(reason="Vente confirmée")
            except Exception: pass

    @discord.ui.button(label="❌ Pas vendu", style=discord.ButtonStyle.red)
    async def pas_vendu(self, interaction, button):
        if interaction.user.id != self.vendeur_id and not is_staff(interaction.user):
            await interaction.response.send_message("❌ Seul le vendeur peut décider.", ephemeral=True); return
        if self.done: await interaction.response.send_message("⚠️ Déjà effectué.", ephemeral=True); return
        self.done = True; self._disable_all(); self.stop()
        await interaction.response.defer()
        embed = discord.Embed(title="❌ Vente annulée", description="Le stock n'a pas été modifié.\nTicket fermé dans 10 secondes.", color=0xE74C3C, timestamp=now_utc())
        await interaction.followup.edit_message(message_id=interaction.message.id, embed=embed, view=self)
        await asyncio.sleep(10)
        channel = interaction.guild.get_channel(self.ticket_channel_id)
        if channel:
            try: await channel.delete(reason="Vente annulée")
            except Exception: pass
class RoleToggleView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔔 Activer/désactiver les notifications", style=discord.ButtonStyle.blurple, custom_id="role_toggle_acheteur")
    async def toggle_role(self, interaction, button):
        role = cfg_role(interaction.guild, "role_acheteur_notif")
        if not role: await interaction.response.send_message("❌ Rôle introuvable.", ephemeral=True); return
        await interaction.response.defer(ephemeral=True, thinking=False)
        member = interaction.user
        if role in member.roles:
            await member.remove_roles(role, reason="Toggle notif market")
            await interaction.followup.send("🔕 Notifications marché **désactivées**.", ephemeral=True)
        else:
            await member.add_roles(role, reason="Toggle notif market")
            await interaction.followup.send("🔔 Notifications marché **activées** !", ephemeral=True)
