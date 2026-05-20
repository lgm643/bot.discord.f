from discord.ext import commands

from bot.core import bot


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        await ctx.send(
            "❌ Commande inconnue. Essayez `!help` pour voir les commandes disponibles.",
            delete_after=8,
        )
    elif isinstance(error, commands.CheckFailure):
        pass
    else:
        print(f"[ERROR] {ctx.command} : {error}")
