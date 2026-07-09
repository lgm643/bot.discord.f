"""
events/ready.py — on_ready et boucles périodiques.

CORRECTIONS v2 :
  [1] _flush_user_data_loop appelle désormais `await flush_user_data_all()`
      (la version async non-bloquante) au lieu de la version synchrone.
  [2] _restore_active_giveaway_views replanifie aussi les timers des giveaways
      encore actifs après un redémarrage — ils ne sont plus perdus.
  [3] Les bot.add_view() des vues persistantes sont protégés par un try/except
      individuel pour ne pas bloquer le démarrage si une vue est invalide.
"""
import asyncio
import time

import discord

import bot.core as _core
from bot.core import bot, active_giveaways, USER_DATA_FLUSH_INTERVAL
from bot.views.ticket_view import TicketView, RelanceRecruteurView
from bot.views.market_view import (
    RoleToggleView, CatalogueView, _CataloguePersoView, CommandeView,
)
from bot.views.vendeur_view import VendeurView, VendeurDecisionView
from bot.views.objectif_views import ObjectifView
from bot.views.giveaway_view import GiveawayView
from bot.utils.invites import init_invite_cache
from bot.events.restore import (
    _restore_all_games, _restore_all_catalogues, _restore_all_objectifs,
    _restore_all_mutes, _auto_refresh_loop,
)
from bot.utils.config import load_config
from bot.utils.market import load_catalogue, _clean_ghost_items


async def _restore_active_giveaway_views():
    """Restaure les vues ET replanifie les timers des giveaways encore actifs."""
    from bot.commands.giveaway import _end_giveaway

    for msg_id, gw in list(active_giveaways.items()):
        try:
            bot.add_view(GiveawayView(msg_id))
            print(f"[GIVEAWAY] Vue restaurée pour msg_id={msg_id}")
        except Exception as e:
            print(f"[GIVEAWAY] Erreur restauration vue msg_id={msg_id} : {e}")

        ends_at   = gw.get("ends_at", 0)
        remaining = ends_at - time.time()
        channel_id = gw.get("channel_id")
        reward     = gw.get("reward", "?")

        if remaining <= 0:
            remaining = 1

        channel = None
        guild_id = gw.get("guild_id")
        if guild_id and channel_id:
            guild = bot.get_guild(guild_id)
            if guild:
                channel = guild.get_channel(channel_id)

        if channel:
            asyncio.create_task(_end_giveaway(msg_id, remaining, channel, reward))
            print(f"[GIVEAWAY] Timer restauré pour msg_id={msg_id}, remaining={int(remaining)}s")
        else:
            print(f"[GIVEAWAY] ⚠️ Salon introuvable pour giveaway msg_id={msg_id} — timer non restauré")


async def _flush_user_data_loop():
    """Flush les données XP sur disque toutes les 60s — version async non-bloquante."""
    from bot.utils.helpers import flush_user_data_all
    print(f"[FLUSH] Boucle flush user_data démarrée ({USER_DATA_FLUSH_INTERVAL}s)")
    while not bot.is_closed():
        await asyncio.sleep(USER_DATA_FLUSH_INTERVAL)
        try:
            await flush_user_data_all()
        except Exception as e:
            print(f"[FLUSH] Erreur : {e}")


@bot.event
async def on_ready():
    print(f"[BOT] Connecté : {bot.user} (ID: {bot.user.id})")
    print(f"[BOT] Serveurs : {[g.name for g in bot.guilds]}")

    for view_cls, kwargs in [
        (TicketView,   {}),
        (RoleToggleView, {}),
        (VendeurView,  {}),
        (ObjectifView, {"guild_id": 0}),
        (CatalogueView, {}),
    ]:
        try:
            bot.add_view(view_cls(**kwargs))
        except Exception as e:
            print(f"[READY] Erreur add_view {view_cls.__name__} : {e}")

    for guild in bot.guilds:
        try:
            data  = load_catalogue(guild.id)
            items = _clean_ghost_items(data.get("items", {}))
            bot.add_view(CommandeView(guild.id, items))
            print(f"[READY] CommandeView enregistrée : guild={guild.id}")
        except Exception as e:
            print(f"[READY] CommandeView erreur guild={guild.id} : {e}")

    try:
        from bot.views.market_view import VenduView
        bot.add_view(VenduView(guild_id=0, vendeur_id=0, nom_key="", quantite=0, ticket_channel_id=0))
    except Exception as e:
        print(f"[READY] Erreur add_view VenduView : {e}")

    for guild in bot.guilds:
        for channel in guild.text_channels:
            topic = getattr(channel, "topic", None) or ""
            if topic.startswith("vendeur_certifie"):
                parts = topic.split("|")
                try:
                    membre_id = int(parts[1]) if len(parts) > 1 else None
                except ValueError:
                    membre_id = None
                try:
                    bot.add_view(VendeurDecisionView(membre_id))
                except Exception as e:
                    print(f"[READY] Erreur add_view VendeurDecisionView ({channel.name}) : {e}")

    await init_invite_cache()

    if not _core._on_ready_done:
        _core._on_ready_done = True

        await _restore_all_games()
        await _restore_all_catalogues()
        await _restore_all_objectifs()
        await _restore_all_mutes()
        from bot.events.restore import _restore_all_giveaways
        await _restore_all_giveaways()

        await _restore_active_giveaway_views()

        for guild in bot.guilds:
            load_config(guild.id)
            print(f"[CONFIG] Serveur configuré : {guild.name} (ID: {guild.id})")

        from bot.utils.giveaways import load_all_ended_giveaways
        load_all_ended_giveaways()

        # Boucles périodiques
        asyncio.create_task(_auto_refresh_loop())
        asyncio.create_task(_flush_user_data_loop())
        from bot.utils.invite_rewards import invite_rewards_sync_loop
        asyncio.create_task(invite_rewards_sync_loop())
        from bot.events.weekly import weekly_loop
        asyncio.create_task(weekly_loop())
        from bot.utils.voice_inactivity import voice_inactivity_loop
        asyncio.create_task(voice_inactivity_loop(bot))

        from bot.utils.ticket_relance import ticket_relance_loop
        asyncio.create_task(ticket_relance_loop(bot))

        from bot.utils.voice_reminder import voice_reminder_loop
        asyncio.create_task(voice_reminder_loop(bot))

        try:
            bot.add_view(RelanceRecruteurView())
        except Exception as e:
            print(f"[READY] Erreur add_view RelanceRecruteurView : {e}")

        # Sync des slash commands (ex: /recherche avec autocomplete) — une fois par démarrage.
        # La propagation peut prendre jusqu'à 1h en sync globale ; c'est normal.
        try:
            synced = await bot.tree.sync()
            print(f"[READY] {len(synced)} slash command(s) synchronisée(s)")
        except Exception as e:
            print(f"[READY] Erreur sync slash commands : {e}")

        print("[BOT] Prêt !")
    else:
        await _restore_active_giveaway_views()
        print("[BOT] Reconnexion détectée — restauration des vues uniquement")git add bot/utils/voice_reminder.py bot/utils/database.py bot/utils/config.py bot/utils/config_panel.py bot/events/logs_events.py bot/events/ready.py
