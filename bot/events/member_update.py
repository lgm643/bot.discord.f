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

from bot.utils.config import load_config, cfg_channel
from bot.utils.embeds import build_roster_embed
from bot.utils.logs import send_log
from bot.utils.helpers import now_utc

@bot.event
async def on_member_update(before, after):
    cfg          = load_config(after.guild.id)
    roster_cfg   = cfg.get("roster_roles", [])
    roster_names = {entry["nom"].lower() for entry in roster_cfg}
    before_roster = {r.name.lower() for r in before.roles if r.name.lower() in roster_names}
    after_roster  = {r.name.lower() for r in after.roles  if r.name.lower() in roster_names}
    if before_roster != after_roster:
        channel = cfg_channel(after.guild, "salon_roster")
        if channel:
            try:
                embed = build_roster_embed(after.guild)
                async for msg in channel.history(limit=20):
                    if msg.author == bot.user and msg.embeds:
                        await msg.edit(embed=embed); break
                else:
                    await channel.send(embed=embed)
            except Exception: pass
    added   = set(after.roles) - set(before.roles)
    removed = set(before.roles) - set(after.roles)
    if added or removed:
        embed = discord.Embed(title="🎭 Rôles modifiés", color=0x9B59B6, timestamp=now_utc())
        embed.add_field(name="👤 Membre", value=f"{after} ({after.id})", inline=True)
        if added:   embed.add_field(name="✅ Ajoutés",  value=", ".join(r.mention for r in added),   inline=False)
        if removed: embed.add_field(name="❌ Retirés",  value=", ".join(r.mention for r in removed), inline=False)
        await send_log(after.guild, embed)
    if before.display_name != after.display_name:
        embed = discord.Embed(title="📝 Pseudo modifié", color=0x3498DB, timestamp=now_utc())
        embed.add_field(name="👤 Membre", value=f"{after} ({after.id})", inline=True)
        embed.add_field(name="📝 Avant",  value=before.display_name, inline=True)
        embed.add_field(name="📝 Après",  value=after.display_name,  inline=True)
        await send_log(after.guild, embed)
