import asyncio
import discord

from bot.core import bot

from bot.utils.config import cfg_roles, cfg_role, cfg_category, cfg_channel, load_config
from bot.utils.permissions import is_staff
from bot.utils.tickets import send_ticket_log


async def _create_ticket_thread(guild: discord.Guild, parent: discord.TextChannel, name: str, creator: discord.Member, extra_members=None) -> discord.Thread:
    """Crée un thread privé pour servir de ticket (alternative aux salons dédiés)."""
    thread = await parent.create_thread(
        name=name[:100],
        type=discord.ChannelType.private_thread,
        invitable=False,
        reason=f"Ticket créé par {creator}",
    )
    try:
        await thread.add_user(creator)
    except Exception:
        pass
    for m in (extra_members or []):
        try:
            await thread.add_user(m)
        except Exception:
            pass
    return thread

class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="📋 Demande de recrutement", style=discord.ButtonStyle.green, custom_id="ticket_recrutement")
    async def recrutement(self, interaction, button):
        await creer_ticket(interaction, "recrutement")

    @discord.ui.button(label="📩 Autre demande", style=discord.ButtonStyle.blurple, custom_id="ticket_autre")
    async def autre(self, interaction, button):
        await creer_ticket(interaction, "autre")


class FermerView(discord.ui.View):
    def __init__(self, closer):
        super().__init__(timeout=30)
        self.closer = closer
        self.action_taken = False
        self._msg = None

    async def update_countdown(self, message):
        self._msg = message
        for remaining in range(29, 0, -1):
            if self.action_taken: return
            await asyncio.sleep(1)
            try:
                embed = discord.Embed(title="🔒 Fermer le ticket", description=f"Es-tu sûr ?\n\n⏳ Expiration dans **{remaining}s**…", color=0xFF0000)
                embed.set_footer(text="Aucune action = ticket conservé")
                await message.edit(embed=embed)
            except Exception: return

    async def on_timeout(self):
        if self.action_taken: return
        self.action_taken = True
        for child in self.children: child.disabled = True
        if self._msg:
            try: await self._msg.edit(embed=discord.Embed(title="⏳ Temps écoulé", description="Le ticket n'a **pas** été fermé.", color=0xE67E22), view=self)
            except Exception: pass

    @discord.ui.button(label="✅ Confirmer la fermeture", style=discord.ButtonStyle.red, custom_id="fermer_confirmer")
    async def confirmer(self, interaction, button):
        if self.action_taken:
            await interaction.response.send_message("⚠️ Déjà effectué.", ephemeral=True); return
        self.action_taken = True
        for child in self.children: child.disabled = True
        self.stop()
        await interaction.response.edit_message(embed=discord.Embed(title="🔒 Fermeture en cours…", description="Suppression dans **5 secondes**.", color=0x2ECC71), view=self)
        await send_ticket_log(interaction.guild, interaction.channel, self.closer)
        await asyncio.sleep(5)
        try: await interaction.channel.delete()
        except discord.NotFound: pass

    @discord.ui.button(label="❌ Annuler", style=discord.ButtonStyle.grey, custom_id="fermer_annuler")
    async def annuler(self, interaction, button):
        if self.action_taken:
            await interaction.response.send_message("⚠️ Déjà effectué.", ephemeral=True); return
        self.action_taken = True
        for child in self.children: child.disabled = True
        self.stop()
        await interaction.response.edit_message(embed=discord.Embed(title="❌ Fermeture annulée", description="Le ticket reste ouvert.", color=0x95A5A6), view=self)


async def creer_ticket(interaction: discord.Interaction, type_ticket: str):
    guild       = interaction.guild
    staff_roles = cfg_roles(guild, "role_staff")
    recruteur   = cfg_role(guild, "role_recruteur")
    category    = cfg_category(guild, "categorie_tickets")
    cfg         = load_config(guild.id)

    if cfg.get("tickets_mode") == "threads":
        parent = cfg_channel(guild, "salon_tickets_parent")
        if not parent:
            await interaction.response.send_message(
                "❌ Mode threads activé mais aucun salon parent configuré. Contacte un staff.",
                ephemeral=True,
            )
            return
        # Staff avec la permission "Gérer les threads/salons" voient les threads privés
        # sans besoin d'y être ajoutés individuellement ; on ajoute quand même le recruteur.
        extra = [recruteur] if (recruteur and type_ticket == "recrutement") else []
        channel = await _create_ticket_thread(guild, parent, f"ticket-{interaction.user.name}", interaction.user, extra)
    else:
        overwrites  = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user:   discord.PermissionOverwrite(view_channel=True, send_messages=True),
        }
        for r in staff_roles:
            overwrites[r] = discord.PermissionOverwrite(view_channel=True, send_messages=True)
        if recruteur and type_ticket == "recrutement":
            overwrites[recruteur] = discord.PermissionOverwrite(view_channel=True, send_messages=True)
        channel = await guild.create_text_channel(f"ticket-{interaction.user.name}", category=category, overwrites=overwrites)
    if type_ticket == "recrutement":
        ping  = recruteur.mention if recruteur else " ".join(r.mention for r in staff_roles) or "@Staff"
        texte = (
            f"{ping} | {interaction.user.mention}\n\n"
            f"📋 **FORMULAIRE DE RECRUTEMENT – LA MYSTIC**\n\n"
            f"**1️⃣ Présentation personnelle**\n➤ Pseudo EXACT en jeu :\n➤ Âge (minimum 16 ans) :\n➤ Style de jeu : (PvP / Farm / Build / Polyvalent)\n➤ Expérience en faction / Points forts :\n\n"
            f"**2️⃣ Objectifs personnels sur le serveur**\n➤ Court terme :\n➤ Long terme :\n\n"
            f"**3️⃣ Motivation et contribution**\n➤ Pourquoi souhaites-tu rejoindre la Mystic ?\n➤ Ce que tu recherches dans une faction :\n➤ Ce que tu peux apporter à la Mystic :\n\n"
            f"**4️⃣ Historique de factions**\n➤ Anciennes factions (si oui, lesquelles ?) :\n➤ Raison(s) de départ :\n\n"
            f"**5️⃣ Plateforme et stuff actuel**\n➤ Plateforme de jeu : (PlayStation / Xbox / PC / Mobile)\n➤ Armure, armes, enchantements importants, ressources notables :\n\n"
            f"**6️⃣ Temps de jeu & disponibilités**\n➤ Jours joués par semaine :\n➤ Plages horaires approximatives :\n\n"
            f"**7️⃣ Auto-critique**\n➤ Quel défaut ou point faible pourrait jouer en ta défaveur dans une faction ?\n\n"
            f"**8️⃣ Mentalité et esprit de faction**\n➤ Comment décrirais-tu le membre idéal d'une faction ?\n➤ Quelle est ta vision du travail d'équipe ?\n\n"
            f"**9️⃣ Informations complémentaires**\n➤ Screenshots OBLIGATOIRES : (stuff, métiers, argent…)\n➤ Autres informations importantes :\n\n"
            f"**✅ Confirmation**\n☐ J'ai 16 ans ou plus\n☐ Je m'engage à respecter les règles de la Mystic\n☐ Je comprends que toute fausse information entraînera un refus\n\n"
            f"*Pour fermer ce ticket : `!fermer`*"
        )
    else:
        ping  = " ".join(r.mention for r in staff_roles) or "@Staff"
        texte = f"{ping} | {interaction.user.mention}\n\n📩 **Autre demande**\n\nExplique ta demande, un membre te répondra.\nPour fermer : `!fermer`"
    await channel.send(texte)
    await interaction.response.send_message(f"✅ Ticket créé : {channel.mention}", ephemeral=True)