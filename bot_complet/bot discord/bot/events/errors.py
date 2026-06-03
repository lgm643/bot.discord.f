from discord.ext import commands

from bot.core import bot

# Commandes réservées vendeurs — message explicatif si non vendeur
_VENDEUR_CMDS = {
    "catalogue", "cataloguesupp", "cataloguesuppall", "stock",
    "gestion", "vendu", "catalogueview", "cataloguesuppjoueur",
}

# Commandes réservées staff — message explicatif si non staff
_STAFF_CMDS = {
    "ban", "bannir", "kick", "expulser", "mute", "silence",
    "unmute", "desilence", "parler", "effacer", "clear", "purge",
    "say", "dit", "ticket", "tickets", "support", "roster",
    "membres", "liste", "faction", "giveaway", "gw", "reroll",
    "commande", "role", "vendeur", "accepter", "refuser",
    "objectif", "pub", "cataloguesuppall", "cataloguesuppjoueur",
    "config", "setup", "avantages",
}


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        # Commande inconnue — message utile selon le contexte
        cmd_name = ctx.invoked_with.lower() if ctx.invoked_with else ""

        if cmd_name in _VENDEUR_CMDS:
            await ctx.send(
                "🏷️ Cette commande est réservée aux **Vendeurs Certifiés**.\n"
                "Soumets ta candidature via `!vendeur` pour obtenir le rôle.",
                delete_after=10,
            )
        elif cmd_name in _STAFF_CMDS:
            await ctx.send(
                "🔒 Cette commande est réservée au **Staff**.",
                delete_after=6,
            )
        else:
            await ctx.send(
                "❌ Commande inconnue. Tape `!help` pour voir toutes les commandes disponibles.",
                delete_after=8,
            )

    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(
            f"❌ Argument manquant : `{error.param.name}`\n"
            f"Tape `!help` pour voir l'usage de cette commande.",
            delete_after=8,
        )

    elif isinstance(error, commands.BadArgument):
        await ctx.send(
            "❌ Argument invalide. Vérifie que tu as bien mentionné un membre ou fourni un nombre valide.",
            delete_after=8,
        )

    elif isinstance(error, commands.CheckFailure):
        err_msg = str(error)
        if err_msg:
            print(f"[CHECK] {ctx.command} refusé pour {ctx.author} ({ctx.author.id}): {err_msg}")

    else:
        print(f"[ERROR] {ctx.command} : {error}")