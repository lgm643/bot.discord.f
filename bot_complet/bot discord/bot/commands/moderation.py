"""
commands/moderation.py — Commandes de modération.

CORRECTIONS v2 — Logs ultra-précis :
  - Chaque action appelle un helper dédié depuis utils/logs.py
  - Ban : cible + modérateur (mention + ID) + raison + nb jours suppression + compte créé + rôles
  - Kick : cible + modérateur + raison + date d'arrivée + rôles qu'il avait
  - Mute : cible + modérateur + durée + expiration exacte + raison
  - Unmute : cible + modérateur (ou "automatique") 
  - Purge : modérateur + salon + nombre exact supprimé
  - Warn : cible + modérateur + raison + compteur d'avertissements
"""
import asyncio
import time
import re

import discord

from bot.core import bot
from bot.utils.permissions import is_staff
from bot.utils.config import cfg_channel
from bot.utils.embeds import build_roster_embed
from bot.utils.logs import (
    send_log,
    log_ban, log_kick, log_mute, log_unmute,
    log_purge, log_warn,
)
from bot.utils.helpers import now_utc
from bot.views.ticket_view import TicketView, FermerView
from bot.utils.database import db_save_mute, db_delete_mute


# ═══════════════════════════════════════════════════════════════
#  TICKETS / ROSTER
# ═══════════════════════════════════════════════════════════════

@bot.command(name="ticket", aliases=["tickets", "support"])
async def ticket(ctx):
    if not is_staff(ctx.author):
        await ctx.send("❌ Permission refusée.", delete_after=5)
        return
    embed = discord.Embed(
        title="🎫 Ouvrir un ticket",
        description="Choisis le type de demande :",
        color=0x9B59B6,
    )
    await ctx.send(embed=embed, view=TicketView())


@bot.command(name="fermer", aliases=["close", "closeticket", "fermeticket"])
async def fermer(ctx):
    if "ticket-" not in ctx.channel.name:
        await ctx.send("❌ Uniquement dans un ticket.", delete_after=5)
        return
    view  = FermerView(closer=ctx.author)
    embed = discord.Embed(
        title="🔒 Fermer le ticket",
        description="Es-tu sûr ?\n\n⏳ Expiration dans **30s**…",
        color=0xFF0000,
    )
    embed.set_footer(text="Aucune action = ticket conservé")
    msg = await ctx.send(embed=embed, view=view)
    asyncio.create_task(view.update_countdown(msg))
    await view.wait()


@bot.command(name="roster", aliases=["membres", "liste", "faction"])
async def roster(ctx):
    if not is_staff(ctx.author):
        await ctx.send("❌ Permission refusée.", delete_after=5)
        return
    channel = cfg_channel(ctx.guild, "salon_roster")
    if not channel:
        await ctx.send("❌ Salon roster introuvable.", delete_after=5)
        return
    embed = build_roster_embed(ctx.guild)
    existing = None
    async for msg in channel.history(limit=20):
        if msg.author == bot.user and msg.embeds:
            existing = msg
            break
    if existing:
        await existing.edit(embed=embed)
        await ctx.send("✅ Roster mis à jour !", delete_after=5)
    else:
        await channel.send(embed=embed)
        await ctx.send(f"✅ Roster posté dans {channel.mention} !", delete_after=5)


# ═══════════════════════════════════════════════════════════════
#  MODÉRATION
# ═══════════════════════════════════════════════════════════════

@bot.command(name="ban", aliases=["bannir", "expulser_def"])
async def ban(ctx, member: discord.Member = None, *, reason: str = "Aucune raison fournie"):
    if not is_staff(ctx.author):
        await ctx.send("❌ Permission refusée.", delete_after=5)
        return
    if member is None:
        await ctx.send("❌ `!ban @membre raison`", delete_after=5)
        return
    if member == ctx.author:
        await ctx.send("❌ Tu ne peux pas te bannir toi-même.", delete_after=5)
        return
    try:
        await member.ban(reason=f"[{ctx.author}] {reason}", delete_message_days=1)
        await ctx.send(
            f"🔨 **{member}** banni par {ctx.author.mention}.\n📝 Raison : {reason}"
        )
        await send_log(ctx.guild, log_ban(ctx.author, member, reason, nb_jours_suppression=1))
    except discord.Forbidden:
        await ctx.send("❌ Je ne peux pas bannir ce membre (rôle supérieur au mien).", delete_after=5)
    except Exception as e:
        await ctx.send(f"❌ Erreur inattendue : {e}", delete_after=8)


@bot.command(name="kick", aliases=["expulser", "virer"])
async def kick(ctx, member: discord.Member = None, *, reason: str = "Aucune raison fournie"):
    if not is_staff(ctx.author):
        await ctx.send("❌ Permission refusée.", delete_after=5)
        return
    if member is None:
        await ctx.send("❌ `!kick @membre raison`", delete_after=5)
        return
    if member == ctx.author:
        await ctx.send("❌ Tu ne peux pas te kick toi-même.", delete_after=5)
        return
    try:
        await member.kick(reason=f"[{ctx.author}] {reason}")
        await ctx.send(
            f"👢 **{member}** expulsé par {ctx.author.mention}.\n📝 Raison : {reason}"
        )
        await send_log(ctx.guild, log_kick(ctx.author, member, reason))
    except discord.Forbidden:
        await ctx.send("❌ Je ne peux pas kick ce membre (rôle supérieur au mien).", delete_after=5)
    except Exception as e:
        await ctx.send(f"❌ Erreur inattendue : {e}", delete_after=8)


def _parse_mute_duration(s: str) -> int | None:
    total = 0
    for val, unit in re.findall(r"(\d+)([smhj])", s.lower()):
        v = int(val)
        if unit == "s": total += v
        elif unit == "m": total += v * 60
        elif unit == "h": total += v * 3600
        elif unit == "j": total += v * 86400
    return total if total > 0 else None


@bot.command(name="mute", aliases=["silence", "rendre_muet"])
async def mute(ctx, member: discord.Member = None, duree: str = None, *, reason: str = "Aucune raison fournie"):
    """
    !mute @membre [durée] [raison]
    Durées : 10s, 5m, 2h, 1j (ou combinés : 1h30m)
    Sans durée = mute permanent jusqu'à !unmute
    """
    if not is_staff(ctx.author):
        await ctx.send("❌ Permission refusée.", delete_after=5)
        return
    if member is None:
        await ctx.send("❌ `!mute @membre [durée] [raison]`\n*(ex: `!mute @Nono 10m spam`)*", delete_after=8)
        return
    if member == ctx.author:
        await ctx.send("❌ Tu ne peux pas te muter toi-même.", delete_after=5)
        return

    seconds = None
    if duree:
        seconds = _parse_mute_duration(duree)
        if seconds is None:
            reason = f"{duree} {reason}".strip()

    # Création du rôle Muted si absent
    mute_role = discord.utils.get(ctx.guild.roles, name="Muted")
    if not mute_role:
        try:
            mute_role = await ctx.guild.create_role(name="Muted", reason="Création auto par le bot")
            await asyncio.gather(*[
                ch.set_permissions(mute_role, send_messages=False, speak=False)
                for ch in ctx.guild.channels
            ], return_exceptions=True)
        except discord.Forbidden:
            await ctx.send("❌ Je n'ai pas la permission de créer le rôle Muted.", delete_after=8)
            return

    try:
        await member.add_roles(mute_role, reason=f"[{ctx.author}] {reason}")
    except discord.Forbidden:
        await ctx.send("❌ Je ne peux pas muter ce membre.", delete_after=5)
        return

    expires_at = (time.time() + seconds) if seconds else None
    db_save_mute(ctx.guild.id, member.id, expires_at, reason)

    duree_str = f"**{duree}**" if seconds else "**permanent**"
    await ctx.send(
        f"🔇 **{member.display_name}** muté par {ctx.author.mention} — "
        f"Durée : {duree_str} — Raison : {reason}"
    )
    await send_log(ctx.guild, log_mute(ctx.author, member, reason, duree_str, expires_at))

    if seconds:
        asyncio.create_task(_schedule_unmute(ctx.guild, member, mute_role, seconds, duree_str))


async def _schedule_unmute(
    guild: discord.Guild,
    member: discord.Member,
    mute_role: discord.Role,
    seconds: float,
    duree_str: str,
):
    """Attend `seconds` puis retire le rôle Muted et envoie un log précis."""
    await asyncio.sleep(seconds)
    try:
        m = guild.get_member(member.id)
        if m and mute_role in m.roles:
            await m.remove_roles(mute_role, reason="Mute expiré automatiquement")
            db_delete_mute(guild.id, member.id)
            # Log unmute automatique — on passe le membre lui-même comme "moderateur"
            # car automatique=True affichera "Expiration automatique" à la place
            await send_log(guild, log_unmute(m, m, automatique=True))
    except Exception as e:
        print(f"[MUTE] Auto-unmute échoué pour {member.id} : {e}")


@bot.command(name="unmute", aliases=["desilence", "parler"])
async def unmute(ctx, member: discord.Member = None):
    if not is_staff(ctx.author):
        await ctx.send("❌ Permission refusée.", delete_after=5)
        return
    if member is None:
        await ctx.send("❌ `!unmute @membre`", delete_after=5)
        return
    mute_role = discord.utils.get(ctx.guild.roles, name="Muted")
    if not mute_role or mute_role not in member.roles:
        await ctx.send("✅ Ce membre n'est pas muté.", delete_after=5)
        return
    await member.remove_roles(mute_role, reason=f"Unmute manuel par {ctx.author}")
    db_delete_mute(ctx.guild.id, member.id)
    await ctx.send(f"🔊 **{member}** unmuté par {ctx.author.mention}.")
    await send_log(ctx.guild, log_unmute(ctx.author, member, automatique=False))


@bot.command(name="effacer", aliases=["clear", "purge", "supprimer", "clean"])
async def effacer(ctx, nombre: int = None):
    if not is_staff(ctx.author):
        await ctx.send("❌ Permission refusée.", delete_after=5)
        return
    if nombre is None:
        await ctx.send("❌ `!effacer 10`", delete_after=5)
        return
    if nombre < 1 or nombre > 100:
        await ctx.send("❌ Entre 1 et 100.", delete_after=5)
        return
    deleted = await ctx.channel.purge(limit=nombre + 1)
    nb = len(deleted) - 1
    await ctx.send(f"🗑️ **{nb}** message(s) supprimé(s) par {ctx.author.mention}.", delete_after=5)
    await send_log(ctx.guild, log_purge(ctx.author, ctx.channel, nb))


@bot.command(name="warn", aliases=["avertir", "avertissement"])
async def warn(ctx, member: discord.Member = None, *, reason: str = "Aucune raison fournie"):
    """!warn @membre raison — Enregistre un avertissement et le log."""
    if not is_staff(ctx.author):
        await ctx.send("❌ Permission refusée.", delete_after=5)
        return
    if member is None:
        await ctx.send("❌ `!warn @membre raison`", delete_after=5)
        return

    # Compteur d'avertissements (stocké en mémoire simple — peut être migré en DB)
    if not hasattr(bot, "_warn_counts"):
        bot._warn_counts = {}
    key = (ctx.guild.id, member.id)
    bot._warn_counts[key] = bot._warn_counts.get(key, 0) + 1
    nb = bot._warn_counts[key]

    await ctx.send(
        f"⚠️ **{member.display_name}** averti par {ctx.author.mention} "
        f"(avertissement n°{nb}) — Raison : {reason}"
    )
    await member.send(
        f"⚠️ Tu as reçu un avertissement sur **{ctx.guild.name}**.\n"
        f"📝 Raison : {reason}\n"
        f"🔢 Total : {nb} avertissement(s)"
    ).anot if False else None   # silencieux si DM fermés

    try:
        await member.send(
            f"⚠️ Tu as reçu un avertissement sur **{ctx.guild.name}**.\n"
            f"📝 Raison : {reason}\n"
            f"🔢 Total avertissements : {nb}"
        )
    except discord.Forbidden:
        pass  # DMs fermés — pas bloquant

    await send_log(ctx.guild, log_warn(ctx.author, member, reason, nb))


# ═══════════════════════════════════════════════════════════════
#  INFO MEMBRE
# ═══════════════════════════════════════════════════════════════

@bot.command(name="info", aliases=["profil", "whois", "user", "membre"])
async def info(ctx, member: discord.Member = None):
    member   = member or ctx.author
    roles    = [r.mention for r in reversed(member.roles) if r.name != "@everyone"]
    top_role = member.top_role.mention if member.top_role.name != "@everyone" else "Aucun"
    perms = []
    if member.guild_permissions.administrator:   perms.append("👑 Administrateur")
    if member.guild_permissions.manage_guild:    perms.append("⚙️ Gérer le serveur")
    if member.guild_permissions.ban_members:     perms.append("🔨 Bannir")
    if member.guild_permissions.kick_members:    perms.append("👢 Expulser")
    if member.guild_permissions.manage_messages: perms.append("🗑️ Gérer messages")
    if member.guild_permissions.manage_roles:    perms.append("🎭 Gérer rôles")
    status_map = {
        discord.Status.online:  "🟢 En ligne",
        discord.Status.idle:    "🟡 Absent",
        discord.Status.dnd:     "🔴 Ne pas déranger",
        discord.Status.offline: "⚫ Hors ligne",
    }
    status   = status_map.get(member.status, "⚫ Inconnu")
    activity = "Aucune"
    if member.activity:
        if isinstance(member.activity, discord.Game):             activity = f"🎮 {member.activity.name}"
        elif isinstance(member.activity, discord.Streaming):      activity = f"📺 {member.activity.name}"
        elif isinstance(member.activity, discord.CustomActivity): activity = f"💬 {member.activity.name}"
        else:                                                      activity = member.activity.name

    embed = discord.Embed(
        title=f"👤 {member.display_name}",
        color=member.color if member.color != discord.Color.default() else 0x3498DB,
        timestamp=now_utc(),
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    if member.banner:
        embed.set_image(url=member.banner.url)
    embed.add_field(name="📛 Pseudo",         value=member.display_name,  inline=True)
    embed.add_field(name="🏷️ Tag",            value=str(member),          inline=True)
    embed.add_field(name="🤖 Bot",             value="✅" if member.bot else "❌", inline=True)
    embed.add_field(name="🆔 ID",              value=str(member.id),       inline=True)
    embed.add_field(name="📅 Compte créé",     value=discord.utils.format_dt(member.created_at, style="D"), inline=True)
    embed.add_field(name="📥 Arrivée serveur", value=discord.utils.format_dt(member.joined_at, style="D") if member.joined_at else "?", inline=True)
    embed.add_field(name="📶 Statut",          value=status,   inline=True)
    embed.add_field(name="🎯 Activité",        value=activity, inline=True)
    embed.add_field(name="🎖️ Rôle principal",  value=top_role, inline=True)
    embed.add_field(name=f"🎭 Rôles ({len(roles)})", value=", ".join(roles[:20]) or "Aucun", inline=False)
    embed.add_field(name="🔑 Permissions",     value=", ".join(perms) or "Aucune", inline=False)
    embed.set_footer(text=f"Demandé par {ctx.author}")
    await ctx.send(embed=embed)


@bot.command(name="say", aliases=["dit"])
async def say_cmd(ctx, channel: discord.TextChannel = None, *, message: str = None):
    if not is_staff(ctx.author):
        await ctx.send("❌ Réservé au staff.", delete_after=5)
        return
    if channel is None or message is None:
        await ctx.send("❌ Utilisation : `!say #salon message`", delete_after=8)
        return
    try:
        await ctx.message.delete()
    except Exception:
        pass
    try:
        await channel.send(message)
    except discord.Forbidden:
        await ctx.send(f"❌ Permission refusée pour {channel.mention}.", delete_after=6)