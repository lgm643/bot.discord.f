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

from bot.core import active_giveaways
from bot.utils.helpers import now_utc

def build_giveaway_embed(gw):
    ends  = discord.utils.format_dt(datetime.fromtimestamp(gw["ends_at"], tz=timezone.utc), style="R")
    embed = discord.Embed(title=f"🎉 GIVEAWAY — {gw['reward']}", description="Clique sur **🎉 Participer** pour tenter ta chance !", color=0xF1C40F)
    embed.add_field(name="⏰ Fin",          value=ends,                         inline=True)
    embed.add_field(name="👥 Participants", value=str(len(gw["participants"])), inline=True)
    embed.add_field(name="🏆 Récompense",  value=gw["reward"],                 inline=False)
    embed.set_footer(text=f"Organisé par {gw['host']}")
    return embed

class GiveawayView(discord.ui.View):
    def __init__(self, msg_id):
        super().__init__(timeout=None)
        self.msg_id = msg_id

    @discord.ui.button(label="🎉 Participer", style=discord.ButtonStyle.green)
    async def participer(self, interaction, button):
        gw = active_giveaways.get(self.msg_id)
        if not gw: await interaction.response.send_message("❌ Ce giveaway est terminé.", ephemeral=True); return
        uid = interaction.user.id
        if uid in gw["participants"]:
            gw["participants"].remove(uid)
            await interaction.response.send_message("❌ Tu t'es retiré du giveaway.", ephemeral=True)
        else:
            gw["participants"].append(uid)
            await interaction.response.send_message("✅ Tu participes au giveaway !", ephemeral=True)
        try:
            msg = await interaction.channel.fetch_message(self.msg_id)
            await msg.edit(embed=build_giveaway_embed(gw))
        except Exception: pass
