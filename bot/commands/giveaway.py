import asyncio
import random
import re
import time

import discord
from discord.ext import commands

from bot.core import bot, active_giveaways
from bot.views.giveaway_view import GiveawayView, build_giveaway_embed
from bot.utils.permissions import is_staff, is_staff_market
from bot.utils.giveaways import (
    save_ended_giveaway,
    load_ended_giveaway,
    can_manage_giveaway,
    get_eligible_participants,
    is_giveaway_still_running,
    build_ended_winner_embed,
    build_reroll_announce_embed,
    build_reroll_log_embed,
    send_giveaway_log,
)


def parse_duration(s):
    total = 0
    for val, unit in re.findall(r"(\d+)([smhj])", s.lower()):
        v = int(val)
        if unit == "s":
            total += v
        elif unit == "m":
            total += v * 60
        elif unit == "h":
            total += v * 3600
        elif unit == "j":
            total += v * 86400
    return total if total > 0 else None


@bot.command(name="giveaway", aliases=["gw"])
async def giveaway_cmd(ctx, duree: str = None, *, reward: str = None):
    """
    !giveaway <durée> <récompense> [--invites N]
    Exemple : !giveaway 1h Pack de paladiums --invites 2
    """
    if not is_staff(ctx.author) and not is_staff_market(ctx.author):
        await ctx.send("❌ Réservé au staff.", delete_after=5)
        return
    if duree is None or reward is None:
        await ctx.send(
            "❌ **Usage :** `!giveaway <durée> <récompense> [--invites N]`\n"
            "**Exemples :**\n"
            "• `!giveaway 1h Pack de paladiums`\n"
            "• `!giveaway 30m Épée légendaire --invites 2`\n"
            "**Durées :** `30s` · `10m` · `2h` · `1j` · `1h30m`",
            delete_after=15
        )
        return
    seconds = parse_duration(duree)
    if not seconds:
        await ctx.send("❌ Durée invalide. Ex : `10m`, `1h`, `2h30m`", delete_after=8)
        return

    # Extraire --invites N depuis la récompense si présent
    import re as _re
    min_invites = 0
    invites_match = _re.search(r"--invites\s+(\d+)", reward)
    if invites_match:
        min_invites = int(invites_match.group(1))
        reward = _re.sub(r"\s*--invites\s+\d+", "", reward).strip()

    ends_at = time.time() + seconds
    gw = {
        "reward":       reward,
        "ends_at":      ends_at,
        "participants": [],
        "host":         str(ctx.author),
        "channel_id":   ctx.channel.id,
        "guild_id":     ctx.guild.id,
        "min_invites":  min_invites,
    }
    embed = build_giveaway_embed(gw)
    msg   = await ctx.send(embed=embed)
    gw_id = msg.id
    active_giveaways[gw_id] = gw
    view = GiveawayView(gw_id)
    bot.add_view(view)
    await msg.edit(view=view)

    asyncio.create_task(_end_giveaway(gw_id, seconds, ctx.channel, reward))


async def _end_giveaway(gw_id, delay, channel, reward):
    await asyncio.sleep(delay)
    gw = active_giveaways.pop(gw_id, None)
    if not gw:
        return
    gw["guild_id"] = channel.guild.id
    try:
        msg = await channel.fetch_message(gw_id)
        if not gw["participants"]:
            embed = discord.Embed(
                title=f"🎉 GIVEAWAY TERMINÉ — {reward}",
                description="😔 Aucun participant...",
                color=0x95A5A6,
            )
            await msg.edit(embed=embed, view=None)
            gw["winner_id"] = None
            save_ended_giveaway(gw_id, gw)
            return
        winner_id = random.choice(gw["participants"])
        gw["winner_id"] = winner_id
        winner = channel.guild.get_member(winner_id)
        name = winner.mention if winner else f"<@{winner_id}>"
        embed = build_ended_winner_embed(gw, name, rerolled=False)
        await msg.edit(embed=embed, view=None)
        await channel.send(f"🎊 Félicitations {name} ! Tu as gagné **{reward}** !")
        save_ended_giveaway(gw_id, gw)
    except Exception as e:
        print(f"[GW] Erreur fin giveaway : {e}")


@bot.command(name="reroll")
async def reroll_cmd(ctx, message_id: str = None):
    """
    Relance un giveaway terminé : !reroll <messageID>
    """
    if not can_manage_giveaway(ctx.author):
        await ctx.send("Vous n'avez pas la permission d'utiliser cette commande.", delete_after=8)
        return

    if message_id is None:
        await ctx.send("❌ `!reroll <messageID>`\nExemple : `!reroll 139284729384729`", delete_after=8)
        return

    try:
        msg_id = int(message_id.strip())
    except ValueError:
        await ctx.send("Giveaway introuvable.", delete_after=8)
        return

    if is_giveaway_still_running(msg_id):
        await ctx.send("Ce giveaway n'est pas encore terminé.", delete_after=8)
        return

    gw = load_ended_giveaway(msg_id)
    channel = None
    msg = None

    if gw:
        channel = ctx.guild.get_channel(gw.get("channel_id")) or ctx.channel
        try:
            msg = await channel.fetch_message(msg_id)
        except discord.NotFound:
            await ctx.send("Giveaway introuvable.", delete_after=8)
            return
        except Exception as e:
            print(f"[GW] Erreur fetch message reroll : {e}")
            await ctx.send("Giveaway introuvable.", delete_after=8)
            return
    else:
        try:
            msg = await ctx.channel.fetch_message(msg_id)
            if not msg.embeds or "TERMINÉ" not in (msg.embeds[0].title or "").upper():
                await ctx.send("Ce giveaway n'est pas encore terminé.", delete_after=8)
                return
            await ctx.send(
                "Giveaway introuvable.\n*(Données participants absentes — giveaway antérieur à la sauvegarde.)*",
                delete_after=10,
            )
            return
        except discord.NotFound:
            await ctx.send("Giveaway introuvable.", delete_after=8)
            return

    old_winner_id = gw.get("winner_id")
    eligible = get_eligible_participants(ctx.guild, gw.get("participants", []), exclude_id=old_winner_id)

    if not eligible and old_winner_id:
        eligible = get_eligible_participants(ctx.guild, gw.get("participants", []), exclude_id=None)

    if not eligible:
        await ctx.send("Aucun participant valide.", delete_after=8)
        return

    new_winner_id = random.choice(eligible)
    gw["winner_id"] = new_winner_id
    gw["reroll_count"] = gw.get("reroll_count", 0) + 1
    save_ended_giveaway(msg_id, gw)

    new_member = ctx.guild.get_member(new_winner_id)
    new_mention = new_member.mention if new_member else f"<@{new_winner_id}>"

    embed = build_ended_winner_embed(gw, new_mention, rerolled=True)
    await msg.edit(embed=embed, view=None)

    await channel.send(embed=build_reroll_announce_embed(new_mention))

    log_embed = build_reroll_log_embed(
        ctx.guild,
        ctx.author,
        msg_id,
        channel,
        old_winner_id,
        new_winner_id,
        gw.get("reward", "?"),
    )
    await send_giveaway_log(ctx.guild, log_embed)

    await ctx.send(f"✅ Reroll effectué — nouveau gagnant : {new_mention}", delete_after=10)