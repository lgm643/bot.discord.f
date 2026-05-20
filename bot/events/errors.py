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
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        await ctx.send("❌ Commande inconnue. Essayez `!help` pour voir les commandes disponibles.", delete_after=8)
    elif isinstance(error, commands.CheckFailure):
        pass
    else:
        print(f"[ERROR] {ctx.command} : {error}")
