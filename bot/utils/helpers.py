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

from bot.core import DATA_DIR, GAMES_DIR

def now_str():  return discord.utils.format_dt(datetime.now(timezone.utc), style="F")
def now_utc():  return datetime.now(timezone.utc)

def fmt_voice(seconds: float) -> str:
    seconds = int(seconds)
    h, r = divmod(seconds, 3600)
    m, s = divmod(r, 60)
    if h: return f"{h}h {m}m"
    if m: return f"{m}m {s}s"
    return f"{s}s"
xp_cooldowns: dict[str, float] = {}

def _data_path(guild_id: int) -> Path: return DATA_DIR / f"{guild_id}.json"

def load_user_data(guild_id: int) -> dict:
    path = _data_path(guild_id)
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and data:
                return data
        except Exception as e:
            print(f"[DATA] Erreur lecture {path} : {e}")
            backup = str(path) + ".bak"
            if Path(backup).exists():
                try:
                    with open(backup, "r", encoding="utf-8") as f:
                        return json.load(f)
                except Exception:
                    pass
    return {}


def save_user_data(guild_id: int, data: dict):
    if not data:
        return
    path = _data_path(guild_id)
    tmp  = str(path) + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        if path.exists():
            import shutil
            shutil.copy2(path, str(path) + ".bak")
        os.replace(tmp, path)
    except Exception as e:
        print(f"[DATA] Erreur sauvegarde : {e}")


def get_user(data: dict, user_id: int) -> dict:
    uid = str(user_id)
    if uid not in data:
        data[uid] = {"xp": 0, "level": 0, "message_count": 0, "voice_time": 0.0, "voice_join": None}
    return data[uid]

def xp_for_level(level: int) -> int: return 100 * (level + 1) + 50 * level * level

def progress_bar(current: int, total: int, length: int = 10) -> str:
    filled = int(length * current / total) if total > 0 else 0
    return "█" * filled + "░" * (length - filled)

# ═══════════════════════════════════════════════════════════════
#  JEUX — persistance
# ═══════════════════════════════════════════════════════════════

def gk(guild_id: int, channel_id: int) -> str: return f"{guild_id}:{channel_id}"

def save_games(guild_id: int):
    from bot.core import active_pendu, active_morpion

    path = GAMES_DIR / f"{guild_id}.json"
    data = {}
    for key, g in active_pendu.items():
        gid, ch_id = key.split(":")
        if int(gid) == guild_id:
            data[f"pendu_{ch_id}"] = {
                "word": g["word"], "guessed": list(g["guessed"]),
                "errors": g["errors"], "creator": g["creator"],
                "participants": g["participants"],
                "msg_id": g.get("msg_id"), "end_time": g["end_time"],
            }
    for key, g in active_morpion.items():
        gid, ch_id = key.split(":")
        if int(gid) == guild_id:
            data[f"morpion_{ch_id}"] = {
                "board": g["board"], "players": g["players"],
                "current": g["current"], "msg_id": g.get("msg_id"),
                "end_time": g["end_time"],
            }
    try:
        with open(path, "w") as f:
            json.dump(data, f)
    except Exception as e:
        print(f"[GAMES] Erreur sauvegarde : {e}")


def load_games_for(guild_id: int) -> dict:
    path = GAMES_DIR / f"{guild_id}.json"
    if path.exists():
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            pass
    return {}
