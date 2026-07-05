"""
events/weekly.py — Classement hebdomadaire automatique (lundi 00h01 UTC).

Contenu :
  💬 Top Messages (10)  🎙️ Top Vocal (10)  ⭐ Top XP (10)
  📨 Top Invitations (10)  🛒 Top Vendeurs (10)
  👑 Membre de la semaine Messages
  🎙️ Membre de la semaine Vocal

Configuration via !config (groupe 📊 Stats & Hebdo) :
  salon_hebdo      : salon d'envoi
  motd_enabled     : 1/0
  role_motd_msg    : rôle Membre de la semaine Messages
  role_motd_vocal  : rôle Membre de la semaine Vocal
"""
import asyncio
from datetime import datetime, timezone, timedelta

import discord

from bot.core import bot
from bot.utils.stats import (
    compute_weekly_rankings,
    compute_motd_messages,
    compute_motd_vocal,
    reset_weekly_stats,
)
from bot.utils.config import load_config, resolve_channel, resolve_role
from bot.utils.helpers import fmt_voice, now_utc


def _seconds_until_next_monday_0001() -> float:
    """Calcule le délai jusqu'au prochain lundi 00h01 heure de Bruxelles (gère l'heure d'été/hiver)."""
    try:
        import zoneinfo
        tz_brussels = zoneinfo.ZoneInfo("Europe/Brussels")
    except ImportError:
        import pytz
        tz_brussels = pytz.timezone("Europe/Brussels")

    now_brussels = datetime.now(tz_brussels)
    days_ahead = (7 - now_brussels.weekday()) % 7
    if days_ahead == 0 and (now_brussels.hour > 0 or now_brussels.minute >= 1):
        days_ahead = 7

    next_monday_local = (now_brussels + timedelta(days=days_ahead)).replace(
        hour=0, minute=1, second=0, microsecond=0
    )
    # Convertir en UTC pour le sleep
    next_monday_utc = next_monday_local.astimezone(timezone.utc)
    now_utc_ts = datetime.now(timezone.utc)
    return (next_monday_utc - now_utc_ts).total_seconds()


def _week_label() -> str:
    now    = datetime.now(timezone.utc)
    monday = now - timedelta(days=now.weekday())
    sunday = monday + timedelta(days=6)
    return f"{monday.strftime('%d/%m')} au {sunday.strftime('%d/%m/%Y')}"


def motd_enabled(cfg: dict) -> bool:
    return bool(cfg.get("motd_enabled", True))


async def _handle_motd_role(guild: discord.Guild, winner: discord.Member | None, role_key: str, cfg: dict):
    """Retire l'ancien rôle et l'attribue au nouveau gagnant."""
    role = resolve_role(guild, cfg.get(role_key))
    if not role:
        return
    for m in guild.members:
        if role in m.roles and (winner is None or m.id != winner.id):
            try:
                await m.remove_roles(role, reason="Nouveau Membre de la semaine")
            except Exception as e:
                print(f"[WEEKLY] Impossible de retirer {role.name} à {m.id} : {e}")
    if winner and role not in winner.roles:
        try:
            await winner.add_roles(role, reason="Membre de la semaine")
        except Exception as e:
            print(f"[WEEKLY] Impossible d'attribuer {role.name} à {winner.id} : {e}")


def _build_weekly_embeds(
    guild: discord.Guild,
    rankings: dict,
    motd_msg: discord.Member | None,
    motd_vocal: discord.Member | None,
    cfg: dict,
) -> list[discord.Embed]:
    embeds = []

    # ── Embed 1 : tops messages / vocal / xp ──────────────────────────────
    main = discord.Embed(
        title="🏆 Classement Hebdomadaire",
        description=f"Semaine du **{_week_label()}**",
        color=0xF1C40F,
        timestamp=now_utc(),
    )
    if guild.icon:
        main.set_thumbnail(url=guild.icon.url)
    main.add_field(name="━━━━━━━━━━━━━━━━━━\n💬 Top Messages",  value=rankings["top_messages"], inline=False)
    main.add_field(name="━━━━━━━━━━━━━━━━━━\n🎙️ Top Vocal",     value=rankings["top_vocal"],    inline=False)
    embeds.append(main)


    # ── Embed 3 : membres de la semaine (si activé) ───────────────────────
    if motd_enabled(cfg):
        motd_embed = discord.Embed(
            title="👑 Membres de la semaine",
            color=0xFFD700,
            timestamp=now_utc(),
        )

        # Catégorie Messages
        if motd_msg:
            motd_embed.add_field(
                name="💬 Meilleur actif — Messages",
                value=(
                    f"🎉 {motd_msg.mention}\n"
                    f"Le membre qui a envoyé le plus de messages cette semaine !\n"
                    f"Continue comme ça 🔥"
                ),
                inline=False,
            )
            motd_embed.set_thumbnail(url=motd_msg.display_avatar.url)
        else:
            motd_embed.add_field(name="💬 Meilleur actif — Messages", value="_Aucun résultat_", inline=False)

        motd_embed.add_field(name="\u200b", value="━━━━━━━━━━━━━━━━━━", inline=False)

        # Catégorie Vocal
        if motd_vocal:
            motd_embed.add_field(
                name="🎙️ Meilleur actif — Vocal",
                value=(
                    f"🎉 {motd_vocal.mention}\n"
                    f"🏆 Champion vocal de la semaine !\n"
                    f"Avec un temps record passé en vocal, il décroche la première place 🎙️"
                ),
                inline=False,
            )
            if motd_vocal.id != (motd_msg.id if motd_msg else -1):
                motd_embed.set_image(url=motd_vocal.display_avatar.url)
        else:
            motd_embed.add_field(name="🎙️ Meilleur actif — Vocal", value="_Aucun résultat_", inline=False)

        embeds.append(motd_embed)

    return embeds


async def send_weekly_report(guild: discord.Guild):
    cfg     = load_config(guild.id)
    channel = resolve_channel(guild, cfg.get("salon_hebdo"))
    if not channel:
        print(f"[WEEKLY] Aucun salon_hebdo configuré pour guild={guild.id}")
        return

    rankings = compute_weekly_rankings(guild)
    msg_uid  = compute_motd_messages(guild, cfg)
    voc_uid  = compute_motd_vocal(guild, cfg)
    motd_msg   = guild.get_member(msg_uid)  if msg_uid else None
    motd_vocal = guild.get_member(voc_uid)  if voc_uid else None

    # Attribution des rôles (2 rôles séparés configurables)
    await _handle_motd_role(guild, motd_msg,   "role_motd_msg",   cfg)
    await _handle_motd_role(guild, motd_vocal, "role_motd_vocal", cfg)

    embeds = _build_weekly_embeds(guild, rankings, motd_msg, motd_vocal, cfg)
    try:
        await channel.send(content="📅 **Récapitulatif de la semaine !**", embeds=embeds)
        print(f"[WEEKLY] Rapport envoyé dans #{channel.name} (guild={guild.id})")
    except Exception as e:
        print(f"[WEEKLY] Erreur envoi rapport guild={guild.id} : {e}")

    reset_weekly_stats(guild.id)


@bot.hybrid_command(name="hebdo", aliases=["classementsemaine", "weekly"])
async def hebdo_cmd(ctx):
    """Affiche le classement hebdomadaire actuel — réservé au staff."""
    from bot.utils.permissions import is_staff
    if not is_staff(ctx.author):
        await ctx.send("❌ Cette commande est réservée au **staff**.", delete_after=10)
        return
    async with ctx.typing():
        cfg      = load_config(ctx.guild.id)
        rankings = compute_weekly_rankings(ctx.guild)
        msg_uid  = compute_motd_messages(ctx.guild, cfg)
        voc_uid  = compute_motd_vocal(ctx.guild, cfg)
        motd_msg   = ctx.guild.get_member(msg_uid)  if msg_uid  else None
        motd_vocal = ctx.guild.get_member(voc_uid)  if voc_uid  else None
        embeds = _build_weekly_embeds(ctx.guild, rankings, motd_msg, motd_vocal, cfg)
    await ctx.send(content="📊 **Classement de la semaine en cours :**", embeds=embeds)


async def weekly_loop():
    await bot.wait_until_ready()
    print(f"[WEEKLY] Boucle démarrée — prochain envoi dans {int(_seconds_until_next_monday_0001())}s")
    while not bot.is_closed():
        delay = _seconds_until_next_monday_0001()
        await asyncio.sleep(delay)
        for guild in bot.guilds:
            try:
                await send_weekly_report(guild)
            except Exception as e:
                print(f"[WEEKLY] Erreur inattendue guild={guild.id} : {e}")
        await asyncio.sleep(120)