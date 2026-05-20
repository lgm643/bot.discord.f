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

from bot.core import bot, GAMES_DIR, active_pendu, active_morpion, _catalogue_msg_ids, _commande_msg_ids
from bot.utils.helpers import load_games_for, gk
from bot.utils.market import load_catalogue
from bot.utils.database import get_db, db_save_objectif_embed
from bot.utils.embeds import build_objectifs_embed
from bot.utils.market import _clean_ghost_items, build_catalogue_embed, _get_catalogue_lock
from bot.utils.config import cfg_channel
from bot.utils.games import _start_pendu_timer, _start_morpion_timer

async def _restore_all_games():
    for path in GAMES_DIR.glob("*.json"):
        try: guild_id = int(path.stem)
        except ValueError: continue
        raw = load_games_for(guild_id)
        now = time.time()
        for key_str, data in raw.items():
            remaining = data.get("end_time", 0) - now
            if remaining <= 0: continue
            if key_str.startswith("pendu_"):
                ch_id = int(key_str.split("_", 1)[1])
                k     = gk(guild_id, ch_id)
                data["guessed"]    = list(data.get("guessed", []))
                data["letter_cd"]  = {}
                data["channel_id"] = ch_id
                active_pendu[k] = data
                await _start_pendu_timer(k, guild_id, remaining)
                print(f"[RESTORE] Pendu restauré : guild={guild_id} ch={ch_id}")
            elif key_str.startswith("morpion_"):
                ch_id = int(key_str.split("_", 1)[1])
                k     = gk(guild_id, ch_id)
                active_morpion[k] = data
                await _start_morpion_timer(k, guild_id, remaining)
                print(f"[RESTORE] Morpion restauré : guild={guild_id} ch={ch_id}")


async def _restore_all_catalogues():
    for path in CATALOGUE_DIR.glob("*.json"):
        try:
            guild_id = int(path.stem)
            data     = load_catalogue(guild_id)
            if data.get("msg_id"):
                _catalogue_msg_ids[guild_id] = data["msg_id"]
                print(f"[CATALOGUE] msg_id restauré : guild={guild_id} → {data['msg_id']}")
            if data.get("commande_msg_id"):
                _commande_msg_ids[guild_id] = data["commande_msg_id"]
                print(f"[COMMANDE]  commande_msg_id restauré : guild={guild_id} → {data['commande_msg_id']}")
        except Exception: pass


async def _restore_all_objectifs():
    with get_db() as conn:
        rows = conn.execute("SELECT guild_id, channel_id, msg_id FROM objectif_embeds").fetchall()
    for row in rows:
        guild = bot.get_guild(row["guild_id"])
        if not guild: continue
        channel = guild.get_channel(row["channel_id"])
        if not channel: continue
        embed = build_objectifs_embed(row["guild_id"])
        try:
            msg = await channel.fetch_message(row["msg_id"])
            await msg.edit(embed=embed)
            print(f"[OBJECTIFS] Embed restauré : guild={row['guild_id']}")
        except Exception:
            try:
                msg = await channel.send(embed=embed)
                db_save_objectif_embed(row["guild_id"], channel.id, msg.id)
                print(f"[OBJECTIFS] Embed recréé : guild={row['guild_id']}")
            except Exception as e:
                print(f"[OBJECTIFS] Impossible de restaurer : {e}")


# ─── Boucle auto-refresh catalogue + commandes toutes les 3s ──

_auto_refresh_running = False

async def _auto_refresh_loop():
    global _auto_refresh_running
    if _auto_refresh_running: return
    _auto_refresh_running = True
    print("[REFRESH] Boucle auto-refresh démarrée (3s)")
    try:
        while True:
            await asyncio.sleep(3)
            for guild in bot.guilds:
                try:
                    data  = load_catalogue(guild.id)
                    items = _clean_ghost_items(data.get("items", {}))
                    await _silent_refresh(guild, items)
                except Exception as e:
                    print(f"[REFRESH] Erreur guild={guild.id} : {e}")
    finally:
        _auto_refresh_running = False


async def _silent_refresh(guild, items):
    async with _get_catalogue_lock(guild.id):
        data = load_catalogue(guild.id)
        cat_msg_id = data.get("msg_id") or _catalogue_msg_ids.get(guild.id)
        if cat_msg_id:
            cat_ch = cfg_channel(guild, "salon_catalogue")
            if cat_ch:
                try:
                    msg = await cat_ch.fetch_message(cat_msg_id)
                    await msg.edit(embed=build_catalogue_embed(items))
                except discord.NotFound:
                    _catalogue_msg_ids.pop(guild.id, None)
                    data.pop("msg_id", None)
                    save_catalogue(guild.id, data)
                except Exception: pass
        cmd_msg_id = data.get("commande_msg_id") or _commande_msg_ids.get(guild.id)
        if cmd_msg_id:
            cmd_ch = cfg_channel(guild, "salon_commandes")
            if cmd_ch:
                try:
                    cmd_msg = await cmd_ch.fetch_message(cmd_msg_id)
                    await cmd_msg.edit(embed=_build_commande_embed_from_items(guild, items), view=__import__('bot.views.market_view', fromlist=['CommandeView']).CommandeView(guild.id, items))
                except discord.NotFound:
                    _commande_msg_ids.pop(guild.id, None)
                    data.pop("commande_msg_id", None)
                    save_catalogue(guild.id, data)
                except Exception: pass
