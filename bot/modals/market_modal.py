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
from bot.utils.helpers import now_utc
from bot.utils.market import load_catalogue, fuzzy_search

class CommandeRechercheModal(discord.ui.Modal, title="🔍 Rechercher un article"):
    terme = discord.ui.TextInput(label="Nom ou mots-clés", placeholder="ex: paladium", max_length=50)
    def __init__(self, guild_id):
        super().__init__()
        self.guild_id = guild_id
    async def on_submit(self, interaction: discord.Interaction):
        data  = load_catalogue(self.guild_id)
        items = data.get("items", {})
        res   = fuzzy_search(str(self.terme), items)
        if not res:
            await interaction.response.send_message("❌ Aucun résultat trouvé.", ephemeral=True); return
        embed = discord.Embed(title=f"🔍 Résultats pour « {self.terme} »", color=0x9B59B6, timestamp=now_utc())
        for key, (item, score) in list(res.items())[:10]:
            vendeur_m = interaction.guild.get_member(item["vendeur_id"])
            vnom      = vendeur_m.display_name if vendeur_m else f"<@{item['vendeur_id']}>"
            embed.add_field(name=f"🔹 {item['nom']} ({int(score*100)}% match)", value=f"📦 {item['quantite']} · 💰 {item['prix']} · 👤 {vnom}", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)
