"""
utils/config.py — Configuration par guild avec cache en mémoire TTL 30s.

AJOUTS v2 :
  - Nouvelles clés pour le système d'inactivité vocale dans DEFAULT_CONFIG.
  - Nouveau groupe "🎙️ Inactivité Vocale" dans CONFIG_GROUPS (config_panel.py).
"""
import json
import time
from pathlib import Path

import discord

from bot.core import (
    CONFIG_DIR,
    _config_cache, _config_cache_ts, CONFIG_CACHE_TTL,
    invalidate_config_cache,
)

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
    "spam_limit":            5,
    "spam_window":           6.0,
    "spam_action":           "warn",
    "role_roster_leader":    "Leader",
    "role_roster_officier":  "Officier",
    "role_roster_confiance": "Membre de confiance",
    "role_roster_plus":      "Membre +",
    "role_roster_membre":    "Membre",
    "role_roster_recrue":    "Recrue",
    "roster_roles": [
        {"nom": "Leader",              "emoji": "👑"},
        {"nom": "Officier",            "emoji": "⚔️"},
        {"nom": "Membre de confiance", "emoji": "🛡️"},
        {"nom": "Membre +",            "emoji": "⭐"},
        {"nom": "Membre",              "emoji": "🔹"},
        {"nom": "Recrue",              "emoji": "🌱"},
    ],
    "faction_roles":   ["Leader", "Officier", "Membre de confiance", "Membre +", "Membre", "Recrue"],
    "allowed_domains": ["tenor.com", "giphy.com"],
    "inviteRole5":           "",
    "inviteRole10":          "",
    "inviteRole20":          "",
    "inviteLogsChannel":     "",
    "salon_avantages":       "",
    "role_giveaway_staff":   "",
    "role_giveaway_notif":   "",
    "salon_giveaway_logs":   "",
    # ── Stats & Hebdo ──────────────────────────────────────────────────────────
    "salon_hebdo":       "",
    "motd_enabled":      True,
    "role_motd_msg":     "",
    "role_motd_vocal":   "",
    # ── Inactivité vocale ──────────────────────────────────────────────────────
    "salon_logs_messages":               "",
    "salon_logs_membres":                "",
    "salon_logs_vocal":                  "",
    "salon_logs_serveur":                "",
    "salon_logs_securite":               "",
    "salon_logs_debug":                  "",
    "debug_enabled":                     False,
    "vocal_inactivity_enabled":          False,
    "vocal_inactivity_delay":            15,     # Délai en minutes avant expulsion
    "vocal_inactivity_exempt_channels":  [],     # Salons vocaux exclus (IDs ou noms)
    "vocal_inactivity_exempt_roles":     [],     # Rôles exclus (IDs ou noms)
    "vocal_inactivity_exempt_users":     [],     # Membres exclus (IDs)
    "salon_logs_vocal_inactivity":       "",     # Salon logs dédié (vide = salon_logs)
    # ── Emojis custom ────────────────────────────────────────────────────────
    "emojis": {},          # ex: {"market": "<:boutique:123>", "giveaway": "<:cadeau:456>"}
    # ── Tickets ─────────────────────────────────────────────────────────────
    "tickets_mode":          "channels",   # "channels" ou "threads"
    "salon_tickets_parent":  "",           # salon texte parent pour les threads privés
    "relance_ticket_heures": 2,            # délai (h) avant proposition de relance recruteur
}


def load_config(guild_id: int) -> dict:
    """Lit depuis le cache mémoire (TTL 30s) ; sinon charge le fichier JSON."""
    now = time.monotonic()
    if guild_id in _config_cache and now - _config_cache_ts.get(guild_id, 0) < CONFIG_CACHE_TTL:
        return _config_cache[guild_id]
    path = CONFIG_DIR / f"{guild_id}.json"
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            merged = DEFAULT_CONFIG.copy()
            merged.update(data)
            _config_cache[guild_id]    = merged
            _config_cache_ts[guild_id] = now
            return merged
        except Exception as e:
            print(f"[CONFIG] Erreur lecture {path} : {e}")
    cfg = DEFAULT_CONFIG.copy()
    save_config(guild_id, cfg)
    _config_cache[guild_id]    = cfg
    _config_cache_ts[guild_id] = now
    return cfg


def save_config(guild_id: int, config: dict):
    """Sauvegarde sur disque et invalide le cache."""
    path = CONFIG_DIR / f"{guild_id}.json"
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        invalidate_config_cache(guild_id)
    except Exception as e:
        print(f"[CONFIG] Erreur sauvegarde {path} : {e}")


# ── Résolution salons / rôles / catégories ─────────────────────────────────────
def resolve_role(guild: discord.Guild, name_or_id) -> discord.Role | None:
    if not name_or_id:
        return None
    try:
        r = guild.get_role(int(name_or_id))
        if r:
            return r
    except (ValueError, TypeError):
        pass
    name_lower = str(name_or_id).lower()
    return discord.utils.find(lambda r: r.name.lower() == name_lower, guild.roles)


def resolve_roles(guild: discord.Guild, names) -> list[discord.Role]:
    if isinstance(names, (str, int)):
        names = [names]
    return [r for n in names if (r := resolve_role(guild, n))]


def resolve_channel(guild: discord.Guild, name_or_id) -> discord.abc.GuildChannel | None:
    if not name_or_id:
        return None
    try:
        ch = guild.get_channel(int(name_or_id))
        if ch:
            return ch
    except (ValueError, TypeError):
        pass
    name_lower = str(name_or_id).lower()
    return discord.utils.find(lambda c: c.name.lower() == name_lower, guild.channels)


def resolve_channels(guild: discord.Guild, names) -> list[discord.abc.GuildChannel]:
    if isinstance(names, (str, int)):
        names = [names]
    return [c for n in names if (c := resolve_channel(guild, n))]


def resolve_category(guild: discord.Guild, name_or_id) -> discord.CategoryChannel | None:
    if not name_or_id:
        return None
    try:
        cat = guild.get_channel(int(name_or_id))
        if isinstance(cat, discord.CategoryChannel):
            return cat
    except (ValueError, TypeError):
        pass
    name_lower = str(name_or_id).lower()
    return discord.utils.find(
        lambda c: isinstance(c, discord.CategoryChannel) and c.name.lower() == name_lower,
        guild.channels
    )


def cfg_role(guild, key):     return resolve_role(guild, load_config(guild.id).get(key))
def cfg_roles(guild, key):    return resolve_roles(guild, load_config(guild.id).get(key, []))
def cfg_channel(guild, key):  return resolve_channel(guild, load_config(guild.id).get(key))
def cfg_channels(guild, key): return resolve_channels(guild, load_config(guild.id).get(key, []))
def cfg_category(guild, key): return resolve_category(guild, load_config(guild.id).get(key))