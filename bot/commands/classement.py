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

from bot.core import bot
from bot.utils.helpers import load_user_data, now_utc, fmt_voice  # FIX : fmt_voice ajouté
from bot.utils.config import load_config

@bot.hybrid_command(name="classement", aliases=["top", "leaderboard", "lb", "rang", "ranking"])
async def classement_cmd(ctx):
    gid    = ctx.guild.id
    data   = load_user_data(gid)
    guild  = ctx.guild
    now    = time.time()
    medals = ["🥇", "🥈", "🥉"]
    cfg    = load_config(gid)

    for uid_str, u in data.items():
        u["_voice_live"] = u["voice_time"] + (now - u["voice_join"]) if u.get("voice_join") else u["voice_time"]

    def top10_field(key, fmt):
        items = sorted(
            [(uid, u) for uid, u in data.items() if u.get(key, 0) > 0],
            key=lambda x: x[1].get(key, 0), reverse=True
        )[:10]
        if not items: return "_Aucun joueur_"
        lines = []
        for i, (uid, u) in enumerate(items):
            m    = guild.get_member(int(uid))
            name = m.display_name if m else "Inconnu"
            rank = medals[i] if i < 3 else f"`#{i+1}`"
            lines.append(f"{rank} **{name}** — {fmt(u)}")
        return "\n".join(lines)

    # ── Top Niveau global ──────────────────────────────────────────────────
    items_lvl = sorted(
        data.items(),
        key=lambda x: (x[1].get("level", 0), x[1].get("xp", 0)),
        reverse=True
    )[:10]
    top_lvl_lines = []
    for i, (uid, u) in enumerate(items_lvl):
        m    = guild.get_member(int(uid))
        name = m.display_name if m else "Inconnu"
        rank = medals[i] if i < 3 else f"`#{i+1}`"
        top_lvl_lines.append(f"{rank} **{name}** — Niv. {u.get('level', 0)} ({u.get('xp', 0)} XP)")
    top_lvl = "\n".join(top_lvl_lines) or "_Aucun joueur_"

    # ── Top Faction ────────────────────────────────────────────────────────
    roster_entries = [
        ("role_roster_leader",    "👑"),
        ("role_roster_officier",  "⚔️"),
        ("role_roster_confiance", "🛡️"),
        ("role_roster_plus",      "⭐"),
        ("role_roster_membre",    "🔹"),
        ("role_roster_recrue",    "🌱"),
    ]
    roster_role_map = {}
    for cfg_key, emoji in roster_entries:
        nom = cfg.get(cfg_key, "")
        if nom:
            roster_role_map[nom.lower()] = (nom, emoji)

    if not roster_role_map:
        for nom in cfg.get("faction_roles", ["Leader", "Officier", "Membre de confiance", "Membre +", "Membre", "Recrue"]):
            roster_role_map[nom.lower()] = (nom, "⚔️")

    faction_members = []
    for member in guild.members:
        if member.bot:
            continue
        member_roles_lower = {r.name.lower(): r.name for r in member.roles}
        role_display = ""
        role_emoji   = ""
        for cfg_key, emoji in roster_entries:
            nom = cfg.get(cfg_key, "")
            if nom and nom.lower() in member_roles_lower:
                role_display = nom
                role_emoji   = emoji
                break
        if not role_display:
            for nom in cfg.get("faction_roles", []):
                if nom.lower() in member_roles_lower:
                    role_display = nom
                    role_emoji   = "⚔️"
                    break
        if not role_display:
            continue

        uid_str = str(member.id)
        u = data.get(uid_str, {"level": 0, "xp": 0, "message_count": 0, "voice_time": 0.0})
        faction_members.append((uid_str, u, member, role_display, role_emoji))

    faction_members.sort(key=lambda x: (x[1].get("level", 0), x[1].get("xp", 0)), reverse=True)

    if faction_members:
        top_faction_lines = []
        for i, (uid, u, m, role_name, role_emoji) in enumerate(faction_members[:10]):
            rank = medals[i] if i < 3 else f"`#{i+1}`"
            top_faction_lines.append(
                f"{rank} **{m.display_name}** — Niv. {u.get('level', 0)} ({u.get('xp', 0)} XP) {role_emoji} *{role_name}*"
            )
        top_faction = "\n".join(top_faction_lines)
    else:
        top_faction = (
            "_Aucun membre de faction trouvé_\n"
            "*(Configure les rôles du roster via `!config` → 🎖️ Roster)*"
        )

    embed = discord.Embed(title="🏆 Classements", color=0xF1C40F, timestamp=now_utc())
    embed.add_field(
        name="━━━━━━━━━━━━━━━━━━\n📊 Top Messages",
        value=top10_field("message_count", lambda u: f"{u['message_count']} msg"),
        inline=False
    )
    embed.add_field(name="━━━━━━━━━━━━━━━━━━\n⭐ Top Niveau",  value=top_lvl, inline=False)
    embed.add_field(
        name="━━━━━━━━━━━━━━━━━━\n🎤 Top Vocal",
        value=top10_field("_voice_live", lambda u: fmt_voice(u["_voice_live"])),
        inline=False
    )
    embed.add_field(
        name=f"━━━━━━━━━━━━━━━━━━\n⚔️ Top Faction ({len(faction_members)} membres)",
        value=top_faction,
        inline=False
    )
    embed.set_footer(text="Top 10 par catégorie • Temps vocal live inclus")
    await ctx.send(embed=embed)
