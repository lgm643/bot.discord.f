"""Split bot.py into bot/ package."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
lines = (ROOT / "bot.py").read_text(encoding="utf-8").splitlines(keepends=True)


def sl(a: int, b: int) -> str:
    return "".join(lines[a - 1 : b])


def w(rel: str, content: str):
    p = ROOT / "bot" / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    print(f"  {rel}")


B = "from bot.core import bot\n\n"
I = """import asyncio
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

""" + B

IC = """import asyncio
import os
import json
import time
import random
import sqlite3
from collections import defaultdict
from pathlib import Path

import discord
from discord.ext import commands

"""

print("Splitting...")

w("__init__.py", '"""La Mystic Discord bot."""\n')

w("core.py", IC + sl(1, 21) + sl(23, 34) + sl(291, 352) + sl(414, 418) + sl(463, 466) + "\n_on_ready_done = False\n")

w("utils/__init__.py", "")
w("utils/database.py", IC.replace("from discord.ext import commands\n\n", "") + "from bot.core import DB_PATH\n\n" + sl(40, 77) + sl(639, 668))
w("utils/config.py", I.replace(B, "") + "from bot.core import CONFIG_DIR\n\n" + sl(79, 230))
w("utils/permissions.py", I + sl(236, 256))
w("utils/logs.py", I + sl(262, 270))
w("utils/helpers.py", I.replace(B, "") + """from bot.core import (
    DATA_DIR, GAMES_DIR, spam_tracker, spam_warned, xp_cooldowns,
    active_pendu, active_morpion, pendu_tasks, morpion_tasks,
)

""" + sl(276, 285) + sl(358, 457))
w("utils/market.py", I + """from bot.core import CATALOGUE_DIR, _catalogue_msg_ids, _commande_msg_ids, _catalogue_lock
from bot.utils.config import cfg_channel, load_config, resolve_channel
from bot.utils.helpers import now_utc

""" + sl(468, 558) + sl(1123, 1139) + sl(1145, 1164) + sl(1184, 1189))
w("utils/tickets.py", I + sl(564, 598))
w("utils/embeds.py", I + """from bot.utils.database import db_get_objectifs, db_get_objectif_embed, db_save_objectif_embed
from bot.utils.config import load_config, resolve_role, cfg_channel
from bot.utils.helpers import now_utc

""" + sl(604, 637) + sl(982, 1022))
w("utils/invites.py", I + """from bot.core import bot, _invite_cache, _invite_locks
from bot.utils.database import db_add_invitation, db_get_invitations
from bot.utils.logs import get_log_channel
from bot.utils.helpers import now_utc

""" + sl(674, 844))
w("utils/games.py", I + """from bot.core import bot, active_pendu, active_morpion, pendu_tasks, morpion_tasks
from bot.utils.helpers import gk, save_games, load_user_data, get_user, save_user_data

""" + sl(1901, 1961) + sl(2017, 2050) + sl(2112, 2258))


w("views/__init__.py", "")
w("views/ticket_view.py", I + """from bot.utils.config import cfg_roles, cfg_role, cfg_category
from bot.utils.permissions import is_staff
from bot.utils.tickets import send_ticket_log

""" + sl(1286, 1383))
w("views/market_view.py", I + """from bot.core import _pending_orders
from bot.utils.market import (
    load_catalogue, fuzzy_search, _clean_ghost_items,
    update_catalogue_message, send_notif, _parse_prix_num,
)
from bot.utils.config import cfg_category, cfg_channel, load_config
from bot.utils.permissions import is_staff, is_vendeur
from bot.utils.helpers import now_utc
from bot.utils.logs import send_log

""" + sl(1170, 1181) + sl(2501, 2510) + sl(2673, 2688) + sl(2783, 2930) + sl(2949, 3012) + sl(3067, 3082))
w("views/giveaway_view.py", I + "from bot.core import active_giveaways\nfrom bot.utils.helpers import now_utc\n\n" + sl(2292, 2320))
w("views/vendeur_view.py", I + """from bot.modals.vendeur_modal import VendeurModal
from bot.utils.config import cfg_role
from bot.utils.permissions import is_staff

""" + sl(4089, 4118))
w("views/objectif_views.py", I + """from bot.modals.recrutement_modal import _ObjectifAddModal
from bot.utils.database import db_get_objectifs, db_del_objectif, db_done_objectif
from bot.utils.permissions import is_staff

""" + sl(1025, 1061) + sl(1074, 1106))
w("views/config_views.py", I + """from bot.utils.config import load_config, save_config, resolve_channel, resolve_role, resolve_category
from bot.utils.helpers import now_utc

""" + sl(3230, 3372))
w("views/game_views.py", I + """from bot.core import bot, active_pendu, active_morpion
from bot.utils.helpers import gk, save_games
from bot.utils.games import (
    PENDU_ART, PENDU_MOTS, build_pendu_embed, build_morpion_embed,
    check_winner, MORPION_EMOJIS, WINS,
    _start_pendu_timer, _start_morpion_timer, _end_pendu, _update_pendu,
)

""" + sl(1964, 2014) + sl(2153, 2239))

w("views/help_view.py", I + sl(3796, 3842))

w("modals/__init__.py", "")
w("modals/vendeur_modal.py", I + sl(3991, 4086))
w("modals/market_modal.py", I + sl(2878, 2894))
w("modals/recrutement_modal.py", I + """from bot.utils.database import db_add_objectif
from bot.utils.embeds import refresh_objectifs_embed

""" + sl(1062, 1071) + "\n\n# Alias module name\n")

w("commands/__init__.py", "")
w("commands/invites.py", I + sl(879, 976))
w("commands/market.py", I + sl(1192, 1280) + sl(2513, 2777) + sl(2933, 2943) + sl(3015, 3061))
w("commands/moderation.py", I + sl(1386, 1551))
w("commands/misc.py", I + """from bot.views.objectif_views import ObjectifView
from bot.utils.embeds import build_objectifs_embed
from bot.utils.database import db_save_objectif_embed
from bot.utils.permissions import is_staff

""" + sl(1109, 1117) + sl(1406, 1423) + sl(3098, 3118) + sl(3387, 3395))
w("commands/classement.py", I + sl(2369, 2495))
w("commands/giveaway.py", I + """from bot.views.giveaway_view import GiveawayView, build_giveaway_embed, parse_duration
from bot.core import active_giveaways

""" + sl(2322, 2363))
w("commands/fidelite.py", I + sl(1873, 1895))
w("commands/help.py", I + "from bot.views.help_view import HelpView\n\n" + sl(3401, 3401) + "\n" + sl(3403, 3851))
w("commands/vendeur.py", I + """from bot.views.vendeur_view import VendeurView
from bot.modals.vendeur_modal import VendeurModal

""" + sl(4121, 4259))
w("commands/config_cmd.py", I + """from bot.views.config_views import _HomeView, _build_home_embed, CONFIG_GROUPS, _fmt_cfg_val, _build_group_embed

""" + sl(3124, 3227) + sl(3375, 3384))
w("commands/games.py", I + """from bot.views.game_views import PenduView, MorpionView
from bot.core import active_pendu, active_morpion, pendu_tasks, morpion_tasks
from bot.utils.helpers import gk, save_games
from bot.utils.games import _start_pendu_timer, _start_morpion_timer, _update_pendu, _end_pendu, build_pendu_embed, build_morpion_embed

""" + sl(2052, 2111) + sl(2261, 2286))

w("events/__init__.py", "")
w("events/invite_events.py", I + sl(848, 876))
w("events/message.py", I + """from bot.utils.market import _auto_delete_in_marche
from bot.core import spam_tracker, spam_warned, xp_cooldowns
from bot.utils.config import load_config
from bot.utils.permissions import is_staff
from bot.utils.logs import send_log
from bot.utils.helpers import now_utc, load_user_data, get_user, save_user_data, xp_for_level

""" + sl(1557, 1607) + sl(1610, 1633) + sl(1636, 1655))
w("events/member_join.py", I + """from bot.utils.invites import on_member_join_invite
from bot.utils.config import load_config, cfg_role, cfg_channel
from bot.utils.helpers import now_utc
from bot.utils.logs import send_log

""" + sl(1661, 1775))
w("events/member_remove.py", I + sl(1778, 1784))
w("events/member_update.py", I + """from bot.utils.config import load_config, cfg_channel
from bot.utils.embeds import build_roster_embed
from bot.utils.logs import send_log
from bot.utils.helpers import now_utc

""" + sl(1787, 1818))
w("events/voice.py", I + sl(1821, 1850))
w("events/channels.py", I + sl(1853, 1867))
w("events/errors.py", I + sl(3857, 3864))
w("events/restore.py", I + """from bot.core import bot, GAMES_DIR, active_pendu, active_morpion, _catalogue_msg_ids, _commande_msg_ids, _auto_refresh_running
from bot.utils.helpers import load_games_for, gk, load_catalogue
from bot.utils.database import get_db, db_save_objectif_embed
from bot.utils.embeds import build_objectifs_embed
from bot.utils.market import _clean_ghost_items, build_catalogue_embed, _get_catalogue_lock
from bot.utils.config import cfg_channel
from bot.utils.games import _start_pendu_timer, _start_morpion_timer

""" + sl(3870, 3981))
rp = ROOT / "bot/events/restore.py"
rp.write_text(
    rp.read_text(encoding="utf-8").replace(
        "view=CommandeView(guild.id, items)",
        "view=__import__('bot.views.market_view', fromlist=['CommandeView']).CommandeView(guild.id, items)",
    ),
    encoding="utf-8",
)
w("events/ready.py", I + """from bot.core import _on_ready_done
from bot.views.ticket_view import TicketView
from bot.views.market_view import RoleToggleView
from bot.views.vendeur_view import VendeurView
from bot.utils.invites import init_invite_cache
from bot.events.restore import (
    _restore_all_games, _restore_all_catalogues, _restore_all_objectifs, _auto_refresh_loop,
)
from bot.utils.config import load_config

""" + sl(4261, 4291))

w("main.py", '''"""Point d\'entrée."""
import os

import bot.core  # noqa: F401
from bot.utils.database import init_db

init_db()

import bot.commands.invites  # noqa: F401
import bot.commands.market  # noqa: F401
import bot.commands.moderation  # noqa: F401
import bot.commands.misc  # noqa: F401
import bot.commands.classement  # noqa: F401
import bot.commands.giveaway  # noqa: F401
import bot.commands.fidelite  # noqa: F401
import bot.commands.help  # noqa: F401
import bot.commands.vendeur  # noqa: F401
import bot.commands.config_cmd  # noqa: F401
import bot.commands.games  # noqa: F401

import bot.events.invite_events  # noqa: F401
import bot.events.message  # noqa: F401
import bot.events.member_join  # noqa: F401
import bot.events.member_remove  # noqa: F401
import bot.events.member_update  # noqa: F401
import bot.events.voice  # noqa: F401
import bot.events.channels  # noqa: F401
import bot.events.errors  # noqa: F401
import bot.events.ready  # noqa: F401

from bot.core import bot


def main():
    bot.run(os.environ.get("DISCORD_TOKEN"))


if __name__ == "__main__":
    main()
''')

# Legacy entry
w("../bot_legacy.py", (ROOT / "bot.py").read_text(encoding="utf-8"))
legacy_main = '''"""Compatibilité : lance le bot modulaire."""
from bot.main import main

if __name__ == "__main__":
    main()
'''
(ROOT / "run_bot.py").write_text(legacy_main, encoding="utf-8")

# Post-patches (lazy imports)
mp = ROOT / "bot/utils/market.py"
mp.write_text(
    mp.read_text(encoding="utf-8").replace(
        "            cmd_view   = CommandeView(guild.id, items)",
        "            from bot.views.market_view import CommandeView\n            cmd_view   = CommandeView(guild.id, items)",
    ),
    encoding="utf-8",
)
ep = ROOT / "bot/utils/embeds.py"
for old, new in [
    ("    view  = ObjectifView(guild.id)", "    from bot.views.objectif_views import ObjectifView\n    view  = ObjectifView(guild.id)"),
]:
    ep.write_text(ep.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")

# Extra imports for split command modules
mk = ROOT / "bot/commands/market.py"
mk.write_text(
    """from bot.utils.market import (
    load_catalogue, save_catalogue, update_catalogue_message, send_notif, fuzzy_search, _parse_prix_num,
)
from bot.utils.config import cfg_channel, resolve_channel, load_config
from bot.utils.permissions import is_staff, is_vendeur, is_staff_market
from bot.utils.helpers import now_utc
from bot.utils.logs import send_log
from bot.views.market_view import _PrixAlertView, _SuppAllView, CommandeView, VenduView, _build_commande_embed_from_items

"""
    + mk.read_text(encoding="utf-8"),
    encoding="utf-8",
)
inv = ROOT / "bot/commands/invites.py"
inv.write_text(
    """from bot.utils.database import db_get_invitations
from bot.utils.helpers import now_utc
import difflib

"""
    + inv.read_text(encoding="utf-8"),
    encoding="utf-8",
)
mod = ROOT / "bot/commands/moderation.py"
mod.write_text(
    """from bot.utils.permissions import is_staff
from bot.utils.config import cfg_channel
from bot.utils.embeds import build_roster_embed
from bot.utils.logs import send_log
from bot.utils.helpers import now_utc
from bot.views.ticket_view import TicketView, FermerView

"""
    + mod.read_text(encoding="utf-8"),
    encoding="utf-8",
)

print("Complete.")
