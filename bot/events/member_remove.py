import discord

from bot.core import bot
from bot.utils.helpers import now_utc
from bot.utils.logs import send_log


@bot.event
async def on_member_remove(member):
    try:
        from bot.utils.invite_rewards import on_invite_chain_update
        await on_invite_chain_update(member.guild, member.id)
    except Exception as e:
        print(f"[INVITE_REWARDS] Erreur après leave pour {member.name} : {e}")

    embed = discord.Embed(title="📤 Membre parti", color=0xE74C3C, timestamp=now_utc())
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="👤 Membre", value=f"{member} ({member.id})", inline=True)
    embed.add_field(name="👥 Total", value=str(member.guild.member_count), inline=True)
    await send_log(member.guild, embed)

    # Roster : si le membre parti avait un rôle roster, on rafraîchit l'embed
    try:
        from bot.utils.config import load_config
        from bot.utils.embeds import refresh_roster_embed
        cfg = load_config(member.guild.id)
        ROSTER_KEYS  = ["role_roster_leader", "role_roster_officier", "role_roster_confiance",
                        "role_roster_plus", "role_roster_membre", "role_roster_recrue"]
        roster_names = {cfg[k].lower() for k in ROSTER_KEYS if cfg.get(k)}
        if any(r.name.lower() in roster_names for r in member.roles):
            await refresh_roster_embed(member.guild)
    except Exception as e:
        print(f"[ROSTER] Erreur refresh après leave : {e}")

    # Indispos : nettoie l'entrée du membre parti s'il en avait une
    try:
        from bot.utils.database import db_get_indispo, db_delete_indispo
        from bot.utils.indispo import refresh_indispo_embed
        if db_get_indispo(member.guild.id, member.id):
            db_delete_indispo(member.guild.id, member.id)
            await refresh_indispo_embed(member.guild)
    except Exception as e:
        print(f"[INDISPO] Erreur nettoyage après leave : {e}")
