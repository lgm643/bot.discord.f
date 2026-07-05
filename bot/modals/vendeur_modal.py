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
from bot.utils.config import load_config, cfg_roles, cfg_category
from bot.utils.helpers import now_utc
from bot.utils.logs import send_log
# Import différé dans on_submit pour éviter un import circulaire avec vendeur_view.py
# (vendeur_view importe déjà VendeurModal depuis ce module).

class VendeurModal(discord.ui.Modal, title="🛒 Demande de Vendeur Certifié"):
    pseudo = discord.ui.TextInput(
        label="🎮 Pseudo Discord",
        placeholder="Ton pseudo Discord exact",
        max_length=50
    )
    produits = discord.ui.TextInput(
        label="📦 Type de produits vendus",
        placeholder="Ex : minerais, stuff PvP, ressources diverses...",
        style=discord.TextStyle.paragraph,
        max_length=300
    )
    disponibilites = discord.ui.TextInput(
        label="⏰ Disponibilités",
        placeholder="Matin / après-midi / soir / week-end...",
        max_length=200
    )
    serieux = discord.ui.TextInput(
        label="🤝 Sérieux & Stock",
        placeholder="Es-tu prêt à respecter les règles ? As-tu du stock prêt ?",
        style=discord.TextStyle.paragraph,
        max_length=500
    )
    motivation = discord.ui.TextInput(
        label="🎯 Motivation",
        placeholder="Pourquoi veux-tu devenir vendeur certifié ?",
        style=discord.TextStyle.paragraph,
        max_length=500
    )

    async def on_submit(self, interaction: discord.Interaction):
        guild       = interaction.guild
        member      = interaction.user
        cfg         = load_config(guild.id)
        staff_roles = cfg_roles(guild, "role_staff")
        category    = cfg_category(guild, "categorie_tickets")

        # Créer le salon ticket privé
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            member:             discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            guild.me:           discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True),
        }
        for r in staff_roles:
            overwrites[r] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

        ticket_ch = await guild.create_text_channel(
            name=f"vendeur-{member.name[:20]}",
            category=category,
            overwrites=overwrites,
            topic=f"vendeur_certifie|{member.id}"
        )

        # Embed récapitulatif dans le ticket
        from bot.utils.emojis import get_emoji
        emoji_vendeur = get_emoji(guild, "vendeur")
        embed = discord.Embed(
            title=f"{emoji_vendeur} Demande de Vendeur Certifié",
            color=0xF1C40F,
            timestamp=now_utc()
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="👤 Candidat",          value=f"{member.mention} (`{member.name}`)", inline=False)
        embed.add_field(name="🎮 Pseudo Discord",    value=str(self.pseudo),        inline=True)
        embed.add_field(name="⏰ Disponibilités",     value=str(self.disponibilites), inline=True)
        embed.add_field(name="📦 Produits vendus",   value=str(self.produits),       inline=False)
        embed.add_field(name="🤝 Sérieux & Stock",   value=str(self.serieux),        inline=False)
        embed.add_field(name="🎯 Motivation",        value=str(self.motivation),     inline=False)
        embed.add_field(
            name="📌 Rappel commandes marché",
            value=(
                "`!gestion` / `!catalogue <nom> <qté> <prix>` → publier un article\n"
                "`!cataloguesupp` → supprimer un article\n"
                "`!vendu` → confirmer une vente dans un ticket\n"
                "`!help` → toutes les commandes"
            ),
            inline=False
        )
        embed.set_footer(text="Staff : utilisez les boutons ✅/❌ ci-dessous (ou !accepter / !refuser) · !fermer pour clore")

        from bot.views.vendeur_view import VendeurDecisionView
        decision_view = VendeurDecisionView(member.id)
        bot.add_view(decision_view)  # persistant après redémarrage grâce au custom_id figé

        ping_staff = " ".join(r.mention for r in staff_roles) if staff_roles else "@Staff"
        await ticket_ch.send(
            content=f"{ping_staff} | {member.mention}\n📋 Nouvelle demande de **Vendeur Certifié** !",
            embed=embed,
            view=decision_view,
        )

        await interaction.response.send_message(
            f"✅ Ta demande a été envoyée ! Ticket créé : {ticket_ch.mention}",
            ephemeral=True
        )

        # Log dans salon logs
        await send_log(guild, discord.Embed(
            title="🛒 Nouvelle demande Vendeur Certifié",
            description=f"{member.mention} (`{member.name}`) a soumis une candidature.\nTicket : {ticket_ch.mention}",
            color=0xF1C40F,
            timestamp=now_utc()
        ))
