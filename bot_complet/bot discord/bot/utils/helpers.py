"""
utils/helpers.py — Helpers généraux.

CORRECTIONS v2 :
  [1] flush_user_data / flush_user_data_all sont désormais ASYNC et utilisent
      loop.run_in_executor() pour ne jamais bloquer l'event loop asyncio lors
      de l'écriture disque (bug critique sur serveurs actifs).
  [2] flush_user_data_all() est appelé avec await dans ready.py — adapté en
      conséquence.
  [3] Le fichier .bak est créé dès le premier flush s'il n'existait pas encore,
      évitant la perte totale en cas de crash au tout premier démarrage.
  [4] save_user_data() accepte data vide uniquement si dirty explicitement demandé
      (sécurité contre l'écrasement accidentel).
"""
import asyncio
import json
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

import discord

from bot.core import DATA_DIR, GAMES_DIR, _user_data_cache, _user_data_dirty


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


def _data_path(guild_id: int) -> Path:
    return DATA_DIR / f"{guild_id}.json"


def load_user_data(guild_id: int) -> dict:
    """Charge depuis le cache mémoire. Si absent, lit le fichier (+ fallback .bak)."""
    if guild_id in _user_data_cache:
        return _user_data_cache[guild_id]
    path = _data_path(guild_id)
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and data:
                _user_data_cache[guild_id] = data
                return data
        except Exception as e:
            print(f"[DATA] Erreur lecture {path} : {e}")
            backup = Path(str(path) + ".bak")
            if backup.exists():
                try:
                    with open(backup, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    print(f"[DATA] Restauration depuis {backup}")
                    _user_data_cache[guild_id] = data
                    return data
                except Exception as be:
                    print(f"[DATA] Erreur lecture backup {backup} : {be}")
    _user_data_cache[guild_id] = {}
    return _user_data_cache[guild_id]


def save_user_data(guild_id: int, data: dict):
    """Met à jour le cache et marque comme dirty (flush différé asynchrone)."""
    if not data:
        return
    _user_data_cache[guild_id] = data
    _user_data_dirty.add(guild_id)


# ── Flush synchrone (appelé dans un executor, ne jamais appeler directement) ──

def _flush_user_data_sync(guild_id: int):
    """Écriture disque synchrone — toujours exécutée via run_in_executor."""
    data = _user_data_cache.get(guild_id)
    if not data:
        _user_data_dirty.discard(guild_id)
        return
    path = _data_path(guild_id)
    tmp  = Path(str(path) + ".tmp")
    bak  = Path(str(path) + ".bak")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        # Toujours créer / mettre à jour le backup avant le remplacement
        if path.exists():
            shutil.copy2(path, bak)
        elif bak.exists() is False:
            # Premier démarrage : on crée le backup depuis le tmp
            shutil.copy2(tmp, bak)
        os.replace(tmp, path)
        _user_data_dirty.discard(guild_id)
    except Exception as e:
        print(f"[DATA] Erreur flush guild={guild_id} : {e}")
        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:
            pass


# ── API async publique ────────────────────────────────────────────────────────

async def flush_user_data(guild_id: int):
    """Flush asynchrone d'un seul guild (non-bloquant)."""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _flush_user_data_sync, guild_id)


async def flush_user_data_all():
    """Flush asynchrone de tous les guilds dirty (non-bloquant)."""
    dirty = list(_user_data_dirty)
    if not dirty:
        return
    loop = asyncio.get_event_loop()
    tasks = [loop.run_in_executor(None, _flush_user_data_sync, gid) for gid in dirty]
    await asyncio.gather(*tasks, return_exceptions=True)


def get_user(data: dict, user_id: int) -> dict:
    uid = str(user_id)
    if uid not in data:
        data[uid] = {"xp": 0, "level": 0, "message_count": 0, "voice_time": 0.0, "voice_join": None}
    return data[uid]


def xp_for_level(level: int) -> int:
    return 100 * (level + 1) + 50 * level * level


def progress_bar(current: int, total: int, length: int = 10) -> str:
    filled = int(length * current / total) if total > 0 else 0
    return "█" * filled + "░" * (length - filled)


# ── Jeux — persistance ─────────────────────────────────────────────────────────

def gk(guild_id: int, channel_id: int) -> str:
    return f"{guild_id}:{channel_id}"


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
            import json as _json
            _json.dump(data, f)
    except Exception as e:
        print(f"[GAMES] Erreur sauvegarde : {e}")


def load_games_for(guild_id: int) -> dict:
    import json as _json
    path = GAMES_DIR / f"{guild_id}.json"
    if path.exists():
        try:
            with open(path) as f:
                return _json.load(f)
        except Exception:
            pass
    return {}