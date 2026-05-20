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

from bot.modals.vendeur_modal import VendeurModal
from bot.utils.config import cfg_role
from bot.utils.permissions import is_staff

class VendeurView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="👉 Devenir vendeur certifié",
        style=discord.ButtonStyle.green,
        custom_id="vendeur_certifie_btn"
    )
    async def devenir_vendeur(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Vérifie si le membre a déjà un ticket vendeur ouvert
        existing = discord.utils.find(
            lambda c: c.name == f"vendeur-{interaction.user.name[:20]}" and hasattr(c, "topic") and c.topic and c.topic.startswith("vendeur_certifie"),
            interaction.guild.channels
        )
        if existing:
            await interaction.response.send_message(
                f"❌ Tu as déjà une demande en cours : {existing.mention}",
                ephemeral=True
            )
            return
        # Vérifie si le membre a déjà le rôle
        role_vendeur = cfg_role(interaction.guild, "role_vendeur")
        if role_vendeur and role_vendeur in interaction.user.roles:
            await interaction.response.send_message(
                "✅ Tu es déjà **Vendeur Certifié** !",
                ephemeral=True
            )
            return
        await interaction.response.send_modal(VendeurModal())
