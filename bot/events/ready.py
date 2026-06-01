"""
events/ready.py — on_ready et boucles périodiques.

CORRECTIONS :
  - Ajout de la boucle flush_user_data_all() toutes les 60s
  - Boucle _auto_refresh_loop déjà à 60s dans restore.py
  - Ajout de la boucle de flush des données XP utilisateur
"""
import asyncio

import discord

import bot.core as _core
from bot.core import bot, active_giveaways, USER_DATA_FLUSH_INTERVAL
from bot.views.ticket_view import TicketView
from bot.views.market_view import (
    RoleToggleView, CatalogueView, _CataloguePersoView, CommandeView,
)
from bot.views.vendeur_view import VendeurView
from bot.views.objectif_views import ObjectifView
from bot.views.giveaway_view import GiveawayView
from bot.utils.invites import init_invite_cache
from bot.events.restore import (
    _restore_all_games, _restore_all_catalogues, _restore_all_objectifs,
    _restore_all_mutes, _auto_refresh_loop,
)
from bot.utils.config import load_config
from bot.utils.market import load_catalogue, _clean_ghost_items


def _restore_active_giveaway_views():
    for msg_id in list(active_giveaways.keys()):
        try:
            bot.add_view(GiveawayView(msg_id))
            print(f"[GIVEAWAY] Vue restaurée pour msg_id={msg_id}")
        except Exception as e:
            print(f"[GIVEAWAY] Erreur restauration vue msg_id={msg_id} : {e}")


async def _flush_user_data_loop():
    """Flush les données XP sur disque toutes les 60s."""
    from bot.utils.helpers import flush_user_data_all
    print(f"[FLUSH] Boucle flush user_data démarrée ({USER_DATA_FLUSH_INTERVAL}s)")
    while not bot.is_closed():
        await asyncio.sleep(USER_DATA_FLUSH_INTERVAL)
        try:
            flush_user_data_all()
        except Exception as e:
            print(f"[FLUSH] Erreur : {e}")


@bot.event
async def on_ready():
    print(f"[BOT] Connecté : {bot.user} (ID: {bot.user.id})")
    print(f"[BOT] Serveurs : {[g.name for g in bot.guilds]}")

    # Vues persistantes — obligatoires après chaque (re)connexion
    bot.add_view(TicketView())
    bot.add_view(RoleToggleView())
    bot.add_view(VendeurView())
    bot.add_view(ObjectifView(guild_id=0))
    bot.add_view(CatalogueView())

    for guild in bot.guilds:
        try:
            data  = load_catalogue(guild.id)
            items = _clean_ghost_items(data.get("items", {}))
            bot.add_view(CommandeView(guild.id, items))
            print(f"[READY] CommandeView enregistrée : guild={guild.id}")
        except Exception as e:
            print(f"[READY] CommandeView erreur guild={guild.id} : {e}")

    from bot.views.market_view import VenduView
    bot.add_view(VenduView(guild_id=0, vendeur_id=0, nom_key="", quantite=0, ticket_channel_id=0))

    await init_invite_cache()

    if not _core._on_ready_done:
        _core._on_ready_done = True

        await _restore_all_games()
        await _restore_all_catalogues()
        await _restore_all_objectifs()
        await _restore_all_mutes()
        from bot.events.restore import _restore_all_giveaways
        await _restore_all_giveaways()

        _restore_active_giveaway_views()

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
        print("[BOT] Prêt !")
    else:
        _restore_active_giveaway_views()
        print("[BOT] Reconnexion détectée — restauration ignorée (déjà effectuée)")
