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
from bot.utils.database import get_db
from bot.utils.logs import get_log_channel
from bot.utils.helpers import now_utc

# Cache : {guild_id: {code: {"uses": int, "inviter_id": int|None, "max_uses": int}}}
_invite_cache: dict[int, dict[str, dict]] = {}
_invite_locks: dict[int, asyncio.Lock]    = {}


def _get_invite_lock(guild_id: int) -> asyncio.Lock:
    if guild_id not in _invite_locks:
        _invite_locks[guild_id] = asyncio.Lock()
    return _invite_locks[guild_id]


def _snapshot(invites: list) -> dict[str, dict]:
    """Convertit une liste d'invitations en snapshot structuré."""
    return {
        inv.code: {
            "uses":      inv.uses,
            "inviter_id": inv.inviter.id if inv.inviter else None,
            "max_uses":  inv.max_uses,
        }
        for inv in invites
    }


# ── CORRECTION #9 : on supprime l'ancien enregistrement si le membre revient ──
def db_add_invitation(guild_id: int, inviter_id: int, invited_id: int, invited_name: str):
    with get_db() as conn:
        # Si le membre est revenu, on supprime l'ancienne entrée et on réenregistre
        conn.execute(
            "DELETE FROM invitations WHERE guild_id=? AND invited_id=?",
            (guild_id, invited_id)
        )
        conn.execute(
            "INSERT INTO invitations (guild_id, inviter_id, invited_id, invited_name, joined_at) VALUES (?,?,?,?,?)",
            (guild_id, inviter_id, invited_id, invited_name, time.time())
        )


def db_get_invitations(guild_id: int, inviter_id: int):
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM invitations WHERE guild_id=? AND inviter_id=? ORDER BY joined_at",
            (guild_id, inviter_id)
        ).fetchall()


def db_get_all_inviters(guild_id: int):
    with get_db() as conn:
        return conn.execute(
            "SELECT inviter_id, COUNT(*) as total FROM invitations WHERE guild_id=? GROUP BY inviter_id ORDER BY total DESC",
            (guild_id,)
        ).fetchall()


async def on_member_join_invite(member: discord.Member):
    """
    Détecte quel membre a invité le nouvel arrivant.
    Envoie un log dans le salon logs avec le résultat.
    """
    guild = member.guild
    lock  = _get_invite_lock(guild.id)

    try:
        async with lock:
            # Petit délai pour laisser Discord mettre à jour les compteurs
            await asyncio.sleep(1)

            try:
                invites_after = await guild.invites()
            except discord.Forbidden:
                print(f"[INVITE] Permission manquante pour lire les invitations (guild={guild.id})")
                await _send_invite_log(guild, member, None, erreur="Permission manquante (bot sans accès aux invitations)")
                return
            except Exception as e:
                print(f"[INVITE] Erreur lors de la récupération des invitations : {e}")
                await _send_invite_log(guild, member, None, erreur=str(e))
                return

            snapshot_after  = _snapshot(invites_after)
            snapshot_before = _invite_cache.get(guild.id, {})
            used_invite     = None

            # ── 1. Invite dont le compteur a augmenté (cas classique) ──────────
            for code, after in snapshot_after.items():
                before_uses = snapshot_before.get(code, {}).get("uses", 0)
                if after["uses"] > before_uses:
                    used_invite = after
                    break

            # ── 2. Invite disparue du cache → usage unique consommé ────────────
            if used_invite is None:
                for code, before in snapshot_before.items():
                    if code not in snapshot_after:
                        if before.get("max_uses") == 1 and before.get("inviter_id"):
                            used_invite = before
                            break

            # ── Mise à jour du cache (dans le lock) ──
            _invite_cache[guild.id] = snapshot_after

        # ── Enregistrement + log hors du lock ────────────────────────────────
        if used_invite and used_invite.get("inviter_id"):
            db_add_invitation(
                guild_id     = guild.id,
                inviter_id   = used_invite["inviter_id"],
                invited_id   = member.id,
                invited_name = member.name,
            )
            inviter = guild.get_member(used_invite["inviter_id"])
            inviter_name = inviter.display_name if inviter else f"ID={used_invite['inviter_id']}"
            print(f"[INVITE] {inviter_name} a invité {member.name} (guild={guild.id})")
            await _send_invite_log(guild, member, inviter)
        else:
            print(f"[INVITE] Impossible de détecter l'invitant pour {member.name} (guild={guild.id})")
            await _send_invite_log(guild, member, None)

    except Exception as e:
        print(f"[INVITE] Erreur non gérée dans on_member_join_invite pour {member.name} : {e}")
        await _send_invite_log(guild, member, None, erreur=str(e))


async def _send_invite_log(guild: discord.Guild, member: discord.Member, inviter, erreur: str = None):
    """Envoie un embed dans le salon logs pour tracer qui a invité qui."""
    log_ch = await get_log_channel(guild)
    if not log_ch:
        return
    try:
        if inviter:
            # Récupérer le total d'invitations de cet invitant
            total = len(db_get_invitations(guild.id, inviter.id))
            embed = discord.Embed(
                title="📨 Invitation détectée",
                color=0x3498DB,
                timestamp=now_utc()
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.add_field(name="👤 Nouveau membre", value=f"{member.mention} (`{member.name}`)", inline=True)
            embed.add_field(name="📩 Invité par",     value=f"{inviter.mention} (`{inviter.name}`)", inline=True)
            embed.add_field(name="📊 Total invitations", value=f"**{total}** membre(s) invité(s) par {inviter.display_name}", inline=False)
            embed.set_footer(text=f"ID membre : {member.id} · ID invitant : {inviter.id}")
        else:
            embed = discord.Embed(
                title="📨 Invitation — Invitant inconnu",
                color=0xE67E22,
                timestamp=now_utc()
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.add_field(name="👤 Nouveau membre", value=f"{member.mention} (`{member.name}`)", inline=False)
            if erreur:
                embed.add_field(name="❌ Erreur", value=f"`{erreur}`", inline=False)
                embed.add_field(name="💡 Cause possible", value="Lien vanity, lien de DM, ou permission manquante", inline=False)
            else:
                embed.add_field(name="⚠️ Raison", value="Impossible de détecter l'invitant.\nLien vanity, lien de DM, ou cache désynchronisé.", inline=False)
            embed.set_footer(text=f"ID membre : {member.id}")
        await log_ch.send(embed=embed)
    except Exception as e:
        print(f"[INVITE] Erreur envoi log invite : {e}")


# ─── Initialisation du cache dans on_ready ──────────────────────────────────
async def init_invite_cache():
    """Charge le snapshot initial de toutes les invitations pour chaque guild."""
    for guild in bot.guilds:
        try:
            invites = await guild.invites()
            _invite_cache[guild.id] = _snapshot(invites)
            print(f"[INVITE] Cache initialisé : {guild.name} ({len(invites)} invitation(s))")
        except discord.Forbidden:
            print(f"[INVITE] Permission manquante pour {guild.name} — cache non initialisé")
        except Exception as e:
            print(f"[INVITE] Erreur init cache {guild.name} : {e}")

