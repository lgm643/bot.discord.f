"""
utils/emojis.py — Emojis custom du serveur, configurables via !emoji.

But : remplacer certains emojis unicode codés en dur (🏪, 🎉, 🛒…) par les
emojis custom de "La Mystic" quand le staff les configure, sans devoir
toucher à chaque embed du bot. Si aucun emoji custom n'est configuré pour
une clé, l'emoji unicode par défaut est utilisé — rien ne casse si tu ne
configures rien.

Clés disponibles (voir DEFAULT_EMOJIS) : market, giveaway, vendeur, ticket,
succes, erreur, argent, stock.
"""
import discord

from bot.utils.config import load_config, save_config

DEFAULT_EMOJIS = {
    "market":   "🏪",
    "giveaway": "🎉",
    "vendeur":  "🛒",
    "ticket":   "🎫",
    "succes":   "✅",
    "erreur":   "❌",
    "argent":   "💰",
    "stock":    "📦",
}


def get_emoji(guild: discord.Guild, key: str) -> str:
    """Retourne l'emoji custom configuré pour `key`, sinon le fallback unicode."""
    cfg    = load_config(guild.id)
    custom = cfg.get("emojis", {}) or {}
    return custom.get(key) or DEFAULT_EMOJIS.get(key, "🔹")


def set_emoji(guild: discord.Guild, key: str, emoji_str: str):
    if key not in DEFAULT_EMOJIS:
        raise ValueError(f"Clé inconnue : {key}")
    cfg = load_config(guild.id)
    custom = dict(cfg.get("emojis", {}) or {})
    custom[key] = emoji_str
    cfg["emojis"] = custom
    save_config(guild.id, cfg)


def reset_emoji(guild: discord.Guild, key: str):
    cfg = load_config(guild.id)
    custom = dict(cfg.get("emojis", {}) or {})
    custom.pop(key, None)
    cfg["emojis"] = custom
    save_config(guild.id, cfg)
