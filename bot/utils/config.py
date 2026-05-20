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

from bot.core import CONFIG_DIR

# ═══════════════════════════════════════════════════════════════
#  CONFIGURATION
# ═══════════════════════════════════════════════════════════════

DEFAULT_CONFIG = {
    "role_recruteur":        "Recruteur",
    "role_staff":            ["Leader", "Officier"],
    "role_officier":         "Officier",
    "role_leader":           "Leader",
    "role_visiteur":         "visiteur",
    "role_vendeur":          "Vendeur Certifié",
    "role_staff_market":     "Staff Market",
    "role_acheteur_notif":   "Acheteur",
    "role_vendu":            "Vendu",
    "salon_logs":            "logs",
    "salon_roster":          "roster",
    "salon_bienvenue":       "bienvenue",
    "salon_catalogue":       "catalogue",
    "salon_commandes":       "commandes",
    "salon_notifications":   "notifications-market",
    "salon_role_toggle":     "roles",
    "salon_recherche":       "catalogue",
    "salon_ventes_log":      "logs-ventes",
    "salon_cmds_allowed":    ["bot-commands", "commandes"],
    "salon_objectifs":       "",
    "salon_gestion":         "",
    "salon_vendeur":         "",
    "categorie_tickets":     "Tickets",
    "categorie_commandes":   "Commandes",
    "alt_min_days":          30,
    "raid_window_secs":      60,
    "raid_threshold":        3,
    "spam_limit":            4,
    "spam_window":           6.0,
    "role_roster_leader":    "Leader",
    "role_roster_officier":  "Officier",
    "role_roster_confiance": "Membre de confiance",
    "role_roster_plus":      "Membre +",
    "role_roster_membre":    "Membre",
    "role_roster_recrue":    "Recrue",
    "roster_roles": [
        {"nom": "Leader",             "emoji": "👑"},
        {"nom": "Officier",           "emoji": "⚔️"},
        {"nom": "Membre de confiance","emoji": "🛡️"},
        {"nom": "Membre +",           "emoji": "⭐"},
        {"nom": "Membre",             "emoji": "🔹"},
        {"nom": "Recrue",             "emoji": "🌱"},
    ],
    "faction_roles":  ["Leader", "Officier", "Membre de confiance", "Membre +", "Membre", "Recrue"],
    "allowed_domains": ["tenor.com", "giphy.com"],
    "inviteRole5":           "",
    "inviteRole10":          "",
    "inviteRole20":          "",
    "inviteLogsChannel":     "",
    "role_giveaway_staff":   "",
    "salon_giveaway_logs":   "",
}


def load_config(guild_id: int) -> dict:
    path = CONFIG_DIR / f"{guild_id}.json"
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            merged = DEFAULT_CONFIG.copy()
            merged.update(data)
            return merged
        except Exception as e:
            print(f"[CONFIG] Erreur lecture {path} : {e}")
    save_config(guild_id, DEFAULT_CONFIG.copy())
    return DEFAULT_CONFIG.copy()


def save_config(guild_id: int, config: dict):
    path = CONFIG_DIR / f"{guild_id}.json"
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[CONFIG] Erreur sauvegarde {path} : {e}")

# ═══════════════════════════════════════════════════════════════
#  RÉSOLUTION SALONS / RÔLES / CATÉGORIES
# ═══════════════════════════════════════════════════════════════

def resolve_role(guild: discord.Guild, name_or_id) -> discord.Role | None:
    if not name_or_id:
        return None
    try:
        rid = int(name_or_id)
        r = guild.get_role(rid)
        if r:
            return r
    except (ValueError, TypeError):
        pass
    name_lower = str(name_or_id).lower()
    return discord.utils.find(lambda r: r.name.lower() == name_lower, guild.roles)


def resolve_roles(guild: discord.Guild, names) -> list[discord.Role]:
    if isinstance(names, (str, int)):
        names = [names]
    result = []
    for n in names:
        r = resolve_role(guild, n)
        if r:
            result.append(r)
    return result


def resolve_channel(guild: discord.Guild, name_or_id) -> discord.abc.GuildChannel | None:
    if not name_or_id:
        return None
    try:
        cid = int(name_or_id)
        ch = guild.get_channel(cid)
        if ch:
            return ch
    except (ValueError, TypeError):
        pass
    name_lower = str(name_or_id).lower()
    return discord.utils.find(lambda c: c.name.lower() == name_lower, guild.channels)


def resolve_channels(guild: discord.Guild, names) -> list[discord.abc.GuildChannel]:
    if isinstance(names, (str, int)):
        names = [names]
    result = []
    for n in names:
        c = resolve_channel(guild, n)
        if c:
            result.append(c)
    return result


def resolve_category(guild: discord.Guild, name_or_id) -> discord.CategoryChannel | None:
    if not name_or_id:
        return None
    try:
        cid = int(name_or_id)
        cat = guild.get_channel(cid)
        if isinstance(cat, discord.CategoryChannel):
            return cat
    except (ValueError, TypeError):
        pass
    name_lower = str(name_or_id).lower()
    return discord.utils.find(
        lambda c: isinstance(c, discord.CategoryChannel) and c.name.lower() == name_lower,
        guild.channels
    )


def cfg_role(guild, key):    return resolve_role(guild, load_config(guild.id).get(key))
def cfg_roles(guild, key):   return resolve_roles(guild, load_config(guild.id).get(key, []))
def cfg_channel(guild, key): return resolve_channel(guild, load_config(guild.id).get(key))
def cfg_channels(guild, key):return resolve_channels(guild, load_config(guild.id).get(key, []))
def cfg_category(guild, key):return resolve_category(guild, load_config(guild.id).get(key))
