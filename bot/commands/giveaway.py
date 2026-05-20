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

from bot.views.giveaway_view import GiveawayView, build_giveaway_embed
from bot.core import active_giveaways
from bot.utils.permissions import is_staff


def parse_duration(s):
    total = 0
    for val, unit in re.findall(r"(\d+)([smhj])", s.lower()):
        v = int(val)
        if unit == "s":   total += v
        elif unit == "m": total += v * 60
        elif unit == "h": total += v * 3600
        elif unit == "j": total += v * 86400
    return total if total > 0 else None

@bot.command(name="giveaway", aliases=["gw"])
async def giveaway_cmd(ctx, duree: str = None, *, reward: str = None):
    if not is_staff(ctx.author): await ctx.send("❌ Réservé au staff.", delete_after=5); return
    if duree is None or reward is None: await ctx.send("❌ `!giveaway 1h Récompense`", delete_after=8); return
    seconds = parse_duration(duree)
    if not seconds: await ctx.send("❌ Durée invalide. Ex : `10m`, `1h`, `2h30m`", delete_after=8); return
    ends_at = time.time() + seconds
    gw = {"reward": reward, "ends_at": ends_at, "participants": [], "host": str(ctx.author), "channel_id": ctx.channel.id}
    embed = build_giveaway_embed(gw)
    msg   = await ctx.send(embed=embed, view=GiveawayView(0))
    gw_id = msg.id
    active_giveaways[gw_id] = gw
    await msg.edit(view=GiveawayView(gw_id))
    asyncio.create_task(_end_giveaway(gw_id, seconds, ctx.channel, reward))

async def _end_giveaway(gw_id, delay, channel, reward):
    await asyncio.sleep(delay)
    gw = active_giveaways.pop(gw_id, None)
    if not gw: return
    try:
        msg = await channel.fetch_message(gw_id)
        if not gw["participants"]:
            await msg.edit(embed=discord.Embed(title=f"🎉 GIVEAWAY TERMINÉ — {reward}", description="😔 Aucun participant...", color=0x95A5A6), view=None)
            return
        winner_id = random.choice(gw["participants"])
        winner    = channel.guild.get_member(winner_id)
        name      = winner.mention if winner else f"<@{winner_id}>"
        embed = discord.Embed(title=f"🎉 GIVEAWAY TERMINÉ — {reward}", description=f"🏆 Gagnant : {name}\n🎊 Félicitations !", color=0x2ECC71)
        embed.set_footer(text=f"Organisé par {gw['host']} • {len(gw['participants'])} participants")
        await msg.edit(embed=embed, view=None)
        await channel.send(f"🎊 Félicitations {name} ! Tu as gagné **{reward}** !")
    except Exception as e: print(f"[GW] Erreur fin giveaway : {e}")
