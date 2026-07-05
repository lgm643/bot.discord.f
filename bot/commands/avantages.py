"""Commande !avantages — affiche les paliers d'invitations et leurs récompenses."""

import discord
from bot.core import bot
from bot.utils.config import load_config, resolve_channel
from bot.utils.helpers import now_utc

# ═══════════════════════════════════════════════════════════════
#  PALIERS
# ═══════════════════════════════════════════════════════════════

INVITE_TIERS = [
    {
        "min":      5,
        "name":     "🐦‍🔥 Initié",
        "benefits": [
            "**−5 %** sur tout le market",
        ],
    },
    {
        "min":      10,
        "name":     "🐦‍🔥 Marchand Elite",
        "benefits": [
            "**−10 %** sur tout le market",
            "Réservation prioritaire des items",
        ],
    },
    {
        "min":      20,
        "name":     "🐦‍🔥 Maître Phénix",
        "benefits": [
            "**−20 %** sur tout le market",
            "Réservation prioritaire des items",
        ],
    },
]

# ═══════════════════════════════════════════════════════════════
#  EMBED (réutilisable depuis d'autres modules)
# ═══════════════════════════════════════════════════════════════

def build_avantages_embed(guild: discord.Guild) -> discord.Embed:
    embed = discord.Embed(
        title="🎁 Paliers d'invitations",
        description=(
            "Invitez des membres pour débloquer des avantages exclusifs sur le market !\n"
            "Seules les invitations **actives** (membres toujours présents) comptent.\n\u200b"
        ),
        color=0xF1C40F,
        timestamp=now_utc(),
    )
    for tier in INVITE_TIERS:
        benefits_text = "\n".join(f"• {b}" for b in tier["benefits"])
        embed.add_field(
            name=f"{tier['name']}  —  `{tier['min']} invitations`",
            value=benefits_text + "\n\u200b",
            inline=False,
        )
    embed.set_footer(
        text=f"Serveur : {guild.name}  •  Utilisez !invite [pseudo] pour vérifier vos invitations",
        icon_url=guild.icon.url if guild.icon else discord.Embed.Empty,
    )
    return embed

# ═══════════════════════════════════════════════════════════════
#  COMMANDE
# ═══════════════════════════════════════════════════════════════

@bot.hybrid_command(name="avantages")
async def avantages_cmd(ctx):
    guild  = ctx.guild
    cfg    = load_config(guild.id)
    target = resolve_channel(guild, cfg.get("salon_avantages"))
    embed  = build_avantages_embed(guild)

    if target and target != ctx.channel:
        await target.send(embed=embed)
        await ctx.send(
            f"📨 Les avantages ont été affichés dans {target.mention} !",
            delete_after=6,
        )
    else:
        await ctx.send(embed=embed)

    if ctx.interaction is None:
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            pass