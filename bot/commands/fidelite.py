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
from bot.utils.helpers import (
    load_user_data, get_user, save_user_data, xp_for_level, progress_bar, now_utc,
    fmt_voice,  # FIX : fmt_voice était utilisé dans !level mais jamais importé → NameError
)


@bot.command(name="level", aliases=["lvl", "xp"])
async def level_cmd(ctx, member: discord.Member = None):
    member   = member or ctx.author
    data     = load_user_data(ctx.guild.id)
    u        = get_user(data, member.id)
    save_user_data(ctx.guild.id, data)
    lvl      = u["level"]
    cur_xp   = u["xp"]
    required = xp_for_level(lvl + 1)
    bar      = progress_bar(cur_xp, required)
    embed    = discord.Embed(title=f"📊 Niveau — {member.display_name}", color=member.color if member.color != discord.Color.default() else 0x9B59B6, timestamp=now_utc())
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="🏆 Niveau",   value=str(lvl),                  inline=True)
    embed.add_field(name="✉️ Messages", value=str(u["message_count"]),    inline=True)
    embed.add_field(name="🎤 Vocal",    value=fmt_voice(u["voice_time"]), inline=True)
    embed.add_field(name=f"⭐ XP — {cur_xp}/{required}", value=f"`{bar}` {int(cur_xp/required*100)}%", inline=False)
    await ctx.send(embed=embed)


@bot.command(name="pileouface", aliases=["pof", "coinflip"])
async def pof_cmd(ctx):
    result = random.choice(["🪙 **Pile**", "🔵 **Face**"])
    await ctx.send(embed=discord.Embed(title="🪙 Pile ou Face", description=f"Résultat : {result}", color=0xF1C40F))