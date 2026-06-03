"""
utils/logs.py — Système de logs ultra-précis.

Chaque action génère un embed dédié avec :
  - Qui a fait l'action (modérateur avec mention + ID)
  - Sur qui (cible avec mention + ID + avatar)
  - Quand (timestamp exact)
  - Pourquoi (raison complète)
  - Où (salon concerné si applicable)
  - Contexte supplémentaire (durée, contenu, historique, etc.)
"""
import discord

from bot.utils.config import cfg_channel
from bot.utils.helpers import now_utc


async def get_log_channel(guild: discord.Guild) -> discord.TextChannel | None:
    return cfg_channel(guild, "salon_logs")


async def send_log(guild: discord.Guild, embed: discord.Embed, content: str = ""):
    ch = await get_log_channel(guild)
    if ch:
        try:
            await ch.send(content=content, embed=embed)
        except Exception as e:
            print(f"[LOG] Erreur envoi log : {e}")


# ═══════════════════════════════════════════════════════════════
#  MODÉRATION — Actions staff
# ═══════════════════════════════════════════════════════════════

def log_ban(
    moderateur: discord.Member,
    cible: discord.Member,
    raison: str,
    nb_jours_suppression: int = 1,
) -> discord.Embed:
    embed = discord.Embed(
        title="🔨 BAN — Membre banni",
        color=0xC0392B,
        timestamp=now_utc(),
    )
    embed.set_thumbnail(url=cible.display_avatar.url)
    embed.add_field(name="🎯 Cible",             value=f"{cible.mention}\n`{cible}` — ID `{cible.id}`",         inline=True)
    embed.add_field(name="🛡️ Modérateur",        value=f"{moderateur.mention}\n`{moderateur}` — ID `{moderateur.id}`", inline=True)
    embed.add_field(name="\u200b",               value="\u200b", inline=True)
    embed.add_field(name="📝 Raison",            value=raison,  inline=False)
    embed.add_field(name="🗑️ Messages supprimés", value=f"{nb_jours_suppression} jour(s)", inline=True)
    embed.add_field(name="📅 Compte créé le",    value=discord.utils.format_dt(cible.created_at, style="D"), inline=True)
    embed.set_footer(text=f"ID action : BAN-{cible.id}")
    return embed


def log_kick(
    moderateur: discord.Member,
    cible: discord.Member,
    raison: str,
) -> discord.Embed:
    embed = discord.Embed(
        title="👢 KICK — Membre expulsé",
        color=0xE67E22,
        timestamp=now_utc(),
    )
    embed.set_thumbnail(url=cible.display_avatar.url)
    embed.add_field(name="🎯 Cible",       value=f"{cible.mention}\n`{cible}` — ID `{cible.id}`",          inline=True)
    embed.add_field(name="🛡️ Modérateur", value=f"{moderateur.mention}\n`{moderateur}` — ID `{moderateur.id}`", inline=True)
    embed.add_field(name="\u200b",         value="\u200b", inline=True)
    embed.add_field(name="📝 Raison",      value=raison,  inline=False)
    embed.add_field(name="📅 Arrivé le",   value=discord.utils.format_dt(cible.joined_at, style="D") if cible.joined_at else "?", inline=True)
    roles = [r.mention for r in reversed(cible.roles) if r.name != "@everyone"]
    embed.add_field(name=f"🎭 Rôles ({len(roles)})", value=", ".join(roles[:10]) or "Aucun", inline=False)
    embed.set_footer(text=f"ID action : KICK-{cible.id}")
    return embed


def log_mute(
    moderateur: discord.Member,
    cible: discord.Member,
    raison: str,
    duree_str: str,
    expires_at: float | None,
) -> discord.Embed:
    import time
    embed = discord.Embed(
        title="🔇 MUTE — Membre réduit au silence",
        color=0xF39C12,
        timestamp=now_utc(),
    )
    embed.set_thumbnail(url=cible.display_avatar.url)
    embed.add_field(name="🎯 Cible",       value=f"{cible.mention}\n`{cible}` — ID `{cible.id}`",          inline=True)
    embed.add_field(name="🛡️ Modérateur", value=f"{moderateur.mention}\n`{moderateur}` — ID `{moderateur.id}`", inline=True)
    embed.add_field(name="\u200b",         value="\u200b", inline=True)
    embed.add_field(name="⏱️ Durée",       value=duree_str, inline=True)
    if expires_at:
        embed.add_field(
            name="⌛ Expiration",
            value=discord.utils.format_dt(discord.utils.snowflake_time(int(expires_at * 1000 - 1420070400000)), style="F")
            if False else f"<t:{int(expires_at)}:F>",
            inline=True,
        )
    else:
        embed.add_field(name="⌛ Expiration", value="Permanent (jusqu'à !unmute)", inline=True)
    embed.add_field(name="📝 Raison", value=raison, inline=False)
    embed.set_footer(text=f"ID action : MUTE-{cible.id}")
    return embed


def log_unmute(
    moderateur: discord.Member,
    cible: discord.Member,
    automatique: bool = False,
) -> discord.Embed:
    embed = discord.Embed(
        title="🔊 UNMUTE — Membre réactivé" + (" (automatique)" if automatique else ""),
        color=0x2ECC71,
        timestamp=now_utc(),
    )
    embed.set_thumbnail(url=cible.display_avatar.url)
    embed.add_field(name="🎯 Cible",      value=f"{cible.mention}\n`{cible}` — ID `{cible.id}`", inline=True)
    if automatique:
        embed.add_field(name="🤖 Source", value="Expiration automatique du mute", inline=True)
    else:
        embed.add_field(name="🛡️ Modérateur", value=f"{moderateur.mention}\n`{moderateur}` — ID `{moderateur.id}`", inline=True)
    embed.set_footer(text=f"ID action : UNMUTE-{cible.id}")
    return embed


def log_warn(
    moderateur: discord.Member,
    cible: discord.Member,
    raison: str,
    nb_avertissements: int,
) -> discord.Embed:
    embed = discord.Embed(
        title="⚠️ AVERTISSEMENT — Membre averti",
        color=0xF1C40F,
        timestamp=now_utc(),
    )
    embed.set_thumbnail(url=cible.display_avatar.url)
    embed.add_field(name="🎯 Cible",              value=f"{cible.mention}\n`{cible}` — ID `{cible.id}`",          inline=True)
    embed.add_field(name="🛡️ Modérateur",         value=f"{moderateur.mention}\n`{moderateur}` — ID `{moderateur.id}`", inline=True)
    embed.add_field(name="🔢 Total avertissements", value=str(nb_avertissements), inline=True)
    embed.add_field(name="📝 Raison",              value=raison, inline=False)
    embed.set_footer(text=f"ID action : WARN-{cible.id}")
    return embed


def log_purge(
    moderateur: discord.Member,
    salon: discord.TextChannel,
    nb_supprimes: int,
) -> discord.Embed:
    embed = discord.Embed(
        title="🗑️ PURGE — Messages supprimés",
        color=0x95A5A6,
        timestamp=now_utc(),
    )
    embed.add_field(name="🛡️ Modérateur",      value=f"{moderateur.mention}\n`{moderateur}` — ID `{moderateur.id}`", inline=True)
    embed.add_field(name="📍 Salon",            value=f"{salon.mention}\n`#{salon.name}`", inline=True)
    embed.add_field(name="🗑️ Messages supprimés", value=str(nb_supprimes), inline=True)
    embed.set_footer(text=f"ID action : PURGE-{salon.id}")
    return embed


# ═══════════════════════════════════════════════════════════════
#  ANTI-SPAM automatique
# ═══════════════════════════════════════════════════════════════

def log_antispam_warn(
    cible: discord.Member,
    nb_messages: int,
    fenetre_secs: float,
    avertissement_num: int,
) -> discord.Embed:
    embed = discord.Embed(
        title="⚠️ ANTI-SPAM — Avertissement automatique",
        color=0xF39C12,
        timestamp=now_utc(),
    )
    embed.set_thumbnail(url=cible.display_avatar.url)
    embed.add_field(name="🎯 Membre",              value=f"{cible.mention}\n`{cible}` — ID `{cible.id}`", inline=True)
    embed.add_field(name="🤖 Source",              value="Système anti-spam automatique", inline=True)
    embed.add_field(name="📊 Déclencheur",         value=f"{nb_messages} messages en {fenetre_secs}s", inline=True)
    embed.add_field(name="🔢 Avertissement n°",    value=str(avertissement_num), inline=True)
    embed.set_footer(text=f"ID : SPAM-WARN-{cible.id}")
    return embed


def log_antispam_kick(
    cible: discord.Member,
    nb_messages: int,
    fenetre_secs: float,
) -> discord.Embed:
    embed = discord.Embed(
        title="🚫 ANTI-SPAM — Kick automatique",
        color=0xC0392B,
        timestamp=now_utc(),
    )
    embed.set_thumbnail(url=cible.display_avatar.url)
    embed.add_field(name="🎯 Membre",           value=f"{cible.mention}\n`{cible}` — ID `{cible.id}`", inline=True)
    embed.add_field(name="🤖 Source",           value="Système anti-spam automatique", inline=True)
    embed.add_field(name="📊 Déclencheur",      value=f"{nb_messages} messages en {fenetre_secs}s", inline=True)
    embed.add_field(name="📝 Raison",           value="Spam répété après avertissement", inline=False)
    embed.set_footer(text=f"ID : SPAM-KICK-{cible.id}")
    return embed


def log_antispam_mute(
    cible: discord.Member,
    nb_messages: int,
    fenetre_secs: float,
    duree_str: str,
) -> discord.Embed:
    embed = discord.Embed(
        title="🔇 ANTI-SPAM — Mute automatique",
        color=0xE67E22,
        timestamp=now_utc(),
    )
    embed.set_thumbnail(url=cible.display_avatar.url)
    embed.add_field(name="🎯 Membre",      value=f"{cible.mention}\n`{cible}` — ID `{cible.id}`", inline=True)
    embed.add_field(name="🤖 Source",      value="Système anti-spam automatique", inline=True)
    embed.add_field(name="⏱️ Durée mute",  value=duree_str, inline=True)
    embed.add_field(name="📊 Déclencheur", value=f"{nb_messages} messages en {fenetre_secs}s", inline=True)
    embed.set_footer(text=f"ID : SPAM-MUTE-{cible.id}")
    return embed


def log_lien_bloque(
    membre: discord.Member,
    salon: discord.TextChannel,
    contenu: str,
    domaine: str,
) -> discord.Embed:
    embed = discord.Embed(
        title="🔗 LIEN BLOQUÉ — Message supprimé",
        color=0xE74C3C,
        timestamp=now_utc(),
    )
    embed.set_thumbnail(url=membre.display_avatar.url)
    embed.add_field(name="👤 Auteur",     value=f"{membre.mention}\n`{membre}` — ID `{membre.id}`", inline=True)
    embed.add_field(name="📍 Salon",      value=f"{salon.mention}\n`#{salon.name}`", inline=True)
    embed.add_field(name="🌐 Domaine",    value=f"`{domaine}`", inline=True)
    embed.add_field(name="💬 Contenu",    value=f"```{contenu[:900]}```", inline=False)
    embed.set_footer(text=f"ID : LINK-{membre.id}")
    return embed


# ═══════════════════════════════════════════════════════════════
#  MEMBRES — Arrivées / Départs
# ═══════════════════════════════════════════════════════════════

def log_member_join(
    member: discord.Member,
    inviteur: discord.Member | None = None,
    code_invite: str | None = None,
) -> discord.Embed:
    from datetime import datetime, timezone
    age_days = (datetime.now(timezone.utc) - member.created_at).days
    embed = discord.Embed(
        title="📥 ARRIVÉE — Nouveau membre",
        color=0x2ECC71,
        timestamp=now_utc(),
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="👤 Membre",       value=f"{member.mention}\n`{member}` — ID `{member.id}`", inline=True)
    embed.add_field(name="📅 Compte créé",  value=discord.utils.format_dt(member.created_at, style="D"), inline=True)
    embed.add_field(name="⏱️ Âge du compte", value=f"{age_days} jour(s)", inline=True)
    embed.add_field(name="👥 Membres total", value=str(member.guild.member_count), inline=True)
    if inviteur:
        embed.add_field(name="📨 Invité par", value=f"{inviteur.mention}\n`{inviteur}` — ID `{inviteur.id}`", inline=True)
    if code_invite:
        embed.add_field(name="🔗 Code invite", value=f"`{code_invite}`", inline=True)
    embed.set_footer(text=f"ID : JOIN-{member.id}")
    return embed


def log_member_leave(
    member: discord.Member,
    raison: str = "Départ volontaire",
    moderateur: discord.Member | None = None,
) -> discord.Embed:
    from datetime import datetime, timezone
    duree_serveur = ""
    if member.joined_at:
        delta = datetime.now(timezone.utc) - member.joined_at
        jours = delta.days
        duree_serveur = f"{jours} jour(s)"
    embed = discord.Embed(
        title="📤 DÉPART — Membre parti",
        color=0xE74C3C,
        timestamp=now_utc(),
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="👤 Membre",          value=f"{member.mention}\n`{member}` — ID `{member.id}`", inline=True)
    embed.add_field(name="📅 Arrivé le",        value=discord.utils.format_dt(member.joined_at, style="D") if member.joined_at else "?", inline=True)
    embed.add_field(name="⏳ Durée sur le serveur", value=duree_serveur or "?", inline=True)
    embed.add_field(name="👥 Membres total",    value=str(member.guild.member_count), inline=True)
    roles = [r.mention for r in reversed(member.roles) if r.name != "@everyone"]
    if roles:
        embed.add_field(name=f"🎭 Rôles qu'il avait ({len(roles)})", value=", ".join(roles[:15]), inline=False)
    if moderateur:
        embed.add_field(name="🛡️ Action par", value=f"{moderateur.mention} — `{raison}`", inline=False)
    embed.set_footer(text=f"ID : LEAVE-{member.id}")
    return embed


# ═══════════════════════════════════════════════════════════════
#  RÔLES & PSEUDO
# ═══════════════════════════════════════════════════════════════

def log_roles_modifies(
    membre: discord.Member,
    ajoutes: set,
    retires: set,
    moderateur: discord.Member | None = None,
) -> discord.Embed:
    embed = discord.Embed(
        title="🎭 RÔLES — Modification détectée",
        color=0x9B59B6,
        timestamp=now_utc(),
    )
    embed.set_thumbnail(url=membre.display_avatar.url)
    embed.add_field(name="👤 Membre", value=f"{membre.mention}\n`{membre}` — ID `{membre.id}`", inline=True)
    if moderateur:
        embed.add_field(name="🛡️ Modifié par", value=f"{moderateur.mention}", inline=True)
    if ajoutes:
        embed.add_field(name="✅ Rôles ajoutés",  value=", ".join(r.mention for r in ajoutes),  inline=False)
    if retires:
        embed.add_field(name="❌ Rôles retirés", value=", ".join(r.mention for r in retires), inline=False)
    embed.set_footer(text=f"ID : ROLES-{membre.id}")
    return embed


def log_pseudo_modifie(
    membre: discord.Member,
    avant: str,
    apres: str,
) -> discord.Embed:
    embed = discord.Embed(
        title="📝 PSEUDO — Changement de pseudo",
        color=0x3498DB,
        timestamp=now_utc(),
    )
    embed.set_thumbnail(url=membre.display_avatar.url)
    embed.add_field(name="👤 Membre", value=f"{membre.mention}\n`{membre}` — ID `{membre.id}`", inline=False)
    embed.add_field(name="📝 Avant",  value=f"`{avant}`", inline=True)
    embed.add_field(name="📝 Après",  value=f"`{apres}`", inline=True)
    embed.set_footer(text=f"ID : NICK-{membre.id}")
    return embed


# ═══════════════════════════════════════════════════════════════
#  MESSAGES SUPPRIMÉS / MODIFIÉS
# ═══════════════════════════════════════════════════════════════

def log_message_supprime(
    message: discord.Message,
    suppresseur: discord.Member | None = None,
) -> discord.Embed:
    embed = discord.Embed(
        title="🗑️ MESSAGE SUPPRIMÉ",
        color=0x7F8C8D,
        timestamp=now_utc(),
    )
    embed.set_thumbnail(url=message.author.display_avatar.url)
    embed.add_field(name="✍️ Auteur",  value=f"{message.author.mention}\n`{message.author}` — ID `{message.author.id}`", inline=True)
    embed.add_field(name="📍 Salon",   value=f"{message.channel.mention}\n`#{message.channel.name}`", inline=True)
    if suppresseur and suppresseur.id != message.author.id:
        embed.add_field(name="🛡️ Supprimé par", value=f"{suppresseur.mention}", inline=True)
    contenu = message.content or "_[aucun texte — pièce jointe ou embed]_"
    embed.add_field(name="💬 Contenu", value=f"```{contenu[:900]}```", inline=False)
    if message.attachments:
        embed.add_field(name="📎 Pièces jointes", value="\n".join(a.url for a in message.attachments), inline=False)
    embed.set_footer(text=f"Message ID : {message.id}")
    return embed


def log_message_modifie(
    avant: str,
    apres: str,
    message: discord.Message,
) -> discord.Embed:
    embed = discord.Embed(
        title="✏️ MESSAGE MODIFIÉ",
        color=0x2980B9,
        timestamp=now_utc(),
    )
    embed.set_thumbnail(url=message.author.display_avatar.url)
    embed.add_field(name="✍️ Auteur", value=f"{message.author.mention}\n`{message.author}` — ID `{message.author.id}`", inline=True)
    embed.add_field(name="📍 Salon",  value=f"{message.channel.mention}\n`#{message.channel.name}`", inline=True)
    embed.add_field(name="🔗 Lien",   value=f"[Aller au message]({message.jump_url})", inline=True)
    embed.add_field(name="📝 Avant",  value=f"```{avant[:400]}```",  inline=False)
    embed.add_field(name="📝 Après",  value=f"```{apres[:400]}```",  inline=False)
    embed.set_footer(text=f"Message ID : {message.id}")
    return embed