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

@bot.event
async def on_guild_channel_create(channel):
    embed = discord.Embed(title="📢 Salon créé", color=0x2ECC71, timestamp=now_utc())
    embed.add_field(name="📍 Nom", value=channel.name, inline=True)
    embed.add_field(name="📂 Type", value=str(channel.type), inline=True)
    embed.add_field(name="🗂️ Catégorie", value=channel.category.name if channel.category else "Aucune", inline=True)
    await send_log(channel.guild, embed)

@bot.event
async def on_guild_channel_delete(channel):
    embed = discord.Embed(title="🗑️ Salon supprimé", color=0xE74C3C, timestamp=now_utc())
    embed.add_field(name="📍 Nom", value=channel.name, inline=True)
    embed.add_field(name="📂 Type", value=str(channel.type), inline=True)
    embed.add_field(name="🗂️ Catégorie", value=channel.category.name if channel.category else "Aucune", inline=True)
    await send_log(channel.guild, embed)
