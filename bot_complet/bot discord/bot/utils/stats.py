"""
utils/stats.py — Statistiques serveur en temps réel et hebdomadaires.

Stockage dans user_data par membre :
  weekly_messages      : int   (reset chaque lundi)
  weekly_voice_seconds : float (reset chaque lundi)
  weekly_xp            : int   (reset chaque lundi)
  daily_messages       : int   (reset chaque jour à minuit UTC)
  daily_xp             : int   (idem)
  daily_voice_seconds  : float (idem)
  last_day_reset       : str   "YYYY-MM-DD"  (date du dernier reset journalier)
  last_week_reset      : str   "YYYY-Wxx"    (semaine ISO du dernier reset)
  weekly_sales         : int   (ventes confirmées dans la semaine)
"""
import time
from datetime import datetime, timezone, timedelta

import discord

from bot.utils.helpers import (
    load_user_data, save_user_data, get_user,
    fmt_voice, now_utc,
)
from bot.utils.invite_stats import get_top_inviters_active


# ── Helpers date ──────────────────────────────────────────────────────────────

def _today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")

def _week_str() -> str:
    d = datetime.now(timezone.utc)
    return f"{d.isocalendar()[0]}-W{d.isocalendar()[1]:02d}"

def _ensure_daily_reset(u: dict):
    today = _today_str()
    if u.get("last_day_reset") != today:
        u["daily_messages"]       = 0
        u["daily_xp"]             = 0
        u["daily_voice_seconds"]  = 0.0
        u["last_day_reset"]       = today

def _ensure_weekly_reset(u: dict):
    week = _week_str()
    if u.get("last_week_reset") != week:
        u["weekly_messages"]       = 0
        u["weekly_voice_seconds"]  = 0.0
        u["weekly_xp"]             = 0
        u["weekly_sales"]          = 0
        u["last_week_reset"]       = week


# ── Mise à jour depuis les événements ─────────────────────────────────────────

def record_message(guild_id: int, user_id: int, xp_gained: int = 0):
    """Appelé après chaque message xp (avec le XP effectivement attribué)."""
    data = load_user_data(guild_id)
    u    = get_user(data, user_id)
    _ensure_daily_reset(u)
    _ensure_weekly_reset(u)
    u["daily_messages"]  = u.get("daily_messages", 0) + 1
    u["weekly_messages"] = u.get("weekly_messages", 0) + 1
    if xp_gained:
        u["daily_xp"]  = u.get("daily_xp", 0) + xp_gained
        u["weekly_xp"] = u.get("weekly_xp", 0) + xp_gained
    save_user_data(guild_id, data)


def record_voice_end(guild_id: int, user_id: int, duration_seconds: float):
    """Appelé à la déconnexion vocale avec la durée de la session."""
    data = load_user_data(guild_id)
    u    = get_user(data, user_id)
    _ensure_daily_reset(u)
    _ensure_weekly_reset(u)
    u["daily_voice_seconds"]  = u.get("daily_voice_seconds", 0.0)  + duration_seconds
    u["weekly_voice_seconds"] = u.get("weekly_voice_seconds", 0.0) + duration_seconds
    save_user_data(guild_id, data)


def record_sale(guild_id: int, user_id: int, qty: int = 1):
    """Appelé lors d'une vente confirmée (!vendu)."""
    data = load_user_data(guild_id)
    u    = get_user(data, user_id)
    _ensure_weekly_reset(u)
    u["weekly_sales"] = u.get("weekly_sales", 0) + qty
    save_user_data(guild_id, data)


# ── Calcul des stats serveur ──────────────────────────────────────────────────

def _live_voice_seconds(u: dict, now: float) -> float:
    """Temps vocal total incluant la session en cours si connecté."""
    base = u.get("voice_time", 0.0)
    if u.get("voice_join"):
        base += now - u["voice_join"]
    return base


def compute_server_stats(guild: discord.Guild) -> dict:
    """Agrège toutes les stats du serveur en un dict."""
    data = load_user_data(guild.id)
    now  = time.time()

    # Membres
    total    = guild.member_count
    online   = sum(1 for m in guild.members if m.status != discord.Status.offline and not m.bot)
    today    = _today_str()
    week_str = _week_str()

    joined_today = 0
    joined_week  = 0
    week_start_ts = _week_start_timestamp()
    day_start_ts  = _day_start_timestamp()

    for m in guild.members:
        if m.bot or not m.joined_at:
            continue
        jts = m.joined_at.timestamp()
        if jts >= day_start_ts:
            joined_today += 1
        if jts >= week_start_ts:
            joined_week  += 1

    # Agrégats messages / vocal / XP
    daily_msgs   = 0
    weekly_msgs  = 0
    monthly_msgs = 0   # approx : 4× weekly
    daily_voice  = 0.0
    weekly_voice = 0.0
    monthly_voice = 0.0

    top_daily_msg  : tuple[int, int]   = (0, 0)   # (uid, count)
    top_daily_xp   : tuple[int, int]   = (0, 0)
    top_daily_voice: tuple[int, float] = (0, 0.0)

    for uid_str, u in data.items():
        _ensure_daily_reset(u)
        _ensure_weekly_reset(u)

        dm  = u.get("daily_messages", 0)
        wm  = u.get("weekly_messages", 0)
        dv  = u.get("daily_voice_seconds", 0.0)
        wv  = u.get("weekly_voice_seconds", 0.0)
        dxp = u.get("daily_xp", 0)

        daily_msgs   += dm
        weekly_msgs  += wm
        monthly_msgs += wm   # approx
        daily_voice  += dv
        weekly_voice += wv
        monthly_voice += wv  # approx

        uid = int(uid_str)
        if dm > top_daily_msg[1]:
            top_daily_msg = (uid, dm)
        if dxp > top_daily_xp[1]:
            top_daily_xp = (uid, dxp)
        if dv > top_daily_voice[1]:
            top_daily_voice = (uid, dv)

    # Résolution membres
    def _name(uid: int) -> str:
        m = guild.get_member(uid)
        return m.mention if m else f"<@{uid}>"

    return {
        "total_members":   total,
        "online_members":  online,
        "joined_today":    joined_today,
        "joined_week":     joined_week,
        "daily_msgs":      daily_msgs,
        "weekly_msgs":     weekly_msgs,
        "monthly_msgs":    monthly_msgs * 4,
        "daily_voice":     daily_voice,
        "weekly_voice":    weekly_voice,
        "monthly_voice":   monthly_voice * 4,
        "top_daily_msg":   (_name(top_daily_msg[0]),   top_daily_msg[1])   if top_daily_msg[0]   else ("—", 0),
        "top_daily_xp":    (_name(top_daily_xp[0]),    top_daily_xp[1])    if top_daily_xp[0]    else ("—", 0),
        "top_daily_voice": (_name(top_daily_voice[0]), top_daily_voice[1]) if top_daily_voice[0] else ("—", 0.0),
    }


def _day_start_timestamp() -> float:
    d = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    return d.timestamp()

def _week_start_timestamp() -> float:
    d = datetime.now(timezone.utc)
    monday = d - timedelta(days=d.weekday())
    monday = monday.replace(hour=0, minute=0, second=0, microsecond=0)
    return monday.timestamp()


# ── Classement hebdomadaire ───────────────────────────────────────────────────

def compute_weekly_rankings(guild: discord.Guild) -> dict:
    """Calcule les tops hebdo pour l'envoi du lundi."""
    data = load_user_data(guild.id)
    medals = ["🥇", "🥈", "🥉"]

    def top10(key: str, fmt_fn) -> str:
        rows = sorted(
            [(int(uid), u.get(key, 0)) for uid, u in data.items() if u.get(key, 0) > 0],
            key=lambda x: x[1], reverse=True
        )[:10]
        if not rows:
            return "_Aucun résultat cette semaine_"
        lines = []
        for i, (uid, val) in enumerate(rows):
            m    = guild.get_member(uid)
            name = m.display_name if m else f"<@{uid}>"
            rank = medals[i] if i < 3 else f"`#{i+1}`"
            lines.append(f"{rank} **{name}** — {fmt_fn(val)}")
        return "\n".join(lines)

    # Top invitations actives
    inv_rows = get_top_inviters_active(guild, limit=10)
    if inv_rows:
        inv_lines = []
        for i, (uid, count) in enumerate(inv_rows):
            m    = guild.get_member(uid)
            name = m.display_name if m else f"<@{uid}>"
            rank = medals[i] if i < 3 else f"`#{i+1}`"
            inv_lines.append(f"{rank} **{name}** — {count} invitation(s)")
        top_invites = "\n".join(inv_lines)
    else:
        top_invites = "_Aucun résultat cette semaine_"

    return {
        "top_messages": top10("weekly_messages", lambda v: f"{v} message(s)"),
        "top_vocal":    top10("weekly_voice_seconds", lambda v: fmt_voice(v)),
        "top_xp":       top10("weekly_xp", lambda v: f"{v} XP"),
        "top_invites":  top_invites,
        "top_ventes":   top10("weekly_sales", lambda v: f"{v} vente(s)"),
    }


# ── Membre de la semaine ──────────────────────────────────────────────────────

def compute_motd_messages(guild: discord.Guild, cfg: dict) -> int | None:
    """Membre de la semaine catégorie Messages — celui qui a envoyé le plus de messages."""
    if not cfg.get("motd_enabled", True):
        return None
    data = load_user_data(guild.id)
    best_uid, best_val = None, 0
    for uid_str, u in data.items():
        uid = int(uid_str)
        m   = guild.get_member(uid)
        if not m or m.bot:
            continue
        val = u.get("weekly_messages", 0)
        if val > best_val:
            best_val = val
            best_uid = uid
    return best_uid


def compute_motd_vocal(guild: discord.Guild, cfg: dict) -> int | None:
    """Membre de la semaine catégorie Vocal — celui qui a passé le plus de temps en vocal."""
    if not cfg.get("motd_enabled", True):
        return None
    data = load_user_data(guild.id)
    best_uid, best_val = None, 0.0
    for uid_str, u in data.items():
        uid = int(uid_str)
        m   = guild.get_member(uid)
        if not m or m.bot:
            continue
        val = u.get("weekly_voice_seconds", 0.0)
        if val > best_val:
            best_val = val
            best_uid = uid
    return best_uid


# ── Reset hebdomadaire ────────────────────────────────────────────────────────

def reset_weekly_stats(guild_id: int):
    """Remet à zéro toutes les stats weekly_* pour tous les membres."""
    data     = load_user_data(guild_id)
    week_str = _week_str()
    for u in data.values():
        u["weekly_messages"]       = 0
        u["weekly_voice_seconds"]  = 0.0
        u["weekly_xp"]             = 0
        u["weekly_sales"]          = 0
        u["last_week_reset"]       = week_str
    save_user_data(guild_id, data)
    print(f"[WEEKLY] Stats hebdo réinitialisées pour guild={guild_id}")
