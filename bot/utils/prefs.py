"""
utils/prefs.py — Préférences utilisateur (DM opt-in, mode d'embed compact/full).

Cache mémoire simple par (guild_id, user_id) pour éviter une requête SQLite
à chaque affichage d'embed personnel. Pas de TTL : invalidé à chaque écriture.
"""
from bot.utils.database import db_get_user_prefs, db_set_user_pref

_prefs_cache: dict[tuple[int, int], dict] = {}


def get_prefs(guild_id: int, user_id: int) -> dict:
    key = (guild_id, user_id)
    if key not in _prefs_cache:
        _prefs_cache[key] = db_get_user_prefs(guild_id, user_id)
    return _prefs_cache[key]


def set_pref(guild_id: int, user_id: int, **kwargs):
    db_set_user_pref(guild_id, user_id, **kwargs)
    _prefs_cache.pop((guild_id, user_id), None)


def wants_dm_giveaway(guild_id: int, user_id: int) -> bool:
    return get_prefs(guild_id, user_id).get("dm_giveaway", True)


def wants_dm_candidature(guild_id: int, user_id: int) -> bool:
    return get_prefs(guild_id, user_id).get("dm_candidature", True)


def get_embed_mode(guild_id: int, user_id: int) -> str:
    return get_prefs(guild_id, user_id).get("embed_mode", "full")


def is_compact(guild_id: int, user_id: int) -> bool:
    return get_embed_mode(guild_id, user_id) == "compact"
