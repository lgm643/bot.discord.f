"""utils/config_panel.py — Panneau !config — constantes et embeds."""
import discord

from bot.utils.config import load_config, resolve_channel, resolve_role, resolve_category
from bot.utils.helpers import now_utc

_NUM_KEYS = {
    "alt_min_days", "raid_window_secs", "raid_threshold",
    "spam_limit", "spam_window",
    "vocal_inactivity_delay",
}
_LIST_KEYS = {
    "role_staff", "faction_roles", "salon_cmds_allowed", "allowed_domains",
    "vocal_inactivity_exempt_channels",
    "vocal_inactivity_exempt_roles",
    "vocal_inactivity_exempt_users",
}

CONFIG_GROUPS = {
    "🔊 Salons": [
        ("salon_logs",           "📜 Logs de modération",               False),
        ("salon_bienvenue",      "👋 Salon de bienvenue",                False),
        ("salon_roster",         "📋 Roster faction",                   False),
        ("salon_catalogue",      "🏪 Catalogue marché",                 False),
        ("salon_commandes",      "🛒 Commandes marché",                 False),
        ("salon_notifications",  "🔔 Notifications marché",             False),
        ("salon_role_toggle",    "🎭 Bouton rôles",                     False),
        ("salon_ventes_log",     "💸 Logs des ventes",                  False),
        ("salon_recherche",      "🔍 Recherche articles",               False),
        ("salon_cmds_allowed",   "✅ Salons commandes (liste)",          True),
        ("salon_objectifs",      "🎯 Salon objectifs",                  False),
        ("salon_gestion",        "📦 Salon gestion stock",              False),
        ("salon_vendeur",        "🛒 Salon demande vendeur certifié",   False),
        ("inviteLogsChannel",    "📨 Logs paliers invitations",         False),
        ("salon_avantages",      "🎁 Salon avantages invitations",      False),
    ],
    "🎉 Giveaways": [
        ("role_giveaway_staff",  "🎉 Rôle staff giveaway (reroll)",    False),
        ("role_giveaway_notif",  "🔔 Rôle notifs giveaways (!rolegw)", False),
        ("salon_giveaway_logs",  "📜 Logs giveaways / reroll",         False),
    ],
    "📨 Récompenses invitations": [
        ("inviteRole5",  "🐦 Rôle palier 5 invitations",               False),
        ("inviteRole10", "🐦 Rôle palier 10 invitations",              False),
        ("inviteRole20", "🐦 Rôle palier 20 invitations",              False),
    ],
    "🎭 Rôles": [
        ("role_staff",           "👑 Staff / Admin (liste)",            True),
        ("role_officier",        "⚔️ Officier",                        False),
        ("role_leader",          "👑 Leader",                           False),
        ("role_visiteur",        "👤 Visiteur (auto à l'arrivée)",      False),
        ("role_recruteur",       "📋 Recruteur (tickets recrutement)",  False),
        ("role_vendeur",         "🏷️ Vendeur certifié",                False),
        ("role_staff_market",    "🛒 Staff marché",                    False),
        ("role_acheteur_notif",  "🔔 Notif acheteur",                  False),
        ("role_vendu",           "✅ Rôle vendu",                       False),
    ],
    "📁 Catégories": [
        ("categorie_tickets",    "🎫 Catégorie tickets",                False),
        ("categorie_commandes",  "📦 Catégorie commandes",              False),
    ],
    "🎖️ Roster": [
        ("role_roster_leader",    "👑 Leader (roster)",                 False),
        ("role_roster_officier",  "⚔️ Officier (roster)",              False),
        ("role_roster_confiance", "🛡️ Membre de confiance (roster)",   False),
        ("role_roster_plus",      "⭐ Membre + (roster)",               False),
        ("role_roster_membre",    "🔹 Membre (roster)",                 False),
        ("role_roster_recrue",    "🌱 Recrue (roster)",                 False),
    ],
    "📊 Stats & Hebdo": [
        ("salon_hebdo",      "📅 Salon classement hebdomadaire",        False),
        ("motd_enabled",     "👑 Activer Membres de la semaine (1/0)",  False),
        ("role_motd_msg",    "💬 Rôle Membre semaine — Messages",       False),
        ("role_motd_vocal",  "🎙️ Rôle Membre semaine — Vocal",         False),
    ],
    "⚙️ Sécurité": [
        ("alt_min_days",      "🛡️ Anti-alt : âge minimum (jours)",     False),
        ("raid_window_secs",  "🚨 Anti-raid : fenêtre (secondes)",      False),
        ("raid_threshold",    "🚨 Anti-raid : seuil membres",           False),
        ("spam_limit",        "⚡ Anti-spam : messages max",            False),
        ("spam_window",       "⚡ Anti-spam : fenêtre (secondes)",      False),
    ],
    "🎙️ Inactivité Vocale": [
        ("vocal_inactivity_enabled",         "🔘 Activer (1=oui / 0=non)",                    False),
        ("vocal_inactivity_delay",           "⏱️ Délai avant expulsion (minutes)",            False),
        ("salon_logs_vocal_inactivity",      "📜 Salon logs dédié (vide = salon_logs)",       False),
        ("vocal_inactivity_exempt_channels", "🔕 Salons vocaux exclus (liste)",               True),
        ("vocal_inactivity_exempt_roles",    "🛡️ Rôles exclus (liste)",                      True),
        ("vocal_inactivity_exempt_users",    "👤 Membres exclus — IDs (liste)",               True),
    ],
    "📜 Salons de logs": [
        ("salon_logs",           "📜 Logs modération (défaut fallback)", False),
        ("salon_logs_messages",  "💬 Logs messages (edit/delete/bulk)",  False),
        ("salon_logs_membres",   "👥 Logs membres (join/leave/rôles)",   False),
        ("salon_logs_vocal",     "🔊 Logs vocal (join/leave/état)",      False),
        ("salon_logs_serveur",   "⚙️ Logs serveur (salons/rôles/emojis)",False),
        ("salon_logs_securite",  "🚨 Alertes sécurité",                  False),
        ("salon_logs_debug",     "🐛 Logs debug (erreurs Python/API)",   False),
        ("debug_enabled",        "🐛 Activer debug (1=oui / 0=non)",     False),
    ],
}


def _fmt_cfg_val(guild, key, val):
    if isinstance(val, list):
        parts = []
        for v in val:
            if "salon" in key or "channel" in key.lower():
                ch = resolve_channel(guild, v)
                parts.append(f"<#{ch.id}>" if ch else f"⚠️`{v}`")
            elif "role" in key:
                r = resolve_role(guild, v)
                parts.append(r.mention if r else f"⚠️`{v}`")
            else:
                parts.append(f"`{v}`")
        return ", ".join(parts) if parts else "_vide_"
    if "salon" in key or "channel" in key.lower():
        ch = resolve_channel(guild, val)
        return f"<#{ch.id}>" if ch else f"⚠️`{val}`"
    if "role" in key:
        r = resolve_role(guild, val)
        return r.mention if r else f"⚠️`{val}`"
    if "categorie" in key:
        cat = resolve_category(guild, val)
        return f"📁 {cat.name}" if cat else f"⚠️`{val}`"
    return f"`{val}`"


def _build_group_embed(guild, group):
    cfg   = load_config(guild.id)
    keys  = CONFIG_GROUPS[group]
    embed = discord.Embed(
        title=f"⚙️ Config — {group}",
        description=(
            "Utilisez le menu ci-dessous pour **modifier une valeur**.\n"
            "Répondez dans ce salon quand demandé.\n"
            "⚠️ = introuvable sur ce serveur"
        ),
        color=0x9B59B6,
        timestamp=now_utc(),
    )
    lines, cur_len = [], 0
    for key, label, _ in keys:
        val  = cfg.get(key, "—")
        line = f"**{label}**\n`{key}` → {_fmt_cfg_val(guild, key, val)}"
        if cur_len + len(line) + 1 > 950 and lines:
            embed.add_field(name="\u200b", value="\n".join(lines), inline=False)
            lines, cur_len = [], 0
        lines.append(line)
        cur_len += len(line) + 1
    if lines:
        embed.add_field(name="\u200b", value="\n".join(lines), inline=False)
    return embed


def _build_home_embed(guild):
    embed = discord.Embed(
        title="⚙️ Configuration du serveur",
        description=(
            "Choisissez une **catégorie** dans le menu déroulant pour voir et modifier les valeurs.\n\n"
            + "\n".join(f"**{g}** — {len(v)} clé(s)" for g, v in CONFIG_GROUPS.items())
            + "\n\n⚠️ = introuvable sur ce serveur"
        ),
        color=0x9B59B6,
        timestamp=now_utc(),
    )
    embed.set_footer(text="Timeout automatique après 5 minutes")
    return embed