"""
commands/stats.py — Commande !statsserveur

Affiche un embed complet des statistiques du serveur :
  - Membres (total, en ligne, arrivées)
  - Activité messages (jour / semaine / mois)
  - Activité vocale  (jour / semaine / mois)
  - Classements du jour (top message, xp, vocal)
"""
import discord

from bot.core import bot
from bot.utils.stats import compute_server_stats
from bot.utils.helpers import fmt_voice, now_utc


@bot.command(name="statsserveur", aliases=["stats", "serverstats", "statistiques"])
async def statsserveur_cmd(ctx):
    """Affiche les statistiques complètes du serveur."""
    async with ctx.typing():
        try:
            s = compute_server_stats(ctx.guild)
        except Exception as e:
            await ctx.send(f"❌ Erreur lors du calcul des stats : {e}", delete_after=10)
            return

    embed = discord.Embed(
        title=f"📊 Statistiques — {ctx.guild.name}",
        color=0x9B59B6,
        timestamp=now_utc(),
    )
    if ctx.guild.icon:
        embed.set_thumbnail(url=ctx.guild.icon.url)

    # ── Membres ──────────────────────────────────────────────────────────────
    embed.add_field(
        name="👥 Membres",
        value=(
            f"**Total :** {s['total_members']}\n"
            f"**En ligne :** {s['online_members']}\n"
            f"**Arrivés aujourd'hui :** {s['joined_today']}\n"
            f"**Arrivés cette semaine :** {s['joined_week']}"
        ),
        inline=True,
    )

    # ── Messages ──────────────────────────────────────────────────────────────
    embed.add_field(
        name="💬 Messages",
        value=(
            f"**Aujourd'hui :** {s['daily_msgs']}\n"
            f"**Cette semaine :** {s['weekly_msgs']}\n"
            f"**Ce mois :** ~{s['monthly_msgs']}"
        ),
        inline=True,
    )

    embed.add_field(name="\u200b", value="\u200b", inline=False)   # spacer mobile

    # ── Vocal ─────────────────────────────────────────────────────────────────
    embed.add_field(
        name="🎙️ Vocal",
        value=(
            f"**Aujourd'hui :** {fmt_voice(s['daily_voice'])}\n"
            f"**Cette semaine :** {fmt_voice(s['weekly_voice'])}\n"
            f"**Ce mois :** ~{fmt_voice(s['monthly_voice'])}"
        ),
        inline=True,
    )

    # ── Classements du jour ───────────────────────────────────────────────────
    top_msg_name,   top_msg_val   = s["top_daily_msg"]
    top_xp_name,    top_xp_val    = s["top_daily_xp"]
    top_voice_name, top_voice_val = s["top_daily_voice"]

    embed.add_field(
        name="🏆 Tops du jour",
        value=(
            f"🔥 **+ actif (msgs) :** {top_msg_name} ({top_msg_val} msg)\n"
            f"⭐ **+ XP :** {top_xp_name} ({top_xp_val} XP)\n"
            f"🎙️ **+ vocal :** {top_voice_name} ({fmt_voice(top_voice_val)})"
        ),
        inline=True,
    )

    embed.set_footer(text=f"Données en temps réel · Demandé par {ctx.author.display_name}")
    await ctx.send(embed=embed)
