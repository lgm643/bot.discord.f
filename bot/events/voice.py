"""
events/voice.py — Événements vocaux + intégration inactivité.

AJOUTS v2 :
  - record_voice_activity() appelé à chaque connexion/changement de salon
    pour réinitialiser le compteur d'inactivité.
  - clear_voice_activity() appelé à la déconnexion pour nettoyer le suivi.
  - Les logs vocaux sont également enrichis (mention + ID).
"""
import time

import discord

from bot.core import bot
from bot.utils.helpers import load_user_data, get_user, save_user_data, now_utc
from bot.utils.logs import send_log
from bot.utils.stats import record_voice_end
from bot.utils.voice_inactivity import record_voice_activity, clear_voice_activity


@bot.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    if member.bot:
        return

    gid  = member.guild.id
    data = load_user_data(gid)
    u    = get_user(data, member.id)
    now  = time.time()

    # ── Stats vocales XP ──────────────────────────────────────────────────────
    if before.channel is None and after.channel is not None:
        # Connexion
        u["voice_join"] = now

    elif before.channel is not None and after.channel is None:
        # Déconnexion
        if u.get("voice_join"):
            duration = now - u["voice_join"]
            u["voice_time"] = u.get("voice_time", 0.0) + duration
            u["voice_join"] = None
            record_voice_end(gid, member.id, duration)

    save_user_data(gid, data)

    # ── Suivi inactivité vocale ───────────────────────────────────────────────
    if after.channel is not None:
        # Connexion ou changement de salon = activité détectée
        record_voice_activity(gid, member.id)
    else:
        # Déconnexion = nettoyer le suivi
        clear_voice_activity(gid, member.id)

    # ── Logs vocaux enrichis ──────────────────────────────────────────────────
    if before.channel is None and after.channel is not None:
        embed = discord.Embed(title="🔊 Connexion vocale", color=0x2ECC71, timestamp=now_utc())
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="👤 Membre", value=f"{member.mention}\n`{member}` — ID `{member.id}`", inline=True)
        embed.add_field(name="📍 Salon",  value=f"{after.channel.mention}\n`{after.channel.name}`", inline=True)
        await send_log(member.guild, embed)

    elif before.channel is not None and after.channel is None:
        embed = discord.Embed(title="🔇 Déconnexion vocale", color=0xE74C3C, timestamp=now_utc())
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="👤 Membre", value=f"{member.mention}\n`{member}` — ID `{member.id}`", inline=True)
        embed.add_field(name="📍 Salon",  value=f"`{before.channel.name}`", inline=True)
        await send_log(member.guild, embed)

    elif before.channel and after.channel and before.channel != after.channel:
        embed = discord.Embed(title="🔄 Changement de salon vocal", color=0x3498DB, timestamp=now_utc())
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="👤 Membre", value=f"{member.mention}\n`{member}` — ID `{member.id}`", inline=True)
        embed.add_field(name="📤 Avant",  value=f"`{before.channel.name}`", inline=True)
        embed.add_field(name="📥 Après",  value=f"{after.channel.mention}", inline=True)
        await send_log(member.guild, embed)

    # Toute activité dans le vocal (unmute, caméra, stream) réinitialise le compteur
    elif before.channel == after.channel and after.channel is not None:
        if (before.self_mute != after.self_mute or
            before.self_deaf != after.self_deaf or
            before.self_video != after.self_video or
            before.self_stream != after.self_stream):
            record_voice_activity(gid, member.id)