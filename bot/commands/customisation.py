"""
commands/customisation.py — !emoji (emojis custom du bot) et !ticketsmode (channels/threads).
"""
import discord

from bot.core import bot
from bot.utils.permissions import is_staff
from bot.utils.emojis import DEFAULT_EMOJIS, get_emoji, set_emoji, reset_emoji
from bot.utils.config import load_config, save_config


@bot.command(name="emoji")
async def emoji_cmd(ctx, cle: str = None, *, valeur: str = None):
    """
    !emoji                     → liste les emojis configurables et leur valeur actuelle
    !emoji <clé> <emoji>       → définit un emoji custom (ex: !emoji market <:boutique:123456>)
    !emoji <clé> reset         → revient à l'emoji unicode par défaut
    """
    if not is_staff(ctx.author):
        await ctx.send("❌ Réservé au staff.", delete_after=5)
        return

    if not cle:
        lignes = [f"`{k}` → {get_emoji(ctx.guild, k)}" for k in DEFAULT_EMOJIS]
        embed = discord.Embed(
            title="🎨 Emojis custom du bot",
            description="\n".join(lignes) + "\n\n`!emoji <clé> <emoji>` pour personnaliser\n`!emoji <clé> reset` pour revenir par défaut",
            color=0x9B59B6,
        )
        await ctx.send(embed=embed)
        return

    cle = cle.lower().strip()
    if cle not in DEFAULT_EMOJIS:
        await ctx.send(f"❌ Clé inconnue. Clés valides : {', '.join(DEFAULT_EMOJIS)}", delete_after=8)
        return

    if not valeur:
        await ctx.send(f"❌ `!emoji {cle} <emoji>` ou `!emoji {cle} reset`", delete_after=8)
        return

    if valeur.strip().lower() == "reset":
        reset_emoji(ctx.guild, cle)
        await ctx.send(f"✅ Emoji `{cle}` réinitialisé → {DEFAULT_EMOJIS[cle]}", delete_after=6)
        return

    set_emoji(ctx.guild, cle, valeur.strip())
    await ctx.send(f"✅ Emoji `{cle}` mis à jour → {valeur.strip()}", delete_after=6)


@bot.command(name="ticketsmode")
async def ticketsmode_cmd(ctx, mode: str = None):
    """
    !ticketsmode                 → affiche le mode actuel
    !ticketsmode channels        → tickets recrutement/support = salons texte (défaut)
    !ticketsmode threads         → tickets recrutement/support = threads privés
                                    (nécessite salon_tickets_parent configuré via !config)
    """
    if not is_staff(ctx.author):
        await ctx.send("❌ Réservé au staff.", delete_after=5)
        return

    cfg = load_config(ctx.guild.id)
    if not mode:
        await ctx.send(f"🧵 Mode tickets actuel : **{cfg.get('tickets_mode', 'channels')}**", delete_after=8)
        return

    mode = mode.lower().strip()
    if mode not in ("channels", "threads"):
        await ctx.send("❌ Valeurs possibles : `channels` ou `threads`", delete_after=6)
        return

    if mode == "threads" and not cfg.get("salon_tickets_parent"):
        await ctx.send(
            "⚠️ Configure d'abord `salon_tickets_parent` via `!config` → 🔊 Salons "
            "(le salon texte qui accueillera les threads privés).",
            delete_after=10,
        )
        return

    cfg["tickets_mode"] = mode
    save_config(ctx.guild.id, cfg)
    await ctx.send(f"✅ Mode tickets : **{mode}**", delete_after=6)
