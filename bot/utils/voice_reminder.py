"""
utils/voice_reminder.py — Rappel périodique pour inciter les membres de la fac
(recrue, membre, etc.) à passer en salon vocal.

Fonctionnement :
  - Toutes les X heures configurables (rappel_vocal_heures, défaut 12), on
    vérifie chaque membre possédant un des rôles suivis (rappel_vocal_roles,
    vide = tous les rôles de faction_roles).
  - Si le membre n'a rejoint aucun salon vocal (ni reçu de rappel) depuis ce
    délai, on lui envoie un MP.
  - Si le MP échoue (DM fermés), on le mentionne dans le salon configuré
    (salon_rappel_vocal) à la place.
  - Le compteur se reset dès que le membre rejoint/rechange de salon vocal
    (hook touch_voice_join() appelé depuis on_voice_state_update).
  - Le rappel se répète toutes les X heures tant que le membre ne s'est
    toujours pas connecté en vocal.

Configuration dans !config (groupe 🔔 Rappel Vocal) :
  rappel_vocal_enabled : bool  (0/1)
  rappel_vocal_heures   : int   délai en heures avant rappel
  rappel_vocal_roles    : list  rôles suivis (vide = faction_roles)
  salon_rappel_vocal    : str   salon de secours si MP fermés
"""
import asyncio
import time

import discord

from bot.utils.config import load_config, resolve_channel, resolve_roles
from bot.utils.database import (
    db_touch_voice_join,
    db_init_voice_reminder_if_missing,
    db_get_voice_reminder,
    db_set_voice_reminder_sent,
)

CHECK_INTERVAL = 1800  # 30 minutes — suffisant pour un délai exprimé en heures


def _get_delay_seconds(cfg: dict) -> float:
    heures = cfg.get("rappel_vocal_heures", 12)
    try:
        heures = float(heures)
    except (ValueError, TypeError):
        heures = 12.0
    return max(1.0, heures) * 3600.0


def _get_tracked_roles(guild: discord.Guild, cfg: dict) -> list[discord.Role]:
    names = cfg.get("rappel_vocal_roles") or cfg.get("faction_roles", [])
    return resolve_roles(guild, names)


def touch_voice_join(guild_id: int, user_id: int):
    """À appeler quand un membre rejoint/change de salon vocal : reset son compteur."""
    db_touch_voice_join(guild_id, user_id, time.time())


async def _send_reminder(guild: discord.Guild, member: discord.Member, cfg: dict, heures: float):
    text = (
        f"👋 Ça fait plus de **{int(heures)}h** que tu n'es pas passé·e en vocal sur "
        f"**{guild.name}**. Pense à faire un tour en salon vocal !"
    )
    try:
        await member.send(text)
        print(f"[RAPPEL-VOCAL] MP envoyé à {member} (guild={guild.id})")
    except (discord.Forbidden, discord.HTTPException):
        # MP fermés -> on mentionne dans le salon configuré à la place
        channel = resolve_channel(guild, cfg.get("salon_rappel_vocal"))
        if channel is None:
            print(
                f"[RAPPEL-VOCAL] ⚠️ MP fermés pour {member} et salon_rappel_vocal "
                f"non configuré (guild={guild.id}) — voir !config"
            )
            return
        try:
            await channel.send(
                content=f"{member.mention} {text}",
                allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False),
            )
        except Exception as e:
            print(f"[RAPPEL-VOCAL] Erreur envoi salon : {e}")


async def _check_guild(guild: discord.Guild):
    cfg = load_config(guild.id)
    if not cfg.get("rappel_vocal_enabled", False):
        return

    delay_s = _get_delay_seconds(cfg)
    heures  = delay_s / 3600.0
    roles   = _get_tracked_roles(guild, cfg)
    if not roles:
        return

    now  = time.time()
    seen: set[int] = set()

    for role in roles:
        for member in role.members:
            if member.bot or member.id in seen:
                continue
            seen.add(member.id)

            # Actuellement en vocal -> aucun rappel nécessaire, on reset direct.
            if member.voice and member.voice.channel:
                db_touch_voice_join(guild.id, member.id, now)
                continue

            row = db_get_voice_reminder(guild.id, member.id)
            if row is None:
                # Premier passage sur ce membre : on initialise sans rappel immédiat.
                db_init_voice_reminder_if_missing(guild.id, member.id, now)
                continue

            reference = max(row["last_voice_at"] or 0, row["last_reminder_at"] or 0)
            if now - reference < delay_s:
                continue

            await _send_reminder(guild, member, cfg, heures)
            db_set_voice_reminder_sent(guild.id, member.id, now)


async def voice_reminder_loop(bot: discord.Client):
    await bot.wait_until_ready()
    print("[RAPPEL-VOCAL] Boucle démarrée")
    while not bot.is_closed():
        try:
            for guild in bot.guilds:
                await _check_guild(guild)
        except Exception as e:
            print(f"[RAPPEL-VOCAL] Erreur boucle : {e}")
        await asyncio.sleep(CHECK_INTERVAL)