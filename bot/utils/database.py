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
            CREATE TABLE IF NOT EXISTS user_prefs (
                guild_id       INTEGER NOT NULL,
                user_id        INTEGER NOT NULL,
                dm_giveaway    INTEGER NOT NULL DEFAULT 1,
                dm_candidature INTEGER NOT NULL DEFAULT 1,
                embed_mode     TEXT    NOT NULL DEFAULT 'full',
                PRIMARY KEY (guild_id, user_id)
            );
            CREATE TABLE IF NOT EXISTS ticket_meta (
                channel_id     INTEGER PRIMARY KEY,
                guild_id       INTEGER NOT NULL,
                type_ticket    TEXT    NOT NULL,
                creator_id     INTEGER NOT NULL,
                created_at     REAL    NOT NULL,
                last_relance_at REAL   NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS indispos (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id         INTEGER NOT NULL,
                user_id          INTEGER NOT NULL,
                date_debut_txt   TEXT    NOT NULL,
                date_fin_txt     TEXT    NOT NULL,
                date_fin_ts      REAL,
                raison           TEXT    NOT NULL DEFAULT '',
                partielle        TEXT    NOT NULL DEFAULT 'non',
                presence_discord TEXT    NOT NULL DEFAULT 'non',
                created_at       REAL    NOT NULL,
                UNIQUE(guild_id, user_id)
            );
            CREATE TABLE IF NOT EXISTS indispo_embed (
                guild_id   INTEGER PRIMARY KEY,
                channel_id INTEGER,
                msg_id     INTEGER
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


# ═══════════════════════════════════════════════════════════════
#  PRÉFÉRENCES UTILISATEUR — SQLITE
#  (notifs DM opt-in, mode d'affichage des embeds)
# ═══════════════════════════════════════════════════════════════

def db_get_user_prefs(guild_id: int, user_id: int) -> dict:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM user_prefs WHERE guild_id=? AND user_id=?",
            (guild_id, user_id)
        ).fetchone()
    if row:
        return {
            "dm_giveaway":    bool(row["dm_giveaway"]),
            "dm_candidature": bool(row["dm_candidature"]),
            "embed_mode":     row["embed_mode"],
        }
    return {"dm_giveaway": True, "dm_candidature": True, "embed_mode": "full"}


def db_set_user_pref(guild_id: int, user_id: int, **kwargs):
    """Met à jour une ou plusieurs préférences (dm_giveaway=, dm_candidature=, embed_mode=)."""
    current = db_get_user_prefs(guild_id, user_id)
    current.update(kwargs)
    with get_db() as conn:
        conn.execute(
            """INSERT INTO user_prefs (guild_id, user_id, dm_giveaway, dm_candidature, embed_mode)
                   VALUES (?,?,?,?,?)
                   ON CONFLICT(guild_id, user_id) DO UPDATE SET
                       dm_giveaway=excluded.dm_giveaway,
                       dm_candidature=excluded.dm_candidature,
                       embed_mode=excluded.embed_mode""",
            (guild_id, user_id, int(current["dm_giveaway"]), int(current["dm_candidature"]), current["embed_mode"])
        )


# ═══════════════════════════════════════════════════════════════
#  TICKET META — SQLITE
#  (tracking pour la relance auto des tickets recrutement sans reponse)
# ═══════════════════════════════════════════════════════════════

def db_save_ticket_meta(channel_id: int, guild_id: int, type_ticket: str, creator_id: int, created_at: float):
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO ticket_meta (channel_id, guild_id, type_ticket, creator_id, created_at, last_relance_at) VALUES (?,?,?,?,?,0)",
            (channel_id, guild_id, type_ticket, creator_id, created_at)
        )


def db_get_open_tickets(guild_id: int, type_ticket: str | None = None) -> list:
    with get_db() as conn:
        if type_ticket:
            return conn.execute(
                "SELECT * FROM ticket_meta WHERE guild_id=? AND type_ticket=?",
                (guild_id, type_ticket)
            ).fetchall()
        return conn.execute("SELECT * FROM ticket_meta WHERE guild_id=?", (guild_id,)).fetchall()


def db_update_ticket_relance(channel_id: int, ts: float):
    with get_db() as conn:
        conn.execute("UPDATE ticket_meta SET last_relance_at=? WHERE channel_id=?", (ts, channel_id))


def db_delete_ticket_meta(channel_id: int):
    with get_db() as conn:
        conn.execute("DELETE FROM ticket_meta WHERE channel_id=?", (channel_id,))


# ═══════════════════════════════════════════════════════════════
#  INDISPONIBILITÉS
# ═══════════════════════════════════════════════════════════════

def db_save_indispo(guild_id: int, user_id: int, date_debut_txt: str, date_fin_txt: str,
                     date_fin_ts, raison: str, partielle: str, presence_discord: str):
    with get_db() as conn:
        conn.execute(
            """INSERT INTO indispos
                   (guild_id, user_id, date_debut_txt, date_fin_txt, date_fin_ts, raison, partielle, presence_discord, created_at)
               VALUES (?,?,?,?,?,?,?,?,?)
               ON CONFLICT(guild_id, user_id) DO UPDATE SET
                   date_debut_txt=excluded.date_debut_txt,
                   date_fin_txt=excluded.date_fin_txt,
                   date_fin_ts=excluded.date_fin_ts,
                   raison=excluded.raison,
                   partielle=excluded.partielle,
                   presence_discord=excluded.presence_discord,
                   created_at=excluded.created_at""",
            (guild_id, user_id, date_debut_txt, date_fin_txt, date_fin_ts, raison, partielle, presence_discord, time.time()),
        )


def db_get_indispos(guild_id: int):
    with get_db() as conn:
        return conn.execute("SELECT * FROM indispos WHERE guild_id=? ORDER BY created_at", (guild_id,)).fetchall()


def db_get_indispo(guild_id: int, user_id: int):
    with get_db() as conn:
        return conn.execute("SELECT * FROM indispos WHERE guild_id=? AND user_id=?", (guild_id, user_id)).fetchone()


def db_delete_indispo(guild_id: int, user_id: int) -> bool:
    with get_db() as conn:
        cur = conn.execute("DELETE FROM indispos WHERE guild_id=? AND user_id=?", (guild_id, user_id))
        return cur.rowcount > 0


def db_get_expired_indispos(guild_id: int, now_ts: float):
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM indispos WHERE guild_id=? AND date_fin_ts IS NOT NULL AND date_fin_ts <= ?",
            (guild_id, now_ts),
        ).fetchall()


def db_get_indispo_embed(guild_id: int):
    with get_db() as conn:
        return conn.execute("SELECT * FROM indispo_embed WHERE guild_id=?", (guild_id,)).fetchone()


def db_save_indispo_embed(guild_id: int, channel_id: int, msg_id: int):
    with get_db() as conn:
        conn.execute(
            "INSERT INTO indispo_embed (guild_id, channel_id, msg_id) VALUES (?,?,?) "
            "ON CONFLICT(guild_id) DO UPDATE SET channel_id=excluded.channel_id, msg_id=excluded.msg_id",
            (guild_id, channel_id, msg_id),
        )