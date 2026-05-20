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

from bot.views.game_views import PenduView, MorpionView
from bot.core import active_pendu, active_morpion, pendu_tasks, morpion_tasks
from bot.utils.helpers import gk, save_games
from bot.utils.games import _start_pendu_timer, _start_morpion_timer, _update_pendu, _end_pendu, build_pendu_embed, build_morpion_embed

@bot.command(name="pendu")
async def pendu_cmd(ctx):
    key = gk(ctx.guild.id, ctx.channel.id)
    if key in active_pendu: await ctx.send("❌ Une partie est déjà en cours dans ce salon.", delete_after=5); return
    await ctx.send("🎯 **Pendu** — Comment veux-tu jouer ?", view=PenduView(ctx.guild.id, ctx.channel.id, ctx.author.id))

@bot.command(name="devine")
async def devine_cmd(ctx, lettre: str = None):
    key  = gk(ctx.guild.id, ctx.channel.id)
    game = active_pendu.get(key)
    if not game: await ctx.send("❌ Aucune partie en cours. Lance `!pendu`.", delete_after=5); return
    if ctx.author.id == game["creator"]: await ctx.send("❌ Le créateur ne peut pas jouer.", delete_after=5); return
    if lettre is None or len(lettre) != 1 or not lettre.isalpha(): await ctx.send("❌ `!devine [lettre]`", delete_after=5); return
    lettre = lettre.lower()
    uid    = ctx.author.id
    now_m  = time.monotonic()
    if now_m - game["letter_cd"].get(str(uid), 0) < 3: await ctx.send("⏳ Attends 3 secondes.", delete_after=3); return
    game["letter_cd"][str(uid)] = now_m
    if lettre in game["guessed"]: await ctx.send(f"⚠️ `{lettre}` déjà jouée.", delete_after=4); return
    game["guessed"].append(lettre)
    if uid not in game["participants"]: game["participants"].append(uid)
    if lettre not in game["word"]: game["errors"] += 1
    save_games(ctx.guild.id)
    try: await ctx.message.delete()
    except Exception: pass
    winner_id = uid if all(l in game["guessed"] for l in game["word"]) else None
    await _update_pendu(ctx, ctx.guild.id, game, winner_id=winner_id)

@bot.command(name="mot")
async def mot_cmd(ctx, *, mot: str = None):
    key  = gk(ctx.guild.id, ctx.channel.id)
    game = active_pendu.get(key)
    if not game: await ctx.send("❌ Aucune partie en cours.", delete_after=5); return
    if ctx.author.id == game["creator"]: await ctx.send("❌ Le créateur ne peut pas jouer.", delete_after=5); return
    if mot is None: await ctx.send("❌ `!mot [mot complet]`", delete_after=5); return
    mot = mot.lower().strip()
    uid = ctx.author.id
    if uid not in game["participants"]: game["participants"].append(uid)
    try: await ctx.message.delete()
    except Exception: pass
    if mot == game["word"]:
        for l in game["word"]:
            if l not in game["guessed"]: game["guessed"].append(l)
        save_games(ctx.guild.id)
        await _update_pendu(ctx, ctx.guild.id, game, winner_id=uid)
    else:
        game["errors"] += 1
        save_games(ctx.guild.id)
        await _update_pendu(ctx, ctx.guild.id, game)

@bot.command(name="pendustop")
async def pendustop_cmd(ctx):
    if not is_staff(ctx.author): await ctx.send("❌ Réservé au staff.", delete_after=5); return
    key  = gk(ctx.guild.id, ctx.channel.id)
    game = active_pendu.get(key)
    if not game: await ctx.send("❌ Aucune partie en cours.", delete_after=5); return
    active_pendu.pop(key, None)
    if key in pendu_tasks: pendu_tasks[key].cancel(); pendu_tasks.pop(key, None)
    save_games(ctx.guild.id)
    await ctx.send(f"🛑 Partie arrêtée. Le mot était **{game['word']}**.")
@bot.command(name="morpion")
async def morpion_cmd(ctx, opponent: discord.Member = None):
    if opponent is None: await ctx.send("❌ `!morpion @joueur`", delete_after=5); return
    if opponent.bot or opponent.id == ctx.author.id: await ctx.send("❌ Adversaire invalide.", delete_after=5); return
    key = gk(ctx.guild.id, ctx.channel.id)
    if key in active_morpion: await ctx.send("❌ Partie déjà en cours.", delete_after=5); return
    end_time = time.time() + 5 * 60
    game = {"board": [None]*9, "players": [ctx.author.id, opponent.id], "current": 0, "msg_id": None, "end_time": end_time}
    active_morpion[key] = game
    view  = MorpionView(ctx.guild.id, ctx.channel.id)
    embed = build_morpion_embed(game)
    msg   = await ctx.send(embed=embed, view=view)
    game["msg_id"] = msg.id
    save_games(ctx.guild.id)
    await _start_morpion_timer(key, ctx.guild.id, 5 * 60)

@bot.command(name="morpionstop")
async def morpionstop_cmd(ctx):
    if not is_staff(ctx.author): await ctx.send("❌ Réservé au staff.", delete_after=5); return
    key  = gk(ctx.guild.id, ctx.channel.id)
    game = active_morpion.get(key)
    if not game: await ctx.send("❌ Aucune partie en cours.", delete_after=5); return
    active_morpion.pop(key, None)
    if key in morpion_tasks: morpion_tasks[key].cancel(); morpion_tasks.pop(key, None)
    save_games(ctx.guild.id)
    await ctx.send("🛑 Partie de morpion arrêtée.")
