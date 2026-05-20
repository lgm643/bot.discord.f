"""Point d'entrée."""
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
