"""
commands/profil.py — Profil complet d'un membre.

!profil           → ton propre profil
!profil @membre   → profil d'un autre membre

Affiche :
  • Niveau, XP, barre de progression, rang au classement
  • Messages envoyés (total / aujourd'hui / cette semaine)
  • Temps vocal (total / aujourd'hui / cette semaine)
  • Rôle faction le plus élevé
  • Invitations actives sur le serveur
  • Giveaways gagnés (compte dans les fichiers sauvegardés)
  • Date d'arrivée sur le serveur
  • Stats hebdomadaires XP
"""
import time
from datetime import datetime, timezone
from pathlib import Path

import discord

from bot.core import bot, GIVEAWAYS_DIR
from bot.utils.helpers import (
    load_user_data, get_user, save_user_data,
    xp_for_level, progress_bar, fmt_voice, now_utc,
)
from bot.utils.config import load_config
from bot.utils.invite_stats import count_active_invitations
from bot.utils.stats import _ensure_daily_reset, _ensure_weekly_reset


# ── Helpers ───────────────────────────────────────────────────────────────────

def _count_giveaways_won(guild_id: int, user_id: int) -> int:
    """Compte les giveaways gagnés en scannant les fichiers JSON sauvegardés."""
    if not GIVEAWAYS_DIR.exists():
        return 0
    count = 0
    for path in GIVEAWAYS_DIR.glob("*.json"):
        try:
            import json
            with open(path, "r", encoding="utf-8") as f:
                gw = json.load(f)
            if gw.get("guild_id") != guild_id:
                continue
            # Support multi-gagnants (winner_ids) et ancien format (winner_id)
            winner_ids = gw.get("winner_ids") or (
                [gw["winner_id"]] if gw.get("winner_id") else []
            )
            if user_id in winner_ids:
                count += 1
        except Exception:
            pass
    return count


def _get_faction_role(member: discord.Member, cfg: dict) -> str | None:
    """Retourne l'emoji + nom du rôle faction le plus élevé du membre."""
    roster_entries = [
        ("role_roster_leader",    "👑 Leader"),
        ("role_roster_officier",  "⚔️ Officier"),
        ("role_roster_confiance", "🛡️ Membre de confiance"),
        ("role_roster_plus",      "⭐ Membre +"),
        ("role_roster_membre",    "🔹 Membre"),
        ("role_roster_recrue",    "🌱 Recrue"),
    ]
    for cfg_key, label in roster_entries:
        nom = cfg.get(cfg_key, "")
        if not nom:
            continue
        if any(r.name.lower() == nom.lower() for r in member.roles):
            return label
    # Fallback : faction_roles
    for nom in cfg.get("faction_roles", []):
        if any(r.name.lower() == nom.lower() for r in member.roles):
            return nom
    return None


def _get_rank(guild_id: int, user_id: int) -> tuple[int, int]:
    """Retourne (rang, total_membres) dans le classement XP du serveur."""
    data    = load_user_data(guild_id)
    sorted_ = sorted(
        data.items(),
        key=lambda x: (x[1].get("level", 0), x[1].get("xp", 0)),
        reverse=True,
    )
    for i, (uid, _) in enumerate(sorted_, 1):
        if int(uid) == user_id:
            return i, len(sorted_)
    return len(sorted_) + 1, len(sorted_)


# ── Commande ──────────────────────────────────────────────────────────────────

@bot.hybrid_command(name="profil", aliases=["profile", "p"])
async def profil_cmd(ctx, member: discord.Member = None):
    member = member or ctx.author
    guild  = ctx.guild
    cfg    = load_config(guild.id)

    # ── Charger les données XP ────────────────────────────────────────────────
    data = load_user_data(guild.id)
    u    = get_user(data, member.id)
    save_user_data(guild.id, data)

    _ensure_daily_reset(u)
    _ensure_weekly_reset(u)

    now_ts   = time.time()
    lvl      = u.get("level", 0)
    cur_xp   = u.get("xp", 0)
    required = xp_for_level(lvl + 1)
    bar      = progress_bar(cur_xp, required, length=12)
    pct      = int(cur_xp / required * 100) if required > 0 else 0

    # Temps vocal en live (si actuellement en vocal)
    voice_total = u.get("voice_time", 0.0)
    if u.get("voice_join"):
        voice_total += now_ts - u["voice_join"]

    voice_daily  = u.get("daily_voice_seconds", 0.0)
    voice_weekly = u.get("weekly_voice_seconds", 0.0)
    msg_total    = u.get("message_count", 0)
    msg_daily    = u.get("daily_messages", 0)
    msg_weekly   = u.get("weekly_messages", 0)
    xp_daily     = u.get("daily_xp", 0)
    xp_weekly    = u.get("weekly_xp", 0)

    # ── Stats externes ────────────────────────────────────────────────────────
    rang, total_membres = _get_rank(guild.id, member.id)

    try:
        invites_actives = count_active_invitations(guild, member.id)
    except Exception:
        invites_actives = 0

    giveaways_gagnes = _count_giveaways_won(guild.id, member.id)

    faction_role = _get_faction_role(member, cfg) or "*Aucun rôle faction*"

    # ── Date d'arrivée ────────────────────────────────────────────────────────
    joined = member.joined_at
    joined_str = discord.utils.format_dt(joined, style="D") if joined else "Inconnue"
    joined_rel = discord.utils.format_dt(joined, style="R") if joined else ""

    # ── Construction de l'embed ───────────────────────────────────────────────
    color = member.color if member.color != discord.Color.default() else 0x9B59B6

    embed = discord.Embed(
        title=f"👤 Profil — {member.display_name}",
        color=color,
        timestamp=now_utc(),
    )
    embed.set_thumbnail(url=member.display_avatar.url)

    # Rang & niveau
    embed.add_field(
        name="🏆 Niveau & Rang",
        value=(
            f"Niveau **{lvl}** · Rang **#{rang}** / {total_membres}\n"
            f"`{bar}` **{pct}%**\n"
            f"{cur_xp} / {required} XP"
        ),
        inline=False,
    )

    # Messages
    embed.add_field(
        name="✉️ Messages",
        value=(
            f"Total : **{msg_total}**\n"
            f"Aujourd'hui : **{msg_daily}**\n"
            f"Cette semaine : **{msg_weekly}**"
        ),
        inline=True,
    )

    # Vocal
    embed.add_field(
        name="🎤 Temps vocal",
        value=(
            f"Total : **{fmt_voice(voice_total)}**\n"
            f"Aujourd'hui : **{fmt_voice(voice_daily)}**\n"
            f"Cette semaine : **{fmt_voice(voice_weekly)}**"
        ),
        inline=True,
    )

    # XP hebdo
    embed.add_field(
        name="⭐ XP gagnée",
        value=(
            f"Aujourd'hui : **{xp_daily}**\n"
            f"Cette semaine : **{xp_weekly}**"
        ),
        inline=True,
    )

    # Faction + invitations + giveaways
    embed.add_field(
        name="⚔️ Faction",
        value=faction_role,
        inline=True,
    )
    embed.add_field(
        name="📨 Invitations actives",
        value=f"**{invites_actives}** membre(s)",
        inline=True,
    )
    embed.add_field(
        name="🎉 Giveaways gagnés",
        value=f"**{giveaways_gagnes}**",
        inline=True,
    )

    # Arrivée
    embed.add_field(
        name="📅 Arrivée sur le serveur",
        value=f"{joined_str} ({joined_rel})",
        inline=False,
    )

    embed.set_footer(
        text=f"ID : {member.id}",
        icon_url=guild.icon.url if guild.icon else discord.Embed.Empty,
    )

    await ctx.send(embed=embed)
