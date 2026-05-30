import discord
from discord.ext import commands

from bot.core import bot
from bot.utils.config_panel import _build_home_embed
from bot.views.config_views import _HomeView


@bot.command(name="config")
async def config_cmd(ctx):
    if not ctx.author.guild_permissions.administrator:
        await ctx.send("❌ Réservé aux administrateurs.", delete_after=5)
        return
    try:
        await ctx.message.delete()
    except Exception:
        pass
    embed = _build_home_embed(ctx.guild)
    view = _HomeView(ctx.author.id)
    msg = await ctx.send(embed=embed, view=view)
    view.msg = msg
