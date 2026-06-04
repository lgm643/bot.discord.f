"""
core.py — Initialisation du bot et état global.

CORRECTIONS APPLIQUÉES :
  [1] intents.all() → intents ciblés (members, message_content, voice_states)
  [2] Cache config en mémoire avec TTL 30s — élimine les open()+json.load() à chaque permission check
  [3] Cache user_data en mémoire avec dirty-set — élimine les I/O à chaque message XP
  [4] Refresh catalogue : 60s au lieu de 3s (anti rate-limit Discord)
"""
import asyncio
import time
from collections import defaultdict
from pathlib import Path

import discord
from discord.ext import commands

# ── [1] Intents ciblés ───────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.members       = True   # on_member_join/remove/update, get_member()
intents.message_content = True  # lecture du contenu des messages (préfixe !)
intents.voice_states  = True   # suivi du temps vocal
intents.moderation    = True   # lecture de l'Audit Log (kick/ban/move vocal)

bot = commands.Bot(command_prefix="!", intents=intents)

# ── Répertoires de données ────────────────────────────────────────────────────
CONFIG_DIR    = Path("/app/data/configs")
DATA_DIR      = Path("/app/data/users")
GAMES_DIR     = Path("/app/data/games")
CATALOGUE_DIR = Path("/app/data/catalogues")
GIVEAWAYS_DIR = Path("/app/data/giveaways")
DB_PATH       = Path("/app/data/bot.db")

for _d in [CONFIG_DIR, DATA_DIR, GAMES_DIR, CATALOGUE_DIR, GIVEAWAYS_DIR, DB_PATH.parent]:
    _d.mkdir(parents=True, exist_ok=True)

# ── [2] Cache config — plus d'open() à chaque is_staff() / cfg_channel() ─────
_config_cache:    dict[int, dict]  = {}
_config_cache_ts: dict[int, float] = {}
CONFIG_CACHE_TTL = 30.0  # secondes

def invalidate_config_cache(guild_id: int):
    """Appelé automatiquement après chaque save_config()."""
    _config_cache.pop(guild_id, None)
    _config_cache_ts.pop(guild_id, None)

# ── [3] Cache user_data — flush périodique toutes les 60s ────────────────────
_user_data_cache: dict[int, dict] = {}    # guild_id → données
_user_data_dirty: set[int]        = set() # guilds avec modifications non flushées
USER_DATA_FLUSH_INTERVAL = 60  # secondes

# ── Anti-spam ─────────────────────────────────────────────────────────────────
spam_tracker: dict[int, dict[int, list[float]]] = defaultdict(lambda: defaultdict(list))
spam_warned:  dict[int, set[int]]               = defaultdict(set)

EXEMPT_COMMANDS = {
    "pendu", "devine", "mot", "pileouface", "pof", "coinflip", "pendustop",
    "morpion", "morpionstop",
    "level", "lvl", "xp", "classement", "top", "leaderboard", "lb", "rang", "ranking",
    "giveaway", "gw", "reroll",
    "pub", "say", "dit", "roster", "membres", "liste", "faction",
    "ticket", "tickets", "support", "fermer", "close", "closeticket", "fermeticket",
    "stock", "recherche",
    "info", "profil", "whois", "user", "membre",
    "help", "aide", "commandes", "setup", "config",
    "gestion", "objectif", "vendu", "cataloguesuppall", "catalogueview",
    "invite", "topinvites", "vendeur", "accepter", "refuser",
    "statsserveur", "stats", "statistiques", "serverstats",
    "hebdo", "classementsemaine", "weekly",
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
            await ctx.send("❌ Réservé aux vendeurs certifiés.\nSoumets ta candidature via `!vendeur`.", delete_after=10)
            return False
        allowed_ids: set[int] = set()
        gestion_ch  = cfg_channel(ctx.guild, "salon_gestion")
        commande_ch = cfg_channel(ctx.guild, "salon_commandes")
        if gestion_ch:  allowed_ids.add(gestion_ch.id)
        if commande_ch: allowed_ids.add(commande_ch.id)
        if not allowed_ids:
            return True
        if ctx.channel.id not in allowed_ids:
            mentions = " ou ".join(f"<#{c.id}>" for c in [gestion_ch, commande_ch] if c)
            await ctx.send(f"❌ Cette commande est réservée à {mentions}.", delete_after=10)
            return False
        return True
    if staff:
        return True
    allowed     = cfg_channels(ctx.guild, "salon_cmds_allowed")
    allowed_ids = {c.id for c in allowed}
    if not allowed_ids:
        return True
    if ctx.channel.id not in allowed_ids:
        ch_mentions = " ou ".join(f"<#{c.id}>" for c in allowed) or "les salons dédiés aux commandes"
        await ctx.send(
            f"❌ {ctx.author.mention} Utilise les commandes dans {ch_mentions}.",
            delete_after=10,
        )
        return False
    return True


# ── État global partagé ───────────────────────────────────────────────────────
active_pendu:     dict[str, dict]          = {}
active_morpion:   dict[str, dict]          = {}
pendu_tasks:      dict[str, asyncio.Task]  = {}
morpion_tasks:    dict[str, asyncio.Task]  = {}
active_giveaways: dict[int, dict]          = {}

_catalogue_msg_ids: dict[int, int]          = {}
_commande_msg_ids:  dict[int, int]          = {}
_pending_orders:    dict[str, bool]         = {}
_catalogue_lock:    dict[int, asyncio.Lock] = {}

_on_ready_done = False

# [4] Refresh catalogue toutes les 60s (était 3s)
CATALOGUE_REFRESH_INTERVAL = 60