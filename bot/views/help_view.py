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

class HelpSelect(discord.ui.Select):
    def __init__(self, is_staff_user: bool):
        self.is_staff_user = is_staff_user
        categories = HELP_CATEGORIES_PUBLIC + (HELP_CATEGORIES_STAFF if is_staff_user else [])
        options = [
            discord.SelectOption(label="🏠 Accueil", value="accueil", description="Page d'accueil de l'aide"),
        ] + [
            discord.SelectOption(label=label, value=value, description=f"Commandes : {label}")
            for label, value in categories
        ]
        super().__init__(
            placeholder="📂 Choisir une catégorie…",
            options=options,
            custom_id="help_select"
        )

    async def callback(self, interaction: discord.Interaction):
        choice = self.values[0]
        embed_map = {
            "accueil":     _help_embed_accueil(self.is_staff_user),
            "general":     _help_embed_general(),
            "invitations": _help_embed_invitations(),
            "tickets":     _help_embed_tickets(),
            "marche":      _help_embed_marche(),
            "jeux":        _help_embed_jeux(),
            "protections": _help_embed_protections(),
            "moderation":  _help_embed_moderation(),
            "config":      _help_embed_config(),
        }
        embed = embed_map.get(choice, _help_embed_accueil(self.is_staff_user))
        await interaction.response.edit_message(embed=embed, view=self.view)


class HelpView(discord.ui.View):
    def __init__(self, is_staff_user: bool, msg=None):
        super().__init__(timeout=300)
        self.msg = msg
        self.add_item(HelpSelect(is_staff_user))

    async def on_timeout(self):
        if self.msg:
            try:
                for item in self.children:
                    item.disabled = True
                await self.msg.edit(view=self)
            except Exception:
                pass
