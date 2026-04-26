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
from datetime import datetime, timezone
from collections import defaultdict
from pathlib import Path

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# ═══════════════════════════════════════════════════════════════
#  CONFIGURATION PAR SERVEUR
#  Chaque serveur a son propre fichier config dans /app/data/configs/<guild_id>.json
#  Les valeurs peuvent être des noms (résolus dynamiquement) ou des IDs (fallback)
# ═══════════════════════════════════════════════════════════════

CONFIG_DIR  = Path("/app/data/configs")
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

# ── Valeurs par défaut (noms) ──────────────────────────────────
DEFAULT_CONFIG = {
    # Rôles
    "role_ticket":          "Staff",            # Rôle qui peut ouvrir les tickets
    "role_autorise":        "Staff",            # Rôle autorisé ticket panel
    "role_staff":           ["Leader", "Officier"],  # Rôles staff (plusieurs possibles)
    "role_officier":        "Officier",
    "role_leader":          "Leader",
    "role_visiteur":        "visiteur",
    "role_giveaway":        ["Leader", "Officier"],
    "role_vendeur":         "Vendeur Certifié",
    "role_staff_market":    "Staff Market",
    "role_acheteur_notif":  "Acheteur",
    "role_vendu":           "Vendu",

    # Salons
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

    # Catégories
    "categorie_tickets":    "Tickets",
    "categorie_commandes":  "Commandes",

    # Paramètres anti-alt / anti-raid
    "alt_min_days":         30,
    "raid_window_secs":     60,
    "raid_threshold":       3,

    # Paramètres anti-spam
    "spam_limit":           4,
    "spam_window":          6.0,

    # Roster (liste ordonnée de rôles à afficher avec emoji)
    "roster_roles": [
        {"nom": "Leader",             "emoji": "👑"},
        {"nom": "Officier",           "emoji": "⚔️"},
        {"nom": "Membre de confiance","emoji": "🛡️"},
        {"nom": "Membre +",           "emoji": "⭐"},
        {"nom": "Membre",             "emoji": "🔹"},
        {"nom": "Recrue",             "emoji": "🌱"},
    ],

    # Rôles faction (pour classement)
    "faction_roles": ["Leader", "Officier", "Membre de confiance", "Membre +", "Membre", "Recrue"],

    # Domaines autorisés pour les liens
    "allowed_domains": ["tenor.com", "giphy.com"],
}


def load_config(guild_id: int) -> dict:
    """Charge la config d'un serveur, crée un fichier par défaut si absent."""
    path = CONFIG_DIR / f"{guild_id}.json"
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Fusionne avec les valeurs par défaut (pour les nouvelles clés)
            merged = DEFAULT_CONFIG.copy()
            merged.update(data)
            return merged
        except Exception as e:
            print(f"[CONFIG] Erreur lecture {path} : {e}")
    # Crée le fichier par défaut
    save_config(guild_id, DEFAULT_CONFIG.copy())
    return DEFAULT_CONFIG.copy()


def save_config(guild_id: int, config: dict):
    """Sauvegarde la config d'un serveur."""
    path = CONFIG_DIR / f"{guild_id}.json"
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[CONFIG] Erreur sauvegarde {path} : {e}")


# ── Résolution dynamique des rôles et salons ──────────────────

def resolve_role(guild: discord.Guild, name_or_id) -> discord.Role | None:
    """Résout un rôle par nom ou ID."""
    if not name_or_id:
        return None
    # Essai par ID (int ou str numérique)
    try:
        rid = int(name_or_id)
        r = guild.get_role(rid)
        if r:
            return r
    except (ValueError, TypeError):
        pass
    # Essai par nom (insensible à la casse)
    name_lower = str(name_or_id).lower()
    return discord.utils.find(lambda r: r.name.lower() == name_lower, guild.roles)


def resolve_roles(guild: discord.Guild, names) -> list[discord.Role]:
    """Résout une liste de noms/IDs en rôles Discord."""
    if isinstance(names, (str, int)):
        names = [names]
    result = []
    for n in names:
        r = resolve_role(guild, n)
        if r:
            result.append(r)
    return result


def resolve_channel(guild: discord.Guild, name_or_id) -> discord.abc.GuildChannel | None:
    """Résout un salon par nom ou ID."""
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
    """Résout une liste de noms/IDs en salons Discord."""
    if isinstance(names, (str, int)):
        names = [names]
    result = []
    for n in names:
        c = resolve_channel(guild, n)
        if c:
            result.append(c)
    return result


def resolve_category(guild: discord.Guild, name_or_id) -> discord.CategoryChannel | None:
    """Résout une catégorie par nom ou ID."""
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


# ── Helpers de config ──────────────────────────────────────────

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
#  UTILITAIRES GÉNÉRAUX
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


async def get_log_channel(guild: discord.Guild) -> discord.TextChannel | None:
    return cfg_channel(guild, "salon_logs")


async def send_log(guild: discord.Guild, embed: discord.Embed):
    ch = await get_log_channel(guild)
    if ch:
        try:
            await ch.send(embed=embed)
        except Exception as e:
            print(f"[LOG] Erreur : {e}")


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
#  ANTI-SPAM (par serveur)
# ═══════════════════════════════════════════════════════════════

# guild_id -> user_id -> list[timestamps]
spam_tracker: dict[int, dict[int, list[float]]] = defaultdict(lambda: defaultdict(list))
spam_warned:  dict[int, set[int]] = defaultdict(set)


# ═══════════════════════════════════════════════════════════════
#  CHECK GLOBAL
# ═══════════════════════════════════════════════════════════════

EXEMPT_COMMANDS = {
    "pendu", "devine", "mot", "pileouface", "pendustop",
    "morpion", "morpionstop",
    "level", "lvl", "xp",
    "classement", "top", "leaderboard",
    "giveaway", "gw",
    "pub", "say", "dit", "fermer", "stock", "recherche",
    "help", "aide", "commandes", "info", "setup",
}


@bot.check
async def check_command_channel(ctx: commands.Context) -> bool:
    cmd = ctx.command.name if ctx.command else ""
    if cmd in EXEMPT_COMMANDS:
        return True
    if is_staff(ctx.author):
        return True
    if cmd in {"catalogue", "cataloguesupp"}:
        if not is_staff_market(ctx.author):
            await ctx.send("❌ Réservé aux vendeurs certifiés.", delete_after=5)
            return False
        allowed = cfg_channels(ctx.guild, "salon_cmds_allowed")
        commandes_ch = cfg_channel(ctx.guild, "salon_commandes")
        if commandes_ch:
            allowed.append(commandes_ch)
        allowed_ids = {c.id for c in allowed}
        if ctx.channel.id not in allowed_ids:
            ch_mentions = " ou ".join(f"<#{c.id}>" for c in allowed) or "les salons prévus"
            await ctx.send(f"❌ Utilise cette commande dans {ch_mentions}.", delete_after=8)
            return False
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
#  DONNÉES UTILISATEURS (XP)
# ═══════════════════════════════════════════════════════════════

DATA_DIR = Path("/app/data/users")
DATA_DIR.mkdir(parents=True, exist_ok=True)

xp_cooldowns: dict[str, float] = {}  # "guild_id:user_id" -> timestamp


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
#  DONNÉES PARTIES (par serveur)
# ═══════════════════════════════════════════════════════════════

GAMES_DIR = Path("/app/data/games")
GAMES_DIR.mkdir(parents=True, exist_ok=True)

active_pendu:    dict[str, dict] = {}   # "guild:channel" -> game
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
#  CATALOGUE (par serveur)
# ═══════════════════════════════════════════════════════════════

CATALOGUE_DIR = Path("/app/data/catalogues")
CATALOGUE_DIR.mkdir(parents=True, exist_ok=True)

_catalogue_msg_ids: dict[int, int] = {}   # guild_id -> msg_id
_pending_orders:    dict[str, bool] = {}  # "guild:user" -> en cours


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
    return {"items": {}, "msg_id": None}


def save_catalogue(guild_id: int, data: dict):
    path = catalogue_path(guild_id)
    tmp  = str(path) + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
    except Exception as e:
        print(f"[CATALOGUE] Erreur sauvegarde : {e}")


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
        for nom, item in items.items():
            embed.add_field(
                name=f"🔹 {item['nom']}",
                value=f"💰 **Prix :** {item['prix']}\n📦 **Stock :** {item['quantite']}\n👤 **Vendeur :** <@{item['vendeur_id']}>",
                inline=True
            )
    embed.set_footer(text="Utilisez !commande pour passer une commande")
    return embed


async def update_catalogue_message(guild: discord.Guild, items: dict):
    data    = load_catalogue(guild.id)
    channel = cfg_channel(guild, "salon_catalogue")
    if not channel:
        return
    embed  = build_catalogue_embed(items)
    msg_id = data.get("msg_id") or _catalogue_msg_ids.get(guild.id)
    if msg_id:
        try:
            msg = await channel.fetch_message(msg_id)
            await msg.edit(embed=embed)
            return
        except Exception:
            pass
    msg = await channel.send(embed=embed)
    _catalogue_msg_ids[guild.id] = msg.id
    data["msg_id"] = msg.id
    save_catalogue(guild.id, data)


async def send_notif(guild: discord.Guild, texte: str):
    channel = cfg_channel(guild, "salon_notifications")
    role    = cfg_role(guild, "role_acheteur_notif")
    if not channel:
        return
    mention = role.mention if role else ""
    await channel.send(f"{mention} {texte}")


# ═══════════════════════════════════════════════════════════════
#  TRANSCRIPT HTML
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
    cfg         = load_config(guild.id)
    roster_cfg  = cfg.get("roster_roles", [])
    categories  = {}
    ordered_keys = []
    for entry in roster_cfg:
        nom   = entry["nom"]
        emoji = entry.get("emoji", "🔹")
        role  = resolve_role(guild, nom)
        if role:
            categories[role.id] = {"label": f"{emoji} {nom}", "members": []}
            ordered_keys.append(role.id)

    for member in guild.members:
        if member.bot:
            continue
        for rid in ordered_keys:
            if any(r.id == rid for r in member.roles):
                categories[rid]["members"].append(member.mention)
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
#  VUES TICKETS
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
        self.closer      = closer
        self.action_taken = False
        self._msg        = None

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


# ═══════════════════════════════════════════════════════════════
#  CRÉATION TICKET
# ═══════════════════════════════════════════════════════════════

async def creer_ticket(interaction: discord.Interaction, type_ticket: str):
    guild    = interaction.guild
    role     = cfg_role(guild, "role_ticket")
    category = cfg_category(guild, "categorie_tickets")
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        interaction.user:   discord.PermissionOverwrite(view_channel=True, send_messages=True),
    }
    if role:
        overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

    channel = await guild.create_text_channel(
        f"ticket-{interaction.user.name}",
        category=category,
        overwrites=overwrites
    )

    role_mention = role.mention if role else "@Staff"
    if type_ticket == "recrutement":
        texte = (
            f"{role_mention} | {interaction.user.mention}\n\n"
            f"📋 **FORMULAIRE DE RECRUTEMENT**\n\n"
            f"**1️⃣ Présentation personnelle**\n➤ Pseudo EXACT en jeu :\n➤ Âge :\n"
            f"➤ Style de jeu :\n➤ Expérience :\n\n"
            f"**2️⃣ Objectifs**\n➤ Court terme :\n➤ Long terme :\n\n"
            f"**3️⃣ Motivation**\n➤ Pourquoi nous rejoindre ?\n➤ Ce que tu recherches :\n➤ Ce que tu apportes :\n\n"
            f"**4️⃣ Historique**\n➤ Anciennes factions/guildes :\n➤ Raison de départ :\n\n"
            f"**5️⃣ Stuff actuel**\n➤ Plateforme :\n➤ Équipement :\n\n"
            f"**6️⃣ Disponibilités**\n➤ Jours par semaine :\n➤ Plages horaires :\n\n"
            f"**✅ Confirmation**\n☐ Je respecterai les règles\n☐ Toute fausse info = refus"
        )
    else:
        texte = f"{role_mention} | {interaction.user.mention}\n\n📩 **Autre demande**\n\nExplique ta demande, un membre te répondra.\nPour fermer : `!fermer`"

    await channel.send(texte)
    await interaction.response.send_message(f"✅ Ticket créé : {channel.mention}", ephemeral=True)


# ═══════════════════════════════════════════════════════════════
#  COMMANDES TICKETS
# ═══════════════════════════════════════════════════════════════

@bot.command()
async def ticket(ctx):
    role = cfg_role(ctx.guild, "role_autorise")
    if role and role not in ctx.author.roles and not is_staff(ctx.author):
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


# ═══════════════════════════════════════════════════════════════
#  COMMANDES ROSTER
# ═══════════════════════════════════════════════════════════════

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
#  COMMANDES MODÉRATION
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


# ═══════════════════════════════════════════════════════════════
#  COMMANDE INFO
# ═══════════════════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════════════════
#  COMMANDE !say
# ═══════════════════════════════════════════════════════════════

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
#  ON_MESSAGE : ANTI-LIENS + ANTI-SPAM + XP
# ═══════════════════════════════════════════════════════════════

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild:
        await bot.process_commands(message)
        return
    member = message.author
    cfg    = load_config(message.guild.id)

    # ── Anti-liens ──
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

    # ── Anti-spam ──
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


# ═══════════════════════════════════════════════════════════════
#  LOGS AUTO — MESSAGES
# ═══════════════════════════════════════════════════════════════

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

_recent_suspects: dict[int, list[float]] = defaultdict(list)  # guild_id -> timestamps


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
    cfg          = load_config(member.guild.id)
    age_days     = (datetime.now(timezone.utc) - member.created_at).days
    officier     = cfg_role(member.guild, "role_officier")
    leader       = cfg_role(member.guild, "role_leader")
    mentions     = " ".join(r.mention for r in [officier, leader] if r)
    raisons_str  = "\n".join(f"- {r}" for r in reasons)
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
#  LOGS AUTO — MEMBRES
# ═══════════════════════════════════════════════════════════════

@bot.event
async def on_member_join(member: discord.Member):
    cfg = load_config(member.guild.id)

    # Rôle visiteur
    visitor_role = cfg_role(member.guild, "role_visiteur")
    if visitor_role:
        try:
            await member.add_roles(visitor_role, reason="Rôle visiteur automatique")
        except Exception as e:
            print(f"[WELCOME] Erreur rôle visiteur : {e}")

    # Message de bienvenue
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

    # Log arrivée
    age_days = (datetime.now(timezone.utc) - member.created_at).days
    embed = discord.Embed(title="📥 Membre arrivé", color=0x2ECC71, timestamp=now_utc())
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="👤 Membre",      value=f"{member} ({member.id})",                              inline=True)
    embed.add_field(name="📅 Compte créé", value=discord.utils.format_dt(member.created_at, style="D"), inline=True)
    embed.add_field(name="⏱️ Âge",         value=f"{age_days} jour(s)",                                  inline=True)
    embed.add_field(name="👥 Total",       value=str(member.guild.member_count),                          inline=True)
    await send_log(member.guild, embed)

    # Anti-Alt
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
    # Roster auto
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

    # Log rôles
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

    # Log pseudo
    if before.display_name != after.display_name:
        embed = discord.Embed(title="📝 Pseudo modifié", color=0x3498DB, timestamp=now_utc())
        embed.add_field(name="👤 Membre", value=f"{after} ({after.id})", inline=True)
        embed.add_field(name="📝 Avant",  value=before.display_name,     inline=True)
        embed.add_field(name="📝 Après",  value=after.display_name,      inline=True)
        await send_log(after.guild, embed)


# ═══════════════════════════════════════════════════════════════
#  LOGS AUTO — VOCAL
# ═══════════════════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════════════════
#  LOGS AUTO — SALONS
# ═══════════════════════════════════════════════════════════════

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
#  COMMANDE LEVEL
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


# ═══════════════════════════════════════════════════════════════
#  MINI-JEU : PILE OU FACE
# ═══════════════════════════════════════════════════════════════

@bot.command(name="pileouface", aliases=["pof", "coinflip"])
async def pof_cmd(ctx):
    result = random.choice(["🪙 **Pile**", "🔵 **Face**"])
    embed  = discord.Embed(title="🪙 Pile ou Face", description=f"Résultat : {result}", color=0xF1C40F)
    await ctx.send(embed=embed)


# ═══════════════════════════════════════════════════════════════
#  MINI-JEU : PENDU
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
#  MINI-JEU : MORPION
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
    gw_roles = cfg_roles(ctx.guild, "role_giveaway")
    if not any(r in ctx.author.roles for r in gw_roles) and not ctx.author.guild_permissions.administrator:
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
    faction_members = [
        (uid, u, guild.get_member(int(uid)))
        for uid, u in data.items()
        if guild.get_member(int(uid)) and any(
            r.name in faction_role_names for r in guild.get_member(int(uid)).roles
        )
    ]
    faction_members.sort(key=lambda x: (x[1].get("level", 0), x[1].get("xp", 0)), reverse=True)
    top_faction = "\n".join(
        f"{medals[i] if i < 3 else f'`#{i+1}`'} **{m.display_name}** — Niv. {u.get('level',0)}"
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
#  SYSTÈME CATALOGUE — COMMANDES
# ═══════════════════════════════════════════════════════════════

@bot.command(name="catalogue")
async def catalogue_cmd(ctx, nom: str = None, quantite: str = None, *, prix: str = None):
    if not is_vendeur(ctx.author):
        await ctx.send("❌ Réservé aux vendeurs certifiés.", delete_after=5); return
    if nom is None or quantite is None or prix is None:
        await ctx.send("❌ `!catalogue [nom] [quantité] [prix]`", delete_after=10); return
    try:
        qty = int(quantite)
        if qty <= 0: raise ValueError
    except ValueError:
        await ctx.send("❌ La quantité doit être un nombre entier positif.", delete_after=6); return

    data     = load_catalogue(ctx.guild.id)
    items    = data.get("items", {})
    nom_key  = nom.lower()

    if nom_key in items:
        items[nom_key]["quantite"] += qty
        items[nom_key]["prix"]      = prix
        action = f"✏️ **{nom}** mis à jour — stock : {items[nom_key]['quantite']} | prix : {prix}"
    else:
        items[nom_key] = {"nom": nom, "quantite": qty, "prix": prix, "vendeur_id": ctx.author.id}
        action = f"➕ **{nom}** ajouté — stock : {qty} | prix : {prix} | vendeur : {ctx.author.mention}"

    data["items"] = items
    save_catalogue(ctx.guild.id, data)
    await update_catalogue_message(ctx.guild, items)
    await send_notif(ctx.guild, action)
    await ctx.send(f"✅ Catalogue mis à jour : **{nom}** (x{qty} à {prix})", delete_after=8)


@bot.command(name="cataloguesupp")
async def cataloguesupp_cmd(ctx, nom: str = None):
    if not is_vendeur(ctx.author):
        await ctx.send("❌ Réservé aux vendeurs certifiés.", delete_after=5); return
    if nom is None:
        await ctx.send("❌ `!cataloguesupp [nom]`", delete_after=8); return

    data    = load_catalogue(ctx.guild.id)
    items   = data.get("items", {})
    nom_key = nom.lower()

    if nom_key not in items:
        await ctx.send(f"❌ Article **{nom}** introuvable.", delete_after=6); return

    del items[nom_key]
    data["items"] = items
    save_catalogue(ctx.guild.id, data)
    await update_catalogue_message(ctx.guild, items)
    await send_notif(ctx.guild, f"🗑️ **{nom}** supprimé du catalogue par {ctx.author.mention}")
    await ctx.send(f"✅ **{nom}** supprimé du catalogue.", delete_after=8)


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

    data        = load_catalogue(ctx.guild.id)
    items       = data.get("items", {})
    terme_lower = terme.lower().strip()
    resultats   = {k: v for k, v in items.items() if terme_lower in k.lower() or terme_lower in v["nom"].lower()}

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


# ─────────────────────────────────────────────
#  Commande !commande
# ─────────────────────────────────────────────

class CommandeSelect(discord.ui.Select):
    def __init__(self, guild_id: int, items: dict):
        self.guild_id = guild_id
        options = [
            discord.SelectOption(
                label=item["nom"][:25],
                value=key,
                description=f"Stock: {item['quantite']} | {item['prix'][:40]}"[:100]
            )
            for key, item in items.items()
        ]
        super().__init__(
            placeholder="🔹 Choisis un article…",
            min_values=1, max_values=1,
            options=options[:25],
            custom_id=f"commande_select_{guild_id}"
        )

    async def callback(self, interaction: discord.Interaction):
        gid = interaction.guild.id
        uid = interaction.user.id
        pk  = f"{gid}:{uid}"

        if _pending_orders.get(pk):
            await interaction.response.send_message("⏳ Tu as déjà une commande en cours.", ephemeral=True)
            return

        data    = load_catalogue(gid)
        items   = data.get("items", {})
        nom_key = self.values[0]
        item    = items.get(nom_key)

        if not item or item["quantite"] <= 0:
            await interaction.response.send_message("❌ Article indisponible.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        _pending_orders[pk] = True
        try:
            embed_ask = discord.Embed(
                title=f"🛒 Commande — {item['nom']}",
                description=f"📦 **Stock :** {item['quantite']}\n💰 **Prix :** {item['prix']}\n\nÉcris la **quantité** souhaitée.\n*(60 secondes)*",
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
                name=f"cmd-{acheteur.display_name[:18]}-{item['nom'][:10]}",
                category=category,
                overwrites=overwrites,
                topic=f"commande|{nom_key}|{qty}|{item['vendeur_id']}"
            )

            # Calcul prix total
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


class CommandeView(discord.ui.View):
    def __init__(self, guild_id: int, items: dict):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        if items:
            self.add_item(CommandeSelect(guild_id, items))

    @discord.ui.button(label="🔄 Rafraîchir", style=discord.ButtonStyle.grey, row=1, custom_id="commande_refresh")
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True, thinking=False)
        data  = load_catalogue(interaction.guild.id)
        items = data.get("items", {})
        if not items:
            await interaction.followup.send("📭 Le catalogue est vide.", ephemeral=True)
            return
        await interaction.message.edit(view=CommandeView(interaction.guild.id, items))
        await interaction.followup.send("✅ Catalogue rafraîchi !", ephemeral=True)


@bot.command(name="commande")
async def commande_cmd(ctx):
    if not is_staff(ctx.author):
        await ctx.send("❌ Réservé au staff.", delete_after=5); return
    data  = load_catalogue(ctx.guild.id)
    items = data.get("items", {})
    if not items:
        await ctx.send("📭 Le catalogue est vide.", delete_after=8); return
    embed = discord.Embed(
        title="🛒 Passer une commande",
        description="Sélectionne un article dans le menu puis indique la quantité.",
        color=0x9B59B6, timestamp=now_utc()
    )
    embed.set_footer(text="Cet embed est permanent et réutilisable")
    await ctx.send(embed=embed, view=CommandeView(ctx.guild.id, items))


# ─────────────────────────────────────────────
#  Commande !vendu
# ─────────────────────────────────────────────

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
        nom_affiche = items[self.nom_key]["nom"] if self.nom_key in items else self.nom_key
        prix_item   = items[self.nom_key].get("prix", "?") if self.nom_key in items else "?"

        # Trouve l'acheteur dans les permissions du ticket
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
            data["items"] = items
            save_catalogue(self.guild_id, data)
            await update_catalogue_message(guild, items)

        await _log_vente(guild=guild, acheteur_id=acheteur_id, vendeur=interaction.user,
                         nom=nom_affiche, quantite=self.quantite, prix_unitaire=prix_item)

        embed = discord.Embed(title="✅ Vente confirmée !",
            description=f"Article : **{nom_affiche}**\nQuantité : **{self.quantite}**",
            color=0x2ECC71, timestamp=now_utc())
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
        embed = discord.Embed(title="❌ Vente annulée",
            description="Le stock n'a pas été modifié.\nTicket fermé dans 10 secondes.",
            color=0xE74C3C, timestamp=now_utc())
        await interaction.followup.edit_message(message_id=interaction.message.id, embed=embed, view=self)
        await asyncio.sleep(10)
        guild   = interaction.guild
        channel = guild.get_channel(self.ticket_channel_id)
        if channel:
            try: await channel.delete(reason="Vente annulée")
            except Exception: pass


@bot.command(name="vendu")
async def vendu_cmd(ctx):
    if not ctx.channel.topic or not ctx.channel.topic.startswith("commande|"):
        await ctx.send("❌ Uniquement dans un ticket de commande.", delete_after=6); return
    parts = ctx.channel.topic.split("|")
    if len(parts) < 4:
        await ctx.send("❌ Données du ticket invalides.", delete_after=6); return
    _, nom_key, quantite_str, vendeur_id_str = parts[:4]
    try:
        quantite   = int(quantite_str)
        vendeur_id = int(vendeur_id_str)
    except ValueError:
        await ctx.send("❌ Données corrompues.", delete_after=6); return
    if ctx.author.id != vendeur_id and not is_staff(ctx.author):
        await ctx.send("❌ Seul le vendeur peut utiliser cette commande.", delete_after=6); return
    data        = load_catalogue(ctx.guild.id)
    items       = data.get("items", {})
    nom_affiche = items[nom_key]["nom"] if nom_key in items else nom_key
    embed = discord.Embed(title="📦 Confirmation de vente",
        description=f"Article : **{nom_affiche}**\nQuantité : **{quantite}**",
        color=0x9B59B6, timestamp=now_utc())
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


# ─────────────────────────────────────────────
#  Toggle rôle notifications
# ─────────────────────────────────────────────

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
    embed = discord.Embed(
        title="🔔 Notifications du marché",
        description="Clique pour **activer ou désactiver** les notifications du marché.",
        color=0x9B59B6
    )
    await channel.send(embed=embed, view=RoleToggleView())
    await ctx.send(f"✅ Embed posté dans {channel.mention}", delete_after=5)


# ═══════════════════════════════════════════════════════════════
#  COMMANDE !pub
# ═══════════════════════════════════════════════════════════════

@bot.command(name="pub")
async def pub_cmd(ctx):
    if not is_staff(ctx.author):
        await ctx.send("❌ Réservé au staff.", delete_after=5); return
    texte = (
        "🔥 **__RECRUTEMENT OUVERT__** 🔥\n\n"
        "Envie de PvP, de farm et de domination ?\n"
        "Rejoins notre faction !\n\n"
        "🎯 **AU PROGRAMME :**\n"
        "• Base organisée\n• Sessions PvP régulières\n• Farms accessibles à tous\n• Bonne ambiance\n\n"
        "✏️ **PRÉREQUIS :**\n• Bonne humeur obligatoire 😄\n• Être actif\n\n"
        "📩 **Intéressé ?** Ouvre un ticket !"
    )
    await ctx.send(texte)


# ═══════════════════════════════════════════════════════════════
#  COMMANDE !setup — Configuration interactive par serveur
# ═══════════════════════════════════════════════════════════════

@bot.command(name="setup")
async def setup_cmd(ctx):
    """Configure le bot pour ce serveur. Réservé aux administrateurs."""
    if not ctx.author.guild_permissions.administrator:
        await ctx.send("❌ Réservé aux administrateurs.", delete_after=5)
        return

    cfg = load_config(ctx.guild.id)

    embed = discord.Embed(
        title="⚙️ Configuration — Bot",
        description=(
            "La configuration de ce serveur est stockée dans un fichier JSON.\n\n"
            "**Pour modifier un paramètre**, utilisez :\n"
            "`!setconfig [clé] [valeur]`\n\n"
            "**Exemples :**\n"
            "`!setconfig salon_logs logs-modération`\n"
            "`!setconfig role_staff Leader,Officier`\n"
            "`!setconfig alt_min_days 30`\n\n"
            "**Pour voir la config actuelle :**\n"
            "`!config`"
        ),
        color=0x9B59B6
    )
    embed.add_field(
        name="📋 Clés disponibles",
        value=(
            "`salon_logs` · `salon_roster` · `salon_bienvenue`\n"
            "`salon_catalogue` · `salon_commandes` · `salon_notifications`\n"
            "`salon_role_toggle` · `salon_ventes_log` · `salon_cmds_allowed`\n"
            "`role_staff` · `role_officier` · `role_leader` · `role_visiteur`\n"
            "`role_giveaway` · `role_vendeur` · `role_acheteur_notif`\n"
            "`categorie_tickets` · `categorie_commandes`\n"
            "`alt_min_days` · `raid_window_secs` · `raid_threshold`\n"
            "`spam_limit` · `spam_window`"
        ),
        inline=False
    )
    embed.set_footer(text="Les noms sont insensibles à la casse. Les listes se séparent par des virgules.")
    await ctx.send(embed=embed)


@bot.command(name="setconfig")
async def setconfig_cmd(ctx, cle: str = None, *, valeur: str = None):
    """Modifie une valeur de configuration. Réservé aux administrateurs."""
    if not ctx.author.guild_permissions.administrator:
        await ctx.send("❌ Réservé aux administrateurs.", delete_after=5); return
    if cle is None or valeur is None:
        await ctx.send("❌ `!setconfig [clé] [valeur]`", delete_after=6); return

    cfg = load_config(ctx.guild.id)
    cle = cle.lower().strip()

    # Clés numériques
    if cle in {"alt_min_days", "raid_window_secs", "raid_threshold", "spam_limit", "spam_window"}:
        try:
            cfg[cle] = float(valeur) if "." in valeur else int(valeur)
        except ValueError:
            await ctx.send(f"❌ `{cle}` doit être un nombre.", delete_after=5); return
    # Clés liste
    elif cle in {"role_staff", "role_giveaway", "faction_roles", "salon_cmds_allowed", "allowed_domains"}:
        cfg[cle] = [v.strip() for v in valeur.split(",") if v.strip()]
    # Clés texte simple
    else:
        cfg[cle] = valeur.strip()

    save_config(ctx.guild.id, cfg)
    await ctx.send(f"✅ `{cle}` mis à jour → `{cfg[cle]}`", delete_after=8)


@bot.command(name="config")
async def config_cmd(ctx):
    """Affiche la configuration actuelle du serveur. Réservé aux administrateurs."""
    if not ctx.author.guild_permissions.administrator:
        await ctx.send("❌ Réservé aux administrateurs.", delete_after=5); return

    cfg = load_config(ctx.guild.id)

    def resolve_display(key: str, val) -> str:
        if isinstance(val, list):
            items = []
            for v in val:
                if key.startswith("salon") or "salon" in key:
                    ch = resolve_channel(ctx.guild, v)
                    items.append(f"#{ch.name}" if ch else f"⚠️ `{v}` (introuvable)")
                elif key.startswith("role") or "role" in key:
                    r = resolve_role(ctx.guild, v)
                    items.append(f"@{r.name}" if r else f"⚠️ `{v}` (introuvable)")
                else:
                    items.append(str(v))
            return ", ".join(items) if items else "_vide_"
        elif key.startswith("salon") or "salon" in key:
            ch = resolve_channel(ctx.guild, val)
            return f"#{ch.name}" if ch else f"⚠️ `{val}` (introuvable)"
        elif key.startswith("role") or "role" in key:
            r = resolve_role(ctx.guild, val)
            return f"@{r.name}" if r else f"⚠️ `{val}` (introuvable)"
        elif key.startswith("categorie"):
            cat = resolve_category(ctx.guild, val)
            return f"📁 {cat.name}" if cat else f"⚠️ `{val}` (introuvable)"
        return str(val)

    # Groupes de clés à afficher
    groups = {
        "🔊 Salons": ["salon_logs", "salon_roster", "salon_bienvenue", "salon_catalogue",
                       "salon_commandes", "salon_notifications", "salon_role_toggle",
                       "salon_ventes_log", "salon_cmds_allowed", "salon_recherche"],
        "🎭 Rôles":  ["role_staff", "role_officier", "role_leader", "role_visiteur",
                       "role_ticket", "role_autorise", "role_giveaway", "role_vendeur",
                       "role_staff_market", "role_acheteur_notif", "role_vendu"],
        "📁 Catégories": ["categorie_tickets", "categorie_commandes"],
        "⚙️ Paramètres": ["alt_min_days", "raid_window_secs", "raid_threshold", "spam_limit", "spam_window"],
    }

    embed = discord.Embed(title="⚙️ Configuration du serveur", color=0x9B59B6, timestamp=now_utc())
    for group_name, keys in groups.items():
        lines = []
        for k in keys:
            if k in cfg and k not in {"roster_roles", "faction_roles"}:
                lines.append(f"`{k}` → {resolve_display(k, cfg[k])}")
        if lines:
            embed.add_field(name=group_name, value="\n".join(lines), inline=False)

    embed.set_footer(text="!setconfig [clé] [valeur] pour modifier • ⚠️ = non résolu sur ce serveur")
    await ctx.send(embed=embed)


# ═══════════════════════════════════════════════════════════════
#  COMMANDE AIDE
# ═══════════════════════════════════════════════════════════════

bot.remove_command("help")


@bot.command(name="help", aliases=["aide", "commandes"])
async def help_cmd(ctx):
    staff = is_staff(ctx.author)
    embed = discord.Embed(
        title="📖 Aide — Bot",
        description="Toutes les commandes disponibles.\n*(🔒 = Staff | 🏷️ = Vendeur certifié)*",
        color=0x9B59B6
    )
    embed.add_field(
        name="━━━━━━━━━━━━━━━━━━\n👤 Général",
        value="`!info [@membre]` · `!level [@membre]` · `!classement` · `!pub` 🔒 · `!help`",
        inline=False
    )
    embed.add_field(
        name="━━━━━━━━━━━━━━━━━━\n🎫 Tickets",
        value="`!ticket` 🔒 — Panneau tickets\n`!fermer` — Fermer un ticket",
        inline=False
    )
    embed.add_field(
        name="━━━━━━━━━━━━━━━━━━\n🏪 Marché",
        value=(
            "`!recherche [item]` — Chercher un article\n"
            "`!catalogue [nom] [qté] [prix]` 🏷️ — Ajouter/MAJ article\n"
            "`!cataloguesupp [nom]` 🏷️ — Supprimer article\n"
            "`!stock [@membre]` 🏷️ — Voir son stock\n"
            "`!commande` 🔒 — Menu de commande interactif\n"
            "`!vendu` 🏷️ — Confirmer/annuler une vente\n"
            "`!role` 🔒 — Bouton toggle notifications"
        ),
        inline=False
    )
    embed.add_field(
        name="━━━━━━━━━━━━━━━━━━\n🎯 Mini-jeux",
        value=(
            "**Pendu** : `!pendu` · `!devine [lettre]` · `!mot [mot]` · `!pendustop` 🔒\n"
            "**Morpion** : `!morpion @joueur` · `!morpionstop` 🔒\n"
            "**Autres** : `!pileouface` · `!giveaway [durée] [récompense]` 🔒"
        ),
        inline=False
    )
    if staff:
        embed.add_field(
            name="━━━━━━━━━━━━━━━━━━\n🔨 Modération 🔒",
            value=(
                "`!ban @membre [raison]` · `!kick @membre [raison]`\n"
                "`!mute @membre` · `!unmute @membre`\n"
                "`!effacer <n>` · `!roster` · `!say #salon message`"
            ),
            inline=False
        )
        embed.add_field(
            name="━━━━━━━━━━━━━━━━━━\n⚙️ Configuration 🔒 (Admin)",
            value="`!setup` · `!config` · `!setconfig [clé] [valeur]`",
            inline=False
        )
    embed.add_field(
        name="━━━━━━━━━━━━━━━━━━\n🛡️ Protections auto",
        value="🔗 Anti-liens · ⚡ Anti-spam · 🛡️ Anti-alt · 🚨 Anti-raid",
        inline=False
    )
    embed.set_footer(text="🔒 = Staff | 🏷️ = Vendeur certifié ou Staff")
    await ctx.send(embed=embed)


@bot.event
async def on_command_error(ctx: commands.Context, error):
    if isinstance(error, commands.CommandNotFound):
        await ctx.send(
            "❌ Commande inconnue. Essayez `!help` pour voir les commandes disponibles.",
            delete_after=8
        )
    elif isinstance(error, commands.CheckFailure):
        pass
    else:
        print(f"[ERROR] {ctx.command} : {error}")


# ═══════════════════════════════════════════════════════════════
#  RESTORE AU DÉMARRAGE
# ═══════════════════════════════════════════════════════════════

async def _restore_all_games():
    for path in GAMES_DIR.glob("*.json"):
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
                k     = gk(guild_id, ch_id)
                data["guessed"]   = list(data.get("guessed", []))
                data["letter_cd"] = {}
                data["channel_id"] = ch_id
                active_pendu[k] = data
                await _start_pendu_timer(k, guild_id, remaining)
                print(f"[RESTORE] Pendu restauré : guild={guild_id} ch={ch_id}")
            elif key_str.startswith("morpion_"):
                ch_id = int(key_str.split("_", 1)[1])
                k     = gk(guild_id, ch_id)
                active_morpion[k] = data
                await _start_morpion_timer(k, guild_id, remaining)
                print(f"[RESTORE] Morpion restauré : guild={guild_id} ch={ch_id}")


async def _restore_all_catalogues():
    for path in CATALOGUE_DIR.glob("*.json"):
        try:
            guild_id = int(path.stem)
            data     = load_catalogue(guild_id)
            msg_id   = data.get("msg_id")
            if msg_id:
                _catalogue_msg_ids[guild_id] = msg_id
                print(f"[CATALOGUE] msg_id restauré : guild={guild_id} → {msg_id}")
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════
#  ON READY
# ═══════════════════════════════════════════════════════════════

@bot.event
async def on_ready():
    print(f"[BOT] Connecté : {bot.user} (ID: {bot.user.id})")
    print(f"[BOT] Serveurs : {[g.name for g in bot.guilds]}")
    # Ajoute les vues persistantes
    bot.add_view(TicketView())
    bot.add_view(RoleToggleView())
    # Restaure les parties et catalogues
    await _restore_all_games()
    await _restore_all_catalogues()
    # Crée les configs par défaut pour tous les serveurs
    for guild in bot.guilds:
        load_config(guild.id)
        print(f"[CONFIG] Serveur configuré : {guild.name} (ID: {guild.id})")
    print("[BOT] Prêt !")


TOKEN = os.environ.get("DISCORD_TOKEN")
bot.run(TOKEN)
