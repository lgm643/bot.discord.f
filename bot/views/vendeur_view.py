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


class _RefusRaisonModal(discord.ui.Modal, title="❌ Raison du refus"):
    raison = discord.ui.TextInput(
        label="Raison",
        placeholder="Ex : stock insuffisant, règles non respectées...",
        style=discord.TextStyle.paragraph,
        max_length=300,
        required=False,
    )

    def __init__(self, membre_id: int | None):
        super().__init__()
        self.membre_id = membre_id

    async def on_submit(self, interaction: discord.Interaction):
        from bot.commands.vendeur import process_refus
        raison_txt = str(self.raison).strip() or "Demande refusée par le staff."
        await interaction.response.defer()
        await process_refus(interaction.guild, interaction.channel, self.membre_id, interaction.user, raison_txt)


class VendeurDecisionView(discord.ui.View):
    """Boutons ✅/❌ posés directement sur le ticket de candidature — évite de taper !accepter/!refuser."""

    def __init__(self, membre_id: int | None = None):
        super().__init__(timeout=None)
        self.membre_id = membre_id
        # custom_id encode le membre_id pour rester fonctionnel après un redémarrage
        self.accepter_btn.custom_id = f"vendeur_decision_accepter_{membre_id or 0}"
        self.refuser_btn.custom_id  = f"vendeur_decision_refuser_{membre_id or 0}"

    def _extract_membre_id(self, interaction: discord.Interaction) -> int | None:
        if self.membre_id:
            return self.membre_id
        topic = getattr(interaction.channel, "topic", None) or ""
        parts = topic.split("|")
        try:
            return int(parts[1]) if len(parts) > 1 else None
        except ValueError:
            return None

    @discord.ui.button(label="✅ Accepter", style=discord.ButtonStyle.green, row=0)
    async def accepter_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_staff(interaction.user):
            await interaction.response.send_message("❌ Réservé au staff.", ephemeral=True)
            return
        from bot.commands.vendeur import process_acceptation
        await interaction.response.defer()
        membre_id = self._extract_membre_id(interaction)
        await process_acceptation(interaction.guild, interaction.channel, membre_id, interaction.user, "Demande acceptée par le staff.")

    @discord.ui.button(label="❌ Refuser", style=discord.ButtonStyle.red, row=0)
    async def refuser_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_staff(interaction.user):
            await interaction.response.send_message("❌ Réservé au staff.", ephemeral=True)
            return
        membre_id = self._extract_membre_id(interaction)
        await interaction.response.send_modal(_RefusRaisonModal(membre_id))


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
