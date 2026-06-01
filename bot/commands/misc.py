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

from bot.views.objectif_views import ObjectifView
from bot.utils.embeds import build_objectifs_embed
from bot.utils.database import db_save_objectif_embed
from bot.utils.permissions import is_staff

@bot.command(name="objectif")
async def objectif_cmd(ctx):
    if not is_staff(ctx.author):
        await ctx.send(embed=discord.Embed(title="❌ Permission refusée", description="Réservé au staff.", color=0xE74C3C), delete_after=5)
        return
    embed = build_objectifs_embed(ctx.guild.id)
    view  = ObjectifView(ctx.guild.id)
    msg   = await ctx.send(embed=embed, view=view)
    db_save_objectif_embed(ctx.guild.id, ctx.channel.id, msg.id)
@bot.command(name="pub")
async def pub_cmd(ctx):
    if not is_staff(ctx.author): await ctx.send("❌ Réservé au staff.", delete_after=5); return
    texte = (
        "**__LA MYSTIC RECRUTE__** 🐦‍🔥\n"
        "Vous ne savez plus quoi faire ? Envie de PvP, de farm et de domination ?\n"
        "La faction **__Mystic__** est faite pour vous !\n"
        "Nous recrutons des **joueurs PvP expérimentés**, des **farmeurs motivés**, "
        "mais aussi des **nouveaux joueurs** qui veulent progresser et rejoindre une faction "
        "sérieuse avec de gros projets et une vraie ambiance d'équipe.\n---\n"
        "**__AU PROGRAMME :__**\n• Base claim solide et organisée\n• Sessions PvP régulières avec toute la faction\n"
        "• Du tryhard et de la compétition\n• Farms de faction énormes accessibles à tous les membres\n"
        "• F-Home commun pour toute la faction\n• Du fun, de la bonne humeur et beaucoup de rigolade\n"
        "• Et plein d'autres projets en équipe\n---\n"
        "**__PRÉREQUIS :__**\n• Avoir Minecraft\n• Âge minimum : 15 ans\n• Bonne humeur obligatoire\n"
        "• Être capable d'être en vocal pour les sessions PvP\n---\n"
        "📩 **__INTÉRESSÉ ?__**\n"
        "Le lien est dans la bio de **@lgm6143** pour rejoindre le Discord et envoyer ta candidature !\n---\n"
        "🐦‍🔥 **__MYSTIC — RISE LIKE A PHOENIX__**"
    )
    await ctx.send(texte)
@bot.command(name="setup")
async def setup_cmd(ctx):
    if not ctx.author.guild_permissions.administrator:
        await ctx.send("❌ Réservé aux administrateurs.", delete_after=5); return
    await ctx.send(embed=discord.Embed(
        title="⚙️ Configuration du serveur",
        description="Utilisez `!config` pour ouvrir le **panneau de configuration interactif** complet.",
        color=0x9B59B6
    ), delete_after=10)
