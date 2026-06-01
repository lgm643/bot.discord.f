import time

import discord

from bot.core import bot
from bot.utils.helpers import load_user_data, get_user, save_user_data, now_utc
from bot.utils.logs import send_log
from bot.utils.stats import record_voice_end


@bot.event
async def on_voice_state_update(member, before, after):
    if member.bot:
        return
    gid = member.guild.id
    data = load_user_data(gid)
    u = get_user(data, member.id)
    now = time.time()
    if before.channel is None and after.channel is not None:
        u["voice_join"] = now
    elif before.channel is not None and after.channel is None:
        if u.get("voice_join"):
            duration = now - u["voice_join"]
            u["voice_time"] += duration
            u["voice_join"] = None
            record_voice_end(gid, member.id, duration)
    save_user_data(gid, data)
    if before.channel is None and after.channel is not None:
        embed = discord.Embed(title="🔊 Connexion vocale", color=0x2ECC71, timestamp=now_utc())
        embed.add_field(name="👤 Membre", value=f"{member} ({member.id})", inline=True)
        embed.add_field(name="📍 Salon", value=after.channel.name, inline=True)
        await send_log(member.guild, embed)
    elif before.channel is not None and after.channel is None:
        embed = discord.Embed(title="🔇 Déconnexion vocale", color=0xE74C3C, timestamp=now_utc())
        embed.add_field(name="👤 Membre", value=f"{member} ({member.id})", inline=True)
        embed.add_field(name="📍 Salon", value=before.channel.name, inline=True)
        await send_log(member.guild, embed)
    elif before.channel and after.channel and before.channel != after.channel:
        embed = discord.Embed(title="🔄 Changement de salon vocal", color=0x3498DB, timestamp=now_utc())
        embed.add_field(name="👤 Membre", value=f"{member} ({member.id})", inline=True)
        embed.add_field(name="📤 Avant", value=before.channel.name, inline=True)
        embed.add_field(name="📥 Après", value=after.channel.name, inline=True)
        await send_log(member.guild, embed)
