import discord

from bot.core import bot

from bot.core import _pending_orders
from bot.utils.market import (
    load_catalogue, save_catalogue, fuzzy_search, _clean_ghost_items,
    update_catalogue_message, send_notif, _parse_prix_num,
)
from bot.utils.config import cfg_category, cfg_channel, cfg_role, load_config
from bot.utils.permissions import is_staff, is_vendeur
from bot.utils.helpers import now_utc
from bot.utils.logs import send_log
from bot.utils.stats import record_sale

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
        # custom_id stable par guild — nécessaire pour bot.add_view() persistant
        super().__init__(
            placeholder="🔹 Choisis un article…",
            min_values=1, max_values=1,
            options=options[:25],
            custom_id=f"commande_select_{guild_id}"
        )

    async def callback(self, interaction: discord.Interaction):
        try:
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
                if msg.content.strip().lower() == "annuler":
                    await interaction.followup.send("❌ Commande annulée.", ephemeral=True); return
                try:
                    qty = int(msg.content.strip())
                    if qty <= 0: raise ValueError
                except ValueError:
                    await interaction.followup.send("❌ Quantité invalide. Tape un nombre entier positif, ou **annuler** pour quitter.", ephemeral=True); return
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
                from bot.utils.invite_rewards import build_market_reward_embed
                reward_embed = build_market_reward_embed(guild, acheteur)
                await ticket_channel.send(
                    content=f"{acheteur.mention} {vendeur.mention if vendeur else ''}",
                    embeds=[embed_ticket, reward_embed],
                )
                await interaction.followup.send(f"✅ Ticket créé : {ticket_channel.mention}", ephemeral=True)
            finally:
                _pending_orders.pop(pk, None)
        except discord.NotFound:
            pass
        except discord.InteractionResponded:
            pass
        except Exception as e:
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(f"❌ Une erreur est survenue : {e}", ephemeral=True)
                else:
                    await interaction.followup.send(f"❌ Une erreur est survenue : {e}", ephemeral=True)
            except Exception:
                pass


class CommandeRechercheModal(discord.ui.Modal, title="🔍 Rechercher un article"):
    terme = discord.ui.TextInput(label="Nom ou mots-clés", placeholder="ex: paladium", max_length=50)
    def __init__(self, guild_id):
        super().__init__()
        self.guild_id = guild_id
    async def on_submit(self, interaction: discord.Interaction):
        try:
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
        except Exception as e:
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(f"❌ Erreur : {e}", ephemeral=True)
                else:
                    await interaction.followup.send(f"❌ Erreur : {e}", ephemeral=True)
            except Exception:
                pass
    async def on_error(self, interaction: discord.Interaction, error: Exception):
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(embed=discord.Embed(title="❌ Erreur inattendue", description=str(error), color=0xE74C3C), ephemeral=True)
            else:
                await interaction.followup.send(embed=discord.Embed(title="❌ Erreur inattendue", description=str(error), color=0xE74C3C), ephemeral=True)
        except Exception:
            pass


class _CommandeRechercheButton(discord.ui.Button):
    def __init__(self, guild_id: int):
        super().__init__(
            label="🔍 Rechercher",
            style=discord.ButtonStyle.blurple,
            row=1,
            custom_id=f"commande_search_{guild_id}",
        )
        self.guild_id = guild_id

    async def callback(self, interaction: discord.Interaction):
        try:
            await interaction.response.send_modal(CommandeRechercheModal(interaction.guild.id))
        except Exception as e:
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        embed=discord.Embed(title="❌ Erreur", description=str(e), color=0xE74C3C),
                        ephemeral=True
                    )
            except Exception:
                pass


class CommandeView(discord.ui.View):
    def __init__(self, guild_id, items):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.add_item(CommandeSelect(guild_id, _clean_ghost_items(items)))
        self.add_item(_CommandeRechercheButton(guild_id))


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
    instructions = "📋 **Menu déroulant** → sélectionner un article\n🔍 **Rechercher** → trouver par nom ou mots-clés\n🔄 Catalogue mis à jour automatiquement"
    if len(live) > 25:
        instructions += f"\n⚠️ **{len(live) - 25} article(s) non affiché(s) dans le menu** — utilisez 🔍 Rechercher pour les trouver"
    embed.add_field(name="━━━━━━━━━━━━━━━━━━", value=instructions, inline=False)
    embed.set_footer(text="Embed permanent · Se met à jour automatiquement toutes les 3s")
    return embed
class VenduView(discord.ui.View):
    def __init__(self, guild_id, vendeur_id, nom_key, quantite, ticket_channel_id):
        super().__init__(timeout=None)
        self.guild_id          = guild_id
        self.vendeur_id        = vendeur_id
        self.nom_key           = nom_key
        self.quantite          = quantite
        self.ticket_channel_id = ticket_channel_id
        self.done              = False

    def _disable_all(self):
        for child in self.children: child.disabled = True

    @discord.ui.button(label="✅ Vendu", style=discord.ButtonStyle.green, custom_id="vendu_confirmer")
    async def vendu(self, interaction, button):
        try:
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
            from bot.commands.market import _log_vente
            await _log_vente(guild=guild, acheteur_id=acheteur_id, vendeur=interaction.user, nom=nom_affiche, quantite=self.quantite, prix_unitaire=prix_item)
            record_sale(self.guild_id, interaction.user.id, self.quantite)
            embed = discord.Embed(title="✅ Vente confirmée !", description=f"Article : **{nom_affiche}**\nQuantité : **{self.quantite}**", color=0x2ECC71, timestamp=now_utc())
            embed.set_footer(text="Ticket fermé dans 10 secondes")
            await interaction.followup.edit_message(message_id=interaction.message.id, embed=embed, view=self)
            await asyncio.sleep(10)
            channel = guild.get_channel(self.ticket_channel_id)
            if channel:
                try: await channel.delete(reason="Vente confirmée")
                except Exception: pass
        except discord.NotFound:
            pass
        except discord.InteractionResponded:
            pass
        except Exception as e:
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(f"❌ Erreur : {e}", ephemeral=True)
                else:
                    await interaction.followup.send(f"❌ Erreur : {e}", ephemeral=True)
            except Exception:
                pass

    @discord.ui.button(label="❌ Pas vendu", style=discord.ButtonStyle.red, custom_id="vendu_annuler")
    async def pas_vendu(self, interaction, button):
        try:
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
        except discord.NotFound:
            pass
        except discord.InteractionResponded:
            pass
        except Exception as e:
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(f"❌ Erreur : {e}", ephemeral=True)
                else:
                    await interaction.followup.send(f"❌ Erreur : {e}", ephemeral=True)
            except Exception:
                pass
class RoleToggleView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔔 Activer/désactiver les notifications", style=discord.ButtonStyle.blurple, custom_id="role_toggle_acheteur")
    async def toggle_role(self, interaction, button):
        try:
            role = cfg_role(interaction.guild, "role_acheteur_notif")
            if not role:
                await interaction.response.send_message("❌ Rôle introuvable.", ephemeral=True); return
            await interaction.response.defer(ephemeral=True)
            member = interaction.user
            if role in member.roles:
                await member.remove_roles(role, reason="Toggle notif market")
                await interaction.followup.send("🔕 Notifications marché **désactivées**.", ephemeral=True)
            else:
                await member.add_roles(role, reason="Toggle notif market")
                await interaction.followup.send("🔔 Notifications marché **activées** !", ephemeral=True)
        except discord.NotFound:
            pass
        except discord.InteractionResponded:
            pass
        except Exception as e:
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(f"❌ Erreur : {e}", ephemeral=True)
                else:
                    await interaction.followup.send(f"❌ Erreur : {e}", ephemeral=True)
            except Exception:
                pass


# ═══════════════════════════════════════════════════════════════
# MODAL QUANTITÉ — après sélection d'un article depuis la recherche
# ═══════════════════════════════════════════════════════════════
class _CatalogueQuantiteModal(discord.ui.Modal, title="🛒 Quantité souhaitée"):
    quantite = discord.ui.TextInput(
        label="Quantité", placeholder="ex: 5", min_length=1, max_length=6
    )

    def __init__(self, guild: discord.Guild, item_key: str, item: dict):
        super().__init__()
        self.guild    = guild
        self.item_key = item_key
        self.item     = item

    async def on_submit(self, interaction: discord.Interaction):
        try:
            qty = int(str(self.quantite).strip())
            if qty <= 0:
                raise ValueError
        except ValueError:
            await interaction.response.send_message(
                embed=discord.Embed(title="❌ Quantité invalide", description="Entre un nombre entier supérieur à 0.", color=0xE74C3C),
                ephemeral=True
            )
            return

        # Recharger le stock en temps réel
        data  = load_catalogue(self.guild.id)
        items = data.get("items", {})
        item  = items.get(self.item_key)
        if not item or item.get("quantite", 0) <= 0:
            await interaction.response.send_message(
                embed=discord.Embed(title="❌ Article indisponible", description="Cet article a été retiré ou est épuisé.", color=0xE74C3C),
                ephemeral=True
            )
            return
        if qty > item["quantite"]:
            await interaction.response.send_message(
                embed=discord.Embed(title="❌ Stock insuffisant", description=f"Stock disponible : **{item['quantite']}**", color=0xE74C3C),
                ephemeral=True
            )
            return

        # Vérif commande en cours
        pk = f"{self.guild.id}:{interaction.user.id}"
        if _pending_orders.get(pk):
            await interaction.response.send_message(
                embed=discord.Embed(title="⏳ Commande en cours", description="Tu as déjà une commande en attente.", color=0xE67E22),
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        _pending_orders[pk] = True
        try:
            acheteur = interaction.user
            vendeur  = self.guild.get_member(item["vendeur_id"])
            category = cfg_category(self.guild, "categorie_commandes")
            overwrites = {
                self.guild.default_role: discord.PermissionOverwrite(view_channel=False),
                acheteur:                discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
                self.guild.me:           discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True),
            }
            if vendeur:
                overwrites[vendeur] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
            ticket_channel = await self.guild.create_text_channel(
                name=f"cmd-{acheteur.display_name[:16]}-{item['nom'][:10]}",
                category=category, overwrites=overwrites,
                topic=f"commande|{self.item_key}|{qty}|{item['vendeur_id']}"
            )
            nums = re.findall(r"[\d]+(?:[.,][\d]+)?", item["prix"])
            prix_total_str = f"{qty} × {item['prix']}"
            if nums:
                try:
                    unit_val  = float(nums[0].replace(",", "."))
                    total_val = unit_val * qty
                    suffix    = str(int(total_val)) if total_val == int(total_val) else f"{total_val:.2f}"
                    prix_total_str = f"{qty} × {item['prix']} = **{suffix}**"
                except Exception:
                    pass
            embed_ticket = discord.Embed(title="📦 Nouvelle commande", color=0x2ECC71, timestamp=now_utc())
            embed_ticket.add_field(name="🔹 Article",    value=item["nom"],     inline=True)
            embed_ticket.add_field(name="📦 Quantité",   value=str(qty),        inline=True)
            embed_ticket.add_field(name="💰 Prix unit.", value=item["prix"],     inline=True)
            embed_ticket.add_field(name="🧾 Prix total", value=prix_total_str,   inline=False)
            embed_ticket.add_field(name="🛒 Acheteur",  value=acheteur.mention, inline=True)
            embed_ticket.add_field(name="👤 Vendeur",   value=vendeur.mention if vendeur else f"<@{item['vendeur_id']}>", inline=True)
            embed_ticket.set_footer(text="Vendeur : utilise !vendu pour confirmer ou refuser")
            from bot.utils.invite_rewards import build_market_reward_embed
            reward_embed = build_market_reward_embed(self.guild, acheteur)
            await ticket_channel.send(
                content=f"{acheteur.mention} {vendeur.mention if vendeur else ''}",
                embeds=[embed_ticket, reward_embed],
            )
            await interaction.followup.send(
                embed=discord.Embed(title="✅ Ticket créé !", description=f"Ta commande a été envoyée dans {ticket_channel.mention}", color=0x2ECC71),
                ephemeral=True
            )
        except Exception as e:
            try:
                await interaction.followup.send(embed=discord.Embed(title="❌ Erreur", description=str(e), color=0xE74C3C), ephemeral=True)
            except Exception:
                pass
        finally:
            _pending_orders.pop(pk, None)

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(embed=discord.Embed(title="❌ Erreur inattendue", description=str(error), color=0xE74C3C), ephemeral=True)
            else:
                await interaction.followup.send(embed=discord.Embed(title="❌ Erreur inattendue", description=str(error), color=0xE74C3C), ephemeral=True)
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════
# SELECT RÉSULTATS RECHERCHE — permet d'acheter directement
# ═══════════════════════════════════════════════════════════════
class _RechercheResultatSelect(discord.ui.Select):
    def __init__(self, guild: discord.Guild, resultats: dict):
        self.guild    = guild
        self.resultats = resultats   # {key: (item, score)}
        options = []
        for key, (item, score) in list(resultats.items())[:25]:
            vendeur_m = guild.get_member(item["vendeur_id"])
            vnom      = vendeur_m.display_name if vendeur_m else "?"
            options.append(discord.SelectOption(
                label=item["nom"][:50],
                value=key,
                description=f"📦 {item['quantite']}x · 💰 {item['prix'][:30]} · 👤 {vnom}"[:100],
            ))
        import uuid
        super().__init__(
            placeholder="Sélectionne un article pour commander…",
            options=options,
            custom_id=f"cat_recherche_select_{uuid.uuid4().hex[:8]}",
        )

    async def callback(self, interaction: discord.Interaction):
        try:
            key  = self.values[0]
            data = load_catalogue(interaction.guild.id)
            item = data.get("items", {}).get(key)
            if not item or item.get("quantite", 0) <= 0:
                await interaction.response.send_message(
                    embed=discord.Embed(title="❌ Article indisponible", description="Cet article n'est plus disponible.", color=0xE74C3C),
                    ephemeral=True
                )
                return
            await interaction.response.send_modal(_CatalogueQuantiteModal(interaction.guild, key, item))
        except discord.NotFound:
            pass
        except discord.InteractionResponded:
            pass
        except Exception as e:
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(f"❌ Erreur : {e}", ephemeral=True)
                else:
                    await interaction.followup.send(f"❌ Erreur : {e}", ephemeral=True)
            except Exception:
                pass


class _RechercheResultatView(discord.ui.View):
    def __init__(self, guild: discord.Guild, resultats: dict):
        super().__init__(timeout=120)
        self.add_item(_RechercheResultatSelect(guild, resultats))


# ═══════════════════════════════════════════════════════════════
# MODAL RECHERCHE CATALOGUE
# ═══════════════════════════════════════════════════════════════
class CatalogueRechercheModal(discord.ui.Modal, title="🔍 Rechercher dans le catalogue"):
    terme = discord.ui.TextInput(label="Nom ou mots-clés", placeholder="ex: findium, titane…", max_length=50)

    def __init__(self, guild_id):
        super().__init__()
        self.guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction):
        try:
            data  = load_catalogue(self.guild_id)
            items = data.get("items", {})
            res   = fuzzy_search(str(self.terme), items)
            if not res:
                await interaction.response.send_message(
                    embed=discord.Embed(
                        title="❌ Aucun résultat",
                        description=f"Aucun article trouvé pour **{self.terme}**.",
                        color=0xE74C3C
                    ),
                    ephemeral=True
                )
                return

            embed = discord.Embed(
                title=f"🔍 Résultats pour « {self.terme} »",
                description="Sélectionne un article ci-dessous pour passer commande.",
                color=0x9B59B6,
                timestamp=now_utc()
            )
            for key, (item, score) in list(res.items())[:10]:
                vendeur_m = interaction.guild.get_member(item["vendeur_id"])
                vnom      = vendeur_m.display_name if vendeur_m else f"<@{item['vendeur_id']}>"
                embed.add_field(
                    name=f"🔹 {item['nom']}",
                    value=f"📦 **Stock :** {item['quantite']}  💰 **Prix :** {item['prix']}  👤 {vnom}",
                    inline=False
                )

            view = _RechercheResultatView(interaction.guild, res)
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        except Exception as e:
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(embed=discord.Embed(title="❌ Erreur", description=str(e), color=0xE74C3C), ephemeral=True)
                else:
                    await interaction.followup.send(embed=discord.Embed(title="❌ Erreur", description=str(e), color=0xE74C3C), ephemeral=True)
            except Exception:
                pass

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(embed=discord.Embed(title="❌ Erreur inattendue", description=str(error), color=0xE74C3C), ephemeral=True)
            else:
                await interaction.followup.send(embed=discord.Embed(title="❌ Erreur inattendue", description=str(error), color=0xE74C3C), ephemeral=True)
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════
# CONSTANTES
# ═══════════════════════════════════════════════════════════════
ITEMS_PAR_PAGE = 10

TRI_LABELS = {
    "az":         "🔤 A → Z",
    "prix_asc":   "💰 Prix croissant",
    "prix_desc":  "💰 Prix décroissant",
    "stock_desc": "📦 Plus gros stock",
    "stock_asc":  "📦 Plus petit stock",
    "vendeur":    "👤 Par vendeur",
}


# ═══════════════════════════════════════════════════════════════
# VUE PUBLIQUE — embed permanent avec un seul bouton
# timeout=None = persistant même après redémarrage
# ═══════════════════════════════════════════════════════════════
class CatalogueView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="🔽 Trier / Parcourir",
        style=discord.ButtonStyle.blurple,
        custom_id="catalogue_open_perso",
    )
    async def ouvrir_perso(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            data  = load_catalogue(interaction.guild.id)
            items = data.get("items", {})
            view  = _CataloguePersoView(interaction.guild, items)
            embed = view.build_embed()
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        except Exception as e:
            try:
                await interaction.response.send_message(
                    embed=discord.Embed(title="❌ Erreur", description=f"Impossible d'ouvrir le catalogue : {e}", color=0xE74C3C),
                    ephemeral=True
                )
            except Exception:
                pass


# ═══════════════════════════════════════════════════════════════
# SELECT TRI (utilisé dans la vue personnelle)
# ═══════════════════════════════════════════════════════════════
class _CatalogueTriSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="🔤 A → Z",            value="az"),
            discord.SelectOption(label="💰 Prix croissant",   value="prix_asc"),
            discord.SelectOption(label="💰 Prix décroissant", value="prix_desc"),
            discord.SelectOption(label="📦 Plus gros stock",  value="stock_desc"),
            discord.SelectOption(label="📦 Plus petit stock", value="stock_asc"),
            discord.SelectOption(label="👤 Par vendeur",      value="vendeur"),
        ]
        import uuid
        super().__init__(placeholder="Trier par…", options=options, custom_id=f"cat_perso_tri_{uuid.uuid4().hex[:8]}")

    async def callback(self, interaction: discord.Interaction):
        try:
            view: _CataloguePersoView = self.view
            view.tri_actif = self.values[0]
            view.page      = 0
            view._rebuild_pages()
            view._sync_buttons()
            await interaction.response.edit_message(embed=view.build_embed(), view=view)
        except Exception as e:
            try:
                await interaction.response.send_message(
                    embed=discord.Embed(title="❌ Erreur", description=str(e), color=0xE74C3C),
                    ephemeral=True
                )
            except Exception:
                pass


# ═══════════════════════════════════════════════════════════════
# VUE PERSONNELLE ÉPHÉMÈRE — tri + pagination + recherche
# ═══════════════════════════════════════════════════════════════
class _CataloguePersoView(discord.ui.View):
    """Vue éphémère personnelle : chaque utilisateur a la sienne."""

    def __init__(self, guild: discord.Guild, items: dict, tri_actif: str = "az", page: int = 0):
        super().__init__(timeout=300)
        self.guild     = guild
        self.items     = _clean_ghost_items(items)
        self.tri_actif = tri_actif
        self.page      = page
        self.pages: list[list] = []
        self._owner_id: int | None = None

        self.add_item(_CatalogueTriSelect())
        self._rebuild_pages()
        self._sync_buttons()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self._owner_id is None:
            self._owner_id = interaction.user.id
        if interaction.user.id != self._owner_id:
            await interaction.response.send_message(
                "❌ Cette vue ne t'appartient pas. Clique sur **🔽 Trier / Parcourir** pour ouvrir la tienne.",
                ephemeral=True
            )
            return False
        return True

    # ── Tri ────────────────────────────────────────────────────
    def _sorted_items(self) -> list:
        items = list(self.items.values())
        if self.tri_actif == "az":
            return sorted(items, key=lambda x: x["nom"].lower())
        elif self.tri_actif == "prix_asc":
            return sorted(items, key=lambda x: (_parse_prix_num(x["prix"]) or float("inf")))
        elif self.tri_actif == "prix_desc":
            return sorted(items, key=lambda x: (_parse_prix_num(x["prix"]) or 0), reverse=True)
        elif self.tri_actif == "stock_desc":
            return sorted(items, key=lambda x: x["quantite"], reverse=True)
        elif self.tri_actif == "stock_asc":
            return sorted(items, key=lambda x: x["quantite"])
        else:  # vendeur
            return sorted(items, key=lambda x: (
                self.guild.get_member(x["vendeur_id"]).display_name.lower()
                if self.guild.get_member(x["vendeur_id"]) else "zzz"
            ))

    # ── Pagination ─────────────────────────────────────────────
    def _rebuild_pages(self):
        sorted_items = self._sorted_items()
        if not sorted_items:
            self.pages = [[]]
        else:
            self.pages = [
                sorted_items[i:i + ITEMS_PAR_PAGE]
                for i in range(0, len(sorted_items), ITEMS_PAR_PAGE)
            ]
        self.page = max(0, min(self.page, len(self.pages) - 1))

    def _sync_buttons(self):
        # Cherche les boutons par leur label plutôt que par custom_id (car les custom_ids sont dynamiques)
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                if child.label == "◀":
                    child.disabled = self.page == 0
                elif child.label == "▶":
                    child.disabled = self.page >= len(self.pages) - 1

    # ── Embed ──────────────────────────────────────────────────
    def build_embed(self) -> discord.Embed:
        total    = len(self.items)
        nb_pages = len(self.pages)
        embed = discord.Embed(
            title="🏪 Catalogue — Vue personnelle",
            description=(
                f"**{total}** article(s) · Tri : {TRI_LABELS.get(self.tri_actif, '—')}\n"
                f"Page **{self.page + 1}** / **{nb_pages}**"
            ),
            color=0xF1C40F,
            timestamp=now_utc(),
        )
        if not self.items:
            embed.add_field(name="📭 Aucun article", value="Le catalogue est vide.", inline=False)
            return embed

        page_items = self.pages[self.page] if self.pages else []

        if self.tri_actif == "vendeur":
            par_vendeur: dict[str, list] = defaultdict(list)
            for item in page_items:
                m    = self.guild.get_member(item["vendeur_id"])
                vnom = m.display_name if m else f"Vendeur #{item['vendeur_id']}"
                par_vendeur[vnom].append(item)
            for vnom, arts in par_vendeur.items():
                lignes = "\n".join(
                    f"🔹 **{a['nom']}** — 📦 {a['quantite']}x · 💰 {a['prix']}"
                    for a in arts
                )
                embed.add_field(name=f"━━━━━━ 👤 {vnom} ━━━━━━", value=lignes, inline=False)
        else:
            chunk, chunks = "", []
            for item in page_items:
                m     = self.guild.get_member(item["vendeur_id"])
                vnom  = m.display_name if m else f"<@{item['vendeur_id']}>"
                ligne = f"🔹 **{item['nom']}** — 📦 {item['quantite']}x · 💰 {item['prix']} · 👤 {vnom}"
                if len(chunk) + len(ligne) + 1 > 1000:
                    chunks.append(chunk); chunk = ligne
                else:
                    chunk = (chunk + "\n" + ligne).strip()
            if chunk: chunks.append(chunk)
            for idx, c in enumerate(chunks):
                embed.add_field(name="📋 Articles" if idx == 0 else "\u200b", value=c, inline=False)

        embed.set_footer(text="Visible uniquement par toi · 🔍 Rechercher pour trouver et commander un article")
        return embed

    # ── Boutons navigation + recherche ─────────────────────────
    @discord.ui.button(label="◀", style=discord.ButtonStyle.grey, row=1, disabled=True)
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            self.page -= 1
            self._sync_buttons()
            await interaction.response.edit_message(embed=self.build_embed(), view=self)
        except Exception as e:
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(embed=discord.Embed(title="❌ Erreur", description=str(e), color=0xE74C3C), ephemeral=True)
                else:
                    await interaction.followup.send(embed=discord.Embed(title="❌ Erreur", description=str(e), color=0xE74C3C), ephemeral=True)
            except Exception:
                pass

    @discord.ui.button(label="🔍 Rechercher", style=discord.ButtonStyle.blurple, row=1)
    async def recherche(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.send_modal(CatalogueRechercheModal(interaction.guild.id))
        except Exception as e:
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(embed=discord.Embed(title="❌ Erreur", description=str(e), color=0xE74C3C), ephemeral=True)
                else:
                    await interaction.followup.send(embed=discord.Embed(title="❌ Erreur", description=str(e), color=0xE74C3C), ephemeral=True)
            except Exception:
                pass

    @discord.ui.button(label="▶", style=discord.ButtonStyle.grey, row=1)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            self.page += 1
            self._sync_buttons()
            await interaction.response.edit_message(embed=self.build_embed(), view=self)
        except Exception as e:
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(embed=discord.Embed(title="❌ Erreur", description=str(e), color=0xE74C3C), ephemeral=True)
                else:
                    await interaction.followup.send(embed=discord.Embed(title="❌ Erreur", description=str(e), color=0xE74C3C), ephemeral=True)
            except Exception:
                pass