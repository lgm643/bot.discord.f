import asyncio
from collections import defaultdict
from pathlib import Path

import discord
from discord.ext import commands

# ═══════════════════════════════════════════════════════════════
#  INTENTS & BOT
# ═══════════════════════════════════════════════════════════════

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# ═══════════════════════════════════════════════════════════════
#  RÉPERTOIRES
# ═══════════════════════════════════════════════════════════════

CONFIG_DIR = Path("/app/data/configs")
DATA_DIR = Path("/app/data/users")
GAMES_DIR = Path("/app/data/games")
CATALOGUE_DIR = Path("/app/data/catalogues")
DB_PATH = Path("/app/data/bot.db")

for d in [CONFIG_DIR, DATA_DIR, GAMES_DIR, CATALOGUE_DIR, DB_PATH.parent]:
    d.mkdir(parents=True, exist_ok=True)

# ═══════════════════════════════════════════════════════════════
#  ANTI-SPAM
# ═══════════════════════════════════════════════════════════════

spam_tracker: dict[int, dict[int, list[float]]] = defaultdict(lambda: defaultdict(list))
spam_warned: dict[int, set[int]] = defaultdict(set)

EXEMPT_COMMANDS = {
    "pendu", "devine", "mot", "pileouface", "pof", "coinflip", "pendustop",
    "morpion", "morpionstop",
    "level", "lvl", "xp", "classement", "top", "leaderboard", "lb", "rang", "ranking",
    "giveaway", "gw",
    "pub", "say", "dit", "roster", "membres", "liste", "faction",
    "ticket", "tickets", "support", "fermer", "close", "closeticket", "fermeticket",
    "stock", "recherche",
    "info", "profil", "whois", "user", "membre",
    "help", "aide", "commandes", "setup", "config",
    "gestion", "objectif", "vendu", "cataloguesuppall",
    "invite", "vendeur", "accepter", "refuser",
}


@bot.check
async def check_command_channel(ctx: commands.Context) -> bool:
    from bot.utils.permissions import is_staff, is_vendeur
    from bot.utils.config import cfg_channel, cfg_channels

    cmd = ctx.command.name if ctx.command else ""
    if cmd in EXEMPT_COMMANDS:
        return True
    staff = is_staff(ctx.author)
    if cmd in {"catalogue", "cataloguesupp", "gestion"}:
        if not is_vendeur(ctx.author):
            await ctx.send("❌ Réservé aux vendeurs certifiés.", delete_after=5)
            return False
        allowed_ids: set[int] = set()
        gestion_ch = cfg_channel(ctx.guild, "salon_gestion")
        commande_ch = cfg_channel(ctx.guild, "salon_commandes")
        if gestion_ch:
            allowed_ids.add(gestion_ch.id)
        if commande_ch:
            allowed_ids.add(commande_ch.id)
        if not allowed_ids:
            return True
        if ctx.channel.id not in allowed_ids:
            mentions = " ou ".join(f"<#{c.id}>" for c in [gestion_ch, commande_ch] if c) or "le salon gestion-stock ou commandes"
            await ctx.send(f"❌ Cette commande est réservée à {mentions}.", delete_after=8)
            return False
        return True
    if staff:
        return True
    allowed = cfg_channels(ctx.guild, "salon_cmds_allowed")
    allowed_ids = {c.id for c in allowed}
    if ctx.channel.id not in allowed_ids:
        ch_mentions = " ou ".join(f"<#{c.id}>" for c in allowed) or "les salons dédiés aux commandes"
        await ctx.send(
            f"❌ {ctx.author.mention} Tu ne peux pas utiliser des commandes dans ce salon.\n➡️ Rends-toi dans {ch_mentions}",
            delete_after=8,
        )
        return False
    return True


# ═══════════════════════════════════════════════════════════════
#  JEUX / MARKET — état global partagé
# ═══════════════════════════════════════════════════════════════

active_pendu: dict[str, dict] = {}
active_morpion: dict[str, dict] = {}
pendu_tasks: dict[str, asyncio.Task] = {}
morpion_tasks: dict[str, asyncio.Task] = {}
active_giveaways: dict[int, dict] = {}
_catalogue_msg_ids: dict[int, int] = {}
_commande_msg_ids: dict[int, int] = {}
_pending_orders: dict[str, bool] = {}
_catalogue_lock: dict[int, asyncio.Lock] = {}

_on_ready_done = False
