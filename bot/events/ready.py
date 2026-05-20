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

from bot.core import _on_ready_done
from bot.views.ticket_view import TicketView
from bot.views.market_view import RoleToggleView
from bot.views.vendeur_view import VendeurView
from bot.utils.invites import init_invite_cache
from bot.events.restore import (
    _restore_all_games, _restore_all_catalogues, _restore_all_objectifs, _auto_refresh_loop,
)
from bot.utils.config import load_config

@bot.event
async def on_ready():
    global _on_ready_done

    print(f"[BOT] Connecté : {bot.user} (ID: {bot.user.id})")
    print(f"[BOT] Serveurs : {[g.name for g in bot.guilds]}")
    print("[BOT] Build: import-fix-r2 (2026-05-20)")

    # Toujours réenregistrer les vues persistantes (nécessaire après reconnexion)
    bot.add_view(TicketView())
    bot.add_view(RoleToggleView())
    bot.add_view(VendeurView())

    # Toujours rafraîchir le cache des invitations (peut changer pendant une déconnexion)
    await init_invite_cache()

    # Le reste ne se fait qu'une seule fois au démarrage initial
    if not _on_ready_done:
        _on_ready_done = True

        await _restore_all_games()
        await _restore_all_catalogues()
        await _restore_all_objectifs()

        for guild in bot.guilds:
            load_config(guild.id)
            print(f"[CONFIG] Serveur configuré : {guild.name} (ID: {guild.id})")

        from bot.utils.giveaways import load_all_ended_giveaways
        load_all_ended_giveaways()

        asyncio.create_task(_auto_refresh_loop())
        from bot.utils.invite_rewards import invite_rewards_sync_loop
        asyncio.create_task(invite_rewards_sync_loop())
        print("[BOT] Prêt !")
    else:
        print("[BOT] Reconnexion détectée — restauration ignorée (déjà effectuée)")
