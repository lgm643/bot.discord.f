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

from bot.modals.recrutement_modal import _ObjectifAddModal
from bot.utils.database import db_get_objectifs, db_del_objectif, db_done_objectif
from bot.utils.permissions import is_staff

class ObjectifView(discord.ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id

    @discord.ui.button(label="➕ Ajouter", style=discord.ButtonStyle.green, custom_id="obj_ajouter")
    async def btn_ajouter(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_staff(interaction.user):
            await interaction.response.send_message(embed=discord.Embed(title="❌ Permission refusée", description="Réservé au staff.", color=0xE74C3C), ephemeral=True)
            return
        await interaction.response.send_modal(_ObjectifAddModal(self.guild_id))

    @discord.ui.button(label="🗑 Supprimer", style=discord.ButtonStyle.red, custom_id="obj_supprimer")
    async def btn_supprimer(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_staff(interaction.user):
            await interaction.response.send_message(embed=discord.Embed(title="❌ Permission refusée", description="Réservé au staff.", color=0xE74C3C), ephemeral=True)
            return
        objectifs = db_get_objectifs(self.guild_id)
        if not objectifs:
            await interaction.response.send_message(embed=discord.Embed(title="❌ Aucun objectif", description="Il n'y a rien à supprimer.", color=0xE74C3C), ephemeral=True)
            return
        options = [discord.SelectOption(label=f"#{obj['id']} — {obj['texte'][:80]}", value=str(obj["id"]), emoji="✅" if obj["done"] else "⏳") for obj in objectifs]
        await interaction.response.send_message(embed=discord.Embed(title="🗑 Supprimer un objectif", description="Sélectionne l'objectif à supprimer.", color=0xE74C3C), view=_ObjectifSuppView(self.guild_id, options), ephemeral=True)

    @discord.ui.button(label="✅ Terminer", style=discord.ButtonStyle.blurple, custom_id="obj_terminer")
    async def btn_terminer(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_staff(interaction.user):
            await interaction.response.send_message(embed=discord.Embed(title="❌ Permission refusée", description="Réservé au staff.", color=0xE74C3C), ephemeral=True)
            return
        objectifs = [o for o in db_get_objectifs(self.guild_id) if not o["done"]]
        if not objectifs:
            await interaction.response.send_message(embed=discord.Embed(title="✅ Tout est terminé !", description="Aucun objectif en cours.", color=0x2ECC71), ephemeral=True)
            return
        options = [discord.SelectOption(label=f"#{obj['id']} — {obj['texte'][:80]}", value=str(obj["id"]), emoji="⏳") for obj in objectifs]
        await interaction.response.send_message(embed=discord.Embed(title="✅ Marquer comme terminé", description="Sélectionne l'objectif à cocher.", color=0x2ECC71), view=_ObjectifDoneView(self.guild_id, options), ephemeral=True)


class _ObjectifSuppSelect(discord.ui.Select):
    def __init__(self, guild_id: int, options: list):
        self.guild_id = guild_id
        super().__init__(placeholder="Choisir un objectif à supprimer…", options=options[:25], min_values=1, max_values=1)
    async def callback(self, interaction: discord.Interaction):
        obj_id = int(self.values[0])
        ok = db_del_objectif(self.guild_id, obj_id)
        embed = discord.Embed(title="✅ Objectif supprimé" if ok else "❌ Introuvable", description=f"L'objectif `#{obj_id}` a été {'supprimé' if ok else 'introuvable'}.", color=0x2ECC71 if ok else 0xE74C3C)
        await interaction.response.edit_message(embed=embed, view=None)
        if ok:
            await refresh_objectifs_embed(interaction.guild)

class _ObjectifSuppView(discord.ui.View):
    def __init__(self, guild_id, options):
        super().__init__(timeout=60)
        self.add_item(_ObjectifSuppSelect(guild_id, options))

class _ObjectifDoneSelect(discord.ui.Select):
    def __init__(self, guild_id: int, options: list):
        self.guild_id = guild_id
        super().__init__(placeholder="Choisir un objectif à terminer…", options=options[:25], min_values=1, max_values=1)
    async def callback(self, interaction: discord.Interaction):
        obj_id = int(self.values[0])
        ok = db_done_objectif(self.guild_id, obj_id)
        embed = discord.Embed(title="✅ Objectif terminé" if ok else "❌ Introuvable", description=f"L'objectif `#{obj_id}` est {'maintenant terminé ✅' if ok else 'introuvable ou déjà terminé'}.", color=0x2ECC71 if ok else 0xE74C3C)
        await interaction.response.edit_message(embed=embed, view=None)
        if ok:
            await refresh_objectifs_embed(interaction.guild)

class _ObjectifDoneView(discord.ui.View):
    def __init__(self, guild_id, options):
        super().__init__(timeout=60)
        self.add_item(_ObjectifDoneSelect(guild_id, options))
