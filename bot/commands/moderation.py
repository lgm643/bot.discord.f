from bot.utils.permissions import is_staff
from bot.utils.config import cfg_channel
from bot.utils.embeds import build_roster_embed
from bot.utils.logs import send_log
from bot.utils.helpers import now_utc
from bot.views.ticket_view import TicketView, FermerView
from bot.utils.database import db_save_mute, db_delete_mute

import asyncio
import time
import re
from datetime import datetime, timezone

import discord
from discord.ext import commands

from bot.core import bot

@bot.hybrid_command(name="ticket", aliases=["tickets", "support"])
async def ticket(ctx):
    if not is_staff(ctx.author):
        await ctx.send("❌ Permission refusée.", delete_after=5); return
    embed = discord.Embed(title="🎫 Ouvrir un ticket", description="Choisis le type de demande :", color=0x9B59B6)
    await ctx.send(embed=embed, view=TicketView())


@bot.hybrid_command(name="fermer", aliases=["close", "closeticket", "fermeticket"])
async def fermer(ctx):
    if "ticket-" not in ctx.channel.name:
        await ctx.send("❌ Uniquement dans un ticket.", delete_after=5); return
    view  = FermerView(closer=ctx.author)
    embed = discord.Embed(title="🔒 Fermer le ticket", description="Es-tu sûr ?\n\n⏳ Expiration dans **30s**…", color=0xFF0000)
    embed.set_footer(text="Aucune action = ticket conservé")
    msg = await ctx.send(embed=embed, view=view)
    asyncio.create_task(view.update_countdown(msg))
    await view.wait()


@bot.hybrid_command(name="roster", aliases=["membres", "liste", "faction"])
async def roster(ctx):
    if not is_staff(ctx.author):
        await ctx.send("❌ Permission refusée.", delete_after=5); return
    channel = cfg_channel(ctx.guild, "salon_roster")
    if not channel:
        await ctx.send("❌ Salon roster introuvable.", delete_after=5); return
    embed = build_roster_embed(ctx.guild)
    existing = None
    async for msg in channel.history(limit=20):
        if msg.author == bot.user and msg.embeds:
            existing = msg; break
    if existing:
        await existing.edit(embed=embed)
        await ctx.send("✅ Roster mis à jour !", delete_after=5)
    else:
        await channel.send(embed=embed)
        await ctx.send(f"✅ Roster posté dans {channel.mention} !", delete_after=5)

# ═══════════════════════════════════════════════════════════════
#  MODÉRATION
# ═══════════════════════════════════════════════════════════════

@bot.hybrid_command(name="ban", aliases=["bannir", "expulser_def"])
async def ban(ctx, member: discord.Member = None, *, reason: str = "Aucune raison fournie"):
    if not is_staff(ctx.author): await ctx.send("❌ Permission refusée.", delete_after=5); return
    if member is None: await ctx.send("❌ `!ban @membre raison`", delete_after=5); return
    try:
        await member.ban(reason=reason, delete_message_days=1)
        await ctx.send(f"🔨 **{member}** banni. Raison : {reason}")
        embed = discord.Embed(title="🔨 Ban", color=0xE74C3C, timestamp=now_utc())
        embed.add_field(name="👤 Membre", value=f"{member} ({member.id})", inline=True)
        embed.add_field(name="🛡️ Modérateur", value=ctx.author.mention, inline=True)
        embed.add_field(name="📝 Raison", value=reason, inline=False)
        await send_log(ctx.guild, embed)
    except discord.Forbidden: await ctx.send("❌ Je ne peux pas bannir ce membre.", delete_after=5)


@bot.hybrid_command(name="kick", aliases=["expulser", "virer"])
async def kick(ctx, member: discord.Member = None, *, reason: str = "Aucune raison fournie"):
    if not is_staff(ctx.author): await ctx.send("❌ Permission refusée.", delete_after=5); return
    if member is None: await ctx.send("❌ `!kick @membre raison`", delete_after=5); return
    try:
        await member.kick(reason=reason)
        await ctx.send(f"👢 **{member}** expulsé. Raison : {reason}")
        embed = discord.Embed(title="👢 Kick", color=0xE67E22, timestamp=now_utc())
        embed.add_field(name="👤 Membre", value=f"{member} ({member.id})", inline=True)
        embed.add_field(name="🛡️ Modérateur", value=ctx.author.mention, inline=True)
        embed.add_field(name="📝 Raison", value=reason, inline=False)
        await send_log(ctx.guild, embed)
    except discord.Forbidden: await ctx.send("❌ Je ne peux pas kick ce membre.", delete_after=5)


def _parse_mute_duration(s: str) -> int | None:
    """Parse une durée type '10m', '2h', '1j30m' en secondes. Retourne None si invalide."""
    import re
    total = 0
    for val, unit in re.findall(r"(\d+)([smhj])", s.lower()):
        v = int(val)
        if unit == "s": total += v
        elif unit == "m": total += v * 60
        elif unit == "h": total += v * 3600
        elif unit == "j": total += v * 86400
    return total if total > 0 else None


@bot.hybrid_command(name="mute", aliases=["silence", "rendre_muet"])
async def mute(ctx, member: discord.Member = None, duree: str = None, *, reason: str = "Aucune raison fournie"):
    """
    !mute @membre [durée] [raison]
    Durées : 10s, 5m, 2h, 1j (ou combinés : 1h30m)
    Sans durée = mute permanent jusqu'à !unmute
    """
    if not is_staff(ctx.author): await ctx.send("❌ Permission refusée.", delete_after=5); return
    if member is None:
        await ctx.send("❌ `!mute @membre [durée] [raison]`\n*(ex: `!mute @Nono 10m spam`)*", delete_after=8)
        return

    # Si 'duree' ne ressemble pas à une durée, c'est le début de la raison
    seconds = None
    if duree:
        seconds = _parse_mute_duration(duree)
        if seconds is None:
            # Pas une durée valide → c'est la raison
            reason = f"{duree} {reason}".strip()

    mute_role = discord.utils.get(ctx.guild.roles, name="Muted")
    if not mute_role:
        mute_role = await ctx.guild.create_role(name="Muted", reason="Création auto")
        await asyncio.gather(*[
            ch.set_permissions(mute_role, send_messages=False, speak=False)
            for ch in ctx.guild.channels
        ], return_exceptions=True)

    await member.add_roles(mute_role, reason=reason)

    expires_at = (time.time() + seconds) if seconds else None
    db_save_mute(ctx.guild.id, member.id, expires_at, reason)

    duree_str = f"**{duree}**" if seconds else "**permanent**"
    await ctx.send(f"🔇 **{member.display_name}** muté — Durée : {duree_str} — Raison : {reason}")

    embed = discord.Embed(title="🔇 Mute", color=0xE67E22, timestamp=now_utc())
    embed.add_field(name="👤 Membre",      value=f"{member} ({member.id})", inline=True)
    embed.add_field(name="🛡️ Modérateur", value=ctx.author.mention,        inline=True)
    embed.add_field(name="⏱️ Durée",      value=duree_str,                  inline=True)
    embed.add_field(name="📝 Raison",     value=reason,                     inline=False)
    await send_log(ctx.guild, embed)

    # Auto-unmute si durée précisée
    if seconds:
        asyncio.create_task(_schedule_unmute(ctx.guild, member, mute_role, seconds, duree_str))


async def _schedule_unmute(guild: discord.Guild, member: discord.Member, mute_role: discord.Role, seconds: float, duree_str: str):
    """Attend `seconds` puis retire le rôle Muted et nettoie la DB."""
    await asyncio.sleep(seconds)
    try:
        m = guild.get_member(member.id)
        if m and mute_role in m.roles:
            await m.remove_roles(mute_role, reason="Mute expiré automatiquement")
            db_delete_mute(guild.id, member.id)
            log_embed = discord.Embed(
                title="🔊 Unmute automatique",
                description=f"{member.mention} a été unmuté automatiquement après {duree_str}.",
                color=0x2ECC71,
                timestamp=now_utc()
            )
            await send_log(guild, log_embed)
    except Exception as e:
        print(f"[MUTE] Auto-unmute échoué pour {member.id} : {e}")


@bot.hybrid_command(name="unmute", aliases=["desilence", "parler"])
async def unmute(ctx, member: discord.Member = None):
    if not is_staff(ctx.author): await ctx.send("❌ Permission refusée.", delete_after=5); return
    if member is None: await ctx.send("❌ `!unmute @membre`", delete_after=5); return
    mute_role = discord.utils.get(ctx.guild.roles, name="Muted")
    if not mute_role or mute_role not in member.roles:
        await ctx.send("✅ Ce membre n'est pas muté.", delete_after=5); return
    await member.remove_roles(mute_role)
    db_delete_mute(ctx.guild.id, member.id)
    await ctx.send(f"🔊 **{member}** unmuté.")
    embed = discord.Embed(title="🔊 Unmute", color=0x2ECC71, timestamp=now_utc())
    embed.add_field(name="👤 Membre", value=f"{member} ({member.id})", inline=True)
    embed.add_field(name="🛡️ Modérateur", value=ctx.author.mention, inline=True)
    await send_log(ctx.guild, embed)


@bot.hybrid_command(name="effacer", aliases=["clear", "purge", "supprimer", "clean"])
async def effacer(ctx, nombre: int = None):
    if not is_staff(ctx.author): await ctx.send("❌ Permission refusée.", delete_after=5); return
    if nombre is None: await ctx.send("❌ `!effacer 10`", delete_after=5); return
    if nombre < 1 or nombre > 100: await ctx.send("❌ Entre 1 et 100.", delete_after=5); return
    deleted = await ctx.channel.purge(limit=nombre + 1)
    await ctx.send(f"🗑️ **{len(deleted) - 1}** messages supprimés.", delete_after=5)
    embed = discord.Embed(title="🗑️ Purge", color=0x95A5A6, timestamp=now_utc())
    embed.add_field(name="🛡️ Modérateur", value=ctx.author.mention, inline=True)
    embed.add_field(name="📍 Salon", value=ctx.channel.mention, inline=True)
    embed.add_field(name="🗑️ Supprimés", value=str(len(deleted) - 1), inline=True)
    await send_log(ctx.guild, embed)


@bot.hybrid_command(name="info", aliases=["whois", "user", "membre"])
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
    status_map = {discord.Status.online:"🟢 En ligne", discord.Status.idle:"🟡 Absent", discord.Status.dnd:"🔴 Ne pas déranger", discord.Status.offline:"⚫ Hors ligne"}
    status   = status_map.get(member.status, "⚫ Inconnu")
    activity = "Aucune"
    if member.activity:
        if isinstance(member.activity, discord.Game):             activity = f"🎮 {member.activity.name}"
        elif isinstance(member.activity, discord.Streaming):      activity = f"📺 {member.activity.name}"
        elif isinstance(member.activity, discord.CustomActivity): activity = f"💬 {member.activity.name}"
        else:                                                      activity = member.activity.name
    embed = discord.Embed(title=f"👤 {member.display_name}", color=member.color if member.color != discord.Color.default() else 0x3498DB, timestamp=now_utc())
    embed.set_thumbnail(url=member.display_avatar.url)
    if member.banner: embed.set_image(url=member.banner.url)
    embed.add_field(name="📛 Pseudo",         value=member.display_name, inline=True)
    embed.add_field(name="🏷️ Tag",            value=str(member),         inline=True)
    embed.add_field(name="🤖 Bot",             value="✅" if member.bot else "❌", inline=True)
    embed.add_field(name="🆔 ID",              value=str(member.id),     inline=True)
    embed.add_field(name="📅 Compte créé",     value=discord.utils.format_dt(member.created_at, style="D"), inline=True)
    embed.add_field(name="📥 Arrivée serveur", value=discord.utils.format_dt(member.joined_at, style="D") if member.joined_at else "?", inline=True)
    embed.add_field(name="📶 Statut",          value=status,   inline=True)
    embed.add_field(name="🎯 Activité",        value=activity, inline=True)
    embed.add_field(name="🎖️ Rôle principal",  value=top_role, inline=True)
    embed.add_field(name=f"🎭 Rôles ({len(roles)})", value=", ".join(roles[:20]) or "Aucun", inline=False)
    embed.add_field(name="🔑 Permissions",     value=", ".join(perms) or "Aucune", inline=False)
    embed.set_footer(text=f"Demandé par {ctx.author}")
    await ctx.send(embed=embed)


@bot.hybrid_command(name="say", aliases=["dit"])
async def say_cmd(ctx, channel: discord.TextChannel = None, *, message: str = None):
    if not is_staff(ctx.author): await ctx.send("❌ Réservé au staff.", delete_after=5); return
    if channel is None or message is None: await ctx.send("❌ Utilisation : `!say #salon message`", delete_after=8); return
    try: await ctx.message.delete()
    except Exception: pass
    try: await channel.send(message)
    except discord.Forbidden: await ctx.send(f"❌ Permission refusée pour {channel.mention}.", delete_after=6)