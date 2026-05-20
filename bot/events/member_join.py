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

from bot.utils.invites import on_member_join_invite
from bot.utils.config import load_config, cfg_role, cfg_channel
from bot.utils.helpers import now_utc
from bot.utils.logs import send_log, get_log_channel

_recent_suspects: dict[int, list[float]] = defaultdict(list)

def _analyse_alt(member, cfg):
    reasons  = []
    age_days = (datetime.now(timezone.utc) - member.created_at).days
    if age_days < cfg.get("alt_min_days", 30):
        reasons.append(f"Compte récent ({age_days} jour(s))")
    if member.avatar is None:
        reasons.append("Pas d'avatar personnalisé")
    return reasons

async def _send_alt_alert(member, reasons):
    log_channel = await get_log_channel(member.guild)
    if not log_channel: return
    age_days = (datetime.now(timezone.utc) - member.created_at).days
    officier = cfg_role(member.guild, "role_officier")
    leader   = cfg_role(member.guild, "role_leader")
    mentions = " ".join(r.mention for r in [officier, leader] if r)
    embed = discord.Embed(title="⚠️ COMPTE SUSPECT — ALT POSSIBLE", color=0xFF6B00, timestamp=now_utc())
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="👤 Utilisateur",    value=f"{member.mention} ({member.id})", inline=False)
    embed.add_field(name="📅 Compte créé le", value=discord.utils.format_dt(member.created_at, style="F"), inline=True)
    embed.add_field(name="⏱️ Âge du compte",  value=f"{age_days} jour(s)", inline=True)
    embed.add_field(name="📌 Raisons",        value="\n".join(f"- {r}" for r in reasons), inline=False)
    embed.set_footer(text="Système Anti-Alt automatique")
    await log_channel.send(content=f"⚠️ **ATTENTION** : ALT possible ! {mentions}", embed=embed)

async def _check_raid(guild, cfg):
    window    = cfg.get("raid_window_secs", 60)
    threshold = cfg.get("raid_threshold", 3)
    now       = time.time()
    _recent_suspects[guild.id] = [t for t in _recent_suspects[guild.id] if now - t < window]
    _recent_suspects[guild.id].append(now)
    if len(_recent_suspects[guild.id]) >= threshold:
        _recent_suspects[guild.id].clear()
        log_channel = await get_log_channel(guild)
        if log_channel:
            officier = cfg_role(guild, "role_officier")
            leader   = cfg_role(guild, "role_leader")
            mentions = " ".join(r.mention for r in [officier, leader] if r)
            embed = discord.Embed(title="🚨 RAID POSSIBLE DÉTECTÉ", description=f"**{threshold}+** comptes suspects ont rejoint en moins de **{window}s** !", color=0xFF0000, timestamp=now_utc())
            await log_channel.send(content=f"🚨 **RAID POSSIBLE !** {mentions}", embed=embed)


# ═══════════════════════════════════════════════════════════════
#  ON_MEMBER_JOIN — CORRIGÉ (#3 #4)
#  Chaque bloc est isolé dans son propre try/except :
#  une erreur dans les invitations ne bloque plus le rôle ni le BVN
# ═══════════════════════════════════════════════════════════════

@bot.event
async def on_member_join(member: discord.Member):
    cfg = load_config(member.guild.id)

    # ── Détection de l'invitant — isolé pour ne jamais bloquer la suite ──
    try:
        await on_member_join_invite(member)
    except Exception as e:
        print(f"[INVITE] Erreur critique non gérée pour {member.name} : {e}")

    try:
        from bot.utils.invite_rewards import on_invite_chain_update
        await on_invite_chain_update(member.guild, member.id)
    except Exception as e:
        print(f"[INVITE_REWARDS] Erreur après join pour {member.name} : {e}")

    # ── Rôle visiteur ──────────────────────────────────────────────────────
    visitor_role = cfg_role(member.guild, "role_visiteur")
    if visitor_role:
        try:
            await member.add_roles(visitor_role, reason="Rôle visiteur automatique")
            print(f"[WELCOME] Rôle visiteur attribué à {member.name}")
        except discord.Forbidden:
            print(f"[WELCOME] Permission manquante pour attribuer le rôle visiteur à {member.name}")
        except Exception as e:
            print(f"[WELCOME] Erreur rôle visiteur pour {member.name} : {e}")
    else:
        # CORRECTION #3 : log si le rôle est introuvable
        role_name = cfg.get("role_visiteur", "visiteur")
        print(f"[WELCOME] ⚠️ Rôle visiteur '{role_name}' introuvable sur {member.guild.name} — vérifie !config")

    # ── Message de bienvenue ───────────────────────────────────────────────
    welcome_channel = cfg_channel(member.guild, "salon_bienvenue")
    if welcome_channel:
        try:
            await welcome_channel.send(
                f"Hey {member.mention} 👋\n"
                f"Bienvenue sur le Discord de **{member.guild.name}** 👑\n"
                f"N'hésite pas à ouvrir un ticket si tu as une question. On est là 🙌"
            )
            print(f"[WELCOME] Message de bienvenue envoyé pour {member.name}")
        except discord.Forbidden:
            print(f"[WELCOME] Permission manquante pour envoyer dans le salon bienvenue")
        except Exception as e:
            print(f"[WELCOME] Erreur message bienvenue pour {member.name} : {e}")
    else:
        # CORRECTION #3 : log si le salon est introuvable
        salon_name = cfg.get("salon_bienvenue", "bienvenue")
        print(f"[WELCOME] ⚠️ Salon bienvenue '{salon_name}' introuvable sur {member.guild.name} — vérifie !config")

    # ── Log d'arrivée ──────────────────────────────────────────────────────
    try:
        age_days = (datetime.now(timezone.utc) - member.created_at).days
        embed = discord.Embed(title="📥 Membre arrivé", color=0x2ECC71, timestamp=now_utc())
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="👤 Membre",      value=f"{member} ({member.id})", inline=True)
        embed.add_field(name="📅 Compte créé", value=discord.utils.format_dt(member.created_at, style="D"), inline=True)
        embed.add_field(name="⏱️ Âge",         value=f"{age_days} jour(s)", inline=True)
        embed.add_field(name="👥 Total",       value=str(member.guild.member_count), inline=True)
        await send_log(member.guild, embed)
    except Exception as e:
        print(f"[WELCOME] Erreur log arrivée pour {member.name} : {e}")

    # ── Anti-alt / Anti-raid ───────────────────────────────────────────────
    try:
        reasons = _analyse_alt(member, cfg)
        if reasons:
            await _send_alt_alert(member, reasons)
            await _check_raid(member.guild, cfg)
    except Exception as e:
        print(f"[WELCOME] Erreur anti-alt/raid pour {member.name} : {e}")
