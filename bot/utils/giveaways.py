"""Giveaways actifs / terminés — persistance pour reroll."""
import json
import os
import random
import time
from pathlib import Path

import discord

from bot.core import active_giveaways, GIVEAWAYS_DIR
from bot.utils.config import load_config, resolve_role, resolve_channel, cfg_channel
from bot.utils.helpers import now_utc

# Cache des giveaways terminés (msg_id → données)
ended_giveaways: dict[int, dict] = {}


def _giveaway_file(msg_id: int) -> Path:
    return GIVEAWAYS_DIR / f"{msg_id}.json"


def save_ended_giveaway(msg_id: int, data: dict):
    """Enregistre un giveaway terminé (disque + mémoire)."""
    data = dict(data)
    data["ended"] = True
    data["msg_id"] = msg_id
    ended_giveaways[msg_id] = data
    path = _giveaway_file(msg_id)
    tmp = str(path) + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        path.parent.mkdir(parents=True, exist_ok=True)
        os.replace(tmp, path)
    except Exception as e:
        print(f"[GW] Erreur sauvegarde giveaway {msg_id} : {e}")


def load_ended_giveaway(msg_id: int) -> dict | None:
    if msg_id in ended_giveaways:
        return ended_giveaways[msg_id]
    path = _giveaway_file(msg_id)
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        ended_giveaways[msg_id] = data
        return data
    except Exception as e:
        print(f"[GW] Erreur lecture giveaway {msg_id} : {e}")
        return None


def load_all_ended_giveaways():
    """Charge tous les giveaways terminés au démarrage."""
    if not GIVEAWAYS_DIR.exists():
        return
    for path in GIVEAWAYS_DIR.glob("*.json"):
        try:
            msg_id = int(path.stem)
            with open(path, "r", encoding="utf-8") as f:
                ended_giveaways[msg_id] = json.load(f)
        except Exception:
            pass
    print(f"[GW] {len(ended_giveaways)} giveaway(s) terminé(s) chargé(s)")


def can_manage_giveaway(member: discord.Member) -> bool:
    if member.guild_permissions.administrator:
        return True
    cfg = load_config(member.guild.id)
    role = resolve_role(member.guild, cfg.get("role_giveaway_staff"))
    return bool(role and role in member.roles)


def get_eligible_participants(guild: discord.Guild, participants: list, exclude_id: int | None = None) -> list[int]:
    """Participants encore sur le serveur, hors ancien gagnant."""
    eligible = []
    for uid in participants:
        if exclude_id and uid == exclude_id:
            continue
        m = guild.get_member(uid)
        if m and not m.bot:
            eligible.append(uid)
    return eligible


def is_giveaway_still_running(msg_id: int) -> bool:
    return msg_id in active_giveaways


def build_ended_winner_embed(gw: dict, winner_mention: str, *, rerolled: bool = False) -> discord.Embed:
    reward = gw.get("reward", "?")
    title = f"🎉 GIVEAWAY TERMINÉ — {reward}"
    if rerolled:
        desc = (
            "Giveaway reroll effectué\n\n"
            "Le dernier gagnant ne correspondait pas aux conditions données.\n\n"
            f"Nouveau gagnant : {winner_mention}\n\n"
            "Félicitations."
        )
    else:
        desc = f"🏆 Gagnant : {winner_mention}\n🎊 Félicitations !"
    embed = discord.Embed(title=title, description=desc, color=0x2ECC71, timestamp=now_utc())
    embed.set_footer(
        text=f"Organisé par {gw.get('host', '?')} • {len(gw.get('participants', []))} participants"
    )
    return embed


def build_reroll_announce_embed(winner_mention: str) -> discord.Embed:
    return discord.Embed(
        title="🐦‍🔥 Giveaway reroll",
        description=(
            "Le dernier gagnant ne correspondait pas aux conditions données.\n\n"
            f"Nouveau gagnant : {winner_mention}\n\n"
            "Félicitations."
        ),
        color=0xF1C40F,
        timestamp=now_utc(),
    )


def build_reroll_log_embed(
    guild: discord.Guild,
    moderator: discord.Member,
    msg_id: int,
    channel: discord.abc.GuildChannel,
    old_winner_id: int | None,
    new_winner_id: int,
    reward: str,
) -> discord.Embed:
    old_m = guild.get_member(old_winner_id) if old_winner_id else None
    new_m = guild.get_member(new_winner_id)
    old_str = old_m.mention if old_m else (f"<@{old_winner_id}>" if old_winner_id else "—")
    new_str = new_m.mention if new_m else f"<@{new_winner_id}>"
    embed = discord.Embed(title="🔄 Log — Giveaway reroll", color=0x9B59B6, timestamp=now_utc())
    embed.add_field(name="🛡️ Reroll par", value=moderator.mention, inline=True)
    embed.add_field(name="🆔 Message ID", value=str(msg_id), inline=True)
    embed.add_field(name="📍 Salon", value=channel.mention if hasattr(channel, "mention") else channel.name, inline=True)
    embed.add_field(name="🏆 Ancien gagnant", value=old_str, inline=True)
    embed.add_field(name="🎊 Nouveau gagnant", value=new_str, inline=True)
    embed.add_field(name="🎁 Récompense", value=reward, inline=False)
    return embed


async def get_giveaway_log_channel(guild: discord.Guild):
    cfg = load_config(guild.id)
    ch = resolve_channel(guild, cfg.get("salon_giveaway_logs"))
    if ch:
        return ch
    return cfg_channel(guild, "salon_logs")


async def send_giveaway_log(guild: discord.Guild, embed: discord.Embed):
    ch = await get_giveaway_log_channel(guild)
    if ch:
        try:
            await ch.send(embed=embed)
        except Exception as e:
            print(f"[GW] Erreur log giveaway : {e}")