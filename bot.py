import discord
from discord.ext import commands
import asyncio
import io
import os
import re
import time
import json
import random
import math
import sqlite3
import difflib
from datetime import datetime, timezone
from collections import defaultdict
from pathlib import Path

# ═══════════════════════════════════════════════════════════════
#  INTENTS & BOT
# ═══════════════════════════════════════════════════════════════

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# ═══════════════════════════════════════════════════════════════
#  RÉPERTOIRES
# ═══════════════════════════════════════════════════════════════

CONFIG_DIR    = Path("/app/data/configs")
DATA_DIR      = Path("/app/data/users")
GAMES_DIR     = Path("/app/data/games")
CATALOGUE_DIR = Path("/app/data/catalogues")
DB_PATH       = Path("/app/data/bot.db")

for d in [CONFIG_DIR, DATA_DIR, GAMES_DIR, CATALOGUE_DIR, DB_PATH.parent]:
    d.mkdir(parents=True, exist_ok=True)

# ═══════════════════════════════════════════════════════════════
#  SQLITE — initialisation
# ═══════════════════════════════════════════════════════════════

def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Crée les tables si elles n'existent pas."""
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS objectifs (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                texte    TEXT    NOT NULL,
                done     INTEGER NOT NULL DEFAULT 0,
                created  REAL    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS objectif_embeds (
                guild_id   INTEGER PRIMARY KEY,
                channel_id INTEGER,
                msg_id     INTEGER
            );

            CREATE TABLE IF NOT EXISTS invitations (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id   INTEGER NOT NULL,
                inviter_id INTEGER NOT NULL,
                invited_id INTEGER NOT NULL,
                code       TEXT,
                joined_at  REAL    NOT NULL
            );
        """)

init_db()

# ═══════════════════════════════════════════════════════════════
#  CONFIGURATION
# ═══════════════════════════════════════════════════════════════

DEFAULT_CONFIG = {
    "role_recruteur":       "Recruteur",
    "role_staff":           ["Leader", "Officier"],
    "role_officier":        "Officier",
    "role_leader":          "Leader",
    "role_visiteur":        "visiteur",
    "role_vendeur":         "Vendeur Certifié",
    "role_staff_market":    "Staff Market",
    "role_acheteur_notif":  "Acheteur",
    "role_vendu":           "Vendu",
    "salon_logs":           "logs",
    "salon_roster":         "roster",
    "salon_bienvenue":      "bienvenue",
    "salon_catalogue":      "catalogue",
    "salon_commandes":      "commandes",
    "salon_notifications":  "notifications-market",
    "salon_role_toggle":    "roles",
    "salon_recherche":      "catalogue",
    "salon_ventes_log":     "logs-ventes",
    "salon_cmds_allowed":   ["bot-commands", "commandes"],
    "salon_objectifs":      "",
    "salon_gestion":        "",
    "categorie_tickets":    "Tickets",
    "categorie_commandes":  "Commandes",
    "alt_min_days":         30,
    "raid_window_secs":     60,
    "raid_threshold":       3,
    "spam_limit":           4,
    "spam_window":          6.0,
    "role_roster_leader":    "Leader",
    "role_roster_officier":  "Officier",
    "role_roster_confiance": "Membre de confiance",
    "role_roster_plus":      "Membre +",
    "role_roster_membre":    "Membre",
    "role_roster_recrue":    "Recrue",
    "roster_roles": [
        {"nom": "Leader",             "emoji": "👑"},
        {"nom": "Officier",           "emoji": "⚔️"},
        {"nom": "Membre de confiance","emoji": "🛡️"},
        {"nom": "Membre +",           "emoji": "⭐"},
        {"nom": "Membre",             "emoji": "🔹"},
        {"nom": "Recrue",             "emoji": "🌱"},
    ],
    "faction_roles": ["Leader", "Officier", "Membre de confiance", "Membre +", "Membre", "Recrue"],
    "allowed_domains": ["tenor.com", "giphy.com"],
}


def load_config(guild_id: int) -> dict:
    path = CONFIG_DIR / f"{guild_id}.json"
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            merged = DEFAULT_CONFIG.copy()
            merged.update(data)
            return merged
        except Exception as e:
            print(f"[CONFIG] Erreur lecture {path} : {e}")
    save_config(guild_id, DEFAULT_CONFIG.copy())
    return DEFAULT_CONFIG.copy()


def save_config(guild_id: int, config: dict):
    path = CONFIG_DIR / f"{guild_id}.json"
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[CONFIG] Erreur sauvegarde {path} : {e}")

# ═══════════════════════════════════════════════════════════════
#  RÉSOLUTION SALONS / RÔLES / CATÉGORIES
# ═══════════════════════════════════════════════════════════════

def resolve_role(guild: discord.Guild, name_or_id) -> discord.Role | None:
    if not name_or_id:
        return None
    try:
        rid = int(name_or_id)
        r = guild.get_role(rid)
        if r:
            return r
    except (ValueError, TypeError):
        pass
    name_lower = str(name_or_id).lower()
    return discord.utils.find(lambda r: r.name.lower() == name_lower, guild.roles)


def resolve_roles(guild: discord.Guild, names) -> list[discord.Role]:
    if isinstance(names, (str, int)):
        names = [names]
    result = []
    for n in names:
        r = resolve_role(guild, n)
        if r:
            result.append(r)
    return result


def resolve_channel(guild: discord.Guild, name_or_id) -> discord.abc.GuildChannel | None:
    if not name_or_id:
        return None
    try:
        cid = int(name_or_id)
        ch = guild.get_channel(cid)
        if ch:
            return ch
    except (ValueError, TypeError):
        pass
    name_lower = str(name_or_id).lower()
    return discord.utils.find(lambda c: c.name.lower() == name_lower, guild.channels)


def resolve_channels(guild: discord.Guild, names) -> list[discord.abc.GuildChannel]:
    if isinstance(names, (str, int)):
        names = [names]
    result = []
    for n in names:
        c = resolve_channel(guild, n)
        if c:
            result.append(c)
    return result


def resolve_category(guild: discord.Guild, name_or_id) -> discord.CategoryChannel | None:
    if not name_or_id:
        return None
    try:
        cid = int(name_or_id)
        cat = guild.get_channel(cid)
        if isinstance(cat, discord.CategoryChannel):
            return cat
    except (ValueError, TypeError):
        pass
    name_lower = str(name_or_id).lower()
    return discord.utils.find(
        lambda c: isinstance(c, discord.CategoryChannel) and c.name.lower() == name_lower,
        guild.channels
    )


def cfg_role(guild: discord.Guild, key: str) -> discord.Role | None:
    cfg = load_config(guild.id)
    return resolve_role(guild, cfg.get(key))


def cfg_roles(guild: discord.Guild, key: str) -> list[discord.Role]:
    cfg = load_config(guild.id)
    return resolve_roles(guild, cfg.get(key, []))


def cfg_channel(guild: discord.Guild, key: str) -> discord.abc.GuildChannel | None:
    cfg = load_config(guild.id)
    return resolve_channel(guild, cfg.get(key))


def cfg_channels(guild: discord.Guild, key: str) -> list[discord.abc.GuildChannel]:
    cfg = load_config(guild.id)
    return resolve_channels(guild, cfg.get(key, []))


def cfg_category(guild: discord.Guild, key: str) -> discord.CategoryChannel | None:
    cfg = load_config(guild.id)
    return resolve_category(guild, cfg.get(key))

# ═══════════════════════════════════════════════════════════════
#  HELPERS STAFF / MARKET
# ═══════════════════════════════════════════════════════════════

def is_staff(member: discord.Member) -> bool:
    if member.guild_permissions.administrator:
        return True
    cfg = load_config(member.guild.id)
    staff_names = cfg.get("role_staff", [])
    if isinstance(staff_names, str):
        staff_names = [staff_names]
    staff_roles = resolve_roles(member.guild, staff_names)
    return any(r in member.roles for r in staff_roles)


def is_staff_market(member: discord.Member) -> bool:
    cfg = load_config(member.guild.id)
    role = resolve_role(member.guild, cfg.get("role_staff_market"))
    vendeur = resolve_role(member.guild, cfg.get("role_vendeur"))
    has_market = role and role in member.roles
    has_vendeur = vendeur and vendeur in member.roles
    return has_market or has_vendeur or is_staff(member)


def is_vendeur(member: discord.Member) -> bool:
    cfg = load_config(member.guild.id)
    role = resolve_role(member.guild, cfg.get("role_vendeur"))
    return (role and role in member.roles) or is_staff(member)

# ═══════════════════════════════════════════════════════════════
#  LOGS
# ═══════════════════════════════════════════════════════════════

async def get_log_channel(guild: discord.Guild) -> discord.TextChannel | None:
    return cfg_channel(guild, "salon_logs")


async def send_log(guild: discord.Guild, embed: discord.Embed):
    ch = await get_log_channel(guild)
    if ch:
        try:
            await ch.send(embed=embed)
        except Exception as e:
            print(f"[LOG] Erreur : {e}")

# ═══════════════════════════════════════════════════════════════
#  UTILITAIRES TEMPS / FORMAT
# ═══════════════════════════════════════════════════════════════

def now_str() -> str:
    return discord.utils.format_dt(datetime.now(timezone.utc), style="F")


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def fmt_voice(seconds: float) -> str:
    seconds = int(seconds)
    h, r = divmod(seconds, 3600)
    m, s = divmod(r, 60)
    if h: return f"{h}h {m}m"
    if m: return f"{m}m {s}s"
    return f"{s}s"

# ═══════════════════════════════════════════════════════════════
#  ANTI-SPAM
# ═══════════════════════════════════════════════════════════════

spam_tracker: dict[int, dict[int, list[float]]] = defaultdict(lambda: defaultdict(list))
spam_warned:  dict[int, set[int]] = defaultdict(set)

EXEMPT_COMMANDS = {
    "pendu", "devine", "mot", "pileouface", "pendustop",
    "morpion", "morpionstop",
    "level", "lvl", "xp",
    "classement", "top", "leaderboard",
    "giveaway", "gw",
    "pub", "say", "dit", "fermer", "stock", "recherche",
    "help", "aide", "commandes", "info", "setup",
    "gestion",
    "vendu",
    "cataloguesuppall",
    # Nouvelles commandes exemptées
    "objectif", "objectifs",
    "invite", "invitations", "invites",
}


@bot.check
async def check_command_channel(ctx: commands.Context) -> bool:
    cmd = ctx.command.name if ctx.command else ""

    if cmd in EXEMPT_COMMANDS:
        return True

    staff = is_staff(ctx.author)

    if cmd in {"catalogue", "cataloguesupp", "gestion"}:
        if not is_vendeur(ctx.author):
            await ctx.send("❌ Réservé aux vendeurs certifiés.", delete_after=5)
            return False
        allowed_ids: set[int] = set()
        gestion_ch  = cfg_channel(ctx.guild, "salon_gestion")
        commande_ch = cfg_channel(ctx.guild, "salon_commandes")
        if gestion_ch:  allowed_ids.add(gestion_ch.id)
        if commande_ch: allowed_ids.add(commande_ch.id)
        if not allowed_ids:
            return staff or True
        if ctx.channel.id not in allowed_ids:
            mentions = " ou ".join(
                f"<#{c.id}>" for c in [gestion_ch, commande_ch] if c
            ) or "le salon gestion-stock ou commandes"
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
            f"❌ {ctx.author.mention} Tu ne peux pas utiliser des commandes dans ce salon.\n"
            f"➡️ Rends-toi dans {ch_mentions}",
            delete_after=8
        )
        return False
    return True

# ═══════════════════════════════════════════════════════════════
#  DONNÉES UTILISATEURS (XP / LEVEL)
# ═══════════════════════════════════════════════════════════════

xp_cooldowns: dict[str, float] = {}


def _data_path(guild_id: int) -> Path:
    return DATA_DIR / f"{guild_id}.json"


def load_user_data(guild_id: int) -> dict:
    path = _data_path(guild_id)
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and data:
                return data
        except Exception as e:
            print(f"[DATA] Erreur lecture {path} : {e}")
            backup = str(path) + ".bak"
            if Path(backup).exists():
                try:
                    with open(backup, "r", encoding="utf-8") as f:
                        return json.load(f)
                except Exception:
                    pass
    return {}


def save_user_data(guild_id: int, data: dict):
    if not data:
        return
    path = _data_path(guild_id)
    tmp  = str(path) + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        if path.exists():
            import shutil
            shutil.copy2(path, str(path) + ".bak")
        os.replace(tmp, path)
    except Exception as e:
        print(f"[DATA] Erreur sauvegarde : {e}")


def get_user(data: dict, user_id: int) -> dict:
    uid = str(user_id)
    if uid not in data:
        data[uid] = {"xp": 0, "level": 0, "message_count": 0, "voice_time": 0.0, "voice_join": None}
    return data[uid]


def xp_for_level(level: int) -> int:
    return 100 * (level + 1) + 50 * level * level


def progress_bar(current: int, total: int, length: int = 10) -> str:
    filled = int(length * current / total) if total > 0 else 0
    return "█" * filled + "░" * (length - filled)

# ═══════════════════════════════════════════════════════════════
#  JEUX — VARIABLES GLOBALES
# ═══════════════════════════════════════════════════════════════

active_pendu:    dict[str, dict] = {}
active_morpion:  dict[str, dict] = {}
pendu_tasks:     dict[str, asyncio.Task] = {}
morpion_tasks:   dict[str, asyncio.Task] = {}
active_giveaways: dict[int, dict] = {}


def gk(guild_id: int, channel_id: int) -> str:
    return f"{guild_id}:{channel_id}"


def save_games(guild_id: int):
    path = GAMES_DIR / f"{guild_id}.json"
    data = {}
    for key, g in active_pendu.items():
        gid, ch_id = key.split(":")
        if int(gid) == guild_id:
            data[f"pendu_{ch_id}"] = {
                "word": g["word"], "guessed": list(g["guessed"]),
                "errors": g["errors"], "creator": g["creator"],
                "participants": g["participants"],
                "msg_id": g.get("msg_id"), "end_time": g["end_time"],
            }
    for key, g in active_morpion.items():
        gid, ch_id = key.split(":")
        if int(gid) == guild_id:
            data[f"morpion_{ch_id}"] = {
                "board": g["board"], "players": g["players"],
                "current": g["current"], "msg_id": g.get("msg_id"),
                "end_time": g["end_time"],
            }
    try:
        with open(path, "w") as f:
            json.dump(data, f)
    except Exception as e:
        print(f"[GAMES] Erreur sauvegarde : {e}")


def load_games_for(guild_id: int) -> dict:
    path = GAMES_DIR / f"{guild_id}.json"
    if path.exists():
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            pass
    return {}

# ═══════════════════════════════════════════════════════════════
#  CATALOGUE
# ═══════════════════════════════════════════════════════════════

_catalogue_msg_ids:  dict[int, int] = {}
_commande_msg_ids:   dict[int, int] = {}
_pending_orders:     dict[str, bool] = {}
_catalogue_lock:     dict[int, asyncio.Lock] = {}


def _item_key(nom: str, vendeur_id: int) -> str:
    return f"{nom.lower().strip()}:{vendeur_id}"


def catalogue_path(guild_id: int) -> Path:
    return CATALOGUE_DIR / f"{guild_id}.json"


def load_catalogue(guild_id: int) -> dict:
    path = catalogue_path(guild_id)
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[CATALOGUE] Erreur lecture : {e}")
    return {"items": {}, "msg_id": None, "commande_msg_id": None}


def save_catalogue(guild_id: int, data: dict):
    path = catalogue_path(guild_id)
    tmp  = str(path) + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
    except Exception as e:
        print(f"[CATALOGUE] Erreur sauvegarde : {e}")


def _clean_ghost_items(items: dict) -> dict:
    return {k: v for k, v in items.items() if v.get("quantite", 0) > 0}


def build_catalogue_embed(items: dict) -> discord.Embed:
    embed = discord.Embed(
        title="🏪 Catalogue",
        description="Articles disponibles à la vente :",
        color=0xF1C40F,
        timestamp=now_utc()
    )
    if not items:
        embed.add_field(name="📭 Aucun article", value="Le catalogue est vide.", inline=False)
    else:
        par_vendeur: dict[int, list] = defaultdict(list)
        for key, item in items.items():
            par_vendeur[item["vendeur_id"]].append(item)
        for vendeur_id, arts in par_vendeur.items():
            vendeur_nom = f"<@{vendeur_id}>"
            lignes = "\n".join(
                f"🔹 **{a['nom']}** — 📦 {a['quantite']} · 💰 {a['prix']}"
                for a in arts
            )
            embed.add_field(name=f"👤 {vendeur_nom}", value=lignes, inline=False)
    embed.set_footer(text="Utilisez !commande pour passer une commande")
    return embed


def _get_catalogue_lock(guild_id: int) -> asyncio.Lock:
    if guild_id not in _catalogue_lock:
        _catalogue_lock[guild_id] = asyncio.Lock()
    return _catalogue_lock[guild_id]


async def update_catalogue_message(guild: discord.Guild, items: dict):
    async with _get_catalogue_lock(guild.id):
        items = _clean_ghost_items(items)
        data  = load_catalogue(guild.id)

        cat_ch = cfg_channel(guild, "salon_catalogue")
        if cat_ch:
            embed  = build_catalogue_embed(items)
            msg_id = data.get("msg_id") or _catalogue_msg_ids.get(guild.id)
            if msg_id:
                try:
                    msg = await cat_ch.fetch_message(msg_id)
                    await msg.edit(embed=embed)
                except Exception:
                    msg = await cat_ch.send(embed=embed)
                    _catalogue_msg_ids[guild.id] = msg.id
                    data["msg_id"] = msg.id
            else:
                msg = await cat_ch.send(embed=embed)
                _catalogue_msg_ids[guild.id] = msg.id
                data["msg_id"] = msg.id

        cmd_ch = cfg_channel(guild, "salon_commandes")
        if cmd_ch:
            cmd_embed = _build_commande_embed_from_items(guild, items)
            cmd_view  = CommandeView(guild.id, items)
            cmd_msg_id = data.get("commande_msg_id") or _commande_msg_ids.get(guild.id)
            if cmd_msg_id:
                try:
                    cmd_msg = await cmd_ch.fetch_message(cmd_msg_id)
                    await cmd_msg.edit(embed=cmd_embed, view=cmd_view)
                except Exception:
                    cmd_msg = await cmd_ch.send(embed=cmd_embed, view=cmd_view)
                    _commande_msg_ids[guild.id] = cmd_msg.id
                    data["commande_msg_id"] = cmd_msg.id

        data["items"] = items
        save_catalogue(guild.id, data)


async def send_notif(guild: discord.Guild, texte: str):
    channel = cfg_channel(guild, "salon_notifications")
    role    = cfg_role(guild, "role_acheteur_notif")
    if not channel:
        return
    mention = role.mention if role else ""
    await channel.send(f"{mention} {texte}")

# ═══════════════════════════════════════════════════════════════
#  TRANSCRIPT / TICKETS
# ═══════════════════════════════════════════════════════════════

async def generate_transcript(channel: discord.TextChannel) -> str:
    messages = []
    async for msg in channel.history(limit=None, oldest_first=True):
        ts      = msg.created_at.strftime("%d/%m/%Y %H:%M:%S")
        author  = discord.utils.escape_markdown(str(msg.author))
        content = msg.content.replace("<", "&lt;").replace(">", "&gt;") or "<em>embed/fichier</em>"
        messages.append(f'<tr><td class="ts">{ts}</td><td class="author">{author}</td><td>{content}</td></tr>')
    rows = "\n".join(messages)
    return f"""<!DOCTYPE html><html lang="fr"><head><meta charset="UTF-8">
<title>Transcript – {channel.name}</title><style>
body{{font-family:Arial,sans-serif;background:#1e1e2e;color:#cdd6f4;padding:20px}}
h1{{color:#cba6f7}}table{{width:100%;border-collapse:collapse;margin-top:16px}}
th{{background:#313244;color:#89b4fa;padding:8px 12px;text-align:left}}
td{{padding:6px 12px;border-bottom:1px solid #313244;vertical-align:top}}
.ts{{color:#a6adc8;white-space:nowrap;width:160px}}.author{{color:#f38ba8;white-space:nowrap;width:180px}}
</style></head><body>
<h1>📄 Transcript – #{channel.name}</h1>
<p>Généré le {now_utc().strftime("%d/%m/%Y à %H:%M UTC")}</p>
<table><thead><tr><th>Horodatage</th><th>Auteur</th><th>Message</th></tr></thead>
<tbody>{rows}</tbody></table></body></html>"""


async def send_ticket_log(guild, ticket_channel, closer):
    ch = await get_log_channel(guild)
    if not ch:
        return
    html = await generate_transcript(ticket_channel)
    file = discord.File(fp=io.BytesIO(html.encode("utf-8")), filename=f"transcript-{ticket_channel.name}.html")
    embed = discord.Embed(title="📁 Ticket fermé", color=0x9B59B6, timestamp=now_utc())
    embed.add_field(name="🎫 Ticket",    value=ticket_channel.name, inline=True)
    embed.add_field(name="👤 Fermé par", value=closer.mention,      inline=True)
    embed.add_field(name="🕐 Date",      value=now_str(),            inline=True)
    try:
        await ch.send(embed=embed, file=file)
    except Exception as e:
        print(f"[LOG] Erreur ticket : {e}")

# ═══════════════════════════════════════════════════════════════
#  ROSTER
# ═══════════════════════════════════════════════════════════════

def build_roster_embed(guild: discord.Guild) -> discord.Embed:
    cfg = load_config(guild.id)

    ROSTER_ENTRIES = [
        ("role_roster_leader",    "👑"),
        ("role_roster_officier",  "⚔️"),
        ("role_roster_confiance", "🛡️"),
        ("role_roster_plus",      "⭐"),
        ("role_roster_membre",    "🔹"),
        ("role_roster_recrue",    "🌱"),
    ]

    categories   = {}
    ordered_keys = []
    for cfg_key, emoji in ROSTER_ENTRIES:
        nom  = cfg.get(cfg_key, "")
        role = resolve_role(guild, nom) if nom else None
        if role:
            categories[role.id] = {"label": f"{emoji} {role.name}", "members": []}
            ordered_keys.append(role.id)

    for member in guild.members:
        if member.bot:
            continue
        for rid in ordered_keys:
            if any(r.id == rid for r in member.roles):
                name = member.display_name or member.name
                categories[rid]["members"].append(name)
                break

    embed = discord.Embed(title="📋 Roster", color=0x9B59B6, timestamp=now_utc())
    total = 0
    for rid in ordered_keys:
        cat = categories[rid]
        total += len(cat["members"])
        if cat["members"]:
            embed.add_field(
                name=f"{cat['label']} ({len(cat['members'])})",
                value="\n".join(cat["members"]),
                inline=False
            )
    embed.set_footer(text=f"Total : {total} membres")
    return embed

# ═══════════════════════════════════════════════════════════════
#  OBJECTIFS — SQLITE + EMBED INTERACTIF
# ═══════════════════════════════════════════════════════════════

# ─── DB helpers ────────────────────────────────────────────────

def db_get_objectifs(guild_id: int) -> list[sqlite3.Row]:
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM objectifs WHERE guild_id=? ORDER BY id", (guild_id,)
        ).fetchall()


def db_add_objectif(guild_id: int, texte: str) -> int:
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO objectifs (guild_id, texte, done, created) VALUES (?,?,0,?)",
            (guild_id, texte, time.time())
        )
        return cur.lastrowid


def db_del_objectif(guild_id: int, obj_id: int) -> bool:
    with get_db() as conn:
        cur = conn.execute(
            "DELETE FROM objectifs WHERE id=? AND guild_id=?", (obj_id, guild_id)
        )
        return cur.rowcount > 0


def db_done_objectif(guild_id: int, obj_id: int) -> bool:
    with get_db() as conn:
        cur = conn.execute(
            "UPDATE objectifs SET done=1 WHERE id=? AND guild_id=?", (obj_id, guild_id)
        )
        return cur.rowcount > 0


def db_get_objectif_embed(guild_id: int) -> sqlite3.Row | None:
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM objectif_embeds WHERE guild_id=?", (guild_id,)
        ).fetchone()


def db_save_objectif_embed(guild_id: int, channel_id: int, msg_id: int):
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO objectif_embeds (guild_id, channel_id, msg_id) VALUES (?,?,?)",
            (guild_id, channel_id, msg_id)
        )


# ─── Embed builder ─────────────────────────────────────────────

def build_objectifs_embed(guild_id: int) -> discord.Embed:
    objectifs = db_get_objectifs(guild_id)
    total     = len(objectifs)
    termines  = sum(1 for o in objectifs if o["done"])

    embed = discord.Embed(
        title="🎯 Objectifs du serveur",
        color=0x9B59B6,
        timestamp=now_utc()
    )

    if not objectifs:
        embed.description = (
            "*Aucun objectif pour le moment.*\n\n"
            "Utilisez le bouton **➕ Ajouter** pour créer votre premier objectif."
        )
    else:
        lignes = []
        for obj in objectifs:
            if obj["done"]:
                lignes.append(f"✅  ~~{obj['texte']}~~")
            else:
                lignes.append(f"⏳  **{obj['texte']}**")
        embed.description = "\n".join(lignes)

        pct  = int(termines / total * 100) if total else 0
        fill = int(termines / total * 10)  if total else 0
        bar  = "█" * fill + "░" * (10 - fill)
        embed.add_field(
            name="📊 Progression",
            value=f"`{bar}` {termines}/{total} ({pct}%)",
            inline=False
        )

    embed.set_footer(text="Staff : utilisez les boutons ci-dessous pour gérer les objectifs")
    return embed


# ─── Modal — Ajouter un objectif ───────────────────────────────

class AjouterObjectifModal(discord.ui.Modal, title="➕ Nouvel objectif"):
    texte = discord.ui.TextInput(
        label="Décris l'objectif",
        placeholder="Ex : Farmer 100 paladiums, Construire la base...",
        max_length=200,
        style=discord.TextStyle.short
    )

    def __init__(self, guild_id: int):
        super().__init__()
        self.guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction):
        contenu = str(self.texte).strip()
        if not contenu:
            await interaction.response.send_message(
                embed=discord.Embed(title="❌ Objectif vide", color=0xE74C3C),
                ephemeral=True
            )
            return
        obj_id = db_add_objectif(self.guild_id, contenu)
        await interaction.response.send_message(
            embed=discord.Embed(
                title="✅ Objectif ajouté !",
                description=f"**#{obj_id}** — {contenu}",
                color=0x2ECC71,
                timestamp=now_utc()
            ),
            ephemeral=True
        )
        await refresh_objectifs_embed(interaction.guild)


# ─── Select — action sur un objectif ──────────────────────────

class _ObjectifActionSelect(discord.ui.Select):
    def __init__(self, objectifs: list, action: str, guild_id: int):
        self.action   = action
        self.guild_id = guild_id

        options = []
        for obj in objectifs[:25]:
            icone = "✅" if obj["done"] else "⏳"
            label = f"{icone} #{obj['id']} — {obj['texte']}"
            options.append(discord.SelectOption(label=label[:100], value=str(obj["id"])))

        placeholder = (
            "Choisir l'objectif à cocher…"
            if action == "done"
            else "Choisir l'objectif à supprimer…"
        )
        super().__init__(placeholder=placeholder, options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        obj_id = int(self.values[0])
        guild  = interaction.guild

        if self.action == "done":
            ok    = db_done_objectif(self.guild_id, obj_id)
            title = "✅ Objectif marqué comme terminé !" if ok else "❌ Déjà terminé ou introuvable"
            desc  = (f"L'objectif **#{obj_id}** est maintenant complété ✅" if ok
                     else f"L'objectif **#{obj_id}** n'a pas pu être mis à jour.")
            color = 0x2ECC71 if ok else 0xE74C3C
        else:
            ok    = db_del_objectif(self.guild_id, obj_id)
            title = "✅ Objectif supprimé !" if ok else "❌ Objectif introuvable"
            desc  = (f"L'objectif **#{obj_id}** a été retiré." if ok
                     else f"L'objectif **#{obj_id}** n'existe plus.")
            color = 0x2ECC71 if ok else 0xE74C3C

        await interaction.response.edit_message(
            embed=discord.Embed(title=title, description=desc, color=color, timestamp=now_utc()),
            view=None
        )
        await refresh_objectifs_embed(guild)


class _ObjectifSelectView(discord.ui.View):
    def __init__(self, objectifs: list, action: str, guild_id: int, author_id: int):
        super().__init__(timeout=60)
        self.author_id = author_id
        self.add_item(_ObjectifActionSelect(objectifs, action, guild_id))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Ce menu ne t'appartient pas.", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True


# ─── Vue principale persistante ────────────────────────────────

class ObjectifView(discord.ui.View):
    """Vue persistante attachée à l'embed objectifs (survit aux redémarrages)."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="➕ Ajouter",
        style=discord.ButtonStyle.green,
        custom_id="objectif_v2_ajouter",
        row=0
    )
    async def btn_ajouter(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_staff(interaction.user):
            await interaction.response.send_message("❌ Réservé au staff.", ephemeral=True)
            return
        await interaction.response.send_modal(AjouterObjectifModal(interaction.guild.id))

    @discord.ui.button(
        label="✅ Terminer",
        style=discord.ButtonStyle.blurple,
        custom_id="objectif_v2_terminer",
        row=0
    )
    async def btn_terminer(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_staff(interaction.user):
            await interaction.response.send_message("❌ Réservé au staff.", ephemeral=True)
            return
        objectifs = db_get_objectifs(interaction.guild.id)
        pending   = [o for o in objectifs if not o["done"]]
        if not pending:
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="🎉 Tous les objectifs sont complétés !",
                    description="Il n'y a plus rien à cocher.",
                    color=0x2ECC71
                ),
                ephemeral=True
            )
            return
        view = _ObjectifSelectView(pending, "done", interaction.guild.id, interaction.user.id)
        await interaction.response.send_message(
            embed=discord.Embed(
                title="✅ Marquer comme terminé",
                description="Sélectionne l'objectif à cocher :",
                color=0x3498DB,
                timestamp=now_utc()
            ),
            view=view,
            ephemeral=True
        )

    @discord.ui.button(
        label="🗑️ Supprimer",
        style=discord.ButtonStyle.red,
        custom_id="objectif_v2_supprimer",
        row=0
    )
    async def btn_supprimer(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_staff(interaction.user):
            await interaction.response.send_message("❌ Réservé au staff.", ephemeral=True)
            return
        objectifs = db_get_objectifs(interaction.guild.id)
        if not objectifs:
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="📭 Aucun objectif",
                    description="Il n'y a rien à supprimer.",
                    color=0x95A5A6
                ),
                ephemeral=True
            )
            return
        view = _ObjectifSelectView(objectifs, "supp", interaction.guild.id, interaction.user.id)
        await interaction.response.send_message(
            embed=discord.Embed(
                title="🗑️ Supprimer un objectif",
                description="Sélectionne l'objectif à retirer :",
                color=0xE74C3C,
                timestamp=now_utc()
            ),
            view=view,
            ephemeral=True
        )


# ─── refresh ───────────────────────────────────────────────────

async def refresh_objectifs_embed(guild: discord.Guild):
    """Met à jour l'embed persistant des objectifs avec la vue interactive."""
    row   = db_get_objectif_embed(guild.id)
    embed = build_objectifs_embed(guild.id)
    view  = ObjectifView()

    if row:
        channel = guild.get_channel(row["channel_id"])
        if channel:
            try:
                msg = await channel.fetch_message(row["msg_id"])
                await msg.edit(embed=embed, view=view)
                return
            except discord.NotFound:
                pass
            except Exception as e:
                print(f"[OBJECTIFS] Erreur refresh : {e}")
                return
        channel = channel or cfg_channel(guild, "salon_objectifs")
        if channel:
            msg = await channel.send(embed=embed, view=view)
            db_save_objectif_embed(guild.id, channel.id, msg.id)
        return

    channel = cfg_channel(guild, "salon_objectifs")
    if channel:
        msg = await channel.send(embed=embed, view=view)
        db_save_objectif_embed(guild.id, channel.id, msg.id)


# ─── Commande !objectif ────────────────────────────────────────

@bot.command(name="objectif", aliases=["objectifs"])
async def objectif_cmd(ctx):
    """Affiche ou recrée l'embed interactif des objectifs."""
    if not is_staff(ctx.author):
        await ctx.send("❌ Réservé au staff.", delete_after=5)
        return
    try:
        await ctx.message.delete()
    except Exception:
        pass
    await refresh_objectifs_embed(ctx.guild)
    await ctx.send("✅ Embed objectifs mis à jour !", delete_after=5)

# ═══════════════════════════════════════════════════════════════
#  RECHERCHE INTELLIGENTE (fuzzy)
# ═══════════════════════════════════════════════════════════════

def fuzzy_search(terme: str, items: dict, seuil: float = 0.5) -> dict:
    terme_lower = terme.lower().strip()
    resultats   = {}

    for key, item in items.items():
        nom_lower = item["nom"].lower()
        key_lower = key.lower()

        if terme_lower == nom_lower or terme_lower == key_lower:
            resultats[key] = (item, 1.0)
            continue
        if terme_lower in nom_lower or terme_lower in key_lower:
            resultats[key] = (item, 0.9)
            continue
        score = max(
            difflib.SequenceMatcher(None, terme_lower, nom_lower).ratio(),
            difflib.SequenceMatcher(None, terme_lower, key_lower).ratio()
        )
        if score >= seuil:
            resultats[key] = (item, score)

    return dict(sorted(resultats.items(), key=lambda x: x[1][1], reverse=True))

# ═══════════════════════════════════════════════════════════════
#  SUPPRESSION AUTO DANS SALON COMMANDES
# ═══════════════════════════════════════════════════════════════

async def _auto_delete_in_marche(message: discord.Message):
    if not message.guild:
        return

    cfg    = load_config(message.guild.id)
    cat_ch = resolve_channel(message.guild, cfg.get("salon_catalogue"))
    cmd_ch = resolve_channel(message.guild, cfg.get("salon_commandes"))

    in_cat = cat_ch and message.channel.id == cat_ch.id
    in_cmd = cmd_ch and message.channel.id == cmd_ch.id

    if not (in_cat or in_cmd):
        return

    await asyncio.sleep(1)

    data      = load_catalogue(message.guild.id)
    protected = {
        data.get("msg_id"),
        data.get("commande_msg_id"),
        _catalogue_msg_ids.get(message.guild.id),
        _commande_msg_ids.get(message.guild.id),
    }
    protected.discard(None)

    if message.id in protected:
        return

    try:
        await message.delete()
    except Exception:
        pass

# ═══════════════════════════════════════════════════════════════
#  GESTION STOCK — commande !gestion
# ═══════════════════════════════════════════════════════════════

class _GestionConfirmView(discord.ui.View):
    def __init__(self, author_id: int):
        super().__init__(timeout=60)
        self.author_id = author_id
        self.result    = None

    async def interaction_check(self, i):
        return i.user.id == self.author_id

    @discord.ui.button(label="✅ Confirmer", style=discord.ButtonStyle.green)
    async def confirmer(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.result = True
        self.stop()
        await interaction.response.defer()

    @discord.ui.button(label="❌ Annuler", style=discord.ButtonStyle.red)
    async def annuler(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.result = False
        self.stop()
        await interaction.response.defer()


@bot.command(name="gestion")
async def gestion_cmd(ctx):
    if not is_vendeur(ctx.author):
        await ctx.send("❌ Réservé aux vendeurs certifiés.", delete_after=5)
        return

    cfg        = load_config(ctx.guild.id)
    gestion_ch = resolve_channel(ctx.guild, cfg.get("salon_gestion"))
    if gestion_ch and ctx.channel.id != gestion_ch.id and not is_staff(ctx.author):
        await ctx.send(f"❌ Cette commande est réservée à {gestion_ch.mention}.", delete_after=6)
        return

    def chk(m: discord.Message) -> bool:
        return m.author.id == ctx.author.id and m.channel.id == ctx.channel.id

    async def ask(titre: str, desc: str) -> discord.Message | None:
        q = await ctx.send(embed=discord.Embed(title=titre, description=desc, color=0x3498DB,
                                               timestamp=now_utc()).set_footer(text="60s · 'annuler' pour quitter"))
        try:
            resp = await bot.wait_for("message", check=chk, timeout=60)
            try: await q.delete()
            except Exception: pass
            try: await resp.delete()
            except Exception: pass
            if resp.content.strip().lower() == "annuler":
                await ctx.send("❌ Gestion annulée.", delete_after=5)
                return None
            return resp
        except asyncio.TimeoutError:
            try: await q.delete()
            except Exception: pass
            await ctx.send("⏰ Temps écoulé. Gestion annulée.", delete_after=6)
            return None

    resp_nom = await ask("📦 Étape 1/3 — Nom de l'objet",
                         "Quel est le **nom** de l'article à ajouter/modifier ?")
    if not resp_nom:
        return
    nom = resp_nom.content.strip()

    resp_qty = await ask("📦 Étape 2/3 — Quantité",
                         f"Quelle **quantité** pour **{nom}** ?")
    if not resp_qty:
        return
    try:
        qty = int(resp_qty.content.strip())
        if qty <= 0:
            raise ValueError
    except ValueError:
        await ctx.send("❌ Quantité invalide.", delete_after=6)
        return

    resp_prix = await ask("📦 Étape 3/3 — Prix",
                          f"Quel est le **prix unitaire** pour **{nom}** ?")
    if not resp_prix:
        return
    prix = resp_prix.content.strip()

    data    = load_catalogue(ctx.guild.id)
    items   = data.get("items", {})
    my_key  = _item_key(nom, ctx.author.id)
    nom_low = nom.lower().strip()

    existant_autre = next(
        (v for k, v in items.items()
         if k.split(":")[0] == nom_low and v.get("vendeur_id") != ctx.author.id),
        None
    )
    existant = items.get(my_key)

    if existant_autre and not existant:
        vendeur_existant = ctx.guild.get_member(existant_autre["vendeur_id"])
        vendeur_nom      = vendeur_existant.display_name if vendeur_existant else f"<@{existant_autre['vendeur_id']}>"
        date_ajout       = ""
        if existant_autre.get("created"):
            dt = datetime.fromtimestamp(existant_autre["created"], tz=timezone.utc)
            date_ajout = f"\n📅 **Ajouté le :** {discord.utils.format_dt(dt, style='D')}"

        warn_embed = discord.Embed(
            title="⚠️ Article déjà en vente par un autre vendeur",
            description=(
                f"**{existant_autre['nom']}** est vendu par **{vendeur_nom}**.\n\n"
                f"💰 **Prix actuel :** {existant_autre['prix']}\n"
                f"📦 **Stock actuel :** {existant_autre['quantite']}{date_ajout}\n\n"
                f"Tu peux quand même ajouter ta propre entrée.\nVeux-tu continuer ?"
            ),
            color=0xE67E22,
            timestamp=now_utc()
        )
        view = _GestionConfirmView(ctx.author.id)
        msg_warn = await ctx.send(embed=warn_embed, view=view)
        await view.wait()
        try: await msg_warn.delete()
        except Exception: pass

        if not view.result:
            await ctx.send(embed=discord.Embed(
                title="❌ Gestion annulée",
                description="Le stock n'a pas été modifié.",
                color=0xE74C3C
            ), delete_after=6)
            return

    if existant:
        ancien_prix_num  = _parse_prix_num(existant["prix"])
        nouveau_prix_num = _parse_prix_num(prix)
        items[my_key]["quantite"] += qty
        if ancien_prix_num is not None and nouveau_prix_num is not None:
            if nouveau_prix_num < ancien_prix_num:
                items[my_key]["prix"] = prix
        else:
            items[my_key]["prix"] = prix
        action = f"✏️ **{nom}** mis à jour par {ctx.author.mention} — stock : {items[my_key]['quantite']} · prix : {items[my_key]['prix']}"
    else:
        items[my_key] = {
            "nom":       nom,
            "quantite":  qty,
            "prix":      prix,
            "vendeur_id": ctx.author.id,
            "created":   time.time()
        }
        action = f"➕ **{nom}** ajouté par {ctx.author.mention} — stock : {qty} · prix : {prix}"

    data["items"] = items
    save_catalogue(ctx.guild.id, data)
    await update_catalogue_message(ctx.guild, items)
    await send_notif(ctx.guild, action)
    await send_log(ctx.guild, discord.Embed(
        title="📦 Stock mis à jour via !gestion",
        description=action,
        color=0x2ECC71,
        timestamp=now_utc()
    ))
    await ctx.send(embed=discord.Embed(
        title="✅ Article enregistré",
        description=f"**{nom}** — x{qty} à {prix}",
        color=0x2ECC71,
        timestamp=now_utc()
    ), delete_after=10)

# ═══════════════════════════════════════════════════════════════
#  TICKETS
# ═══════════════════════════════════════════════════════════════

class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="📋 Demande de recrutement", style=discord.ButtonStyle.green, custom_id="ticket_recrutement")
    async def recrutement(self, interaction: discord.Interaction, button: discord.ui.Button):
        await creer_ticket(interaction, "recrutement")

    @discord.ui.button(label="📩 Autre demande", style=discord.ButtonStyle.blurple, custom_id="ticket_autre")
    async def autre(self, interaction: discord.Interaction, button: discord.ui.Button):
        await creer_ticket(interaction, "autre")


class FermerView(discord.ui.View):
    def __init__(self, closer: discord.Member):
        super().__init__(timeout=30)
        self.closer       = closer
        self.action_taken = False
        self._msg         = None

    async def update_countdown(self, message: discord.Message):
        self._msg = message
        for remaining in range(29, 0, -1):
            if self.action_taken:
                return
            await asyncio.sleep(1)
            try:
                embed = discord.Embed(
                    title="🔒 Fermer le ticket",
                    description=f"Es-tu sûr ?\n\n⏳ Expiration dans **{remaining}s**…",
                    color=0xFF0000
                )
                embed.set_footer(text="Aucune action = ticket conservé")
                await message.edit(embed=embed)
            except Exception:
                return

    async def on_timeout(self):
        if self.action_taken:
            return
        self.action_taken = True
        self._disable_all()
        if self._msg:
            embed = discord.Embed(title="⏳ Temps écoulé", description="Le ticket n'a **pas** été fermé.", color=0xE67E22)
            try:
                await self._msg.edit(embed=embed, view=self)
            except Exception:
                pass

    def _disable_all(self):
        for child in self.children:
            child.disabled = True

    @discord.ui.button(label="✅ Confirmer la fermeture", style=discord.ButtonStyle.red, custom_id="fermer_confirmer")
    async def confirmer(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.action_taken:
            await interaction.response.send_message("⚠️ Déjà effectué.", ephemeral=True)
            return
        self.action_taken = True
        self._disable_all()
        self.stop()
        embed = discord.Embed(title="🔒 Fermeture en cours…", description="Suppression dans **5 secondes**.", color=0x2ECC71)
        await interaction.response.edit_message(embed=embed, view=self)
        await send_ticket_log(interaction.guild, interaction.channel, self.closer)
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete()
        except discord.NotFound:
            pass

    @discord.ui.button(label="❌ Annuler", style=discord.ButtonStyle.grey, custom_id="fermer_annuler")
    async def annuler(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.action_taken:
            await interaction.response.send_message("⚠️ Déjà effectué.", ephemeral=True)
            return
        self.action_taken = True
        self._disable_all()
        self.stop()
        embed = discord.Embed(title="❌ Fermeture annulée", description="Le ticket reste ouvert.", color=0x95A5A6)
        await interaction.response.edit_message(embed=embed, view=self)


async def creer_ticket(interaction: discord.Interaction, type_ticket: str):
    guild       = interaction.guild
    staff_roles = cfg_roles(guild, "role_staff")
    recruteur   = cfg_role(guild, "role_recruteur")
    category    = cfg_category(guild, "categorie_tickets")

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        interaction.user:   discord.PermissionOverwrite(view_channel=True, send_messages=True),
    }
    for r in staff_roles:
        overwrites[r] = discord.PermissionOverwrite(view_channel=True, send_messages=True)
    if recruteur and type_ticket == "recrutement":
        overwrites[recruteur] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

    channel = await guild.create_text_channel(
        f"ticket-{interaction.user.name}",
        category=category,
        overwrites=overwrites
    )

    if type_ticket == "recrutement":
        ping = recruteur.mention if recruteur else " ".join(r.mention for r in staff_roles) or "@Staff"
        texte = (
            f"{ping} | {interaction.user.mention}\n\n"
            f"📋 **FORMULAIRE DE RECRUTEMENT – LA MYSTIC**\n\n"
            f"**1️⃣ Présentation personnelle**\n"
            f"➤ Pseudo EXACT en jeu :\n"
            f"➤ Âge (minimum 16 ans) :\n"
            f"➤ Style de jeu : (PvP / Farm / Build / Polyvalent)\n"
            f"➤ Expérience en faction / Points forts :\n\n"
            f"**2️⃣ Objectifs personnels sur le serveur**\n"
            f"➤ Court terme :\n"
            f"➤ Long terme :\n\n"
            f"**3️⃣ Motivation et contribution**\n"
            f"➤ Pourquoi souhaites-tu rejoindre la Mystic ?\n"
            f"➤ Ce que tu recherches dans une faction :\n"
            f"➤ Ce que tu peux apporter à la Mystic :\n\n"
            f"**4️⃣ Historique de factions**\n"
            f"➤ Anciennes factions (si oui, lesquelles ?) :\n"
            f"➤ Raison(s) de départ :\n\n"
            f"**5️⃣ Plateforme et stuff actuel**\n"
            f"➤ Plateforme de jeu : (PlayStation / Xbox / PC / Mobile)\n"
            f"➤ Armure, armes, enchantements importants, ressources notables :\n\n"
            f"**6️⃣ Temps de jeu & disponibilités**\n"
            f"➤ Jours joués par semaine :\n"
            f"➤ Plages horaires approximatives :\n\n"
            f"**7️⃣ Auto-critique**\n"
            f"➤ Quel défaut ou point faible pourrait jouer en ta défaveur dans une faction ?\n\n"
            f"**8️⃣ Mentalité et esprit de faction**\n"
            f"➤ Comment décrirais-tu le membre idéal d'une faction ?\n"
            f"➤ Quelle est ta vision du travail d'équipe ?\n\n"
            f"**9️⃣ Informations complémentaires**\n"
            f"➤ Screenshots OBLIGATOIRES : (stuff, métiers, argent…)\n"
            f"➤ Autres informations importantes : (sanctions passées, contraintes, objectifs spécifiques…)\n\n"
            f"**✅ Confirmation**\n"
            f"☐ J'ai 16 ans ou plus\n"
            f"☐ Je m'engage à respecter les règles de la Mystic\n"
            f"☐ Je comprends que toute fausse information entraînera un refus\n\n"
            f"*Pour fermer ce ticket : `!fermer`*"
        )
    else:
        ping  = " ".join(r.mention for r in staff_roles) or "@Staff"
        texte = f"{ping} | {interaction.user.mention}\n\n📩 **Autre demande**\n\nExplique ta demande, un membre te répondra.\nPour fermer : `!fermer`"

    await channel.send(texte)
    await interaction.response.send_message(f"✅ Ticket créé : {channel.mention}", ephemeral=True)


@bot.command()
async def ticket(ctx):
    if not is_staff(ctx.author):
        await ctx.send("❌ Permission refusée.", delete_after=5)
        return
    embed = discord.Embed(title="🎫 Ouvrir un ticket", description="Choisis le type de demande :", color=0x9B59B6)
    await ctx.send(embed=embed, view=TicketView())


@bot.command()
async def fermer(ctx):
    if "ticket-" not in ctx.channel.name:
        await ctx.send("❌ Uniquement dans un ticket.", delete_after=5)
        return
    view  = FermerView(closer=ctx.author)
    embed = discord.Embed(title="🔒 Fermer le ticket", description="Es-tu sûr ?\n\n⏳ Expiration dans **30s**…", color=0xFF0000)
    embed.set_footer(text="Aucune action = ticket conservé")
    msg = await ctx.send(embed=embed, view=view)
    asyncio.create_task(view.update_countdown(msg))
    await view.wait()


@bot.command()
async def roster(ctx):
    if not is_staff(ctx.author):
        await ctx.send("❌ Permission refusée.", delete_after=5)
        return
    channel = cfg_channel(ctx.guild, "salon_roster")
    if not channel:
        await ctx.send("❌ Salon roster introuvable. Configurez `salon_roster` avec `!setup`.", delete_after=5)
        return
    embed    = build_roster_embed(ctx.guild)
    existing = None
    async for msg in channel.history(limit=20):
        if msg.author == bot.user and msg.embeds:
            existing = msg
            break
    if existing:
        await existing.edit(embed=embed)
        await ctx.send("✅ Roster mis à jour !", delete_after=5)
    else:
        await channel.send(embed=embed)
        await ctx.send(f"✅ Roster posté dans {channel.mention} !", delete_after=5)

# ═══════════════════════════════════════════════════════════════
#  MODÉRATION
# ═══════════════════════════════════════════════════════════════

@bot.command()
async def ban(ctx, member: discord.Member = None, *, reason: str = "Aucune raison fournie"):
    if not is_staff(ctx.author): await ctx.send("❌ Permission refusée.", delete_after=5); return
    if member is None: await ctx.send("❌ `!ban @membre raison`", delete_after=5); return
    try:
        await member.ban(reason=reason, delete_message_days=1)
        await ctx.send(f"🔨 **{member}** banni. Raison : {reason}")
        embed = discord.Embed(title="🔨 Ban", color=0xE74C3C, timestamp=now_utc())
        embed.add_field(name="👤 Membre",     value=f"{member} ({member.id})", inline=True)
        embed.add_field(name="🛡️ Modérateur", value=ctx.author.mention,       inline=True)
        embed.add_field(name="📝 Raison",     value=reason,                   inline=False)
        await send_log(ctx.guild, embed)
    except discord.Forbidden:
        await ctx.send("❌ Je ne peux pas bannir ce membre.", delete_after=5)


@bot.command()
async def kick(ctx, member: discord.Member = None, *, reason: str = "Aucune raison fournie"):
    if not is_staff(ctx.author): await ctx.send("❌ Permission refusée.", delete_after=5); return
    if member is None: await ctx.send("❌ `!kick @membre raison`", delete_after=5); return
    try:
        await member.kick(reason=reason)
        await ctx.send(f"👢 **{member}** expulsé. Raison : {reason}")
        embed = discord.Embed(title="👢 Kick", color=0xE67E22, timestamp=now_utc())
        embed.add_field(name="👤 Membre",     value=f"{member} ({member.id})", inline=True)
        embed.add_field(name="🛡️ Modérateur", value=ctx.author.mention,       inline=True)
        embed.add_field(name="📝 Raison",     value=reason,                   inline=False)
        await send_log(ctx.guild, embed)
    except discord.Forbidden:
        await ctx.send("❌ Je ne peux pas kick ce membre.", delete_after=5)


@bot.command()
async def mute(ctx, member: discord.Member = None, *, reason: str = "Aucune raison fournie"):
    if not is_staff(ctx.author): await ctx.send("❌ Permission refusée.", delete_after=5); return
    if member is None: await ctx.send("❌ `!mute @membre raison`", delete_after=5); return
    mute_role = discord.utils.get(ctx.guild.roles, name="Muted")
    if not mute_role:
        mute_role = await ctx.guild.create_role(name="Muted", reason="Création auto")
        for ch in ctx.guild.channels:
            await ch.set_permissions(mute_role, send_messages=False, speak=False)
    await member.add_roles(mute_role, reason=reason)
    await ctx.send(f"🔇 **{member}** muté. Raison : {reason}")
    embed = discord.Embed(title="🔇 Mute", color=0xE67E22, timestamp=now_utc())
    embed.add_field(name="👤 Membre",     value=f"{member} ({member.id})", inline=True)
    embed.add_field(name="🛡️ Modérateur", value=ctx.author.mention,       inline=True)
    embed.add_field(name="📝 Raison",     value=reason,                   inline=False)
    await send_log(ctx.guild, embed)


@bot.command()
async def unmute(ctx, member: discord.Member = None):
    if not is_staff(ctx.author): await ctx.send("❌ Permission refusée.", delete_after=5); return
    if member is None: await ctx.send("❌ `!unmute @membre`", delete_after=5); return
    mute_role = discord.utils.get(ctx.guild.roles, name="Muted")
    if not mute_role or mute_role not in member.roles:
        await ctx.send("✅ Ce membre n'est pas muté.", delete_after=5); return
    await member.remove_roles(mute_role)
    await ctx.send(f"🔊 **{member}** unmuté.")
    embed = discord.Embed(title="🔊 Unmute", color=0x2ECC71, timestamp=now_utc())
    embed.add_field(name="👤 Membre",     value=f"{member} ({member.id})", inline=True)
    embed.add_field(name="🛡️ Modérateur", value=ctx.author.mention,       inline=True)
    await send_log(ctx.guild, embed)


@bot.command()
async def effacer(ctx, nombre: int = None):
    if not is_staff(ctx.author): await ctx.send("❌ Permission refusée.", delete_after=5); return
    if nombre is None: await ctx.send("❌ `!effacer 10`", delete_after=5); return
    if nombre < 1 or nombre > 100: await ctx.send("❌ Entre 1 et 100.", delete_after=5); return
    deleted = await ctx.channel.purge(limit=nombre + 1)
    await ctx.send(f"🗑️ **{len(deleted) - 1}** messages supprimés.", delete_after=5)
    embed = discord.Embed(title="🗑️ Purge", color=0x95A5A6, timestamp=now_utc())
    embed.add_field(name="🛡️ Modérateur", value=ctx.author.mention,    inline=True)
    embed.add_field(name="📍 Salon",      value=ctx.channel.mention,   inline=True)
    embed.add_field(name="🗑️ Supprimés", value=str(len(deleted) - 1), inline=True)
    await send_log(ctx.guild, embed)


@bot.command()
async def info(ctx, member: discord.Member = None):
    member   = member or ctx.author
    roles    = [r.mention for r in reversed(member.roles) if r.name != "@everyone"]
    top_role = member.top_role.mention if member.top_role.name != "@everyone" else "Aucun"
    perms = []
    if member.guild_permissions.administrator:   perms.append("👑 Administrateur")
    if member.guild_permissions.manage_guild:    perms.append("⚙️ Gérer le serveur")
    if member.guild_permissions.ban_members:     perms.append("🔨 Bannir")
    if member.guild_permissions.kick_members:    perms.append("👢 Expulser")
    if member.guild_permissions.manage_messages: perms.append("🗑️ Gérer messages")
    if member.guild_permissions.manage_roles:    perms.append("🎭 Gérer rôles")
    status_map = {
        discord.Status.online:  "🟢 En ligne",
        discord.Status.idle:    "🟡 Absent",
        discord.Status.dnd:     "🔴 Ne pas déranger",
        discord.Status.offline: "⚫ Hors ligne",
    }
    status   = status_map.get(member.status, "⚫ Inconnu")
    activity = "Aucune"
    if member.activity:
        if isinstance(member.activity, discord.Game):             activity = f"🎮 {member.activity.name}"
        elif isinstance(member.activity, discord.Streaming):      activity = f"📺 {member.activity.name}"
        elif isinstance(member.activity, discord.CustomActivity): activity = f"💬 {member.activity.name}"
        else:                                                      activity = member.activity.name
    embed = discord.Embed(
        title=f"👤 {member.display_name}",
        color=member.color if member.color != discord.Color.default() else 0x3498DB,
        timestamp=now_utc()
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    if member.banner: embed.set_image(url=member.banner.url)
    embed.add_field(name="📛 Pseudo",         value=member.display_name, inline=True)
    embed.add_field(name="🏷️ Tag",            value=str(member),         inline=True)
    embed.add_field(name="🤖 Bot",             value="✅" if member.bot else "❌", inline=True)
    embed.add_field(name="🆔 ID",              value=str(member.id),     inline=True)
    embed.add_field(name="📅 Compte créé",     value=discord.utils.format_dt(member.created_at, style="D"), inline=True)
    embed.add_field(name="📥 Arrivée serveur", value=discord.utils.format_dt(member.joined_at, style="D") if member.joined_at else "?", inline=True)
    embed.add_field(name="📶 Statut",          value=status,   inline=True)
    embed.add_field(name="🎯 Activité",        value=activity, inline=True)
    embed.add_field(name="🎖️ Rôle principal",  value=top_role, inline=True)
    embed.add_field(name=f"🎭 Rôles ({len(roles)})", value=", ".join(roles[:20]) or "Aucun", inline=False)
    embed.add_field(name="🔑 Permissions",     value=", ".join(perms) or "Aucune", inline=False)
    embed.set_footer(text=f"Demandé par {ctx.author}")
    await ctx.send(embed=embed)


@bot.command(name="say", aliases=["dit"])
async def say_cmd(ctx, channel: discord.TextChannel = None, *, message: str = None):
    if not is_staff(ctx.author):
        await ctx.send("❌ Réservé au staff.", delete_after=5)
        return
    if channel is None or message is None:
        await ctx.send("❌ Utilisation : `!say #salon message`", delete_after=8)
        return
    try:
        await ctx.message.delete()
    except Exception:
        pass
    try:
        await channel.send(message)
    except discord.Forbidden:
        await ctx.send(f"❌ Je n'ai pas la permission d'envoyer dans {channel.mention}.", delete_after=6)

# ═══════════════════════════════════════════════════════════════
#  EVENTS — on_message
# ═══════════════════════════════════════════════════════════════

@bot.event
async def on_message(message: discord.Message):
    if not message.guild:
        if not message.author.bot:
            await bot.process_commands(message)
        return

    asyncio.create_task(_auto_delete_in_marche(message))

    if message.author.bot:
        return

    member = message.author
    cfg    = load_config(message.guild.id)

    # ── Anti-lien
    url_pattern = re.compile(r"(https?://|www\.)\S+", re.IGNORECASE)
    if url_pattern.search(message.content) and not member.guild_permissions.administrator:
        allowed_domains = cfg.get("allowed_domains", ["tenor.com", "giphy.com"])
        domain_match = re.search(r"(?:https?://|www\.)([^/\s]+)", message.content, re.IGNORECASE)
        domain = domain_match.group(1).lower() if domain_match else ""
        if not any(domain == d or domain.endswith("." + d) for d in allowed_domains):
            try:
                await message.delete()
                await message.channel.send(f"❌ {member.mention} Tu n'as pas la permission d'envoyer des liens ici.", delete_after=6)
                embed = discord.Embed(title="🔗 Lien bloqué", color=0xE74C3C, timestamp=now_utc())
                embed.add_field(name="👤 Auteur",  value=f"{member} ({member.id})", inline=True)
                embed.add_field(name="📍 Salon",   value=message.channel.mention,   inline=True)
                embed.add_field(name="💬 Contenu", value=message.content[:500],     inline=False)
                await send_log(message.guild, embed)
            except Exception:
                pass
            return

    # ── Anti-spam
    if not is_staff(member):
        spam_limit  = cfg.get("spam_limit", 4)
        spam_window = cfg.get("spam_window", 6.0)
        gid         = message.guild.id
        uid         = member.id
        now_m       = time.monotonic()
        spam_tracker[gid][uid].append(now_m)
        spam_tracker[gid][uid] = [t for t in spam_tracker[gid][uid] if now_m - t <= spam_window]
        if len(spam_tracker[gid][uid]) > spam_limit:
            if uid in spam_warned[gid]:
                spam_warned[gid].discard(uid)
                spam_tracker[gid].pop(uid, None)
                try:
                    await member.kick(reason="Anti-spam automatique")
                    await message.channel.send(f"🚫 {member.mention} expulsé pour spam répété.", delete_after=10)
                    embed = discord.Embed(title="🚫 Kick Anti-Spam", color=0xE74C3C, timestamp=now_utc())
                    embed.add_field(name="👤 Membre", value=f"{member} ({member.id})", inline=True)
                    await send_log(message.guild, embed)
                except discord.Forbidden:
                    pass
            else:
                spam_warned[gid].add(uid)
                spam_tracker[gid][uid] = []
                await message.channel.send(f"⚠️ {member.mention} **Stop le spam !** Prochaine fois = **expulsion automatique**.", delete_after=10)

    await bot.process_commands(message)


@bot.listen("on_message")
async def xp_on_message(message: discord.Message):
    if message.author.bot or not message.guild:
        return
    uid = message.author.id
    gid = message.guild.id
    key = f"{gid}:{uid}"
    now = time.monotonic()
    if now - xp_cooldowns.get(key, 0) < 10:
        return
    xp_cooldowns[key] = now
    data = load_user_data(gid)
    u    = get_user(data, uid)
    u["message_count"] += 1
    gained   = random.randint(5, 15)
    u["xp"] += gained
    old_level = u["level"]
    required  = xp_for_level(old_level + 1)
    if u["xp"] >= required:
        u["level"] += 1
        u["xp"]    -= required
        save_user_data(gid, data)
        msg = await message.channel.send(f"🎉 {message.author.mention} passe niveau **{u['level']}** ! GG 🔥")
        await asyncio.sleep(2)
        try:
            await msg.delete()
        except Exception:
            pass
        return
    save_user_data(gid, data)


@bot.event
async def on_message_delete(message: discord.Message):
    if message.author.bot or not message.guild:
        return
    embed = discord.Embed(title="🗑️ Message supprimé", color=0x95A5A6, timestamp=now_utc())
    embed.add_field(name="👤 Auteur",  value=f"{message.author} ({message.author.id})", inline=True)
    embed.add_field(name="📍 Salon",   value=message.channel.mention,                   inline=True)
    embed.add_field(name="💬 Contenu", value=message.content[:1000] or "<vide>",        inline=False)
    await send_log(message.guild, embed)


@bot.event
async def on_message_edit(before: discord.Message, after: discord.Message):
    if before.author.bot or not before.guild or before.content == after.content:
        return
    embed = discord.Embed(title="✏️ Message modifié", color=0x3498DB, timestamp=now_utc())
    embed.add_field(name="👤 Auteur", value=f"{before.author} ({before.author.id})", inline=True)
    embed.add_field(name="📍 Salon",  value=before.channel.mention,                  inline=True)
    embed.add_field(name="📝 Avant",  value=before.content[:500] or "<vide>",        inline=False)
    embed.add_field(name="📝 Après",  value=after.content[:500] or "<vide>",         inline=False)
    embed.add_field(name="🔗 Lien",   value=f"[Voir]({after.jump_url})",             inline=True)
    await send_log(before.guild, embed)

# ═══════════════════════════════════════════════════════════════
#  ANTI-ALT / ANTI-RAID
# ═══════════════════════════════════════════════════════════════

_recent_suspects: dict[int, list[float]] = defaultdict(list)


def _analyse_alt(member: discord.Member, cfg: dict) -> list[str]:
    reasons  = []
    now      = datetime.now(timezone.utc)
    age_days = (now - member.created_at).days
    alt_min  = cfg.get("alt_min_days", 30)
    if age_days < alt_min:
        reasons.append(f"Compte récent ({age_days} jour(s))")
    if member.avatar is None:
        reasons.append("Pas d'avatar personnalisé")
    return reasons


async def _send_alt_alert(member: discord.Member, reasons: list[str]):
    log_channel = await get_log_channel(member.guild)
    if not log_channel:
        return
    age_days    = (datetime.now(timezone.utc) - member.created_at).days
    officier    = cfg_role(member.guild, "role_officier")
    leader      = cfg_role(member.guild, "role_leader")
    mentions    = " ".join(r.mention for r in [officier, leader] if r)
    raisons_str = "\n".join(f"- {r}" for r in reasons)
    embed = discord.Embed(title="⚠️ COMPTE SUSPECT — ALT POSSIBLE", color=0xFF6B00, timestamp=now_utc())
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="👤 Utilisateur",    value=f"{member.mention} ({member.id})", inline=False)
    embed.add_field(name="📅 Compte créé le", value=discord.utils.format_dt(member.created_at, style="F"), inline=True)
    embed.add_field(name="⏱️ Âge du compte",  value=f"{age_days} jour(s)",             inline=True)
    embed.add_field(name="📌 Raisons",        value=raisons_str,                        inline=False)
    embed.set_footer(text="Système Anti-Alt automatique")
    await log_channel.send(content=f"⚠️ **ATTENTION** : ALT possible ! {mentions}", embed=embed)


async def _check_raid(guild: discord.Guild, cfg: dict):
    window    = cfg.get("raid_window_secs", 60)
    threshold = cfg.get("raid_threshold", 3)
    now       = time.time()
    _recent_suspects[guild.id] = [t for t in _recent_suspects[guild.id] if now - t < window]
    _recent_suspects[guild.id].append(now)
    if len(_recent_suspects[guild.id]) >= threshold:
        _recent_suspects[guild.id].clear()
        log_channel = await get_log_channel(guild)
        if log_channel:
            officier = cfg_role(guild, "role_officier")
            leader   = cfg_role(guild, "role_leader")
            mentions = " ".join(r.mention for r in [officier, leader] if r)
            embed = discord.Embed(
                title="🚨 RAID POSSIBLE DÉTECTÉ",
                description=f"**{threshold}+** comptes suspects ont rejoint en moins de **{window}s** !",
                color=0xFF0000, timestamp=now_utc()
            )
            await log_channel.send(content=f"🚨 **RAID POSSIBLE !** {mentions}", embed=embed)

# ═══════════════════════════════════════════════════════════════
#  SUIVI DES INVITATIONS
# ═══════════════════════════════════════════════════════════════

_invite_cache: dict[int, dict[str, discord.Invite]] = {}


async def _cache_guild_invites(guild: discord.Guild):
    """Met à jour le cache des invitations d'un serveur."""
    try:
        invites = await guild.fetch_invites()
        _invite_cache[guild.id] = {inv.code: inv for inv in invites}
    except Exception as e:
        print(f"[INVITES] Impossible de charger guild={guild.id} : {e}")


async def _cache_all_invites():
    """Charge le cache d'invitations pour tous les serveurs au démarrage."""
    for guild in bot.guilds:
        await _cache_guild_invites(guild)
    print(f"[INVITES] Cache chargé pour {len(bot.guilds)} serveur(s).")


# ─── DB helpers ────────────────────────────────────────────────

def db_record_invite(guild_id: int, inviter_id: int, invited_id: int, code: str | None):
    with get_db() as conn:
        conn.execute(
            "INSERT INTO invitations (guild_id, inviter_id, invited_id, code, joined_at) VALUES (?,?,?,?,?)",
            (guild_id, inviter_id, invited_id, code, time.time())
        )


def db_get_invites_by(guild_id: int, inviter_id: int) -> list[sqlite3.Row]:
    with get_db() as conn:
        return conn.execute(
            "SELECT invited_id, code, joined_at FROM invitations "
            "WHERE guild_id=? AND inviter_id=? ORDER BY joined_at DESC",
            (guild_id, inviter_id)
        ).fetchall()


def db_search_member(query: str, guild: discord.Guild) -> list[discord.Member]:
    """Recherche intelligente multi-méthodes (exacte → sous-chaîne → fuzzy)."""
    q       = query.lower().strip()
    exact   = []
    partial = []
    fuzzy_r = []

    for member in guild.members:
        if member.bot:
            continue
        dn = member.display_name.lower()
        un = member.name.lower()

        if q == dn or q == un:
            exact.append(member)
        elif q in dn or q in un or dn.startswith(q):
            partial.append(member)
        else:
            score = max(
                difflib.SequenceMatcher(None, q, dn).ratio(),
                difflib.SequenceMatcher(None, q, un).ratio()
            )
            if score >= 0.55:
                fuzzy_r.append((member, score))

    fuzzy_r.sort(key=lambda x: x[1], reverse=True)
    return (exact + partial + [m for m, _ in fuzzy_r])[:5]


# ─── Tracking à l'arrivée ──────────────────────────────────────

async def _track_invite_used(guild: discord.Guild, member: discord.Member):
    """Détermine quelle invitation a été utilisée et l'enregistre en DB."""
    old_cache = _invite_cache.get(guild.id, {})

    try:
        new_invites = await guild.fetch_invites()
    except discord.Forbidden:
        print(f"[INVITES] Permission manquante pour guild={guild.id} (MANAGE_GUILD requis).")
        return
    except Exception as e:
        print(f"[INVITES] Erreur fetch guild={guild.id} : {e}")
        return

    new_cache: dict[str, discord.Invite] = {inv.code: inv for inv in new_invites}

    inviter_id: int | None = None
    used_code:  str | None = None

    # Cas 1 : compteur augmenté
    for code, new_inv in new_cache.items():
        old_uses = old_cache[code].uses if code in old_cache else 0
        if new_inv.uses > old_uses:
            inviter_id = new_inv.inviter.id if new_inv.inviter else None
            used_code  = code
            break

    # Cas 2 : invitation à usage unique disparue
    if inviter_id is None:
        for code, old_inv in old_cache.items():
            if code not in new_cache and old_inv.max_uses == 1:
                inviter_id = old_inv.inviter.id if old_inv.inviter else None
                used_code  = code
                break

    _invite_cache[guild.id] = new_cache

    if inviter_id:
        db_record_invite(guild.id, inviter_id, member.id, used_code)
        print(f"[INVITES] {member.display_name} invité par ID={inviter_id} (code={used_code})")
    else:
        print(f"[INVITES] Inviteur introuvable pour {member.display_name}")


# ─── Mise à jour du cache (invitations créées / supprimées) ────

@bot.event
async def on_invite_create(invite: discord.Invite):
    if invite.guild:
        _invite_cache.setdefault(invite.guild.id, {})[invite.code] = invite


@bot.event
async def on_invite_delete(invite: discord.Invite):
    if invite.guild:
        _invite_cache.get(invite.guild.id, {}).pop(invite.code, None)


# ─── Commande !invite ──────────────────────────────────────────

@bot.command(name="invite", aliases=["invitations", "invites"])
async def invite_cmd(ctx, *, joueur: str = None):
    """Affiche les invitations d'un joueur (ou les siennes par défaut)."""

    # Résolution du joueur cible
    if joueur is None:
        target = ctx.author
    elif ctx.message.mentions:
        target = ctx.message.mentions[0]
    else:
        resultats = db_search_member(joueur, ctx.guild)
        if not resultats:
            await ctx.send(embed=discord.Embed(
                title="❌ Joueur introuvable",
                description=f"Aucun membre trouvé pour **{joueur}**.\nVérifie l'orthographe du pseudo.",
                color=0xE74C3C
            ), delete_after=12)
            return

        if len(resultats) > 1:
            desc = "\n".join(f"• **{m.display_name}** (`{m.name}`)" for m in resultats)
            await ctx.send(embed=discord.Embed(
                title="🔍 Plusieurs joueurs trouvés",
                description=f"Sois plus précis :\n{desc}\n\nEx : `!invite {resultats[0].display_name}`",
                color=0xE67E22
            ), delete_after=20)
            return

        target = resultats[0]

    rows = db_get_invites_by(ctx.guild.id, target.id)

    if not rows:
        await ctx.send(embed=discord.Embed(
            title=f"📨 Invitations de {target.display_name}",
            description="❌ Ce joueur n'a encore invité personne.",
            color=0xE74C3C
        ))
        return

    total      = len(rows)
    encore_la  = sum(1 for r in rows if ctx.guild.get_member(r["invited_id"]) is not None)
    partis     = total - encore_la

    embed = discord.Embed(
        title=f"📨 Invitations de {target.display_name}",
        color=0x9B59B6,
        timestamp=now_utc()
    )
    embed.set_thumbnail(url=target.display_avatar.url)
    embed.add_field(name="👥 Total invités",    value=f"**{total}**",      inline=True)
    embed.add_field(name="✅ Encore membres",   value=f"**{encore_la}**",  inline=True)
    embed.add_field(name="📤 Partis",           value=f"**{partis}**",     inline=True)

    lignes = []
    for row in rows[:20]:
        member = ctx.guild.get_member(row["invited_id"])
        ts     = f"<t:{int(row['joined_at'])}:d>"
        if member:
            lignes.append(f"• **{member.display_name}** — {ts}")
        else:
            lignes.append(f"• ~~Joueur parti~~ — {ts}")

    if total > 20:
        lignes.append(f"*…et {total - 20} autre(s) non affichés*")

    embed.add_field(name="📋 Joueurs invités", value="\n".join(lignes), inline=False)
    embed.set_footer(text="Données enregistrées depuis l'activation du système d'invitations")
    await ctx.send(embed=embed)

# ═══════════════════════════════════════════════════════════════
#  EVENTS MEMBRES
# ═══════════════════════════════════════════════════════════════

@bot.event
async def on_member_join(member: discord.Member):
    cfg = load_config(member.guild.id)

    # ── Suivi des invitations (en premier) ──
    asyncio.create_task(_track_invite_used(member.guild, member))

    # ── Rôle visiteur ──
    visitor_role = cfg_role(member.guild, "role_visiteur")
    if visitor_role:
        try:
            await member.add_roles(visitor_role, reason="Rôle visiteur automatique")
        except Exception as e:
            print(f"[WELCOME] Erreur rôle visiteur : {e}")

    # ── Message de bienvenue ──
    welcome_channel = cfg_channel(member.guild, "salon_bienvenue")
    if welcome_channel:
        try:
            await welcome_channel.send(
                f"Hey {member.mention} 👋\n"
                f"Bienvenue sur le Discord de **{member.guild.name}** 👑\n"
                f"N'hésite pas à ouvrir un ticket si tu as une question. On est là 🙌"
            )
        except Exception as e:
            print(f"[WELCOME] Erreur envoi bienvenue : {e}")

    # ── Log d'arrivée ──
    age_days = (datetime.now(timezone.utc) - member.created_at).days
    embed = discord.Embed(title="📥 Membre arrivé", color=0x2ECC71, timestamp=now_utc())
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="👤 Membre",      value=f"{member} ({member.id})",                              inline=True)
    embed.add_field(name="📅 Compte créé", value=discord.utils.format_dt(member.created_at, style="D"), inline=True)
    embed.add_field(name="⏱️ Âge",         value=f"{age_days} jour(s)",                                  inline=True)
    embed.add_field(name="👥 Total",       value=str(member.guild.member_count),                          inline=True)
    await send_log(member.guild, embed)

    # ── Anti-alt / anti-raid ──
    reasons = _analyse_alt(member, cfg)
    if reasons:
        await _send_alt_alert(member, reasons)
        await _check_raid(member.guild, cfg)


@bot.event
async def on_member_remove(member: discord.Member):
    embed = discord.Embed(title="📤 Membre parti", color=0xE74C3C, timestamp=now_utc())
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="👤 Membre", value=f"{member} ({member.id})",      inline=True)
    embed.add_field(name="👥 Total",  value=str(member.guild.member_count), inline=True)
    await send_log(member.guild, embed)


@bot.event
async def on_member_update(before: discord.Member, after: discord.Member):
    cfg         = load_config(after.guild.id)
    roster_cfg  = cfg.get("roster_roles", [])
    roster_names = {entry["nom"].lower() for entry in roster_cfg}
    before_roster = {r.name.lower() for r in before.roles if r.name.lower() in roster_names}
    after_roster  = {r.name.lower() for r in after.roles  if r.name.lower() in roster_names}
    if before_roster != after_roster:
        channel = cfg_channel(after.guild, "salon_roster")
        if channel:
            try:
                embed = build_roster_embed(after.guild)
                async for msg in channel.history(limit=20):
                    if msg.author == bot.user and msg.embeds:
                        await msg.edit(embed=embed)
                        break
                else:
                    await channel.send(embed=embed)
            except Exception:
                pass

    added   = set(after.roles) - set(before.roles)
    removed = set(before.roles) - set(after.roles)
    if added or removed:
        embed = discord.Embed(title="🎭 Rôles modifiés", color=0x9B59B6, timestamp=now_utc())
        embed.add_field(name="👤 Membre", value=f"{after} ({after.id})", inline=True)
        if added:
            embed.add_field(name="✅ Ajoutés",  value=", ".join(r.mention for r in added),   inline=False)
        if removed:
            embed.add_field(name="❌ Retirés",  value=", ".join(r.mention for r in removed), inline=False)
        await send_log(after.guild, embed)

    if before.display_name != after.display_name:
        embed = discord.Embed(title="📝 Pseudo modifié", color=0x3498DB, timestamp=now_utc())
        embed.add_field(name="👤 Membre", value=f"{after} ({after.id})", inline=True)
        embed.add_field(name="📝 Avant",  value=before.display_name,     inline=True)
        embed.add_field(name="📝 Après",  value=after.display_name,      inline=True)
        await send_log(after.guild, embed)


@bot.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    if member.bot:
        return
    gid  = member.guild.id
    data = load_user_data(gid)
    u    = get_user(data, member.id)
    now  = time.time()

    if before.channel is None and after.channel is not None:
        u["voice_join"] = now
    elif before.channel is not None and after.channel is None:
        if u.get("voice_join"):
            u["voice_time"] += now - u["voice_join"]
            u["voice_join"]  = None
    save_user_data(gid, data)

    if before.channel is None and after.channel is not None:
        embed = discord.Embed(title="🔊 Connexion vocale", color=0x2ECC71, timestamp=now_utc())
        embed.add_field(name="👤 Membre", value=f"{member} ({member.id})", inline=True)
        embed.add_field(name="📍 Salon",  value=after.channel.name,        inline=True)
        await send_log(member.guild, embed)
    elif before.channel is not None and after.channel is None:
        embed = discord.Embed(title="🔇 Déconnexion vocale", color=0xE74C3C, timestamp=now_utc())
        embed.add_field(name="👤 Membre", value=f"{member} ({member.id})", inline=True)
        embed.add_field(name="📍 Salon",  value=before.channel.name,       inline=True)
        await send_log(member.guild, embed)
    elif before.channel is not None and after.channel is not None and before.channel != after.channel:
        embed = discord.Embed(title="🔄 Changement de salon vocal", color=0x3498DB, timestamp=now_utc())
        embed.add_field(name="👤 Membre", value=f"{member} ({member.id})", inline=True)
        embed.add_field(name="📤 Avant",  value=before.channel.name,       inline=True)
        embed.add_field(name="📥 Après",  value=after.channel.name,        inline=True)
        await send_log(member.guild, embed)


@bot.event
async def on_guild_channel_create(channel):
    embed = discord.Embed(title="📢 Salon créé", color=0x2ECC71, timestamp=now_utc())
    embed.add_field(name="📍 Nom",       value=channel.name,      inline=True)
    embed.add_field(name="📂 Type",      value=str(channel.type), inline=True)
    embed.add_field(name="🗂️ Catégorie", value=channel.category.name if channel.category else "Aucune", inline=True)
    await send_log(channel.guild, embed)


@bot.event
async def on_guild_channel_delete(channel):
    embed = discord.Embed(title="🗑️ Salon supprimé", color=0xE74C3C, timestamp=now_utc())
    embed.add_field(name="📍 Nom",       value=channel.name,      inline=True)
    embed.add_field(name="📂 Type",      value=str(channel.type), inline=True)
    embed.add_field(name="🗂️ Catégorie", value=channel.category.name if channel.category else "Aucune", inline=True)
    await send_log(channel.guild, embed)

# ═══════════════════════════════════════════════════════════════
#  XP / LEVEL
# ═══════════════════════════════════════════════════════════════

@bot.command(name="level", aliases=["lvl", "xp"])
async def level_cmd(ctx, member: discord.Member = None):
    member   = member or ctx.author
    data     = load_user_data(ctx.guild.id)
    u        = get_user(data, member.id)
    save_user_data(ctx.guild.id, data)
    lvl      = u["level"]
    cur_xp   = u["xp"]
    required = xp_for_level(lvl + 1)
    bar      = progress_bar(cur_xp, required)
    embed    = discord.Embed(
        title=f"📊 Niveau — {member.display_name}",
        color=member.color if member.color != discord.Color.default() else 0x9B59B6,
        timestamp=now_utc()
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="🏆 Niveau",   value=str(lvl),                  inline=True)
    embed.add_field(name="✉️ Messages", value=str(u["message_count"]),    inline=True)
    embed.add_field(name="🎤 Vocal",    value=fmt_voice(u["voice_time"]), inline=True)
    embed.add_field(name=f"⭐ XP — {cur_xp}/{required}",
        value=f"`{bar}` {int(cur_xp/required*100)}%", inline=False)
    await ctx.send(embed=embed)


@bot.command(name="pileouface", aliases=["pof", "coinflip"])
async def pof_cmd(ctx):
    result = random.choice(["🪙 **Pile**", "🔵 **Face**"])
    embed  = discord.Embed(title="🪙 Pile ou Face", description=f"Résultat : {result}", color=0xF1C40F)
    await ctx.send(embed=embed)

# ═══════════════════════════════════════════════════════════════
#  PENDU
# ═══════════════════════════════════════════════════════════════

PENDU_MOTS = [
    "horloge","montagne","riviere","ocean","plage","desert","foret","ile","vallee","colline",
    "nuage","orage","tempete","pluie","neige","vent","soleil","lune","etoile","ciel",
    "musique","chanson","instrument","guitare","piano","batterie","violon","concert","festival","spectacle",
    "film","cinema","acteur","realisateur","scene","camera","studio","projection","serie","episode",
    "livre","roman","auteur","lecture","bibliotheque","page","chapitre","histoire","conte","poeme",
    "faction","alliance","serveur","armure","epee","bouclier","ressource","territoire",
    "combat","recrue","officier","leader","victoire","forteresse","invasion","guilde",
    "diamant","emeraude","enchantement","potion","portail","zombie","squelette","creeper",
]

PENDU_ART = [
    "```\n  +---+\n      |\n      |\n      |\n      |\n=========```",
    "```\n  +---+\n  O   |\n      |\n      |\n      |\n=========```",
    "```\n  +---+\n  O   |\n  |   |\n      |\n      |\n=========```",
    "```\n  +---+\n  O   |\n /|   |\n      |\n      |\n=========```",
    "```\n  +---+\n  O   |\n /|\\  |\n      |\n      |\n=========```",
    "```\n  +---+\n  O   |\n /|\\  |\n /    |\n      |\n=========```",
    "```\n  +---+\n  O   |\n /|\\  |\n / \\  |\n      |\n=========```",
]


def build_pendu_embed(game: dict) -> discord.Embed:
    word      = game["word"]
    guessed   = set(game["guessed"])
    errors    = game["errors"]
    display   = " ".join(l if l in guessed else "_" for l in word)
    wrong     = [l for l in guessed if l not in word]
    remaining = max(0, int(game.get("end_time", 0) - time.time()))
    mins, secs = divmod(remaining, 60)
    won  = all(l in guessed for l in word)
    lost = errors >= 6
    color = 0x2ECC71 if won else (0xE74C3C if lost else 0x9B59B6)
    embed = discord.Embed(title="🎯 Pendu", color=color)
    embed.add_field(name="Mot",         value=f"`{display}`",                                                    inline=False)
    embed.add_field(name="Dessin",      value=PENDU_ART[min(errors, 6)],                                         inline=False)
    embed.add_field(name="❌ Erreurs",  value=f"{errors}/6 — `{''.join(wrong) or 'aucune'}`",                    inline=True)
    embed.add_field(name="✅ Trouvées", value=f"`{''.join(sorted(l for l in guessed if l in word)) or 'aucune'}`", inline=True)
    embed.add_field(name="⏱️ Temps",    value=f"{mins}m {secs:02d}s",                                            inline=True)
    if game.get("participants"):
        embed.add_field(name="👥 Joueurs", value=", ".join(f"<@{u}>" for u in game["participants"]), inline=False)
    embed.set_footer(text="!devine [lettre]  •  !mot [mot complet]")
    return embed


async def _start_pendu_timer(key: str, guild_id: int, remaining: float):
    if key in pendu_tasks:
        pendu_tasks[key].cancel()

    async def _run():
        await asyncio.sleep(remaining)
        game = active_pendu.pop(key, None)
        pendu_tasks.pop(key, None)
        if not game:
            return
        save_games(guild_id)
        channel = bot.get_channel(game.get("channel_id", 0))
        if channel:
            await channel.send(f"⏰ Temps écoulé ! Le mot était : **{game['word']}**")
            if game.get("msg_id"):
                try:
                    m = await channel.fetch_message(game["msg_id"])
                    await m.delete()
                except Exception:
                    pass

    pendu_tasks[key] = asyncio.create_task(_run())


class PenduView(discord.ui.View):
    def __init__(self, guild_id: int, channel_id: int, creator_id: int):
        super().__init__(timeout=60)
        self.guild_id   = guild_id
        self.channel_id = channel_id
        self.creator_id = creator_id

    def _game_key(self):
        return gk(self.guild_id, self.channel_id)

    @discord.ui.button(label="🎲 Mot aléatoire", style=discord.ButtonStyle.green)
    async def random_word(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.creator_id:
            await interaction.response.send_message("❌ Seul le créateur peut choisir.", ephemeral=True)
            return
        word = random.choice(PENDU_MOTS)
        await self._launch(interaction, word)

    @discord.ui.button(label="✍️ Mot personnalisé", style=discord.ButtonStyle.blurple)
    async def custom_word(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.creator_id:
            await interaction.response.send_message("❌ Seul le créateur peut choisir.", ephemeral=True)
            return
        await interaction.response.edit_message(content="📩 DM envoyé pour le mot !", view=None)
        try:
            dm = await interaction.user.create_dm()
            await dm.send("✍️ Entre le mot (lettres minuscules, sans accents) :")
            def chk(m):
                return m.author.id == interaction.user.id and isinstance(m.channel, discord.DMChannel)
            dm_msg = await bot.wait_for("message", check=chk, timeout=60)
            word   = dm_msg.content.strip().lower()
            if not word.isalpha():
                await dm.send("❌ Mot invalide.")
                return
            key = self._game_key()
            channel = bot.get_channel(self.channel_id)
            if channel and key not in active_pendu:
                end_time = time.time() + 30 * 60
                game = {"word": word, "guessed": [], "errors": 0,
                        "creator": interaction.user.id, "participants": [],
                        "msg_id": None, "letter_cd": {}, "end_time": end_time,
                        "channel_id": self.channel_id}
                active_pendu[key] = game
                msg = await channel.send(embed=build_pendu_embed(game))
                game["msg_id"] = msg.id
                save_games(self.guild_id)
                await _start_pendu_timer(key, self.guild_id, 30 * 60)
                await dm.send(f"✅ Partie lancée avec le mot `{word}` !")
        except asyncio.TimeoutError:
            pass

    async def _launch(self, interaction: discord.Interaction, word: str):
        self.stop()
        key      = self._game_key()
        end_time = time.time() + 30 * 60
        game = {"word": word, "guessed": [], "errors": 0,
                "creator": interaction.user.id, "participants": [],
                "msg_id": None, "letter_cd": {}, "end_time": end_time,
                "channel_id": self.channel_id}
        active_pendu[key] = game
        await interaction.response.edit_message(content=None, embed=build_pendu_embed(game), view=None)
        msg = await interaction.original_response()
        game["msg_id"] = msg.id
        save_games(self.guild_id)
        await _start_pendu_timer(key, self.guild_id, 30 * 60)


async def _end_pendu(channel, guild_id: int, game: dict, won: bool, winner_id: int = None):
    key = gk(guild_id, channel.id)
    active_pendu.pop(key, None)
    if key in pendu_tasks:
        pendu_tasks[key].cancel()
        pendu_tasks.pop(key, None)
    save_games(guild_id)
    if game.get("msg_id"):
        try:
            msg = await channel.fetch_message(game["msg_id"])
            await msg.edit(embed=build_pendu_embed(game))
        except Exception:
            pass
    if won:
        data = load_user_data(guild_id)
        if winner_id:
            u = get_user(data, winner_id)
            u["xp"] += 150
        save_user_data(guild_id, data)
        winner_mention = f"<@{winner_id}>" if winner_id else "Quelqu'un"
        await channel.send(f"🏆 {winner_mention} a trouvé le mot **{game['word']}** ! **+150 XP** 🎉")
    else:
        await channel.send(f"💀 Perdu ! Le mot était **{game['word']}**.")


async def _update_pendu(ctx, guild_id: int, game: dict, winner_id: int = None):
    guessed = set(game["guessed"])
    won     = all(l in guessed for l in game["word"])
    lost    = game["errors"] >= 6
    if game.get("msg_id"):
        try:
            msg = await ctx.channel.fetch_message(game["msg_id"])
            await msg.edit(embed=build_pendu_embed(game))
        except discord.NotFound:
            key = gk(guild_id, ctx.channel.id)
            active_pendu.pop(key, None)
            if key in pendu_tasks:
                pendu_tasks[key].cancel()
                pendu_tasks.pop(key, None)
            save_games(guild_id)
            return
        except Exception:
            pass
    if won:
        await _end_pendu(ctx.channel, guild_id, game, won=True, winner_id=winner_id)
    elif lost:
        await _end_pendu(ctx.channel, guild_id, game, won=False)


@bot.command(name="pendu")
async def pendu_cmd(ctx):
    key = gk(ctx.guild.id, ctx.channel.id)
    if key in active_pendu:
        await ctx.send("❌ Une partie est déjà en cours dans ce salon.", delete_after=5)
        return
    view = PenduView(ctx.guild.id, ctx.channel.id, ctx.author.id)
    await ctx.send("🎯 **Pendu** — Comment veux-tu jouer ?", view=view)


@bot.command(name="devine")
async def devine_cmd(ctx, lettre: str = None):
    key  = gk(ctx.guild.id, ctx.channel.id)
    game = active_pendu.get(key)
    if not game: await ctx.send("❌ Aucune partie en cours. Lance `!pendu`.", delete_after=5); return
    if ctx.author.id == game["creator"]: await ctx.send("❌ Le créateur ne peut pas jouer.", delete_after=5); return
    if lettre is None or len(lettre) != 1 or not lettre.isalpha():
        await ctx.send("❌ `!devine [lettre]`", delete_after=5); return
    lettre = lettre.lower()
    uid    = ctx.author.id
    now_m  = time.monotonic()
    if now_m - game["letter_cd"].get(str(uid), 0) < 3:
        await ctx.send("⏳ Attends 3 secondes.", delete_after=3); return
    game["letter_cd"][str(uid)] = now_m
    if lettre in game["guessed"]: await ctx.send(f"⚠️ `{lettre}` déjà jouée.", delete_after=4); return
    game["guessed"].append(lettre)
    if uid not in game["participants"]: game["participants"].append(uid)
    if lettre not in game["word"]: game["errors"] += 1
    save_games(ctx.guild.id)
    try: await ctx.message.delete()
    except Exception: pass
    winner_id = uid if all(l in game["guessed"] for l in game["word"]) else None
    await _update_pendu(ctx, ctx.guild.id, game, winner_id=winner_id)


@bot.command(name="mot")
async def mot_cmd(ctx, *, mot: str = None):
    key  = gk(ctx.guild.id, ctx.channel.id)
    game = active_pendu.get(key)
    if not game: await ctx.send("❌ Aucune partie en cours.", delete_after=5); return
    if ctx.author.id == game["creator"]: await ctx.send("❌ Le créateur ne peut pas jouer.", delete_after=5); return
    if mot is None: await ctx.send("❌ `!mot [mot complet]`", delete_after=5); return
    mot = mot.lower().strip()
    uid = ctx.author.id
    if uid not in game["participants"]: game["participants"].append(uid)
    try: await ctx.message.delete()
    except Exception: pass
    if mot == game["word"]:
        for l in game["word"]:
            if l not in game["guessed"]: game["guessed"].append(l)
        save_games(ctx.guild.id)
        await _update_pendu(ctx, ctx.guild.id, game, winner_id=uid)
    else:
        game["errors"] += 1
        save_games(ctx.guild.id)
        await _update_pendu(ctx, ctx.guild.id, game)


@bot.command(name="pendustop")
async def pendustop_cmd(ctx):
    if not is_staff(ctx.author): await ctx.send("❌ Réservé au staff.", delete_after=5); return
    key  = gk(ctx.guild.id, ctx.channel.id)
    game = active_pendu.get(key)
    if not game: await ctx.send("❌ Aucune partie en cours.", delete_after=5); return
    active_pendu.pop(key, None)
    if key in pendu_tasks:
        pendu_tasks[key].cancel()
        pendu_tasks.pop(key, None)
    save_games(ctx.guild.id)
    await ctx.send(f"🛑 Partie arrêtée. Le mot était **{game['word']}**.")

# ═══════════════════════════════════════════════════════════════
#  MORPION
# ═══════════════════════════════════════════════════════════════

MORPION_EMOJIS = {None: "⬜", "X": "❌", "O": "⭕"}
WINS = [(0,1,2),(3,4,5),(6,7,8),(0,3,6),(1,4,7),(2,5,8),(0,4,8),(2,4,6)]


def check_winner(board: list) -> str | None:
    for a, b, c in WINS:
        if board[a] and board[a] == board[b] == board[c]:
            return board[a]
    return None


def build_morpion_embed(game: dict) -> discord.Embed:
    board     = game["board"]
    players   = game["players"]
    current   = game["current"]
    remaining = max(0, int(game.get("end_time", 0) - time.time()))
    mins, secs = divmod(remaining, 60)
    winner = check_winner(board)
    full   = all(c is not None for c in board)
    color  = 0x2ECC71 if winner else (0x95A5A6 if full else 0x3498DB)
    embed  = discord.Embed(title="❌⭕ Morpion", color=color)
    rows = ""
    for i in range(0, 9, 3):
        rows += "".join(MORPION_EMOJIS[board[i+j]] for j in range(3)) + "\n"
    embed.add_field(name="Plateau", value=rows, inline=False)
    if winner:
        winner_id = players[0] if winner == "X" else players[1]
        embed.add_field(name="🏆 Gagnant", value=f"<@{winner_id}>", inline=True)
    elif full:
        embed.add_field(name="Résultat", value="🤝 Égalité !", inline=True)
    else:
        cur_id = players[current]
        sym    = "❌" if current == 0 else "⭕"
        embed.add_field(name="Tour",     value=f"{sym} <@{cur_id}>",   inline=True)
        embed.add_field(name="⏱️ Temps", value=f"{mins}m {secs:02d}s", inline=True)
    embed.add_field(name="Joueurs", value=f"❌ <@{players[0]}>  vs  ⭕ <@{players[1]}>", inline=False)
    return embed


class MorpionView(discord.ui.View):
    def __init__(self, guild_id: int, channel_id: int):
        super().__init__(timeout=None)
        self.guild_id   = guild_id
        self.channel_id = channel_id
        self._rebuild()

    def _key(self):
        return gk(self.guild_id, self.channel_id)

    def _rebuild(self):
        self.clear_items()
        game  = active_morpion.get(self._key())
        board = game["board"] if game else [None]*9
        ended = game is None or check_winner(board) is not None or all(c is not None for c in board)
        for i in range(9):
            row = i // 3
            lbl = MORPION_EMOJIS[board[i]]
            btn = discord.ui.Button(
                label=lbl,
                style=discord.ButtonStyle.secondary if board[i] is None else discord.ButtonStyle.primary,
                disabled=(board[i] is not None or ended),
                row=row,
                custom_id=f"morpion_{self.guild_id}_{self.channel_id}_{i}"
            )
            btn.callback = self._make_callback(i)
            self.add_item(btn)

    def _make_callback(self, cell: int):
        async def callback(interaction: discord.Interaction):
            key  = self._key()
            game = active_morpion.get(key)
            if not game:
                await interaction.response.send_message("❌ Partie terminée.", ephemeral=True)
                return
            uid     = interaction.user.id
            current = game["current"]
            players = game["players"]
            if uid != players[current]:
                await interaction.response.send_message("❌ Ce n'est pas ton tour.", ephemeral=True)
                return
            if game["board"][cell] is not None:
                await interaction.response.send_message("❌ Case déjà jouée.", ephemeral=True)
                return
            sym = "X" if current == 0 else "O"
            game["board"][cell] = sym
            game["current"] = 1 - current
            save_games(self.guild_id)
            winner = check_winner(game["board"])
            full   = all(c is not None for c in game["board"])
            if winner or full:
                active_morpion.pop(key, None)
                if key in morpion_tasks:
                    morpion_tasks[key].cancel()
                    morpion_tasks.pop(key, None)
                save_games(self.guild_id)
                for item in self.children:
                    item.disabled = True
                embed = build_morpion_embed(game)
                if winner:
                    winner_id = players[0] if winner == "X" else players[1]
                    data = load_user_data(self.guild_id)
                    u    = get_user(data, winner_id)
                    u["xp"] += 50
                    save_user_data(self.guild_id, data)
                    revanche_view = RevancheView(
                        loser_id=players[1] if winner == "X" else players[0],
                        players=players, guild_id=self.guild_id, channel_id=self.channel_id
                    )
                    await interaction.response.edit_message(embed=embed, view=revanche_view)
                    await interaction.followup.send(f"🎉 <@{winner_id}> a gagné ! **+50 XP** 🏆")
                else:
                    await interaction.response.edit_message(embed=embed, view=None)
                    await interaction.followup.send("🤝 Égalité !")
            else:
                self._rebuild()
                await interaction.response.edit_message(embed=build_morpion_embed(game), view=self)
        return callback


class RevancheView(discord.ui.View):
    def __init__(self, loser_id: int, players: list, guild_id: int, channel_id: int, timeout_sec: int = 10):
        super().__init__(timeout=timeout_sec)
        self.loser_id   = loser_id
        self.players    = players
        self.guild_id   = guild_id
        self.channel_id = channel_id

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True

    @discord.ui.button(label="🔁 Revanche", style=discord.ButtonStyle.green)
    async def revanche(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.loser_id:
            await interaction.response.send_message("❌ Seul le perdant peut demander la revanche.", ephemeral=True)
            return
        self.stop()
        new_players = list(reversed(self.players))
        end_time    = time.time() + 5 * 60
        key         = gk(self.guild_id, self.channel_id)
        game = {"board": [None]*9, "players": new_players, "current": 0, "msg_id": None, "end_time": end_time}
        active_morpion[key] = game
        view  = MorpionView(self.guild_id, self.channel_id)
        embed = build_morpion_embed(game)
        await interaction.response.send_message(embed=embed, view=view)
        msg = await interaction.original_response()
        game["msg_id"] = msg.id
        save_games(self.guild_id)
        await _start_morpion_timer(key, self.guild_id, 5 * 60)


async def _start_morpion_timer(key: str, guild_id: int, remaining: float):
    if key in morpion_tasks:
        morpion_tasks[key].cancel()

    async def _run():
        await asyncio.sleep(remaining)
        game = active_morpion.pop(key, None)
        morpion_tasks.pop(key, None)
        if not game:
            return
        save_games(guild_id)
        _, ch_id = key.split(":")
        channel = bot.get_channel(int(ch_id))
        if channel:
            await channel.send("⏰ Temps écoulé ! Partie de morpion annulée.")
            if game.get("msg_id"):
                try:
                    m = await channel.fetch_message(game["msg_id"])
                    await m.edit(view=None)
                except Exception:
                    pass

    morpion_tasks[key] = asyncio.create_task(_run())


@bot.command(name="morpion")
async def morpion_cmd(ctx, opponent: discord.Member = None):
    if opponent is None: await ctx.send("❌ `!morpion @joueur`", delete_after=5); return
    if opponent.bot or opponent.id == ctx.author.id: await ctx.send("❌ Adversaire invalide.", delete_after=5); return
    key = gk(ctx.guild.id, ctx.channel.id)
    if key in active_morpion: await ctx.send("❌ Partie déjà en cours.", delete_after=5); return
    end_time = time.time() + 5 * 60
    game = {"board": [None]*9, "players": [ctx.author.id, opponent.id],
            "current": 0, "msg_id": None, "end_time": end_time}
    active_morpion[key] = game
    view  = MorpionView(ctx.guild.id, ctx.channel.id)
    embed = build_morpion_embed(game)
    msg   = await ctx.send(embed=embed, view=view)
    game["msg_id"] = msg.id
    save_games(ctx.guild.id)
    await _start_morpion_timer(key, ctx.guild.id, 5 * 60)


@bot.command(name="morpionstop")
async def morpionstop_cmd(ctx):
    if not is_staff(ctx.author): await ctx.send("❌ Réservé au staff.", delete_after=5); return
    key  = gk(ctx.guild.id, ctx.channel.id)
    game = active_morpion.get(key)
    if not game: await ctx.send("❌ Aucune partie en cours.", delete_after=5); return
    active_morpion.pop(key, None)
    if key in morpion_tasks:
        morpion_tasks[key].cancel()
        morpion_tasks.pop(key, None)
    save_games(ctx.guild.id)
    await ctx.send("🛑 Partie de morpion arrêtée.")

# ═══════════════════════════════════════════════════════════════
#  GIVEAWAY
# ═══════════════════════════════════════════════════════════════

def build_giveaway_embed(gw: dict) -> discord.Embed:
    ends  = discord.utils.format_dt(datetime.fromtimestamp(gw["ends_at"], tz=timezone.utc), style="R")
    embed = discord.Embed(title=f"🎉 GIVEAWAY — {gw['reward']}",
        description="Clique sur **🎉 Participer** pour tenter ta chance !", color=0xF1C40F)
    embed.add_field(name="⏰ Fin",          value=ends,                         inline=True)
    embed.add_field(name="👥 Participants", value=str(len(gw["participants"])), inline=True)
    embed.add_field(name="🏆 Récompense",  value=gw["reward"],                 inline=False)
    embed.set_footer(text=f"Organisé par {gw['host']}")
    return embed


class GiveawayView(discord.ui.View):
    def __init__(self, msg_id: int):
        super().__init__(timeout=None)
        self.msg_id = msg_id

    @discord.ui.button(label="🎉 Participer", style=discord.ButtonStyle.green)
    async def participer(self, interaction: discord.Interaction, button: discord.ui.Button):
        gw = active_giveaways.get(self.msg_id)
        if not gw:
            await interaction.response.send_message("❌ Ce giveaway est terminé.", ephemeral=True)
            return
        uid = interaction.user.id
        if uid in gw["participants"]:
            gw["participants"].remove(uid)
            await interaction.response.send_message("❌ Tu t'es retiré du giveaway.", ephemeral=True)
        else:
            gw["participants"].append(uid)
            await interaction.response.send_message("✅ Tu participes au giveaway !", ephemeral=True)
        try:
            msg = await interaction.channel.fetch_message(self.msg_id)
            await msg.edit(embed=build_giveaway_embed(gw))
        except Exception:
            pass


def parse_duration(s: str) -> int | None:
    total = 0
    for val, unit in re.findall(r"(\d+)([smhj])", s.lower()):
        v = int(val)
        if unit == "s":   total += v
        elif unit == "m": total += v * 60
        elif unit == "h": total += v * 3600
        elif unit == "j": total += v * 86400
    return total if total > 0 else None


@bot.command(name="giveaway", aliases=["gw"])
async def giveaway_cmd(ctx, duree: str = None, *, reward: str = None):
    if not is_staff(ctx.author):
        await ctx.send("❌ Réservé au staff.", delete_after=5); return
    if duree is None or reward is None:
        await ctx.send("❌ `!giveaway 1h Récompense`", delete_after=8); return
    seconds = parse_duration(duree)
    if not seconds:
        await ctx.send("❌ Durée invalide. Ex : `10m`, `1h`, `2h30m`", delete_after=8); return
    ends_at = time.time() + seconds
    gw = {"reward": reward, "ends_at": ends_at, "participants": [],
          "host": str(ctx.author), "channel_id": ctx.channel.id}
    embed = build_giveaway_embed(gw)
    msg   = await ctx.send(embed=embed, view=GiveawayView(0))
    gw_id = msg.id
    active_giveaways[gw_id] = gw
    await msg.edit(view=GiveawayView(gw_id))
    asyncio.create_task(_end_giveaway(gw_id, seconds, ctx.channel, reward))


async def _end_giveaway(gw_id: int, delay: int, channel: discord.TextChannel, reward: str):
    await asyncio.sleep(delay)
    gw = active_giveaways.pop(gw_id, None)
    if not gw:
        return
    try:
        msg = await channel.fetch_message(gw_id)
        if not gw["participants"]:
            embed = discord.Embed(title=f"🎉 GIVEAWAY TERMINÉ — {reward}",
                description="😔 Aucun participant...", color=0x95A5A6)
            await msg.edit(embed=embed, view=None)
            return
        winner_id = random.choice(gw["participants"])
        winner    = channel.guild.get_member(winner_id)
        name      = winner.mention if winner else f"<@{winner_id}>"
        embed = discord.Embed(title=f"🎉 GIVEAWAY TERMINÉ — {reward}",
            description=f"🏆 Gagnant : {name}\n🎊 Félicitations !", color=0x2ECC71)
        embed.set_footer(text=f"Organisé par {gw['host']} • {len(gw['participants'])} participants")
        await msg.edit(embed=embed, view=None)
        await channel.send(f"🎊 Félicitations {name} ! Tu as gagné **{reward}** !")
    except Exception as e:
        print(f"[GW] Erreur fin giveaway : {e}")

# ═══════════════════════════════════════════════════════════════
#  CLASSEMENT
# ═══════════════════════════════════════════════════════════════

@bot.command(name="classement", aliases=["top", "leaderboard"])
async def classement_cmd(ctx):
    gid   = ctx.guild.id
    data  = load_user_data(gid)
    guild = ctx.guild
    now   = time.time()
    medals = ["🥇", "🥈", "🥉"]
    cfg   = load_config(gid)

    for uid_str, u in data.items():
        u["_voice_live"] = u["voice_time"] + (now - u["voice_join"]) if u.get("voice_join") else u["voice_time"]

    def top10_field(key: str, fmt) -> str:
        items = sorted([(uid, u) for uid, u in data.items() if u.get(key, 0) > 0],
                        key=lambda x: x[1].get(key, 0), reverse=True)[:10]
        if not items: return "_Aucun joueur_"
        lines = []
        for i, (uid, u) in enumerate(items):
            m    = guild.get_member(int(uid))
            name = m.display_name if m else "Inconnu"
            rank = medals[i] if i < 3 else f"`#{i+1}`"
            lines.append(f"{rank} **{name}** — {fmt(u)}")
        return "\n".join(lines)

    items_lvl = sorted(data.items(), key=lambda x: (x[1].get("level", 0), x[1].get("xp", 0)), reverse=True)[:10]
    top_lvl = "\n".join(
        f"{medals[i] if i < 3 else f'`#{i+1}`'} **{guild.get_member(int(uid)).display_name if guild.get_member(int(uid)) else 'Inconnu'}** — Niv. {u.get('level',0)} ({u.get('xp',0)} XP)"
        for i, (uid, u) in enumerate(items_lvl)
    ) or "_Aucun joueur_"

    faction_role_names = cfg.get("faction_roles", [])
    faction_members = []
    for member in guild.members:
        if member.bot:
            continue
        if any(r.name in faction_role_names for r in member.roles):
            uid_str = str(member.id)
            u = data.get(uid_str, {"level": 0, "xp": 0})
            faction_members.append((uid_str, u, member))
    faction_members.sort(key=lambda x: (x[1].get("level", 0), x[1].get("xp", 0)), reverse=True)
    top_faction = "\n".join(
        f"{medals[i] if i < 3 else f'`#{i+1}`'} **{m.display_name}** — Niv. {u.get('level', 0)}"
        for i, (uid, u, m) in enumerate(faction_members[:10])
    ) or "_Aucun membre faction_"

    embed = discord.Embed(title="🏆 Classements", color=0xF1C40F, timestamp=now_utc())
    embed.add_field(name="━━━━━━━━━━━━━━━━━━\n📊 Top Messages", value=top10_field("message_count", lambda u: f"{u['message_count']} msg"), inline=False)
    embed.add_field(name="━━━━━━━━━━━━━━━━━━\n⭐ Top Niveau",   value=top_lvl,  inline=False)
    embed.add_field(name="━━━━━━━━━━━━━━━━━━\n🎤 Top Vocal",    value=top10_field("_voice_live", lambda u: fmt_voice(u["_voice_live"])), inline=False)
    embed.add_field(name="━━━━━━━━━━━━━━━━━━\n⚔️ Top Faction",  value=top_faction, inline=False)
    embed.set_footer(text="Top 10 par catégorie • Temps vocal live inclus")
    await ctx.send(embed=embed)

# ═══════════════════════════════════════════════════════════════
#  CATALOGUE / COMMANDES
# ═══════════════════════════════════════════════════════════════

class _PrixAlertView(discord.ui.View):
    def __init__(self, author_id: int):
        super().__init__(timeout=60)
        self.author_id = author_id
        self.result    = None

    async def interaction_check(self, i):
        return i.user.id == self.author_id

    @discord.ui.button(label="✅ Oui, publier quand même", style=discord.ButtonStyle.green)
    async def oui(self, i, b):
        self.result = True; self.stop(); await i.response.defer()

    @discord.ui.button(label="❌ Non, annuler", style=discord.ButtonStyle.red)
    async def non(self, i, b):
        self.result = False; self.stop(); await i.response.defer()


def _parse_prix_num(prix: str) -> float | None:
    nums = re.findall(r"[\d]+(?:[.,][\d]+)?", prix)
    if nums:
        try:
            return float(nums[0].replace(",", "."))
        except ValueError:
            pass
    return None


@bot.command(name="catalogue")
async def catalogue_cmd(ctx, *, args: str = None):
    if not is_vendeur(ctx.author):
        await ctx.send(embed=discord.Embed(
            title="❌ Permission insuffisante",
            description="Réservé aux vendeurs certifiés.",
            color=0xE74C3C
        ), delete_after=5)
        return

    if not args:
        await ctx.send("❌ `!catalogue <nom> <quantité> <prix>`\nExemple : `!catalogue paladium ingot 10 500$`", delete_after=10)
        return

    tokens = args.split()
    if len(tokens) < 3:
        await ctx.send("❌ `!catalogue <nom> <quantité> <prix>`\nExemple : `!catalogue épée légendaire 5 1000$`", delete_after=10)
        return

    qty_idx = None
    for i in range(len(tokens) - 1, 0, -1):
        if tokens[i].isdigit():
            qty_idx = i
            break

    if qty_idx is None or qty_idx == 0 or qty_idx == len(tokens) - 1:
        await ctx.send("❌ Format invalide. `!catalogue <nom> <quantité> <prix>`\nExemple : `!catalogue bloc de paladium 20 200$`", delete_after=10)
        return

    nom   = " ".join(tokens[:qty_idx])
    prix  = " ".join(tokens[qty_idx + 1:])
    try:
        qty = int(tokens[qty_idx])
        if qty <= 0:
            raise ValueError
    except ValueError:
        await ctx.send("❌ La quantité doit être un nombre entier positif.", delete_after=6)
        return

    data    = load_catalogue(ctx.guild.id)
    items   = data.get("items", {})
    nom_low = nom.lower().strip()
    my_key  = _item_key(nom, ctx.author.id)

    autres = {
        k: v for k, v in items.items()
        if k.split(":")[0] == nom_low and v.get("vendeur_id") != ctx.author.id
    }

    prix_num = _parse_prix_num(prix)
    if autres and prix_num is not None:
        prix_min_item = min(autres.values(), key=lambda v: (_parse_prix_num(v["prix"]) or float("inf")))
        prix_min_num  = _parse_prix_num(prix_min_item["prix"])
        if prix_min_num is not None and prix_num > prix_min_num:
            vendeur_moins_cher = ctx.guild.get_member(prix_min_item["vendeur_id"])
            vnom = vendeur_moins_cher.display_name if vendeur_moins_cher else f"<@{prix_min_item['vendeur_id']}>"
            warn_embed = discord.Embed(
                title="⚠️ Prix plus élevé détecté",
                description=(
                    f"**{nom}** est déjà vendu à **{prix_min_item['prix']}** par **{vnom}**.\n\n"
                    f"Tu veux le vendre à **{prix}** — c'est plus cher.\n\n"
                    f"Veux-tu quand même publier cet article ?"
                ),
                color=0xE67E22,
                timestamp=now_utc()
            )
            view     = _PrixAlertView(ctx.author.id)
            warn_msg = await ctx.send(embed=warn_embed, view=view)
            await view.wait()
            try: await warn_msg.delete()
            except Exception: pass
            if not view.result:
                await ctx.send(embed=discord.Embed(
                    title="❌ Publication annulée",
                    description="L'article n'a pas été ajouté.",
                    color=0xE74C3C
                ), delete_after=5)
                return

    if my_key in items:
        ancien_prix_num  = _parse_prix_num(items[my_key]["prix"])
        nouveau_prix_num = prix_num
        items[my_key]["quantite"] += qty
        if ancien_prix_num is not None and nouveau_prix_num is not None:
            if nouveau_prix_num < ancien_prix_num:
                items[my_key]["prix"] = prix
        else:
            items[my_key]["prix"] = prix
        items[my_key]["updated"] = time.time()
        action = (
            f"✏️ **{nom}** mis à jour par {ctx.author.mention} — "
            f"stock : {items[my_key]['quantite']} · prix : {items[my_key]['prix']}"
        )
    else:
        items[my_key] = {
            "nom":        nom,
            "quantite":   qty,
            "prix":       prix,
            "vendeur_id": ctx.author.id,
            "created":    time.time(),
            "updated":    time.time()
        }
        action = f"➕ **{nom}** ajouté par {ctx.author.mention} — stock : {qty} · prix : {prix}"

    data["items"] = items
    save_catalogue(ctx.guild.id, data)
    await update_catalogue_message(ctx.guild, items)
    await send_notif(ctx.guild, action)
    await ctx.send(embed=discord.Embed(
        title="✅ Catalogue mis à jour",
        description=f"**{nom}** — x{qty} à {prix}",
        color=0x2ECC71
    ), delete_after=8)


@bot.command(name="cataloguesupp")
async def cataloguesupp_cmd(ctx):
    if not is_vendeur(ctx.author):
        await ctx.send(embed=discord.Embed(
            title="❌ Permission insuffisante",
            description="Réservé aux vendeurs certifiés.",
            color=0xE74C3C
        ), delete_after=5)
        return

    data  = load_catalogue(ctx.guild.id)
    items = data.get("items", {})
    staff = is_staff(ctx.author)

    items_visibles = items if staff else {k: v for k, v in items.items() if v.get("vendeur_id") == ctx.author.id}

    if not items_visibles:
        await ctx.send(embed=discord.Embed(
            title="❌ Aucun article trouvé",
            description="Tu n'as aucun article dans le catalogue." if not staff else "Le catalogue est vide.",
            color=0xE74C3C
        ), delete_after=8)
        return

    embed = discord.Embed(title="🗑️ Suppression d'article — Choisir", color=0xE74C3C, timestamp=now_utc())

    lignes = []
    keys_list = list(items_visibles.keys())
    for i, key in enumerate(keys_list, 1):
        item = items_visibles[key]
        if staff:
            vendeur_m = ctx.guild.get_member(item["vendeur_id"])
            vnom = vendeur_m.display_name if vendeur_m else f"<@{item['vendeur_id']}>"
            lignes.append(f"`{i}.` 🔹 **{item['nom']}** — 📦 {item['quantite']} · 💰 {item['prix']} · 👤 {vnom}")
        else:
            lignes.append(f"`{i}.` 🔹 **{item['nom']}** — 📦 {item['quantite']} · 💰 {item['prix']}")

    chunk, chunks = "", []
    for l in lignes:
        if len(chunk) + len(l) + 1 > 1000:
            chunks.append(chunk)
            chunk = l
        else:
            chunk = (chunk + "\n" + l).strip()
    if chunk:
        chunks.append(chunk)

    for idx, c in enumerate(chunks):
        embed.add_field(name="\u200b" if idx > 0 else "📋 Articles disponibles", value=c, inline=False)

    embed.set_footer(text="Réponds avec le numéro ou le nom exact · 'annuler' pour quitter · 60s")
    msg_list = await ctx.send(embed=embed)

    def chk(m):
        return m.author.id == ctx.author.id and m.channel.id == ctx.channel.id

    try:
        resp = await bot.wait_for("message", check=chk, timeout=60)
    except asyncio.TimeoutError:
        try: await msg_list.delete()
        except Exception: pass
        await ctx.send(embed=discord.Embed(title="⏰ Temps écoulé", description="Suppression annulée.", color=0xE67E22), delete_after=6)
        return

    try: await resp.delete()
    except Exception: pass
    try: await msg_list.delete()
    except Exception: pass

    contenu = resp.content.strip()
    if contenu.lower() == "annuler":
        await ctx.send(embed=discord.Embed(title="❌ Annulé", description="Aucun article supprimé.", color=0x95A5A6), delete_after=5)
        return

    target_key = None
    if contenu.isdigit():
        idx = int(contenu) - 1
        if 0 <= idx < len(keys_list):
            target_key = keys_list[idx]

    if target_key is None:
        contenu_low = contenu.lower()
        for k, v in items_visibles.items():
            if v["nom"].lower() == contenu_low or k.split(":")[0] == contenu_low:
                target_key = k
                break

    if target_key is None:
        await ctx.send(embed=discord.Embed(title="❌ Article introuvable", description=f"Aucun article correspondant à **{contenu}**.", color=0xE74C3C), delete_after=8)
        return

    item_cible = items.get(target_key)
    if not item_cible:
        await ctx.send(embed=discord.Embed(title="❌ Article introuvable", description="Cet article n'existe plus.", color=0xE74C3C), delete_after=8)
        return

    if not staff and item_cible.get("vendeur_id") != ctx.author.id:
        await ctx.send(embed=discord.Embed(title="❌ Permission insuffisante", description="Tu ne peux supprimer que tes propres articles.", color=0xE74C3C), delete_after=6)
        return

    nom_supp = item_cible["nom"]
    del items[target_key]
    data["items"] = items
    save_catalogue(ctx.guild.id, data)
    await update_catalogue_message(ctx.guild, items)
    await send_notif(ctx.guild, f"🗑️ **{nom_supp}** supprimé du catalogue par {ctx.author.mention}")
    await send_log(ctx.guild, discord.Embed(title="🗑️ Article supprimé du catalogue", description=f"**{nom_supp}** retiré par {ctx.author.mention}", color=0xE74C3C, timestamp=now_utc()))
    await ctx.send(embed=discord.Embed(title="✅ Article supprimé", description=f"**{nom_supp}** a été retiré du catalogue.", color=0x2ECC71), delete_after=8)


class _SuppAllView(discord.ui.View):
    def __init__(self, author_id: int):
        super().__init__(timeout=30)
        self.author_id = author_id
        self.result    = None

    async def interaction_check(self, i):
        return i.user.id == self.author_id

    @discord.ui.button(label="✅ Confirmer — Tout supprimer", style=discord.ButtonStyle.red)
    async def confirmer(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.result = True
        self.stop()
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="❌ Annuler", style=discord.ButtonStyle.grey)
    async def annuler(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.result = False
        self.stop()
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)


@bot.command(name="cataloguesuppall")
async def cataloguesuppall_cmd(ctx):
    if not is_staff(ctx.author):
        await ctx.send(embed=discord.Embed(title="❌ Permission insuffisante", description="Cette commande est réservée au staff.", color=0xE74C3C), delete_after=5)
        return

    data  = load_catalogue(ctx.guild.id)
    items = data.get("items", {})

    if not items:
        await ctx.send(embed=discord.Embed(title="📭 Catalogue vide", description="Il n'y a aucun article à supprimer.", color=0x95A5A6), delete_after=6)
        return

    nb = len(items)
    warn = discord.Embed(
        title="⚠️ Suppression totale du catalogue",
        description=f"Tu es sur le point de supprimer **{nb} article(s)** du catalogue.\n\n**Cette action est irréversible.**\n\nConfirmes-tu ?",
        color=0xE74C3C, timestamp=now_utc()
    )
    view     = _SuppAllView(ctx.author.id)
    warn_msg = await ctx.send(embed=warn, view=view)
    await view.wait()

    try: await warn_msg.delete()
    except Exception: pass

    if not view.result:
        await ctx.send(embed=discord.Embed(title="❌ Annulé", description="Le catalogue n'a pas été modifié.", color=0x95A5A6), delete_after=5)
        return

    data["items"] = {}
    save_catalogue(ctx.guild.id, data)
    await update_catalogue_message(ctx.guild, {})
    await send_notif(ctx.guild, f"🗑️ Le catalogue a été entièrement vidé par {ctx.author.mention}.")
    await send_log(ctx.guild, discord.Embed(title="🗑️ Catalogue entièrement supprimé", description=f"Vidé par {ctx.author.mention} — {nb} article(s) supprimé(s).", color=0xE74C3C, timestamp=now_utc()))
    await ctx.send(embed=discord.Embed(title="✅ Catalogue entièrement supprimé", description=f"**{nb} article(s)** ont été supprimés par {ctx.author.mention}.", color=0x2ECC71), delete_after=10)


@bot.command(name="stock")
async def stock_cmd(ctx, cible: discord.Member = None):
    catalogue_ch = cfg_channel(ctx.guild, "salon_catalogue")
    in_catalogue = catalogue_ch and ctx.channel.id == catalogue_ch.id

    if not in_catalogue and not is_staff_market(ctx.author):
        await ctx.send("❌ Réservé aux vendeurs certifiés.", delete_after=5); return

    target    = cible or ctx.author
    data      = load_catalogue(ctx.guild.id)
    items     = data.get("items", {})
    ses_items = {k: v for k, v in items.items() if v.get("vendeur_id") == target.id}
    title     = f"📦 Mon stock — {target.display_name}" if target.id == ctx.author.id else f"📦 Stock de {target.display_name}"
    embed     = discord.Embed(title=title, color=0x3498DB, timestamp=now_utc())

    if not ses_items:
        embed.description = f"Aucun article en vente pour **{target.display_name}**."
    else:
        total_u = sum(v["quantite"] for v in ses_items.values())
        embed.description = f"**{len(ses_items)}** article(s) • **{total_u}** unité(s) au total"
        for key, item in ses_items.items():
            embed.add_field(name=f"🔹 {item['nom']}", value=f"📦 {item['quantite']}\n💰 {item['prix']}", inline=True)

    if in_catalogue:
        try: await ctx.message.delete()
        except Exception: pass
        await ctx.author.send(embed=embed)
        await ctx.send(f"📩 {ctx.author.mention} Réponse envoyée en DM.", delete_after=6)
    else:
        await ctx.send(embed=embed)


@bot.command(name="recherche")
async def recherche_cmd(ctx, *, terme: str = None):
    if terme is None:
        await ctx.send("❌ `!recherche [nom_item]`", delete_after=6); return

    recherche_ch = cfg_channel(ctx.guild, "salon_recherche")
    if not is_staff(ctx.author) and recherche_ch and ctx.channel.id != recherche_ch.id:
        await ctx.send(f"❌ Utilise `!recherche` dans {recherche_ch.mention}.", delete_after=8); return

    data     = load_catalogue(ctx.guild.id)
    items    = data.get("items", {})
    resultats_raw = fuzzy_search(terme, items)
    resultats     = {k: v for k, (v, score) in resultats_raw.items()}

    embed = discord.Embed(title=f"🔍 Recherche : « {terme} »", color=0x9B59B6, timestamp=now_utc())
    if not resultats:
        embed.description = f"❌ Aucun article trouvé pour **{terme}**."
    else:
        embed.description = f"**{len(resultats)}** résultat(s) :"
        for key, item in resultats.items():
            vendeur_m   = ctx.guild.get_member(item["vendeur_id"])
            vendeur_str = vendeur_m.display_name if vendeur_m else f"<@{item['vendeur_id']}>"
            embed.add_field(
                name=f"🔹 {item['nom']}",
                value=f"📦 **Stock :** {item['quantite']}\n💰 **Prix :** {item['prix']}\n👤 {vendeur_str}",
                inline=True
            )
    embed.set_footer(text="Utilisez !commande pour passer une commande")

    catalogue_ch = cfg_channel(ctx.guild, "salon_catalogue")
    if catalogue_ch and ctx.channel.id == catalogue_ch.id:
        try: await ctx.message.delete()
        except Exception: pass
        await ctx.author.send(embed=embed)
        await ctx.send(f"📩 {ctx.author.mention} Résultat envoyé en DM.", delete_after=6)
    else:
        await ctx.send(embed=embed)

# ═══════════════════════════════════════════════════════════════
#  SYSTÈME DE COMMANDE
# ═══════════════════════════════════════════════════════════════

class CommandeSelect(discord.ui.Select):
    def __init__(self, guild_id: int, items: dict):
        self.guild_id = guild_id
        options = []
        for key, item in items.items():
            if item.get("quantite", 0) <= 0:
                continue
            options.append(discord.SelectOption(
                label=f"{item['nom'][:20]} ({item['prix'][:15]})"[:25],
                value=key,
                description=f"Stock: {item['quantite']} · Vendeur: <@{item['vendeur_id']}>"[:100]
            ))
        if not options:
            options = [discord.SelectOption(label="Aucun article disponible", value="__vide__")]
        super().__init__(
            placeholder="🔹 Choisis un article…",
            min_values=1, max_values=1,
            options=options[:25],
            custom_id=f"commande_select_{guild_id}"
        )

    async def callback(self, interaction: discord.Interaction):
        nom_key = self.values[0]
        if nom_key == "__vide__":
            await interaction.response.send_message("📭 Aucun article disponible.", ephemeral=True)
            return

        gid = interaction.guild.id
        uid = interaction.user.id
        pk  = f"{gid}:{uid}"

        if _pending_orders.get(pk):
            await interaction.response.send_message("⏳ Tu as déjà une commande en cours.", ephemeral=True)
            return

        data  = load_catalogue(gid)
        items = data.get("items", {})
        item  = items.get(nom_key)

        if not item or item.get("quantite", 0) <= 0:
            await interaction.response.send_message("❌ Article indisponible ou épuisé.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        _pending_orders[pk] = True
        try:
            embed_ask = discord.Embed(
                title=f"🛒 Commande — {item['nom']}",
                description=(
                    f"📦 **Stock :** {item['quantite']}\n"
                    f"💰 **Prix :** {item['prix']}\n\n"
                    f"Écris la **quantité** souhaitée dans ce salon.\n*(60 secondes)*"
                ),
                color=0x3498DB
            )
            await interaction.followup.send(embed=embed_ask, ephemeral=True)

            def check(m: discord.Message) -> bool:
                return m.author.id == uid and m.channel.id == interaction.channel.id

            try:
                msg = await bot.wait_for("message", check=check, timeout=60)
            except asyncio.TimeoutError:
                await interaction.followup.send("⏰ Temps écoulé. Commande annulée.", ephemeral=True)
                return

            try: await msg.delete()
            except Exception: pass

            try:
                qty = int(msg.content.strip())
                if qty <= 0: raise ValueError
            except ValueError:
                await interaction.followup.send("❌ Quantité invalide.", ephemeral=True)
                return

            data  = load_catalogue(gid)
            items = data.get("items", {})
            item  = items.get(nom_key)
            if not item:
                await interaction.followup.send("❌ Article retiré entre-temps.", ephemeral=True)
                return
            if qty > item["quantite"]:
                await interaction.followup.send(f"❌ Stock insuffisant. Disponible : **{item['quantite']}**", ephemeral=True)
                return

            guild    = interaction.guild
            acheteur = interaction.user
            vendeur  = guild.get_member(item["vendeur_id"])
            category = cfg_category(guild, "categorie_commandes")
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                acheteur:           discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
                guild.me:           discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True),
            }
            if vendeur:
                overwrites[vendeur] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

            ticket_channel = await guild.create_text_channel(
                name=f"cmd-{acheteur.display_name[:16]}-{item['nom'][:10]}",
                category=category,
                overwrites=overwrites,
                topic=f"commande|{nom_key}|{qty}|{item['vendeur_id']}"
            )

            nums = re.findall(r"[\d]+(?:[.,][\d]+)?", item["prix"])
            prix_total_str = f"{qty} × {item['prix']}"
            if nums:
                try:
                    unit_val  = float(nums[0].replace(",", "."))
                    total_val = unit_val * qty
                    suffix    = str(int(total_val)) if total_val == int(total_val) else f"{total_val:.2f}"
                    prix_total_str = f"{qty} × {item['prix']} = **{suffix}**"
                except Exception:
                    pass

            embed_ticket = discord.Embed(title="📦 Nouvelle commande", color=0x2ECC71, timestamp=now_utc())
            embed_ticket.add_field(name="🔹 Article",    value=item["nom"],      inline=True)
            embed_ticket.add_field(name="📦 Quantité",   value=str(qty),         inline=True)
            embed_ticket.add_field(name="💰 Prix unit.", value=item["prix"],      inline=True)
            embed_ticket.add_field(name="🧾 Prix total", value=prix_total_str,    inline=False)
            embed_ticket.add_field(name="🛒 Acheteur",  value=acheteur.mention,  inline=True)
            embed_ticket.add_field(name="👤 Vendeur",   value=vendeur.mention if vendeur else f"<@{item['vendeur_id']}>", inline=True)
            embed_ticket.set_footer(text="Vendeur : utilise !vendu pour confirmer ou refuser")

            await ticket_channel.send(
                content=f"{acheteur.mention} {vendeur.mention if vendeur else ''}",
                embed=embed_ticket
            )
            await interaction.followup.send(f"✅ Ticket créé : {ticket_channel.mention}", ephemeral=True)

        finally:
            _pending_orders.pop(pk, None)


class CommandeRechercheModal(discord.ui.Modal, title="🔍 Rechercher un article"):
    terme = discord.ui.TextInput(label="Nom ou mots-clés", placeholder="ex: paladium", max_length=50)

    def __init__(self, guild_id: int):
        super().__init__()
        self.guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction):
        data  = load_catalogue(self.guild_id)
        items = data.get("items", {})
        res   = fuzzy_search(str(self.terme), items)

        if not res:
            await interaction.response.send_message("❌ Aucun résultat trouvé.", ephemeral=True)
            return

        embed = discord.Embed(title=f"🔍 Résultats pour « {self.terme} »", color=0x9B59B6, timestamp=now_utc())
        for key, (item, score) in list(res.items())[:10]:
            vendeur_m = interaction.guild.get_member(item["vendeur_id"])
            vnom      = vendeur_m.display_name if vendeur_m else f"<@{item['vendeur_id']}>"
            embed.add_field(
                name=f"🔹 {item['nom']} ({int(score*100)}% match)",
                value=f"📦 {item['quantite']} · 💰 {item['prix']} · 👤 {vnom}",
                inline=False
            )
        embed.set_footer(text="Utilisez le menu ci-dessous pour commander")
        await interaction.response.send_message(embed=embed, ephemeral=True)


class CommandeView(discord.ui.View):
    def __init__(self, guild_id: int, items: dict):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        live_items = _clean_ghost_items(items)
        self.add_item(CommandeSelect(guild_id, live_items))

    @discord.ui.button(label="🔍 Rechercher", style=discord.ButtonStyle.blurple, row=1, custom_id="commande_search")
    async def recherche(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(CommandeRechercheModal(interaction.guild.id))


def _build_commande_embed_from_items(guild: discord.Guild, items: dict) -> discord.Embed:
    embed = discord.Embed(title="🛒 Boutique — Passer une commande", color=0x9B59B6, timestamp=now_utc())
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)

    live = _clean_ghost_items(items)
    if not live:
        embed.description = "📭 **Le catalogue est vide pour l'instant.**\nRevenez bientôt !"
    else:
        par_vendeur: dict[int, list] = defaultdict(list)
        for key, item in live.items():
            par_vendeur[item["vendeur_id"]].append(item)
        lignes = []
        for vendeur_id, arts in par_vendeur.items():
            membre = guild.get_member(vendeur_id)
            vnom   = membre.display_name if membre else f"Vendeur #{vendeur_id}"
            lignes.append(f"**🏷️ {vnom}**")
            for art in arts:
                lignes.append(f"  └ 🔹 **{art['nom']}** — 📦 {art['quantite']} · 💰 {art['prix']}")
        embed.description = "\n".join(lignes)

    embed.add_field(
        name="━━━━━━━━━━━━━━━━━━",
        value="📋 **Menu déroulant** → sélectionner un article\n🔍 **Rechercher** → trouver par nom ou mots-clés\n🔄 Catalogue mis à jour automatiquement",
        inline=False
    )
    embed.set_footer(text="Embed permanent · Se met à jour automatiquement toutes les 3s")
    return embed


def _build_commande_embed(guild: discord.Guild) -> discord.Embed:
    data  = load_catalogue(guild.id)
    items = data.get("items", {})
    return _build_commande_embed_from_items(guild, items)


@bot.command(name="commande")
async def commande_cmd(ctx):
    if not is_staff(ctx.author):
        await ctx.send("❌ Réservé au staff.", delete_after=5); return
    data  = load_catalogue(ctx.guild.id)
    items = data.get("items", {})
    embed = _build_commande_embed_from_items(ctx.guild, items)
    view  = CommandeView(ctx.guild.id, items)
    msg   = await ctx.send(embed=embed, view=view)
    _commande_msg_ids[ctx.guild.id] = msg.id
    data["commande_msg_id"] = msg.id
    save_catalogue(ctx.guild.id, data)

# ═══════════════════════════════════════════════════════════════
#  VENDU / LOG VENTES
# ═══════════════════════════════════════════════════════════════

class VenduView(discord.ui.View):
    def __init__(self, guild_id: int, vendeur_id: int, nom_key: str, quantite: int, ticket_channel_id: int):
        super().__init__(timeout=600)
        self.guild_id          = guild_id
        self.vendeur_id        = vendeur_id
        self.nom_key           = nom_key
        self.quantite          = quantite
        self.ticket_channel_id = ticket_channel_id
        self.done              = False

    def _disable_all(self):
        for child in self.children:
            child.disabled = True

    @discord.ui.button(label="✅ Vendu", style=discord.ButtonStyle.green)
    async def vendu(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.vendeur_id and not is_staff(interaction.user):
            await interaction.response.send_message("❌ Seul le vendeur peut valider.", ephemeral=True); return
        if self.done:
            await interaction.response.send_message("⚠️ Déjà effectué.", ephemeral=True); return
        self.done = True
        self._disable_all()
        self.stop()
        await interaction.response.defer()

        guild = interaction.guild
        data  = load_catalogue(self.guild_id)
        items = data.get("items", {})
        nom_affiche = items[self.nom_key]["nom"] if self.nom_key in items else self.nom_key.split(":")[0]
        prix_item   = items[self.nom_key].get("prix", "?") if self.nom_key in items else "?"

        ticket_ch = guild.get_channel(self.ticket_channel_id)
        acheteur_id = None
        if ticket_ch:
            for target, _ in ticket_ch.overwrites.items():
                if isinstance(target, discord.Member) and target.id != interaction.user.id and not target.bot:
                    acheteur_id = target.id
                    break

        if self.nom_key in items:
            items[self.nom_key]["quantite"] -= self.quantite
            if items[self.nom_key]["quantite"] <= 0:
                del items[self.nom_key]
                await send_notif(guild, f"📭 **{nom_affiche}** épuisé et retiré du catalogue.")
            items = _clean_ghost_items(items)
            data["items"] = items
            save_catalogue(self.guild_id, data)
            await update_catalogue_message(guild, items)

        await _log_vente(guild=guild, acheteur_id=acheteur_id, vendeur=interaction.user,
                         nom=nom_affiche, quantite=self.quantite, prix_unitaire=prix_item)

        embed = discord.Embed(title="✅ Vente confirmée !", description=f"Article : **{nom_affiche}**\nQuantité : **{self.quantite}**", color=0x2ECC71, timestamp=now_utc())
        embed.set_footer(text="Ticket fermé dans 10 secondes")
        await interaction.followup.edit_message(message_id=interaction.message.id, embed=embed, view=self)
        await asyncio.sleep(10)
        channel = guild.get_channel(self.ticket_channel_id)
        if channel:
            try: await channel.delete(reason="Vente confirmée")
            except Exception: pass

    @discord.ui.button(label="❌ Pas vendu", style=discord.ButtonStyle.red)
    async def pas_vendu(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.vendeur_id and not is_staff(interaction.user):
            await interaction.response.send_message("❌ Seul le vendeur peut décider.", ephemeral=True); return
        if self.done:
            await interaction.response.send_message("⚠️ Déjà effectué.", ephemeral=True); return
        self.done = True
        self._disable_all()
        self.stop()
        await interaction.response.defer()
        embed = discord.Embed(title="❌ Vente annulée", description="Le stock n'a pas été modifié.\nTicket fermé dans 10 secondes.", color=0xE74C3C, timestamp=now_utc())
        await interaction.followup.edit_message(message_id=interaction.message.id, embed=embed, view=self)
        await asyncio.sleep(10)
        guild   = interaction.guild
        channel = guild.get_channel(self.ticket_channel_id)
        if channel:
            try: await channel.delete(reason="Vente annulée")
            except Exception: pass


@bot.command(name="vendu")
async def vendu_cmd(ctx):
    topic = getattr(ctx.channel, "topic", None) or ""
    if not topic.startswith("commande|"):
        await ctx.send(embed=discord.Embed(title="❌ Mauvais salon", description="Cette commande s'utilise uniquement dans un **ticket de commande market**.", color=0xE74C3C), delete_after=6)
        return

    if not is_vendeur(ctx.author):
        await ctx.send(embed=discord.Embed(title="❌ Vous n'avez pas la permission d'utiliser cette commande", description="Cette commande est réservée aux **vendeurs certifiés** et au **staff**.", color=0xE74C3C), delete_after=8)
        return

    parts = topic.split("|")
    if len(parts) < 4:
        await ctx.send(embed=discord.Embed(title="❌ Ticket invalide", description="Les données de ce ticket sont invalides ou corrompues.", color=0xE74C3C), delete_after=6)
        return

    _, *nom_parts, quantite_str, vendeur_id_str = parts
    nom_key = "|".join(nom_parts)

    try:
        quantite   = int(quantite_str)
        vendeur_id = int(vendeur_id_str)
    except ValueError:
        await ctx.send(embed=discord.Embed(title="❌ Données corrompues", description="Impossible de lire la quantité ou l'ID vendeur du ticket.", color=0xE74C3C), delete_after=6)
        return

    data        = load_catalogue(ctx.guild.id)
    items       = data.get("items", {})
    nom_affiche = items[nom_key]["nom"] if nom_key in items else nom_key.split(":")[0]

    embed = discord.Embed(
        title="📦 Confirmation de vente",
        description=f"Article : **{nom_affiche}**\nQuantité : **{quantite}**\n\nConfirme ou annule la transaction.",
        color=0x9B59B6, timestamp=now_utc()
    )
    await ctx.send(embed=embed, view=VenduView(ctx.guild.id, vendeur_id, nom_key, quantite, ctx.channel.id))


async def _log_vente(guild: discord.Guild, acheteur_id, vendeur: discord.Member, nom: str, quantite: int, prix_unitaire: str):
    log_ch = cfg_channel(guild, "salon_ventes_log")
    if not log_ch:
        return
    nums = re.findall(r"[\d]+(?:[.,][\d]+)?", prix_unitaire)
    prix_total_str = "?"
    if nums:
        try:
            unit_val  = float(nums[0].replace(",", "."))
            total_val = unit_val * quantite
            prix_total_str = str(int(total_val)) if total_val == int(total_val) else f"{total_val:.2f}"
        except Exception:
            pass
    embed = discord.Embed(title="💸 Vente confirmée", color=0x2ECC71, timestamp=now_utc())
    embed.add_field(name="🔹 Article",    value=nom,           inline=True)
    embed.add_field(name="📦 Quantité",   value=str(quantite), inline=True)
    embed.add_field(name="💰 Prix unit.", value=prix_unitaire, inline=True)
    embed.add_field(name="🧾 Prix total", value=f"{quantite} × {prix_unitaire} = **{prix_total_str}**", inline=False)
    embed.add_field(name="🛒 Acheteur",  value=f"<@{acheteur_id}>" if acheteur_id else "Inconnu", inline=True)
    embed.add_field(name="👤 Vendeur",   value=vendeur.mention, inline=True)
    await log_ch.send(embed=embed)

# ═══════════════════════════════════════════════════════════════
#  TOGGLE RÔLE NOTIF MARCHÉ
# ═══════════════════════════════════════════════════════════════

class RoleToggleView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔔 Activer/désactiver les notifications", style=discord.ButtonStyle.blurple, custom_id="role_toggle_acheteur")
    async def toggle_role(self, interaction: discord.Interaction, button: discord.ui.Button):
        role = cfg_role(interaction.guild, "role_acheteur_notif")
        if not role:
            await interaction.response.send_message("❌ Rôle introuvable.", ephemeral=True); return
        await interaction.response.defer(ephemeral=True, thinking=False)
        member = interaction.user
        if role in member.roles:
            await member.remove_roles(role, reason="Toggle notif market")
            await interaction.followup.send("🔕 Notifications marché **désactivées**.", ephemeral=True)
        else:
            await member.add_roles(role, reason="Toggle notif market")
            await interaction.followup.send("🔔 Notifications marché **activées** !", ephemeral=True)


@bot.command(name="role")
async def role_cmd(ctx):
    if not is_staff(ctx.author):
        await ctx.send("❌ Réservé au staff.", delete_after=5); return
    channel = cfg_channel(ctx.guild, "salon_role_toggle")
    if not channel:
        await ctx.send("❌ Salon introuvable. Configurez `salon_role_toggle`.", delete_after=5); return
    embed = discord.Embed(title="🔔 Notifications du marché", description="Clique pour **activer ou désactiver** les notifications du marché.", color=0x9B59B6)
    await channel.send(embed=embed, view=RoleToggleView())
    await ctx.send(f"✅ Embed posté dans {channel.mention}", delete_after=5)

# ═══════════════════════════════════════════════════════════════
#  PUB
# ═══════════════════════════════════════════════════════════════

@bot.command(name="pub")
async def pub_cmd(ctx):
    if not is_staff(ctx.author):
        await ctx.send("❌ Réservé au staff.", delete_after=5); return
    texte = (
        "**__LA MYSTIC RECRUTE__** 🐦‍🔥\n"
        "Vous ne savez plus quoi faire ? Envie de PvP, de farm et de domination ?\n"
        "La faction **__Mystic__** est faite pour vous !\n"
        "Nous recrutons des **joueurs PvP expérimentés**, des **farmeurs motivés**, "
        "mais aussi des **nouveaux joueurs** qui veulent progresser et rejoindre une faction "
        "sérieuse avec de gros projets et une vraie ambiance d'équipe.\n"
        "---\n"
        "**__AU PROGRAMME :__**\n"
        "• Base claim solide et organisée\n"
        "• Sessions PvP régulières avec toute la faction\n"
        "• Du tryhard et de la compétition\n"
        "• Farms de faction énormes accessibles à tous les membres\n"
        "• F-Home commun pour toute la faction\n"
        "• Du fun, de la bonne humeur et beaucoup de rigolade\n"
        "• Et plein d'autres projets en équipe\n"
        "---\n"
        "**__PRÉREQUIS :__**\n"
        "• Avoir Minecraft\n"
        "• Âge minimum : 15 ans\n"
        "• Bonne humeur obligatoire\n"
        "• Être capable d'être en vocal pour les sessions PvP\n"
        "---\n"
        "📩 **__INTÉRESSÉ ?__**\n"
        "Le lien est dans la bio de **@lgm6143** pour rejoindre le Discord et envoyer ta candidature !\n"
        "---\n"
        "🐦‍🔥 **__MYSTIC — RISE LIKE A PHOENIX__**"
    )
    await ctx.send(texte)

# ═══════════════════════════════════════════════════════════════
#  SETUP / CONFIG
# ═══════════════════════════════════════════════════════════════

SETUP_TIMEOUT = 300
COULEURS_SETUP = {
    "violet": 0x9B59B6, "bleu": 0x3498DB, "vert": 0x2ECC71,
    "rouge": 0xE74C3C, "orange": 0xE67E22, "or": 0xF1C40F, "gris": 0x95A5A6,
}


def embed_setup(titre: str, desc: str, couleur: int = 0x9B59B6, footer: str = "⏱️ Timeout : 5 minutes") -> discord.Embed:
    e = discord.Embed(title=titre, description=desc, color=couleur, timestamp=now_utc())
    e.set_footer(text=footer)
    return e


def embed_ok(titre: str, desc: str) -> discord.Embed:
    return discord.Embed(title=f"✅ {titre}", description=desc, color=0x2ECC71, timestamp=now_utc())


def embed_err_setup(desc: str) -> discord.Embed:
    return discord.Embed(title="❌ Erreur", description=desc, color=0xE74C3C)


class _OuiNonView(discord.ui.View):
    def __init__(self, author_id: int):
        super().__init__(timeout=60)
        self.author_id = author_id
        self.result    = None
        self.msg       = None

    async def interaction_check(self, i): return i.user.id == self.author_id
    async def on_timeout(self):
        if self.msg:
            try: await self.msg.delete()
            except Exception: pass

    @discord.ui.button(label="✅ Oui", style=discord.ButtonStyle.green)
    async def oui(self, i, b):
        self.result = True; self.stop()
        await i.response.defer()
        if self.msg:
            try: await self.msg.delete()
            except Exception: pass

    @discord.ui.button(label="❌ Non", style=discord.ButtonStyle.red)
    async def non(self, i, b):
        self.result = False; self.stop()
        await i.response.defer()
        if self.msg:
            try: await self.msg.delete()
            except Exception: pass


class _TypeSalonView(discord.ui.View):
    def __init__(self, author_id: int):
        super().__init__(timeout=60)
        self.author_id = author_id
        self.result    = None
        self.msg       = None

    async def interaction_check(self, i): return i.user.id == self.author_id
    async def on_timeout(self):
        if self.msg:
            try: await self.msg.delete()
            except Exception: pass

    @discord.ui.button(label="📄 Salon textuel", style=discord.ButtonStyle.blurple)
    async def textuel(self, i, b):
        self.result = "textuel"; self.stop()
        await i.response.defer()
        if self.msg:
            try: await self.msg.delete()
            except Exception: pass

    @discord.ui.button(label="🔊 Salon vocal", style=discord.ButtonStyle.grey)
    async def vocal(self, i, b):
        self.result = "vocal"; self.stop()
        await i.response.defer()
        if self.msg:
            try: await self.msg.delete()
            except Exception: pass


class _VisibiliteView(discord.ui.View):
    def __init__(self, author_id: int):
        super().__init__(timeout=60)
        self.author_id = author_id
        self.result    = None
        self.msg       = None

    async def interaction_check(self, i): return i.user.id == self.author_id
    async def on_timeout(self):
        if self.msg:
            try: await self.msg.delete()
            except Exception: pass

    @discord.ui.button(label="🌍 Public", style=discord.ButtonStyle.green)
    async def pub(self, i, b):
        self.result = "public"; self.stop()
        await i.response.defer()
        if self.msg:
            try: await self.msg.delete()
            except Exception: pass

    @discord.ui.button(label="🔒 Privé", style=discord.ButtonStyle.red)
    async def priv(self, i, b):
        self.result = "prive"; self.stop()
        await i.response.defer()
        if self.msg:
            try: await self.msg.delete()
            except Exception: pass


class _PermsRoleView(discord.ui.View):
    def __init__(self, author_id: int):
        super().__init__(timeout=60)
        self.author_id = author_id
        self.result    = None
        self.msg       = None

    async def interaction_check(self, i): return i.user.id == self.author_id
    async def on_timeout(self):
        if self.msg:
            try: await self.msg.delete()
            except Exception: pass

    @discord.ui.button(label="👑 Admin", style=discord.ButtonStyle.red)
    async def admin(self, i, b):
        self.result = "admin"; self.stop()
        await i.response.defer()
        if self.msg:
            try: await self.msg.delete()
            except Exception: pass

    @discord.ui.button(label="🛡️ Modération", style=discord.ButtonStyle.blurple)
    async def modo(self, i, b):
        self.result = "modo"; self.stop()
        await i.response.defer()
        if self.msg:
            try: await self.msg.delete()
            except Exception: pass

    @discord.ui.button(label="👤 Membre simple", style=discord.ButtonStyle.green)
    async def membre(self, i, b):
        self.result = "membre"; self.stop()
        await i.response.defer()
        if self.msg:
            try: await self.msg.delete()
            except Exception: pass


class _SecuriteView(discord.ui.View):
    def __init__(self, author_id: int):
        super().__init__(timeout=60)
        self.author_id = author_id
        self.result    = None
        self.msg       = None

    async def interaction_check(self, i): return i.user.id == self.author_id
    async def on_timeout(self):
        if self.msg:
            try: await self.msg.delete()
            except Exception: pass

    @discord.ui.button(label="✅ Activer", style=discord.ButtonStyle.green)
    async def activer(self, i, b):
        self.result = True; self.stop()
        await i.response.defer()
        if self.msg:
            try: await self.msg.delete()
            except Exception: pass

    @discord.ui.button(label="❌ Désactiver", style=discord.ButtonStyle.red)
    async def desactiver(self, i, b):
        self.result = False; self.stop()
        await i.response.defer()
        if self.msg:
            try: await self.msg.delete()
            except Exception: pass


class _ParamsView(discord.ui.View):
    def __init__(self, author_id: int):
        super().__init__(timeout=60)
        self.author_id      = author_id
        self.configure_spam = False
        self.configure_alt  = False
        self.msg            = None

    async def interaction_check(self, i): return i.user.id == self.author_id
    async def on_timeout(self):
        if self.msg:
            try: await self.msg.delete()
            except Exception: pass

    @discord.ui.button(label="⚡ Configurer l'anti-spam", style=discord.ButtonStyle.blurple, row=0)
    async def btn_spam(self, i, b):
        self.configure_spam = True
        b.style = discord.ButtonStyle.green; b.label = "✅ Anti-spam sélectionné"; b.disabled = True
        await i.response.edit_message(view=self)

    @discord.ui.button(label="🛡️ Configurer l'anti-alt", style=discord.ButtonStyle.blurple, row=0)
    async def btn_alt(self, i, b):
        self.configure_alt = True
        b.style = discord.ButtonStyle.green; b.label = "✅ Anti-alt sélectionné"; b.disabled = True
        await i.response.edit_message(view=self)

    @discord.ui.button(label="✔️ Valider", style=discord.ButtonStyle.green, row=1)
    async def valider(self, i, b):
        self.stop()
        await i.response.defer()
        if self.msg:
            try: await self.msg.delete()
            except Exception: pass

    @discord.ui.button(label="❌ Annuler", style=discord.ButtonStyle.red, row=1)
    async def annuler(self, i, b):
        self.configure_spam = False; self.configure_alt = False; self.stop()
        await i.response.defer()
        if self.msg:
            try: await self.msg.delete()
            except Exception: pass


async def _wait_resp(ctx, titre: str, desc: str, timeout: int = 60) -> discord.Message | None:
    q = await ctx.send(embed=embed_setup(titre, desc, footer=f"⏱️ {timeout} secondes · 'skip' pour ignorer"))
    try:
        resp = await ctx.bot.wait_for(
            "message",
            check=lambda m: m.author.id == ctx.author.id and m.channel.id == ctx.channel.id,
            timeout=timeout
        )
        try: await q.delete()
        except Exception: pass
        try: await resp.delete()
        except Exception: pass
        return resp
    except asyncio.TimeoutError:
        try: await q.delete()
        except Exception: pass
        await ctx.send(embed=embed_err_setup("Temps écoulé. Revenez au menu principal."), delete_after=8)
        return None


async def _flux_salons(ctx):
    cfg    = load_config(ctx.guild.id)
    etapes = [
        ("salon_logs",          "📜 Salon des logs",          "Enregistre les actions : kicks, bans, modifications…"),
        ("salon_bienvenue",     "👋 Salon de bienvenue",      "Accueille les nouveaux membres automatiquement"),
        ("salon_roster",        "📋 Salon du roster",         "Affiche la liste des membres de la faction"),
        ("salon_catalogue",     "🏪 Salon catalogue",         "Affiche les articles disponibles à la vente"),
        ("salon_commandes",     "🛒 Salon commandes",         "Salon de commandes du marché"),
        ("salon_notifications", "🔔 Salon notifications",     "Alertes quand un article est ajouté au marché"),
        ("salon_ventes_log",    "💸 Salon logs des ventes",   "Historique des ventes confirmées"),
        ("salon_role_toggle",   "🎭 Salon rôles",             "Bouton pour activer les notifications marché"),
        ("salon_objectifs",     "🎯 Salon objectifs",         "Embed persistant des objectifs de la faction"),
        ("salon_gestion",       "📦 Salon gestion stock",     "Salon dédié à la gestion du stock via !gestion"),
    ]

    info = await ctx.send(embed=embed_setup(
        "📂 Configuration des salons",
        "Vous allez choisir les salons importants, **un par un**.\n\n"
        "👉 Mentionnez le salon avec `#nom-du-salon` ou tapez son nom.\n"
        "💡 Tapez `skip` pour ignorer une étape."
    ))

    modifies = []
    for cle, titre, desc in etapes:
        resp = await _wait_resp(ctx, titre, f"**{desc}**\n\nMentionnez le salon ou tapez son nom.")
        if not resp:
            break
        if resp.content.strip().lower() == "skip":
            continue
        ch = resp.channel_mentions[0] if resp.channel_mentions else discord.utils.find(
            lambda c: c.name.lower() == resp.content.strip().lstrip("#").lower(), ctx.guild.text_channels
        )
        if ch:
            cfg[cle] = ch.name
            modifies.append(f"✅ **{titre}** → {ch.mention}")
        else:
            modifies.append(f"⚠️ **{titre}** → `{resp.content.strip()}` introuvable, ignoré")

    save_config(ctx.guild.id, cfg)
    try: await info.delete()
    except Exception: pass

    if modifies:
        await ctx.send(embed=embed_ok("Salons configurés !", "\n".join(modifies)), delete_after=25)


async def _flux_roles(ctx):
    cfg    = load_config(ctx.guild.id)
    etapes = [
        ("role_staff",          "👑 Rôle(s) Staff / Admin",   "Rôles avec accès aux commandes d'administration", True),
        ("role_officier",       "⚔️ Rôle Officier",           "Officiers (sous-admins)", False),
        ("role_leader",         "👑 Rôle Leader",             "Leaders / fondateurs", False),
        ("role_visiteur",       "👤 Rôle Visiteur",           "Attribué automatiquement aux nouveaux arrivants", False),
        ("role_recruteur",      "📋 Rôle Recruteur",          "Mentionné et notifié dans les tickets de recrutement", False),
        ("role_vendeur",        "🏷️ Rôle Vendeur certifié",  "Accès aux commandes du marché", False),
        ("role_acheteur_notif", "🔔 Rôle Notifications",      "Mentionné lors des nouvelles offres du marché", False),
    ]

    info = await ctx.send(embed=embed_setup(
        "🎭 Configuration des rôles",
        "Vous allez choisir les rôles importants, **un par un**.\n\n"
        "👉 Mentionnez le rôle avec `@Nom` ou tapez son nom.\n"
        "💡 Tapez `skip` pour ignorer · Pour plusieurs : séparez par des virgules."
    ))

    modifies = []
    for cle, titre, desc, multi in etapes:
        hint = "\n\nPour plusieurs rôles : `@Leader, @Officier`" if multi else ""
        resp = await _wait_resp(ctx, titre, f"**{desc}**{hint}\n\nMentionnez le rôle ou tapez son nom.")
        if not resp:
            break
        if resp.content.strip().lower() == "skip":
            continue

        if multi:
            noms  = [p.strip().lstrip("@") for p in resp.content.split(",")]
            found = [r.name for r in resp.role_mentions] if resp.role_mentions else [
                r.name for n in noms
                if (r := discord.utils.find(lambda ro: ro.name.lower() == n.lower(), ctx.guild.roles))
            ]
            if found:
                cfg[cle] = found
                modifies.append(f"✅ **{titre}** → {', '.join(f'`{n}`' for n in found)}")
            else:
                modifies.append(f"⚠️ **{titre}** → introuvable, ignoré")
        else:
            role = resp.role_mentions[0] if resp.role_mentions else discord.utils.find(
                lambda r: r.name.lower() == resp.content.strip().lstrip("@").lower(), ctx.guild.roles
            )
            if role:
                cfg[cle] = role.name
                modifies.append(f"✅ **{titre}** → `{role.name}`")
            else:
                modifies.append(f"⚠️ **{titre}** → introuvable, ignoré")

    save_config(ctx.guild.id, cfg)
    try: await info.delete()
    except Exception: pass
    if modifies:
        await ctx.send(embed=embed_ok("Rôles configurés !", "\n".join(modifies)), delete_after=25)


async def _flux_securite(ctx):
    view = _SecuriteView(ctx.author.id)
    msg  = await ctx.send(embed=embed_setup(
        "🛡️ Protection anti-lien",
        "Voulez-vous **bloquer les liens** pour les membres ?\n\n"
        "✅ **Activer** — Les membres sans permission ne peuvent pas envoyer de liens.\n"
        "❌ **Désactiver** — Tout le monde peut envoyer des liens librement.\n\n"
        "💡 *Les admins et le staff ne sont jamais bloqués.*"
    ), view=view)
    view.msg = msg
    await view.wait()

    if view.result is None:
        return

    cfg = load_config(ctx.guild.id)
    cfg["antilink_enabled"] = view.result
    save_config(ctx.guild.id, cfg)

    if view.result:
        resp = await _wait_resp(ctx, "🛡️ Domaines autorisés",
            "Quels domaines sont autorisés malgré tout ?\n\n"
            "Séparez par des virgules.\n> Exemple : `tenor.com, giphy.com, youtube.com`\n\n"
            "💡 Tapez `skip` pour garder la valeur par défaut (tenor.com, giphy.com)"
        )
        if resp and resp.content.strip().lower() != "skip":
            domaines = [d.strip().lower() for d in resp.content.split(",") if d.strip()]
            if domaines:
                cfg["allowed_domains"] = domaines
                save_config(ctx.guild.id, cfg)

    statut = "✅ **activée**" if view.result else "❌ **désactivée**"
    await ctx.send(embed=embed_ok("Sécurité mise à jour", f"Protection anti-lien : {statut}"), delete_after=10)


async def _flux_params(ctx):
    view = _ParamsView(ctx.author.id)
    msg  = await ctx.send(embed=embed_setup("⚙️ Paramètres généraux", "Sélectionnez les paramètres à configurer, puis cliquez **Valider**."), view=view)
    view.msg = msg
    await view.wait()

    cfg = load_config(ctx.guild.id)

    if view.configure_spam:
        resp = await _wait_resp(ctx, "⚡ Anti-spam — Seuil",
            "Combien de messages en **6 secondes** avant avertissement ?\n\n"
            "👉 Tapez un nombre entre `2` et `10`\n> Valeur recommandée : `4`"
        )
        if resp:
            try:
                val = int(resp.content.strip())
                if 2 <= val <= 10:
                    cfg["spam_limit"] = val
                    await ctx.send(embed=embed_ok("Anti-spam", f"Seuil fixé à **{val} messages** / 6s."), delete_after=8)
            except ValueError:
                pass

    if view.configure_alt:
        resp = await _wait_resp(ctx, "🛡️ Anti-alt — Âge minimum",
            "Quel est l'**âge minimum** (en jours) d'un compte Discord pour ne pas être suspect ?\n\n"
            "👉 Tapez un nombre entre `7` et `365`\n> Valeur recommandée : `30`"
        )
        if resp:
            try:
                val = int(resp.content.strip())
                if 7 <= val <= 365:
                    cfg["alt_min_days"] = val
                    await ctx.send(embed=embed_ok("Anti-alt", f"Âge minimum : **{val} jours**."), delete_after=8)
            except ValueError:
                pass

    save_config(ctx.guild.id, cfg)


async def _flux_creer_salon(ctx):
    guild = ctx.guild

    type_v = _TypeSalonView(ctx.author.id)
    msg    = await ctx.send(embed=embed_setup("➕ Type de salon", "Quel type de salon voulez-vous créer ?"), view=type_v)
    type_v.msg = msg
    await type_v.wait()
    if type_v.result is None: return
    is_vocal = type_v.result == "vocal"

    resp_nom = await _wait_resp(ctx, f"➕ Nom du salon {'vocal' if is_vocal else 'textuel'}",
        "Tapez le **nom** du salon.\n> Exemple : `général`, `pvp-stratégie`\n💡 Espaces → tirets automatiquement.")
    if not resp_nom: return
    nom = resp_nom.content.strip().lower().replace(" ", "-")

    resp_cat = await _wait_resp(ctx, "📁 Catégorie (optionnel)",
        "Dans quelle **catégorie** placer ce salon ?\n> Tapez le nom de la catégorie, ou `skip`")
    category = None
    if resp_cat and resp_cat.content.strip().lower() != "skip":
        category = discord.utils.find(
            lambda c: isinstance(c, discord.CategoryChannel) and c.name.lower() == resp_cat.content.strip().lower(),
            guild.channels
        )

    visi_v = _VisibiliteView(ctx.author.id)
    msg_v  = await ctx.send(embed=embed_setup("🔒 Visibilité",
        "Ce salon sera :\n\n🌍 **Public** — Visible par tous\n🔒 **Privé** — Visible par certains rôles seulement"
    ), view=visi_v)
    visi_v.msg = msg_v
    await visi_v.wait()
    if visi_v.result is None: return

    overwrites = {}
    if visi_v.result == "prive":
        overwrites[guild.default_role] = discord.PermissionOverwrite(view_channel=False)
        resp_r = await _wait_resp(ctx, "🎭 Rôles autorisés",
            "Quels **rôles** peuvent voir ce salon privé ?\n> Mentionnez-les ou tapez leurs noms séparés par des virgules")
        if resp_r:
            roles_ok = resp_r.role_mentions or [
                discord.utils.find(lambda r: r.name.lower() == n.strip().lstrip("@").lower(), guild.roles)
                for n in resp_r.content.split(",")
            ]
            for r in roles_ok:
                if r:
                    overwrites[r] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

    try:
        ch = await (guild.create_voice_channel if is_vocal else guild.create_text_channel)(
            nom, category=category, overwrites=overwrites
        )
        visi_label = "🔒 Privé" if visi_v.result == "prive" else "🌍 Public"
        await ctx.send(embed=embed_ok("Salon créé !",
            f"{'🔊' if is_vocal else '💬'} {ch.mention} créé !\n"
            f"**Catégorie :** {category.name if category else 'Aucune'} · **Visibilité :** {visi_label}"
        ), delete_after=15)
    except discord.Forbidden:
        await ctx.send(embed=embed_err_setup("Je n'ai pas la permission de créer des salons."), delete_after=8)


async def _flux_creer_role(ctx):
    guild = ctx.guild

    resp_nom = await _wait_resp(ctx, "➕ Nom du rôle", "Tapez le **nom** du rôle.\n> Exemple : `Modérateur`, `VIP`")
    if not resp_nom: return
    nom = resp_nom.content.strip()

    resp_c = await _wait_resp(ctx, "🎨 Couleur (optionnel)",
        "Couleurs : `violet`, `bleu`, `vert`, `rouge`, `orange`, `or`, `gris`\nOu un code hex : `#FF5500`\n\n💡 `skip` = pas de couleur")
    couleur = discord.Color.default()
    if resp_c and resp_c.content.strip().lower() != "skip":
        c = resp_c.content.strip().lower()
        if c in COULEURS_SETUP:
            couleur = discord.Color(COULEURS_SETUP[c])
        elif c.startswith("#") and len(c) == 7:
            try: couleur = discord.Color(int(c[1:], 16))
            except ValueError: pass

    perm_v = _PermsRoleView(ctx.author.id)
    msg_p  = await ctx.send(embed=embed_setup("🔑 Permissions",
        "Quel niveau de permissions pour ce rôle ?\n\n"
        "👑 **Admin** — Toutes les permissions (dangereux !)\n"
        "🛡️ **Modération** — Kick, ban, gérer les messages\n"
        "👤 **Membre simple** — Lire et écrire seulement"
    ), view=perm_v)
    perm_v.msg = msg_p
    await perm_v.wait()
    if perm_v.result is None: return

    perms = discord.Permissions()
    if perm_v.result == "admin":
        perms = discord.Permissions.all()
    elif perm_v.result == "modo":
        perms = discord.Permissions(kick_members=True, ban_members=True, manage_messages=True,
                                     manage_channels=True, read_messages=True, send_messages=True)
    else:
        perms = discord.Permissions(read_messages=True, send_messages=True)

    mention_v = _OuiNonView(ctx.author.id)
    msg_m     = await ctx.send(embed=embed_setup("📢 Mentionnable ?", "Ce rôle pourra-t-il être mentionné par les membres ?"), view=mention_v)
    mention_v.msg = msg_m
    await mention_v.wait()
    mentionnable = mention_v.result if mention_v.result is not None else False

    try:
        role = await guild.create_role(name=nom, color=couleur, permissions=perms,
                                        mentionable=mentionnable, reason=f"Créé via !setup par {ctx.author}")
        await ctx.send(embed=embed_ok("Rôle créé !",
            f"{role.mention} créé !\n**Couleur :** `{str(couleur)}`\n**Mentionnable :** {'Oui' if mentionnable else 'Non'}"
        ), delete_after=15)
    except discord.Forbidden:
        await ctx.send(embed=embed_err_setup("Je n'ai pas la permission de créer des rôles."), delete_after=8)


async def _flux_voir_config(ctx):
    guild = ctx.guild
    cfg   = load_config(guild.id)

    def affiche(cle: str, val) -> str:
        if isinstance(val, list):
            parts = []
            for v in val:
                if "salon" in cle:
                    ch = resolve_channel(guild, v)
                    parts.append(f"#{ch.name}" if ch else f"⚠️`{v}`")
                elif "role" in cle:
                    r = resolve_role(guild, v)
                    parts.append(f"`{r.name}`" if r else f"⚠️`{v}`")
                else:
                    parts.append(str(v))
            return ", ".join(parts) or "_vide_"
        if "salon" in cle:
            ch = resolve_channel(guild, val)
            return f"#{ch.name}" if ch else f"⚠️`{val}`"
        if "role" in cle:
            r = resolve_role(guild, val)
            return f"`{r.name}`" if r else f"⚠️`{val}`"
        if "categorie" in cle:
            cat = resolve_category(guild, val)
            return f"📁{cat.name}" if cat else f"⚠️`{val}`"
        return str(val)

    embed = discord.Embed(title="📋 Configuration actuelle", color=0x9B59B6, timestamp=now_utc())
    salon_keys  = ["salon_logs","salon_bienvenue","salon_roster","salon_catalogue",
                   "salon_commandes","salon_notifications","salon_ventes_log","salon_role_toggle",
                   "salon_objectifs","salon_gestion"]
    role_keys   = ["role_staff","role_officier","role_leader","role_visiteur",
                   "role_recruteur","role_vendeur","role_acheteur_notif"]
    param_keys  = ["alt_min_days","spam_limit","raid_threshold","antilink_enabled"]
    cat_keys    = ["categorie_tickets","categorie_commandes"]

    embed.add_field(name="🔊 Salons",     value="\n".join(f"`{k}` → {affiche(k, cfg.get(k,'?'))}" for k in salon_keys), inline=False)
    embed.add_field(name="🎭 Rôles",      value="\n".join(f"`{k}` → {affiche(k, cfg.get(k,'?'))}" for k in role_keys),  inline=False)
    embed.add_field(name="📁 Catégories", value="\n".join(f"`{k}` → {affiche(k, cfg.get(k,'?'))}" for k in cat_keys),   inline=False)
    embed.add_field(name="⚙️ Paramètres", value="\n".join(f"`{k}` → `{cfg.get(k,'?')}`"           for k in param_keys), inline=False)
    embed.set_footer(text="⚠️ = introuvable sur ce serveur")
    await ctx.send(embed=embed, delete_after=60)


class SetupMainView(discord.ui.View):
    def __init__(self, ctx: commands.Context):
        super().__init__(timeout=SETUP_TIMEOUT)
        self.ctx = ctx
        self.msg: discord.Message | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("❌ Seul l'administrateur qui a lancé `!setup` peut interagir.", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        if self.msg:
            try: await self.msg.delete()
            except Exception: pass
        try:
            await self.ctx.send("⏱️ **Configuration annulée** — timeout (5 min).", delete_after=8)
        except Exception:
            pass

    @discord.ui.button(label="📂 Définir les salons",      style=discord.ButtonStyle.blurple, row=0)
    async def btn_salons(self, i, b):
        await i.response.defer()
        await _flux_salons(self.ctx)

    @discord.ui.button(label="🎭 Définir les rôles",       style=discord.ButtonStyle.blurple, row=0)
    async def btn_roles(self, i, b):
        await i.response.defer()
        await _flux_roles(self.ctx)

    @discord.ui.button(label="🛡️ Sécurité (anti-lien)",   style=discord.ButtonStyle.grey,    row=1)
    async def btn_secu(self, i, b):
        await i.response.defer()
        await _flux_securite(self.ctx)

    @discord.ui.button(label="⚙️ Paramètres généraux",     style=discord.ButtonStyle.grey,    row=1)
    async def btn_params(self, i, b):
        await i.response.defer()
        await _flux_params(self.ctx)

    @discord.ui.button(label="➕ Créer un salon",           style=discord.ButtonStyle.green,   row=2)
    async def btn_salon(self, i, b):
        await i.response.defer()
        await _flux_creer_salon(self.ctx)

    @discord.ui.button(label="➕ Créer un rôle",            style=discord.ButtonStyle.green,   row=2)
    async def btn_role(self, i, b):
        await i.response.defer()
        await _flux_creer_role(self.ctx)

    @discord.ui.button(label="📋 Voir la config actuelle", style=discord.ButtonStyle.grey,    row=3)
    async def btn_voir(self, i, b):
        await i.response.defer()
        await _flux_voir_config(self.ctx)

    @discord.ui.button(label="❌ Quitter",                 style=discord.ButtonStyle.red,     row=3)
    async def btn_quitter(self, i, b):
        self.stop()
        if self.msg:
            try: await self.msg.delete()
            except Exception: pass
        await i.response.send_message("👋 Configuration fermée.", ephemeral=True)


@bot.command(name="setup")
async def setup_cmd(ctx):
    if not ctx.author.guild_permissions.administrator:
        await ctx.send("❌ Réservé aux administrateurs.", delete_after=5)
        return
    embed = discord.Embed(
        title="⚙️ Configuration du serveur",
        description="Utilisez `!config` pour ouvrir le **panneau de configuration interactif** complet.",
        color=0x9B59B6
    )
    await ctx.send(embed=embed, delete_after=10)

# ═══════════════════════════════════════════════════════════════
#  CONFIG — panneau avancé
# ═══════════════════════════════════════════════════════════════

_NUM_KEYS  = {"alt_min_days", "raid_window_secs", "raid_threshold", "spam_limit", "spam_window"}
_LIST_KEYS = {"role_staff", "faction_roles", "salon_cmds_allowed", "allowed_domains"}

CONFIG_GROUPS = {
    "🔊 Salons": [
        ("salon_logs",          "📜 Logs de modération",          False),
        ("salon_bienvenue",     "👋 Salon de bienvenue",          False),
        ("salon_roster",        "📋 Roster faction",              False),
        ("salon_catalogue",     "🏪 Catalogue marché",            False),
        ("salon_commandes",     "🛒 Commandes marché",            False),
        ("salon_notifications", "🔔 Notifications marché",        False),
        ("salon_role_toggle",   "🎭 Bouton rôles",                False),
        ("salon_ventes_log",    "💸 Logs des ventes",             False),
        ("salon_recherche",     "🔍 Recherche articles",          False),
        ("salon_cmds_allowed",  "✅ Salons commandes (liste)",    True),
        ("salon_objectifs",     "🎯 Salon objectifs",             False),
        ("salon_gestion",       "📦 Salon gestion stock",         False),
    ],
    "🎭 Rôles": [
        ("role_staff",          "👑 Staff / Admin (liste)",       True),
        ("role_officier",       "⚔️ Officier",                   False),
        ("role_leader",         "👑 Leader",                      False),
        ("role_visiteur",       "👤 Visiteur (auto à l'arrivée)", False),
        ("role_recruteur",      "📋 Recruteur (tickets recrutement)", False),
        ("role_vendeur",        "🏷️ Vendeur certifié",           False),
        ("role_staff_market",   "🛒 Staff marché",                False),
        ("role_acheteur_notif", "🔔 Notif acheteur",             False),
        ("role_vendu",          "✅ Rôle vendu",                  False),
    ],
    "📁 Catégories": [
        ("categorie_tickets",   "🎫 Catégorie tickets",          False),
        ("categorie_commandes", "📦 Catégorie commandes",        False),
    ],
    "🎖️ Roster": [
        ("role_roster_leader",    "👑 Leader (roster)",             False),
        ("role_roster_officier",  "⚔️ Officier (roster)",          False),
        ("role_roster_confiance", "🛡️ Membre de confiance (roster)",False),
        ("role_roster_plus",      "⭐ Membre + (roster)",           False),
        ("role_roster_membre",    "🔹 Membre (roster)",             False),
        ("role_roster_recrue",    "🌱 Recrue (roster)",             False),
    ],
    "⚙️ Sécurité": [
        ("alt_min_days",     "🛡️ Anti-alt : âge minimum (jours)", False),
        ("raid_window_secs", "🚨 Anti-raid : fenêtre (secondes)", False),
        ("raid_threshold",   "🚨 Anti-raid : seuil membres",      False),
        ("spam_limit",       "⚡ Anti-spam : messages max",        False),
        ("spam_window",      "⚡ Anti-spam : fenêtre (secondes)",  False),
    ],
}


def _fmt_cfg_val(guild: discord.Guild, key: str, val) -> str:
    if isinstance(val, list):
        parts = []
        for v in val:
            if "salon" in key:
                ch = resolve_channel(guild, v)
                parts.append(f"<#{ch.id}>" if ch else f"⚠️`{v}`")
            elif "role" in key:
                r = resolve_role(guild, v)
                parts.append(r.mention if r else f"⚠️`{v}`")
            else:
                parts.append(f"`{v}`")
        return ", ".join(parts) if parts else "_vide_"
    if "salon" in key:
        ch = resolve_channel(guild, val)
        return f"<#{ch.id}>" if ch else f"⚠️`{val}`"
    if "role" in key:
        r = resolve_role(guild, val)
        return r.mention if r else f"⚠️`{val}`"
    if "categorie" in key:
        cat = resolve_category(guild, val)
        return f"📁 {cat.name}" if cat else f"⚠️`{val}`"
    return f"`{val}`"


def _build_group_embed(guild: discord.Guild, group: str) -> discord.Embed:
    cfg   = load_config(guild.id)
    keys  = CONFIG_GROUPS[group]
    embed = discord.Embed(
        title=f"⚙️ Config — {group}",
        description="Utilisez le menu ci-dessous pour **modifier une valeur**.\nRépondez dans ce salon quand demandé.\n⚠️ = introuvable sur ce serveur",
        color=0x9B59B6,
        timestamp=now_utc()
    )
    lines, cur_len, field_n = [], 0, 0
    for key, label, _ in keys:
        val  = cfg.get(key, "—")
        line = f"**{label}**\n`{key}` → {_fmt_cfg_val(guild, key, val)}"
        if cur_len + len(line) + 1 > 950 and lines:
            embed.add_field(name="\u200b", value="\n".join(lines), inline=False)
            lines, cur_len, field_n = [], 0, field_n + 1
        lines.append(line)
        cur_len += len(line) + 1
    if lines:
        embed.add_field(name="\u200b", value="\n".join(lines), inline=False)
    embed.set_footer(text="💡 Noms ou IDs acceptés • Listes : +valeur / -valeur / tout remplacer")
    return embed


def _build_home_embed(guild: discord.Guild) -> discord.Embed:
    embed = discord.Embed(
        title="⚙️ Configuration du serveur",
        description=(
            "Choisissez une **catégorie** dans le menu déroulant pour voir et modifier les valeurs.\n\n"
            + "\n".join(f"**{g}** — {len(v)} clé(s)" for g, v in CONFIG_GROUPS.items())
            + "\n\n⚠️ = introuvable sur ce serveur"
        ),
        color=0x9B59B6,
        timestamp=now_utc()
    )
    embed.set_footer(text="Timeout automatique après 5 minutes")
    return embed


class _GroupSelect(discord.ui.Select):
    def __init__(self, author_id: int):
        self.author_id = author_id
        options = []
        for grp in CONFIG_GROUPS:
            first = grp.split()[0]
            emoji = first if first and not first[0].isascii() else None
            opt   = discord.SelectOption(label=grp, value=grp)
            if emoji:
                opt.emoji = emoji
            options.append(opt)
        super().__init__(placeholder="📂 Choisir une catégorie…", options=options, custom_id="cfg_group_sel")

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Ce menu ne t'appartient pas.", ephemeral=True); return
        group = self.values[0]
        embed = _build_group_embed(interaction.guild, group)
        view  = _GroupView(self.author_id, group, interaction.message)
        await interaction.response.edit_message(embed=embed, view=view)


class _HomeView(discord.ui.View):
    def __init__(self, author_id: int, msg: discord.Message | None = None):
        super().__init__(timeout=300)
        self.author_id = author_id
        self.msg       = msg
        self.add_item(_GroupSelect(author_id))

    async def on_timeout(self):
        if self.msg:
            try:
                for item in self.children:
                    item.disabled = True
                await self.msg.edit(view=self)
            except Exception:
                pass

    @discord.ui.button(label="❌ Fermer", style=discord.ButtonStyle.red, row=1)
    async def fermer(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Ce menu ne t'appartient pas.", ephemeral=True); return
        self.stop()
        try: await interaction.message.delete()
        except Exception: pass
        await interaction.response.send_message("👋 Configuration fermée.", ephemeral=True)


class _KeySelect(discord.ui.Select):
    def __init__(self, author_id: int, group: str, orig_msg: discord.Message):
        self.author_id = author_id
        self.group     = group
        self.orig_msg  = orig_msg
        options = [
            discord.SelectOption(label=label[:50], value=key, description=f"clé : {key}")
            for key, label, _ in CONFIG_GROUPS[group]
        ]
        super().__init__(placeholder="🔑 Choisir la clé à modifier…", options=options[:25], custom_id="cfg_key_sel")

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Ce menu ne t'appartient pas.", ephemeral=True); return

        key      = self.values[0]
        label    = next((lbl for k, lbl, _ in CONFIG_GROUPS[self.group] if k == key), key)
        is_list  = key in _LIST_KEYS
        is_num   = key in _NUM_KEYS
        is_salon = "salon" in key or "categorie" in key
        is_role  = "role" in key

        if is_list and is_salon:
            action = "➕ Ajouter un salon : `+nom-du-salon`\n➖ Retirer un salon : `-nom-du-salon`\n🔄 Remplacer tout : `salon1, salon2`"
        elif is_list and is_role:
            action = "➕ Ajouter un rôle : `+NomDuRole`\n➖ Retirer un rôle : `-NomDuRole`\n🔄 Remplacer tout : `Role1, Role2`"
        elif is_list:
            action = "➕ `+valeur` · ➖ `-valeur` · 🔄 `val1, val2`"
        elif is_num:
            action = "Tapez un **nombre entier** (ex: `30`)"
        elif is_salon:
            action = "Tapez le **nom exact** du salon ou mentionnez-le avec `#`"
        elif is_role:
            action = "Tapez le **nom exact** du rôle ou mentionnez-le avec `@`"
        else:
            action = "Tapez la nouvelle valeur"

        cfg = load_config(interaction.guild.id)
        cur = _fmt_cfg_val(interaction.guild, key, cfg.get(key, "—"))

        embed = discord.Embed(
            title=f"✏️ Modifier : {label}",
            description=f"**Clé :** `{key}`\n**Valeur actuelle :** {cur}\n\n{action}\n\n💬 Répondez dans ce salon **(60 secondes)**.\nTapez `annuler` pour abandonner.",
            color=0x3498DB, timestamp=now_utc()
        )
        embed.set_footer(text="⏱️ 60 secondes pour répondre")
        await interaction.response.edit_message(embed=embed, view=None)

        guild = interaction.guild
        def chk(m: discord.Message) -> bool:
            return m.author.id == self.author_id and m.channel.id == interaction.channel.id

        try:
            msg = await bot.wait_for("message", check=chk, timeout=60)
        except asyncio.TimeoutError:
            await interaction.followup.send("⏰ Temps écoulé.", ephemeral=True)
            embed = _build_group_embed(guild, self.group)
            view  = _GroupView(self.author_id, self.group, self.orig_msg)
            await self.orig_msg.edit(embed=embed, view=view)
            return

        try: await msg.delete()
        except Exception: pass

        valeur = msg.content.strip()
        if valeur.lower() == "annuler":
            await interaction.followup.send("❌ Modification annulée.", ephemeral=True)
            embed = _build_group_embed(guild, self.group)
            view  = _GroupView(self.author_id, self.group, self.orig_msg)
            await self.orig_msg.edit(embed=embed, view=view)
            return

        cfg = load_config(guild.id)

        if is_num:
            try:
                cfg[key] = float(valeur) if "." in valeur else int(valeur)
            except ValueError:
                await interaction.followup.send(f"❌ `{key}` attend un nombre.", ephemeral=True)
                embed = _build_group_embed(guild, self.group)
                view  = _GroupView(self.author_id, self.group, self.orig_msg)
                await self.orig_msg.edit(embed=embed, view=view)
                return
        elif is_list:
            current = cfg.get(key, [])
            if isinstance(current, str):
                current = [current]
            if valeur.startswith("+"):
                to_add = valeur[1:].strip()
                if to_add and to_add not in current:
                    current.append(to_add)
                cfg[key] = current
            elif valeur.startswith("-"):
                to_rm    = valeur[1:].strip().lower()
                cfg[key] = [x for x in current if str(x).lower() != to_rm]
            else:
                cfg[key] = [v.strip() for v in valeur.split(",") if v.strip()]
        else:
            clean = re.sub(r"[<#@&>]", "", valeur).strip()
            cfg[key] = clean

        save_config(guild.id, cfg)

        val_saved   = cfg[key]
        @bot.event
async def on_ready():
    bot.add_view(ObjectifView())
    bot.add_view(TicketView())
    bot.add_view(RoleToggleView())
    await _cache_all_invites()
    print(f"✅ Connecté en tant que {bot.user} ({bot.user.id})")

TOKEN = os.environ.get("DISCORD_TOKEN")
bot.run(TOKEN)
