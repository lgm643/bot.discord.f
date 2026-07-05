import discord
from discord.ext import commands

from bot.core import bot
from bot.utils.helpers import now_utc
from bot.utils.invite_stats import get_top_inviters_active

MEDALS = ["🥇", "🥈", "🥉"]


@bot.hybrid_command(name="topinvites")
async def topinvites_cmd(ctx):
    """Classement des 10 meilleurs inviteurs (invitations actives)."""
    guild = ctx.guild
    top = get_top_inviters_active(guild, limit=10)

    embed = discord.Embed(
        title=f"🏆 Top 10 des Inviteurs — {guild.name}",
        color=0xF1C40F,
        timestamp=now_utc(),
    )

    if not top:
        embed.description = "_Aucune invitation enregistrée pour le moment._"
    else:
        lines = []
        for i, (uid, count) in enumerate(top, 1):
            member = guild.get_member(uid)
            label = member.mention if member else f"<@{uid}>"
            rank = MEDALS[i - 1] if i <= 3 else f"{i}."
            lines.append(f"{rank} {label} — **{count}** invitation(s)")
        embed.description = "\n".join(lines)

    embed.set_footer(text=f"Basé sur les membres encore présents (✅) · Demandé par {ctx.author.display_name}")
    await ctx.send(embed=embed)
