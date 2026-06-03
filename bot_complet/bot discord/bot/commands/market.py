from bot.utils.market import (
    load_catalogue, save_catalogue, update_catalogue_message, send_notif, fuzzy_search, _parse_prix_num,
    _item_key,
)
from bot.utils.config import cfg_channel, resolve_channel, load_config
from bot.utils.permissions import is_staff, is_vendeur, is_staff_market
from bot.utils.helpers import now_utc
from bot.utils.logs import send_log
from bot.views.market_view import (
    _PrixAlertView, _SuppAllView, _GestionConfirmView,
    CommandeView, VenduView, RoleToggleView,
    _build_commande_embed_from_items, CatalogueView,
)

import asyncio
import os
import re
import time
import json
from datetime import datetime, timezone
from collections import defaultdict
from pathlib import Path

import discord
from discord.ext import commands

from bot.core import bot, _commande_msg_ids, _catalogue_msg_ids

@bot.command(name="gestion")
async def gestion_cmd(ctx):
    if not is_vendeur(ctx.author):
        await ctx.send("❌ Réservé aux vendeurs certifiés.", delete_after=5); return
    cfg        = load_config(ctx.guild.id)
    gestion_ch = resolve_channel(ctx.guild, cfg.get("salon_gestion"))
    if gestion_ch and ctx.channel.id != gestion_ch.id and not is_staff(ctx.author):
        await ctx.send(f"❌ Cette commande est réservée à {gestion_ch.mention}.", delete_after=6); return

    def chk(m): return m.author.id == ctx.author.id and m.channel.id == ctx.channel.id

    async def ask(titre, desc):
        q = await ctx.send(embed=discord.Embed(title=titre, description=desc, color=0x3498DB, timestamp=now_utc()).set_footer(text="60s · 'annuler' pour quitter"))
        try:
            resp = await bot.wait_for("message", check=chk, timeout=60)
            try: await q.delete()
            except Exception: pass
            try: await resp.delete()
            except Exception: pass
            if resp.content.strip().lower() == "annuler":
                await ctx.send("❌ Gestion annulée.", delete_after=5); return None
            return resp
        except asyncio.TimeoutError:
            try: await q.delete()
            except Exception: pass
            await ctx.send("⏰ Temps écoulé. Gestion annulée.", delete_after=6); return None

    resp_nom = await ask("📦 Étape 1/3 — Nom de l'objet", "Quel est le **nom** de l'article à ajouter/modifier ?")
    if not resp_nom: return
    nom = resp_nom.content.strip()

    resp_qty = await ask("📦 Étape 2/3 — Quantité", f"Quelle **quantité** pour **{nom}** ?")
    if not resp_qty: return
    try:
        qty = int(resp_qty.content.strip())
        if qty <= 0: raise ValueError
    except ValueError:
        await ctx.send("❌ Quantité invalide.", delete_after=6); return

    resp_prix = await ask("📦 Étape 3/3 — Prix", f"Quel est le **prix unitaire** pour **{nom}** ?")
    if not resp_prix: return
    prix = resp_prix.content.strip()

    data    = load_catalogue(ctx.guild.id)
    items   = data.get("items", {})
    my_key  = _item_key(nom, ctx.author.id)
    nom_low = nom.lower().strip()

    existant_autre = next((v for k, v in items.items() if k.split(":")[0] == nom_low and v.get("vendeur_id") != ctx.author.id), None)
    existant = items.get(my_key)

    if existant_autre and not existant:
        vendeur_existant = ctx.guild.get_member(existant_autre["vendeur_id"])
        vendeur_nom = vendeur_existant.display_name if vendeur_existant else f"<@{existant_autre['vendeur_id']}>"
        warn_embed = discord.Embed(title="⚠️ Article déjà en vente par un autre vendeur",
            description=(f"**{existant_autre['nom']}** est vendu par **{vendeur_nom}**.\n\n"
                         f"💰 **Prix actuel :** {existant_autre['prix']}\n"
                         f"📦 **Stock actuel :** {existant_autre['quantite']}\n\n"
                         f"Tu peux quand même ajouter ta propre entrée.\nVeux-tu continuer ?"),
            color=0xE67E22, timestamp=now_utc())
        view = _GestionConfirmView(ctx.author.id)
        msg_warn = await ctx.send(embed=warn_embed, view=view)
        await view.wait()
        try: await msg_warn.delete()
        except Exception: pass
        if not view.result:
            await ctx.send(embed=discord.Embed(title="❌ Gestion annulée", description="Le stock n'a pas été modifié.", color=0xE74C3C), delete_after=6)
            return

    if existant:
        items[my_key]["quantite"] += qty
        items[my_key]["prix"] = prix
        action = f"✏️ **{nom}** mis à jour par {ctx.author.mention} — stock : {items[my_key]['quantite']} · prix : {items[my_key]['prix']}"
    else:
        items[my_key] = {"nom": nom, "quantite": qty, "prix": prix, "vendeur_id": ctx.author.id, "created": time.time()}
        action = f"➕ **{nom}** ajouté par {ctx.author.mention} — stock : {qty} · prix : {prix}"

    data["items"] = items
    save_catalogue(ctx.guild.id, data)
    await update_catalogue_message(ctx.guild, items)
    await send_notif(ctx.guild, action)
    await send_log(ctx.guild, discord.Embed(title="📦 Stock mis à jour via !gestion", description=action, color=0x2ECC71, timestamp=now_utc()))
    await ctx.send(embed=discord.Embed(title="✅ Article enregistré", description=f"**{nom}** — x{qty} à {prix}", color=0x2ECC71, timestamp=now_utc()), delete_after=10)
@bot.command(name="catalogue")
async def catalogue_cmd(ctx, *, args: str = None):
    if not is_vendeur(ctx.author):
        await ctx.send(embed=discord.Embed(title="❌ Permission insuffisante", description="Réservé aux vendeurs certifiés.", color=0xE74C3C), delete_after=5)
        return
    if not args:
        await ctx.send("❌ `!catalogue <nom> <quantité> <prix>`\nExemple : `!catalogue paladium ingot 10 500$`", delete_after=10)
        return
    tokens = args.split()
    if len(tokens) < 3:
        await ctx.send("❌ `!catalogue <nom> <quantité> <prix>`", delete_after=10)
        return
    # Cherche le PREMIER entier pur (de gauche à droite) après la position 0.
    # La quantité est toujours avant le prix : !catalogue <nom...> <QTY> <prix...>
    qty_idx = None
    for i in range(1, len(tokens) - 1):
        if tokens[i].isdigit():
            qty_idx = i
            break
    if qty_idx is None:
        await ctx.send("❌ Format invalide. `!catalogue <nom> <quantité> <prix>`\nExemple : `!catalogue paladium ingot 10 500$`", delete_after=10)
        return
    nom  = " ".join(tokens[:qty_idx])
    prix = " ".join(tokens[qty_idx + 1:])
    if not nom or not prix:
        await ctx.send("❌ Format invalide. `!catalogue <nom> <quantité> <prix>`\nExemple : `!catalogue paladium ingot 10 500$`", delete_after=10)
        return
    try:
        qty = int(tokens[qty_idx])
        if qty <= 0: raise ValueError
    except ValueError:
        await ctx.send("❌ La quantité doit être un nombre entier positif.", delete_after=6)
        return

    data    = load_catalogue(ctx.guild.id)
    items   = data.get("items", {})
    nom_low = nom.lower().strip()
    my_key  = _item_key(nom, ctx.author.id)
    autres  = {k: v for k, v in items.items() if k.split(":")[0] == nom_low and v.get("vendeur_id") != ctx.author.id}
    prix_num = _parse_prix_num(prix)

    if autres and prix_num is not None:
        prix_min_item = min(autres.values(), key=lambda v: (_parse_prix_num(v["prix"]) or float("inf")))
        prix_min_num  = _parse_prix_num(prix_min_item["prix"])
        if prix_min_num is not None and prix_num > prix_min_num:
            vendeur_moins_cher = ctx.guild.get_member(prix_min_item["vendeur_id"])
            vnom = vendeur_moins_cher.display_name if vendeur_moins_cher else f"<@{prix_min_item['vendeur_id']}>"
            warn_embed = discord.Embed(
                title="⚠️ Prix plus élevé détecté",
                description=(f"**{nom}** est déjà vendu à **{prix_min_item['prix']}** par **{vnom}**.\n\n"
                             f"Tu veux le vendre à **{prix}** — c'est plus cher.\n\nVeux-tu quand même publier cet article ?"),
                color=0xE67E22, timestamp=now_utc()
            )
            view     = _PrixAlertView(ctx.author.id)
            warn_msg = await ctx.send(embed=warn_embed, view=view)
            await view.wait()
            try: await warn_msg.delete()
            except Exception: pass
            if not view.result:
                await ctx.send(embed=discord.Embed(title="❌ Publication annulée", description="L'article n'a pas été ajouté.", color=0xE74C3C), delete_after=5)
                return

    if my_key in items:
        ancien_prix_num  = _parse_prix_num(items[my_key]["prix"])
        items[my_key]["quantite"] += qty
        if ancien_prix_num is not None and prix_num is not None and prix_num < ancien_prix_num:
            items[my_key]["prix"] = prix
        else:
            items[my_key]["prix"] = prix
        items[my_key]["updated"] = time.time()
        action = f"✏️ **{nom}** mis à jour par {ctx.author.mention} — stock : {items[my_key]['quantite']} · prix : {items[my_key]['prix']}"
    else:
        items[my_key] = {"nom": nom, "quantite": qty, "prix": prix, "vendeur_id": ctx.author.id, "created": time.time(), "updated": time.time()}
        action = f"➕ **{nom}** ajouté par {ctx.author.mention} — stock : {qty} · prix : {prix}"

    data["items"] = items
    save_catalogue(ctx.guild.id, data)
    await update_catalogue_message(ctx.guild, items)
    await send_notif(ctx.guild, action)
    await ctx.send(embed=discord.Embed(title="✅ Catalogue mis à jour", description=f"**{nom}** — x{qty} à {prix}", color=0x2ECC71), delete_after=8)


@bot.command(name="cataloguesupp")
async def cataloguesupp_cmd(ctx):
    if not is_vendeur(ctx.author):
        await ctx.send(embed=discord.Embed(title="❌ Permission insuffisante", description="Réservé aux vendeurs certifiés.", color=0xE74C3C), delete_after=5)
        return
    data  = load_catalogue(ctx.guild.id)
    items = data.get("items", {})
    staff = is_staff(ctx.author)
    items_visibles = items if staff else {k: v for k, v in items.items() if v.get("vendeur_id") == ctx.author.id}

    if not items_visibles:
        await ctx.send(embed=discord.Embed(title="❌ Aucun article trouvé", description="Tu n'as aucun article dans le catalogue." if not staff else "Le catalogue est vide.", color=0xE74C3C), delete_after=8)
        return

    embed = discord.Embed(title="🗑️ Suppression d'article — Choisir", color=0xE74C3C, timestamp=now_utc())
    lignes    = []
    keys_list = list(items_visibles.keys())
    for i, key in enumerate(keys_list, 1):
        item = items_visibles[key]
        if staff:
            vendeur_m = ctx.guild.get_member(item["vendeur_id"])
            vnom = vendeur_m.display_name if vendeur_m else f"<@{item['vendeur_id']}>"
            lignes.append(f"`{i}.` 🔹 **{item['nom']}** — 📦 {item['quantite']} · 💰 {item['prix']} · 👤 {vnom}")
        else:
            lignes.append(f"`{i}.` 🔹 **{item['nom']}** — 📦 {item['quantite']} · 💰 {item['prix']}")

    chunk, chunks = "", []
    for l in lignes:
        if len(chunk) + len(l) + 1 > 1000: chunks.append(chunk); chunk = l
        else: chunk = (chunk + "\n" + l).strip()
    if chunk: chunks.append(chunk)
    for idx, c in enumerate(chunks):
        embed.add_field(name="\u200b" if idx > 0 else "📋 Articles disponibles", value=c, inline=False)
    embed.set_footer(text="Réponds avec le numéro ou le nom exact · 'annuler' pour quitter · 60s")
    msg_list = await ctx.send(embed=embed)

    def chk(m): return m.author.id == ctx.author.id and m.channel.id == ctx.channel.id
    try: resp = await bot.wait_for("message", check=chk, timeout=60)
    except asyncio.TimeoutError:
        try: await msg_list.delete()
        except Exception: pass
        await ctx.send(embed=discord.Embed(title="⏰ Temps écoulé", description="Suppression annulée.", color=0xE67E22), delete_after=6)
        return

    try: await resp.delete()
    except Exception: pass
    try: await msg_list.delete()
    except Exception: pass

    contenu = resp.content.strip()
    if contenu.lower() == "annuler":
        await ctx.send(embed=discord.Embed(title="❌ Annulé", description="Aucun article supprimé.", color=0x95A5A6), delete_after=5)
        return

    target_key = None
    if contenu.isdigit():
        idx = int(contenu) - 1
        if 0 <= idx < len(keys_list): target_key = keys_list[idx]
    if target_key is None:
        contenu_low = contenu.lower()
        for k, v in items_visibles.items():
            if v["nom"].lower() == contenu_low or k.split(":")[0] == contenu_low:
                target_key = k; break
    if target_key is None:
        await ctx.send(embed=discord.Embed(title="❌ Article introuvable", description=f"Aucun article correspondant à **{contenu}**.", color=0xE74C3C), delete_after=8)
        return

    item_cible = items.get(target_key)
    if not item_cible:
        await ctx.send(embed=discord.Embed(title="❌ Article introuvable", description="Cet article n'existe plus dans le catalogue.", color=0xE74C3C), delete_after=8)
        return
    if not staff and item_cible.get("vendeur_id") != ctx.author.id:
        await ctx.send(embed=discord.Embed(title="❌ Permission insuffisante", description="Tu ne peux supprimer que tes propres articles.", color=0xE74C3C), delete_after=6)
        return

    nom_supp = item_cible["nom"]
    del items[target_key]
    data["items"] = items
    save_catalogue(ctx.guild.id, data)
    await update_catalogue_message(ctx.guild, items)
    await send_notif(ctx.guild, f"🗑️ **{nom_supp}** supprimé du catalogue par {ctx.author.mention}")
    await send_log(ctx.guild, discord.Embed(title="🗑️ Article supprimé du catalogue", description=f"**{nom_supp}** retiré par {ctx.author.mention}", color=0xE74C3C, timestamp=now_utc()))
    await ctx.send(embed=discord.Embed(title="✅ Article supprimé", description=f"**{nom_supp}** a été retiré du catalogue.", color=0x2ECC71), delete_after=8)




@bot.command(name="cataloguesuppall")
async def cataloguesuppall_cmd(ctx):
    if not is_staff(ctx.author):
        await ctx.send(embed=discord.Embed(title="❌ Permission insuffisante", description="Cette commande est réservée au staff.", color=0xE74C3C), delete_after=5)
        return
    data  = load_catalogue(ctx.guild.id)
    items = data.get("items", {})
    if not items:
        await ctx.send(embed=discord.Embed(title="📭 Catalogue vide", description="Il n'y a aucun article à supprimer.", color=0x95A5A6), delete_after=6)
        return
    nb   = len(items)
    view = _SuppAllView(ctx.author.id)
    warn_msg = await ctx.send(embed=discord.Embed(
        title="⚠️ Suppression totale du catalogue",
        description=f"Tu es sur le point de supprimer **{nb} article(s)** du catalogue.\n\n**Cette action est irréversible.**\n\nConfirmes-tu ?",
        color=0xE74C3C, timestamp=now_utc()
    ), view=view)
    await view.wait()
    try: await warn_msg.delete()
    except Exception: pass
    if not view.result:
        await ctx.send(embed=discord.Embed(title="❌ Annulé", description="Le catalogue n'a pas été modifié.", color=0x95A5A6), delete_after=5)
        return
    data["items"] = {}
    save_catalogue(ctx.guild.id, data)
    await update_catalogue_message(ctx.guild, {})
    await send_notif(ctx.guild, f"🗑️ Le catalogue a été entièrement vidé par {ctx.author.mention}.")
    await send_log(ctx.guild, discord.Embed(title="🗑️ Catalogue entièrement supprimé", description=f"Vidé par {ctx.author.mention} — {nb} article(s) supprimé(s).", color=0xE74C3C, timestamp=now_utc()))
    await ctx.send(embed=discord.Embed(title="✅ Catalogue entièrement supprimé", description=f"**{nb} article(s)** ont été supprimés.", color=0x2ECC71), delete_after=10)


@bot.command(name="stock")
async def stock_cmd(ctx, cible: discord.Member = None):
    catalogue_ch = cfg_channel(ctx.guild, "salon_catalogue")
    in_catalogue = catalogue_ch and ctx.channel.id == catalogue_ch.id
    if not in_catalogue and not is_staff_market(ctx.author):
        await ctx.send("❌ Réservé aux vendeurs certifiés.", delete_after=5); return
    target    = cible or ctx.author
    data      = load_catalogue(ctx.guild.id)
    items     = data.get("items", {})
    ses_items = {k: v for k, v in items.items() if v.get("vendeur_id") == target.id}
    title     = f"📦 Mon stock — {target.display_name}" if target.id == ctx.author.id else f"📦 Stock de {target.display_name}"
    embed     = discord.Embed(title=title, color=0x3498DB, timestamp=now_utc())
    if not ses_items:
        embed.description = f"Aucun article en vente pour **{target.display_name}**."
    else:
        total_u = sum(v["quantite"] for v in ses_items.values())
        embed.description = f"**{len(ses_items)}** article(s) • **{total_u}** unité(s) au total"
        for key, item in ses_items.items():
            embed.add_field(name=f"🔹 {item['nom']}", value=f"📦 {item['quantite']}\n💰 {item['prix']}", inline=True)
    if in_catalogue:
        try: await ctx.message.delete()
        except Exception: pass
        try:
            await ctx.author.send(embed=embed)
            await ctx.send(f"📩 {ctx.author.mention} Réponse envoyée en DM.", delete_after=6)
        except discord.Forbidden:
            await ctx.send(f"{ctx.author.mention} Impossible d'envoyer le DM — active tes messages privés.", delete_after=8)
    else:
        await ctx.send(embed=embed)


@bot.command(name="recherche")
async def recherche_cmd(ctx, *, terme: str = None):
    if terme is None: await ctx.send("❌ `!recherche [nom_item]`", delete_after=6); return
    recherche_ch = cfg_channel(ctx.guild, "salon_recherche")
    if not is_staff(ctx.author) and recherche_ch and ctx.channel.id != recherche_ch.id:
        await ctx.send(f"❌ Utilise `!recherche` dans {recherche_ch.mention}.", delete_after=8); return
    data          = load_catalogue(ctx.guild.id)
    items         = data.get("items", {})
    resultats_raw = fuzzy_search(terme, items)
    resultats     = {k: v for k, (v, score) in resultats_raw.items()}
    embed = discord.Embed(title=f"🔍 Recherche : « {terme} »", color=0x9B59B6, timestamp=now_utc())
    if not resultats:
        embed.description = f"❌ Aucun article trouvé pour **{terme}**."
    else:
        embed.description = f"**{len(resultats)}** résultat(s) :"
        for key, item in resultats.items():
            vendeur_m   = ctx.guild.get_member(item["vendeur_id"])
            vendeur_str = vendeur_m.display_name if vendeur_m else f"<@{item['vendeur_id']}>"
            embed.add_field(name=f"🔹 {item['nom']}", value=f"📦 **Stock :** {item['quantite']}\n💰 **Prix :** {item['prix']}\n👤 {vendeur_str}", inline=True)
    embed.set_footer(text="Utilisez !commande pour passer une commande")
    catalogue_ch = cfg_channel(ctx.guild, "salon_catalogue")
    if catalogue_ch and ctx.channel.id == catalogue_ch.id:
        try: await ctx.message.delete()
        except Exception: pass
        try:
            await ctx.author.send(embed=embed)
            await ctx.send(f"📩 {ctx.author.mention} Résultat envoyé en DM.", delete_after=6)
        except discord.Forbidden:
            await ctx.send(f"{ctx.author.mention} Impossible d'envoyer le DM — active tes messages privés.", delete_after=8)
    else:
        await ctx.send(embed=embed)
@bot.command(name="commande")
async def commande_cmd(ctx):
    if not is_staff(ctx.author): await ctx.send("❌ Réservé au staff.", delete_after=5); return

    # Récupérer le salon salon_commandes configuré
    cmd_ch = cfg_channel(ctx.guild, "salon_commandes")
    if not cmd_ch:
        await ctx.send("❌ Salon `salon_commandes` introuvable. Configurez-le d'abord.", delete_after=8)
        return

    # Supprimer le message de commande du staff
    try:
        await ctx.message.delete()
    except Exception:
        pass

    data  = load_catalogue(ctx.guild.id)
    items = data.get("items", {})
    embed = _build_commande_embed_from_items(ctx.guild, items)
    view  = CommandeView(ctx.guild.id, items)

    # Récupérer l'ancien message embed s'il existe pour l'éditer plutôt que d'en créer un nouveau
    old_msg_id = data.get("commande_msg_id") or _commande_msg_ids.get(ctx.guild.id)
    msg = None
    if old_msg_id:
        try:
            msg = await cmd_ch.fetch_message(old_msg_id)
            await msg.edit(embed=embed, view=view)
        except Exception:
            msg = None

    if msg is None:
        # Purger tous les messages du salon sauf l'embed permanent
        try:
            await cmd_ch.purge(limit=100, check=lambda m: True)
        except Exception:
            pass
        msg = await cmd_ch.send(embed=embed, view=view)

    _commande_msg_ids[ctx.guild.id] = msg.id
    data["commande_msg_id"] = msg.id
    save_catalogue(ctx.guild.id, data)

    await ctx.send(f"✅ Embed de commande posté/mis à jour dans {cmd_ch.mention} !", delete_after=5)
@bot.command(name="vendu")
async def vendu_cmd(ctx):
    topic = getattr(ctx.channel, "topic", None) or ""
    if not topic.startswith("commande|"):
        await ctx.send(embed=discord.Embed(title="❌ Mauvais salon", description="Cette commande s'utilise uniquement dans un **ticket de commande market**.", color=0xE74C3C), delete_after=6)
        return
    if not is_vendeur(ctx.author):
        await ctx.send(embed=discord.Embed(title="❌ Permission refusée", description="Cette commande est réservée aux **vendeurs certifiés** et au **staff**.", color=0xE74C3C), delete_after=8)
        return
    parts = topic.split("|")
    if len(parts) < 4:
        await ctx.send(embed=discord.Embed(title="❌ Ticket invalide", description="Les données de ce ticket sont invalides.", color=0xE74C3C), delete_after=6)
        return
    _, *nom_parts, quantite_str, vendeur_id_str = parts
    nom_key = "|".join(nom_parts)
    try:
        quantite   = int(quantite_str)
        vendeur_id = int(vendeur_id_str)
    except ValueError:
        await ctx.send(embed=discord.Embed(title="❌ Données corrompues", description="Impossible de lire la quantité ou l'ID vendeur.", color=0xE74C3C), delete_after=6)
        return
    data        = load_catalogue(ctx.guild.id)
    items       = data.get("items", {})
    nom_affiche = items[nom_key]["nom"] if nom_key in items else nom_key.split(":")[0]
    embed = discord.Embed(title="📦 Confirmation de vente", description=f"Article : **{nom_affiche}**\nQuantité : **{quantite}**\n\nConfirme ou annule la transaction.", color=0x9B59B6, timestamp=now_utc())
    await ctx.send(embed=embed, view=VenduView(ctx.guild.id, vendeur_id, nom_key, quantite, ctx.channel.id))


@bot.command(name="role")
async def role_cmd(ctx):
    if not is_staff(ctx.author):
        await ctx.send("❌ Réservé au staff.", delete_after=5)
        return
    channel = cfg_channel(ctx.guild, "salon_role_toggle")
    if not channel:
        await ctx.send("❌ Salon introuvable. Configurez `salon_role_toggle`.", delete_after=5)
        return
    embed = discord.Embed(
        title="🔔 Notifications du marché",
        description="Clique pour **activer ou désactiver** les notifications du marché.",
        color=0x9B59B6,
    )
    await channel.send(embed=embed, view=RoleToggleView())
    await ctx.send(f"✅ Embed posté dans {channel.mention}", delete_after=5)


async def _log_vente(guild, acheteur_id, vendeur, nom, quantite, prix_unitaire):
    log_ch = cfg_channel(guild, "salon_ventes_log")
    if not log_ch: return
    nums = re.findall(r"[\d]+(?:[.,][\d]+)?", prix_unitaire)
    prix_total_str = "?"
    if nums:
        try:
            unit_val  = float(nums[0].replace(",", "."))
            total_val = unit_val * quantite
            prix_total_str = str(int(total_val)) if total_val == int(total_val) else f"{total_val:.2f}"
        except Exception: pass
    embed = discord.Embed(title="💸 Vente confirmée", color=0x2ECC71, timestamp=now_utc())
    embed.add_field(name="🔹 Article",    value=nom,           inline=True)
    embed.add_field(name="📦 Quantité",   value=str(quantite), inline=True)
    embed.add_field(name="💰 Prix unit.", value=prix_unitaire, inline=True)
    embed.add_field(name="🧾 Prix total", value=f"{quantite} × {prix_unitaire} = **{prix_total_str}**", inline=False)
    embed.add_field(name="🛒 Acheteur",  value=f"<@{acheteur_id}>" if acheteur_id else "Inconnu", inline=True)
    embed.add_field(name="👤 Vendeur",   value=vendeur.mention, inline=True)
    await log_ch.send(embed=embed)


# ════════════════════════════════════════════════════════════════
#  !catalogueview — poste l'embed catalogue permanent dans le salon dédié
# ════════════════════════════════════════════════════════════════
@bot.command(name="catalogueview")
async def catalogueview_cmd(ctx):
    """Poste l'embed catalogue permanent dans le salon catalogue configuré."""
    if not ctx.author.guild_permissions.administrator and not is_staff(ctx.author):
        await ctx.send("❌ Réservé au staff.", delete_after=5)
        return

    guild   = ctx.guild
    cfg     = load_config(guild.id)
    data    = load_catalogue(guild.id)
    items   = data.get("items", {})

    # Salon cible : salon_catalogue configuré ou salon actuel
    salon_id = cfg.get("salon_catalogue") or cfg.get("catalogue_channel")
    target   = guild.get_channel(int(salon_id)) if salon_id else ctx.channel

    if not target:
        target = ctx.channel

    # Embed public (statique, A→Z)
    from bot.utils.market import build_catalogue_embed
    embed = build_catalogue_embed(items)

    # Vue publique avec bouton "🔽 Trier / Parcourir" (timeout=None = persistant)
    view = CatalogueView()

    try:
        await ctx.message.delete()
    except discord.Forbidden:
        pass

    msg = await target.send(embed=embed, view=view)

    # Sauvegarder l'ID du message pour les mises à jour automatiques
    data["msg_id"] = msg.id
    _catalogue_msg_ids[guild.id] = msg.id
    save_catalogue(guild.id, data)

    if target != ctx.channel:
        await ctx.send(f"✅ Catalogue posté dans {target.mention} !", delete_after=5)


# ════════════════════════════════════════════════════════════════
#  !cataloguesuppjoueur — supprime toutes les annonces d'un joueur
# ════════════════════════════════════════════════════════════════
class _SuppJoueurConfirmView(discord.ui.View):
    def __init__(self, author_id: int):
        super().__init__(timeout=30)
        self.author_id = author_id
        self.result    = None

    async def interaction_check(self, i: discord.Interaction):
        return i.user.id == self.author_id

    @discord.ui.button(label="✅ Confirmer", style=discord.ButtonStyle.red)
    async def confirmer(self, interaction, button):
        self.result = True
        self.stop()
        for child in self.children: child.disabled = True
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="❌ Annuler", style=discord.ButtonStyle.grey)
    async def annuler(self, interaction, button):
        self.result = False
        self.stop()
        for child in self.children: child.disabled = True
        await interaction.response.edit_message(view=self)


@bot.command(name="cataloguesuppjoueur")
async def cataloguesuppjoueur_cmd(ctx, *, cible: str = None):
    """Supprime toutes les annonces d'un joueur (staff/admin uniquement)."""
    if not is_staff(ctx.author):
        await ctx.send(
            embed=discord.Embed(title="❌ Permission insuffisante", description="Réservé au staff.", color=0xE74C3C),
            delete_after=5
        )
        return

    if not cible:
        await ctx.send("❌ `!cataloguesuppjoueur <pseudo ou @mention ou ID>`", delete_after=8)
        return

    # Résolution du membre : mention, ID ou pseudo
    member = None
    if ctx.message.mentions:
        member = ctx.message.mentions[0]
    else:
        try:
            member = ctx.guild.get_member(int(cible))
        except ValueError:
            pass
        if not member:
            cible_low = cible.lower()
            for m in ctx.guild.members:
                if m.display_name.lower() == cible_low or m.name.lower() == cible_low:
                    member = m
                    break

    data  = load_catalogue(ctx.guild.id)
    items = data.get("items", {})

    if not member:
        await ctx.send(
            embed=discord.Embed(
                title="⚠️ Membre introuvable",
                description=(
                    f"Aucun membre nommé **{cible}** sur ce serveur.\n"
                    "Si le joueur a quitté, utilisez son **ID Discord** :\n"
                    "`!cataloguesuppjoueur 123456789012345678`"
                ),
                color=0xE67E22
            ),
            delete_after=12
        )
        return

    nom_affiche = member.display_name
    cibles_keys = {k for k, v in items.items() if v.get("vendeur_id") == member.id}

    if not cibles_keys:
        await ctx.send(
            embed=discord.Embed(
                title="📭 Aucune annonce trouvée",
                description=f"**{nom_affiche}** n'a aucune annonce dans le catalogue.",
                color=0x95A5A6
            ),
            delete_after=8
        )
        return

    nb = len(cibles_keys)

    # Confirmation
    view     = _SuppJoueurConfirmView(ctx.author.id)
    warn_msg = await ctx.send(
        embed=discord.Embed(
            title="⚠️ Confirmation requise",
            description=(
                f"Voulez-vous vraiment supprimer **{nb} annonce(s)** appartenant à **{nom_affiche}** ?\n\n"
                "**Cette action est irréversible.**"
            ),
            color=0xE67E22,
            timestamp=now_utc()
        ),
        view=view
    )
    await view.wait()
    try: await warn_msg.delete()
    except Exception: pass

    if not view.result:
        await ctx.send(
            embed=discord.Embed(title="❌ Annulé", description="Aucune annonce supprimée.", color=0x95A5A6),
            delete_after=5
        )
        return

    # Suppression effective
    for k in cibles_keys:
        del items[k]

    data["items"] = items
    save_catalogue(ctx.guild.id, data)
    await update_catalogue_message(ctx.guild, items)
    await send_notif(ctx.guild, f"🗑️ Toutes les annonces de **{nom_affiche}** ont été supprimées par {ctx.author.mention}.")
    await send_log(ctx.guild, discord.Embed(
        title="🗑️ Annonces joueur supprimées",
        description=f"**{nb}** annonce(s) de **{nom_affiche}** supprimées par {ctx.author.mention}.",
        color=0xE74C3C,
        timestamp=now_utc()
    ))
    await ctx.send(
        embed=discord.Embed(
            title="✅ Annonces supprimées",
            description=f"🗑️ Toutes les annonces de **{nom_affiche}** ont été supprimées du catalogue. ({nb} article(s))",
            color=0x2ECC71,
            timestamp=now_utc()
        ),
        delete_after=12
    )