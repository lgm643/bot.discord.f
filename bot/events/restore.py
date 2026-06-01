"""
events/restore.py — Restauration au démarrage et boucle de refresh.

CORRECTIONS :
  [1] _auto_refresh_loop : sleep 60s au lieu de 3s → élimine les rate limits Discord
  [2] Giveaways actifs sauvegardés/restaurés sur disque (bug critique corrigé)
"""
import asyncio
import json
import os
import time
from pathlib import Path

import discord

from bot.core import (
    bot, GAMES_DIR, CATALOGUE_DIR, GIVEAWAYS_DIR,
    active_pendu, active_morpion, active_giveaways,
    _catalogue_msg_ids, _commande_msg_ids,
    CATALOGUE_REFRESH_INTERVAL,
)
from bot.utils.helpers import load_games_for, gk
from bot.utils.market import (
    load_catalogue, _clean_ghost_items, build_catalogue_embed, _get_catalogue_lock,
)
from bot.utils.database import get_db, db_save_objectif_embed, db_get_mutes, db_delete_mute
from bot.utils.embeds import build_objectifs_embed
from bot.utils.config import cfg_channel
from bot.utils.games import _start_pendu_timer, _start_morpion_timer

_auto_refresh_running = False

# ── Fichier de persistance des giveaways actifs ───────────────────────────────
_ACTIVE_GW_FILE = GIVEAWAYS_DIR / "active.json"


def _save_active_giveaways():
    """Persiste les giveaways actifs sur disque."""
    try:
        tmp = str(_ACTIVE_GW_FILE) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(active_giveaways, f, indent=2, ensure_ascii=False)
        os.replace(tmp, str(_ACTIVE_GW_FILE))
    except Exception as e:
        print(f"[GW] Erreur sauvegarde giveaways actifs : {e}")


def _load_active_giveaways():
    """Charge les giveaways actifs depuis le disque au démarrage."""
    if not _ACTIVE_GW_FILE.exists():
        return {}
    try:
        with open(_ACTIVE_GW_FILE, "r", encoding="utf-8") as f:
            return {int(k): v for k, v in json.load(f).items()}
    except Exception as e:
        print(f"[GW] Erreur lecture giveaways actifs : {e}")
        return {}


async def _restore_all_games():
    for path in GAMES_DIR.glob("*.json"):
        if path.name == "active.json":
            continue
        try:
            guild_id = int(path.stem)
        except ValueError:
            continue
        raw = load_games_for(guild_id)
        now = time.time()
        for key_str, data in raw.items():
            remaining = data.get("end_time", 0) - now
            if remaining <= 0:
                continue
            if key_str.startswith("pendu_"):
                ch_id = int(key_str.split("_", 1)[1])
                k = gk(guild_id, ch_id)
                data["guessed"]    = list(data.get("guessed", []))
                data["letter_cd"]  = {}
                data["channel_id"] = ch_id
                active_pendu[k] = data
                await _start_pendu_timer(k, guild_id, remaining)
                print(f"[RESTORE] Pendu restauré : guild={guild_id} ch={ch_id}")
            elif key_str.startswith("morpion_"):
                ch_id = int(key_str.split("_", 1)[1])
                k = gk(guild_id, ch_id)
                active_morpion[k] = data
                await _start_morpion_timer(k, guild_id, remaining)
                print(f"[RESTORE] Morpion restauré : guild={guild_id} ch={ch_id}")


async def _restore_all_giveaways():
    """[CORRECTIF] Restaure les giveaways actifs et relance leurs timers."""
    saved = _load_active_giveaways()
    now   = time.time()
    for msg_id, gw in saved.items():
        ends_at = gw.get("ends_at", 0)
        remaining = ends_at - now
        if remaining <= 0:
            print(f"[GW] Giveaway expiré ignoré : msg_id={msg_id}")
            continue
        channel_id = gw.get("channel_id")
        active_giveaways[msg_id] = gw
        from bot.views.giveaway_view import GiveawayView
        try:
            bot.add_view(GiveawayView(msg_id))
        except Exception:
            pass
        channel = bot.get_channel(channel_id) if channel_id else None
        if channel:
            from bot.commands.giveaway import _end_giveaway
            asyncio.create_task(_end_giveaway(msg_id, remaining, channel, gw.get("reward", "?")))
            print(f"[GW] Timer restauré : msg_id={msg_id} remaining={int(remaining)}s")


async def _restore_all_catalogues():
    for path in CATALOGUE_DIR.glob("*.json"):
        try:
            guild_id = int(path.stem)
            data = load_catalogue(guild_id)
            items = _clean_ghost_items(data.get("items", {}))
            if data.get("msg_id"):
                _catalogue_msg_ids[guild_id] = data["msg_id"]
                from bot.views.market_view import CatalogueView
                bot.add_view(CatalogueView(), message_id=data["msg_id"])
                print(f"[CATALOGUE] msg_id restauré : guild={guild_id} → {data['msg_id']}")
            if data.get("commande_msg_id"):
                _commande_msg_ids[guild_id] = data["commande_msg_id"]
                from bot.views.market_view import CommandeView
                bot.add_view(CommandeView(guild_id, items), message_id=data["commande_msg_id"])
                print(f"[COMMANDE] commande_msg_id restauré : guild={guild_id} → {data['commande_msg_id']}")
        except Exception as e:
            print(f"[CATALOGUE] Erreur restauration : {e}")


async def _restore_all_objectifs():
    with get_db() as conn:
        rows = conn.execute("SELECT guild_id, channel_id, msg_id FROM objectif_embeds").fetchall()
    for row in rows:
        guild = bot.get_guild(row["guild_id"])
        if not guild:
            continue
        channel = guild.get_channel(row["channel_id"])
        if not channel:
            continue
        embed = build_objectifs_embed(row["guild_id"])
        try:
            msg = await channel.fetch_message(row["msg_id"])
            await msg.edit(embed=embed)
            print(f"[OBJECTIFS] Embed restauré : guild={row['guild_id']}")
        except Exception:
            try:
                msg = await channel.send(embed=embed)
                db_save_objectif_embed(row["guild_id"], channel.id, msg.id)
                print(f"[OBJECTIFS] Embed recréé : guild={row['guild_id']}")
            except Exception as e:
                print(f"[OBJECTIFS] Impossible de restaurer : {e}")


async def _restore_all_mutes():
    now = time.time()
    for guild in bot.guilds:
        rows = db_get_mutes(guild.id)
        for row in rows:
            member    = guild.get_member(row["user_id"])
            mute_role = discord.utils.get(guild.roles, name="Muted")
            if not mute_role:
                continue
            expires_at = row["expires_at"]
            if expires_at and expires_at <= now:
                try:
                    if member and mute_role in member.roles:
                        await member.remove_roles(mute_role, reason="Mute expiré (restauration)")
                    db_delete_mute(guild.id, row["user_id"])
                    print(f"[MUTE] Mute expiré nettoyé : user={row['user_id']} guild={guild.id}")
                except Exception as e:
                    print(f"[MUTE] Erreur nettoyage mute expiré : {e}")
                continue
            if member and mute_role not in member.roles:
                try:
                    await member.add_roles(mute_role, reason="Restauration mute après redémarrage")
                except Exception:
                    pass
            if expires_at:
                remaining = expires_at - now
                from bot.commands.moderation import _schedule_unmute
                asyncio.create_task(_schedule_unmute(guild, member, mute_role, remaining, "durée restante"))
                print(f"[MUTE] Timer relancé : user={row['user_id']} remaining={int(remaining)}s")


async def _auto_refresh_loop():
    """[CORRECTIF] Refresh toutes les 60s au lieu de 3s."""
    global _auto_refresh_running
    if _auto_refresh_running:
        return
    _auto_refresh_running = True
    print(f"[REFRESH] Boucle auto-refresh démarrée ({CATALOGUE_REFRESH_INTERVAL}s)")
    try:
        while True:
            await asyncio.sleep(CATALOGUE_REFRESH_INTERVAL)
            guilds = list(bot.guilds)
            for i, guild in enumerate(guilds):
                try:
                    data  = load_catalogue(guild.id)
                    items = _clean_ghost_items(data.get("items", {}))
                    await _silent_refresh(guild, items)
                except Exception as e:
                    print(f"[REFRESH] Erreur guild={guild.id} : {e}")
                if i < len(guilds) - 1:
                    await asyncio.sleep(1)
    finally:
        _auto_refresh_running = False


async def _silent_refresh(guild, items):
    async with _get_catalogue_lock(guild.id):
        data = load_catalogue(guild.id)
        cat_msg_id = data.get("msg_id") or _catalogue_msg_ids.get(guild.id)
        if cat_msg_id:
            cat_ch = cfg_channel(guild, "salon_catalogue")
            if cat_ch:
                try:
                    msg = await cat_ch.fetch_message(cat_msg_id)
                    from bot.views.market_view import CatalogueView
                    await msg.edit(embed=build_catalogue_embed(items), view=CatalogueView())
                except discord.NotFound:
                    _catalogue_msg_ids.pop(guild.id, None)
                    data.pop("msg_id", None)
                    from bot.utils.market import save_catalogue
                    save_catalogue(guild.id, data)
                except Exception:
                    pass
        cmd_msg_id = data.get("commande_msg_id") or _commande_msg_ids.get(guild.id)
        if cmd_msg_id:
            cmd_ch = cfg_channel(guild, "salon_commandes")
            if cmd_ch:
                try:
                    from bot.views.market_view import CommandeView, _build_commande_embed_from_items
                    cmd_msg = await cmd_ch.fetch_message(cmd_msg_id)
                    await cmd_msg.edit(
                        embed=_build_commande_embed_from_items(guild, items),
                        view=CommandeView(guild.id, items),
                    )
                except discord.NotFound:
                    _commande_msg_ids.pop(guild.id, None)
                    data.pop("commande_msg_id", None)
                    from bot.utils.market import save_catalogue
                    save_catalogue(guild.id, data)
                except Exception:
                    pass
