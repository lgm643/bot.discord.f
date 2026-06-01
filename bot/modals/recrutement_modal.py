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

from bot.utils.database import db_add_objectif
from bot.utils.embeds import refresh_objectifs_embed

class _ObjectifAddModal(discord.ui.Modal, title="➕ Ajouter un objectif"):
    texte = discord.ui.TextInput(label="Texte de l'objectif", placeholder="Ex : Farmer 100 paladiums", max_length=200)
    def __init__(self, guild_id: int):
        super().__init__()
        self.guild_id = guild_id
    async def on_submit(self, interaction: discord.Interaction):
        texte  = str(self.texte).strip()
        obj_id = db_add_objectif(self.guild_id, texte)
        await interaction.response.send_message(embed=discord.Embed(title="✅ Objectif ajouté", description=f"`#{obj_id}` — {texte}", color=0x2ECC71), ephemeral=True)
        await refresh_objectifs_embed(interaction.guild)


# Alias module name
