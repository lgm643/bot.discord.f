import discord

from bot.core import bot

from bot.utils.database import db_get_objectifs, db_get_objectif_embed, db_save_objectif_embed
from bot.utils.config import load_config, resolve_role, cfg_channel
from bot.utils.helpers import now_utc

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
                categories[rid]["members"].append(member.display_name or member.name)
                break
    embed = discord.Embed(title="📋 Roster", color=0x9B59B6, timestamp=now_utc())
    total = 0
    for rid in ordered_keys:
        cat = categories[rid]
        total += len(cat["members"])
        if cat["members"]:
            embed.add_field(name=f"{cat['label']} ({len(cat['members'])})", value="\n".join(cat["members"]), inline=False)
    embed.set_footer(text=f"Total : {total} membres")
    return embed
def build_objectifs_embed(guild_id: int) -> discord.Embed:
    objectifs = db_get_objectifs(guild_id)
    embed = discord.Embed(title="🎯 Objectifs du serveur", color=0x9B59B6, timestamp=now_utc())
    if not objectifs:
        embed.description = "_Aucun objectif pour le moment._\nUtilise les boutons ci-dessous pour en ajouter."
    else:
        lignes = []
        for i, obj in enumerate(objectifs, 1):
            statut = "✅" if obj["done"] else "⏳"
            texte  = f"~~{obj['texte']}~~" if obj["done"] else obj["texte"]
            lignes.append(f"{statut} **{i}.** {texte}  `#{obj['id']}`")
        embed.description = "\n".join(lignes)
    total    = len(objectifs)
    termines = sum(1 for o in objectifs if o["done"])
    embed.set_footer(text=f"✅ {termines}/{total} terminé(s) · Utilise les boutons pour gérer les objectifs")
    return embed


async def refresh_objectifs_embed(guild: discord.Guild):
    row   = db_get_objectif_embed(guild.id)
    embed = build_objectifs_embed(guild.id)
    from bot.views.objectif_views import ObjectifView
    view  = ObjectifView(guild.id)
    if row:
        channel = guild.get_channel(row["channel_id"])
        if channel:
            try:
                msg = await channel.fetch_message(row["msg_id"])
                await msg.edit(embed=embed, view=view)
                return
            except Exception:
                pass
        if channel is None:
            channel = cfg_channel(guild, "salon_objectifs")
        if channel:
            msg = await channel.send(embed=embed, view=view)
            db_save_objectif_embed(guild.id, channel.id, msg.id)
        return
    channel = cfg_channel(guild, "salon_objectifs")
    if channel:
        msg = await channel.send(embed=embed, view=view)
        db_save_objectif_embed(guild.id, channel.id, msg.id)
