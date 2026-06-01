import asyncio
import os
import json
import time
import random
import sqlite3
from collections import defaultdict
from pathlib import Path

import discord
from bot.core import DB_PATH

def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS objectifs (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                texte    TEXT    NOT NULL,
                done     INTEGER NOT NULL DEFAULT 0,
                created  REAL    NOT NULL
            );
            CREATE TABLE IF NOT EXISTS objectif_embeds (
                guild_id   INTEGER PRIMARY KEY,
                channel_id INTEGER,
                msg_id     INTEGER
            );
            CREATE TABLE IF NOT EXISTS invitations (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id     INTEGER NOT NULL,
                inviter_id   INTEGER NOT NULL,
                invited_id   INTEGER NOT NULL,
                invited_name TEXT    NOT NULL DEFAULT '',
                joined_at    REAL    NOT NULL
            );
            CREATE TABLE IF NOT EXISTS invite_reward_state (
                guild_id INTEGER NOT NULL,
                user_id  INTEGER NOT NULL,
                tier     INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (guild_id, user_id)
            );
            CREATE TABLE IF NOT EXISTS mutes (
                guild_id   INTEGER NOT NULL,
                user_id    INTEGER NOT NULL,
                expires_at REAL,
                reason     TEXT NOT NULL DEFAULT 'Aucune raison fournie',
                PRIMARY KEY (guild_id, user_id)
            );
        """)
        # Migration : ajoute invited_name si la table existait sans cette colonne
        try:
            conn.execute("ALTER TABLE invitations ADD COLUMN invited_name TEXT NOT NULL DEFAULT ''")
            print("[DB] Migration : colonne invited_name ajoutée à la table invitations")
        except Exception:
            pass  # La colonne existe déjà, c'est normal

# ═══════════════════════════════════════════════════════════════
#  OBJECTIFS — SQLITE
# ═══════════════════════════════════════════════════════════════

def db_get_objectifs(guild_id: int):
    with get_db() as conn:
        return conn.execute("SELECT * FROM objectifs WHERE guild_id=? ORDER BY id", (guild_id,)).fetchall()

def db_add_objectif(guild_id: int, texte: str) -> int:
    with get_db() as conn:
        cur = conn.execute("INSERT INTO objectifs (guild_id, texte, done, created) VALUES (?,?,0,?)", (guild_id, texte, time.time()))
        return cur.lastrowid

def db_del_objectif(guild_id: int, obj_id: int) -> bool:
    with get_db() as conn:
        cur = conn.execute("DELETE FROM objectifs WHERE id=? AND guild_id=?", (obj_id, guild_id))
        return cur.rowcount > 0

def db_done_objectif(guild_id: int, obj_id: int) -> bool:
    with get_db() as conn:
        cur = conn.execute("UPDATE objectifs SET done=1 WHERE id=? AND guild_id=?", (obj_id, guild_id))
        return cur.rowcount > 0

def db_get_objectif_embed(guild_id: int):
    with get_db() as conn:
        return conn.execute("SELECT * FROM objectif_embeds WHERE guild_id=?", (guild_id,)).fetchone()

def db_save_objectif_embed(guild_id: int, channel_id: int, msg_id: int):
    with get_db() as conn:
        conn.execute("INSERT OR REPLACE INTO objectif_embeds (guild_id, channel_id, msg_id) VALUES (?,?,?)", (guild_id, channel_id, msg_id))

# ═══════════════════════════════════════════════════════════════
#  MUTES — SQLITE
# ═══════════════════════════════════════════════════════════════

def db_save_mute(guild_id: int, user_id: int, expires_at: float | None, reason: str):
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO mutes (guild_id, user_id, expires_at, reason) VALUES (?,?,?,?)",
            (guild_id, user_id, expires_at, reason)
        )

def db_delete_mute(guild_id: int, user_id: int):
    with get_db() as conn:
        conn.execute("DELETE FROM mutes WHERE guild_id=? AND user_id=?", (guild_id, user_id))

def db_get_mutes(guild_id: int):
    with get_db() as conn:
        return conn.execute("SELECT * FROM mutes WHERE guild_id=?", (guild_id,)).fetchall()