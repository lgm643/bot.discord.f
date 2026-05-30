import discord

from bot.utils.config import cfg_channel


async def get_log_channel(guild):
    return cfg_channel(guild, "salon_logs")


async def send_log(guild: discord.Guild, embed: discord.Embed):
    ch = await get_log_channel(guild)
    if ch:
        try:
            await ch.send(embed=embed)
        except Exception as e:
            print(f"[LOG] Erreur : {e}")
