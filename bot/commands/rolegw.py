"""
commands/rolegw.py — Toggle du rôle notifications giveaways.

!rolegw — Donne ou retire le rôle giveaway notif à soi-même.
          Le rôle est configuré via !config → 🎉 Giveaways → role_giveaway_notif.
"""
import discord

from bot.core import bot
from bot.utils.config import cfg_role


@bot.command(name="rolegw", aliases=["gwrole", "giveawayrole"])
async def rolegw_cmd(ctx):
    """Toggle du rôle notifications giveaways."""
    role = cfg_role(ctx.guild, "role_giveaway_notif")
    if not role:
        await ctx.send(
            "❌ Aucun rôle giveaway configuré.\n"
            "Configure-le via `!config` → 🎉 Giveaways → `role_giveaway_notif`.",
            delete_after=10,
        )
        return

    try:
        if role in ctx.author.roles:
            await ctx.author.remove_roles(role, reason="Toggle !rolegw")
            embed = discord.Embed(
                title="🔕 Notifications giveaways désactivées",
                description=f"Le rôle {role.mention} t'a été retiré.\nTu ne seras plus mentionné lors des prochains giveaways.",
                color=0x95A5A6,
            )
        else:
            await ctx.author.add_roles(role, reason="Toggle !rolegw")
            embed = discord.Embed(
                title="🔔 Notifications giveaways activées !",
                description=f"Le rôle {role.mention} t'a été attribué.\nTu seras mentionné lors des prochains giveaways !",
                color=0x2ECC71,
            )
        await ctx.send(embed=embed, delete_after=10)
    except discord.Forbidden:
        await ctx.send("❌ Je n'ai pas la permission de modifier tes rôles.", delete_after=8)
    except Exception as e:
        await ctx.send(f"❌ Erreur : {e}", delete_after=8)
