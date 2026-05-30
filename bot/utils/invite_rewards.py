"""Récompenses par paliers d'invitations — module autonome (ne modifie pas !invite)."""
import asyncio

import discord

from bot.core import bot
from bot.utils.config import load_config, resolve_role, resolve_channel
from bot.utils.database import get_db
from bot.utils.helpers import now_utc
from bot.utils.invite_stats import (
    count_active_invitations,
    db_get_inviter_for_member,
    get_distinct_inviter_ids,
)

# Paliers : du plus haut au plus bas
INVITE_TIERS = [
    {
        "key": 20,
        "min": 20,
        "name": "🐦‍🔥 Maître Phénix",
        "discount": 20,
        "role_key": "inviteRole20",
        "benefits": "• Rôle **Maître Phénix**\n• **−20%** sur le market",
    },
    {
        "key": 10,
        "min": 10,
        "name": "🐦‍🔥 Marchand Elite",
        "discount": 10,
        "role_key": "inviteRole10",
        "benefits": "• Rôle **Marchand Elite**\n• **−10%** sur le market",
    },
    {
        "key": 5,
        "min": 5,
        "name": "🐦‍🔥 Initié",
        "discount": 5,
        "role_key": "inviteRole5",
        "benefits": "• Rôle **Initié**\n• **−5%** sur le market",
    },
]

TIER_ROLE_KEYS = ("inviteRole5", "inviteRole10", "inviteRole20")
SYNC_INTERVAL_SECS = 600


def _tier_for_active_count(active_count: int) -> dict | None:
    for tier in INVITE_TIERS:
        if active_count >= tier["min"]:
            return tier
    return None


def get_member_invite_reward(guild: discord.Guild, member_id: int) -> dict:
    """Infos récompense pour un membre (market, affichage)."""
    active = count_active_invitations(guild, member_id)
    tier = _tier_for_active_count(active)
    if not tier:
        return {
            "active": active,
            "tier": None,
            "tier_name": "Aucun rang",
            "discount": 0,
            "discount_label": "Aucune",
        }
    return {
        "active": active,
        "tier": tier,
        "tier_name": tier["name"],
        "discount": tier["discount"],
        "discount_label": f"−{tier['discount']}%",
    }


def build_market_reward_embed(guild: discord.Guild, member: discord.Member) -> discord.Embed:
    info = get_member_invite_reward(guild, member.id)
    embed = discord.Embed(title="🎁 Avantage Invitations", color=0xF1C40F, timestamp=now_utc())
    embed.add_field(name="👤 Client", value=member.mention, inline=True)
    embed.add_field(name="📨 Invitations actives", value=str(info["active"]), inline=True)
    embed.add_field(name="💸 Réduction applicable", value=info["discount_label"], inline=True)
    embed.add_field(name="🏅 Rang actuel", value=info["tier_name"], inline=False)
    return embed


def _db_get_stored_tier(guild_id: int, user_id: int) -> int:
    with get_db() as conn:
        row = conn.execute(
            "SELECT tier FROM invite_reward_state WHERE guild_id=? AND user_id=?",
            (guild_id, user_id),
        ).fetchone()
    return int(row["tier"]) if row else 0


def _db_set_stored_tier(guild_id: int, user_id: int, tier: int):
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO invite_reward_state (guild_id, user_id, tier) VALUES (?,?,?)",
            (guild_id, user_id, tier),
        )


def _resolve_tier_roles(guild: discord.Guild) -> dict[int, discord.Role | None]:
    cfg = load_config(guild.id)
    return {t["key"]: resolve_role(guild, cfg.get(t["role_key"])) for t in INVITE_TIERS}


async def _apply_tier_roles(member: discord.Member, tier: dict | None):
    """Un seul rôle de palier actif ; retire les autres."""
    if not member:
        return
    guild = member.guild
    tier_roles = _resolve_tier_roles(guild)
    target = tier_roles.get(tier["key"]) if tier else None
    to_remove = [r for k, r in tier_roles.items() if r and (not tier or k != tier["key"])]
    try:
        remove = [r for r in to_remove if r in member.roles]
        if remove:
            await member.remove_roles(*remove, reason="Palier invitations (rétrogradation / changement)")
        if target and target not in member.roles:
            await member.add_roles(target, reason=f"Palier invitations — {tier['name']}")
    except discord.Forbidden:
        print(f"[INVITE_REWARDS] Permission manquante pour les rôles — {member} (guild={guild.id})")
    except Exception as e:
        print(f"[INVITE_REWARDS] Erreur rôles pour {member.id} : {e}")


async def _notify_rank_up(guild: discord.Guild, member: discord.Member, tier: dict, active: int):
    dm_embed = discord.Embed(
        title="🐦‍🔥 Nouveau rang atteint !",
        description=(
            f"Félicitations {member.mention} !\n"
            f"Tu viens d'atteindre le rang **{tier['name']}**.\n\n"
            f"✅ Tes avantages ont été automatiquement activés :\n"
            f"{tier['benefits']}"
        ),
        color=0xF1C40F,
        timestamp=now_utc(),
    )
    try:
        await member.send(embed=dm_embed)
    except discord.Forbidden:
        pass
    except Exception as e:
        print(f"[INVITE_REWARDS] DM impossible pour {member.id} : {e}")

    cfg = load_config(guild.id)
    log_ch = resolve_channel(guild, cfg.get("inviteLogsChannel")) or resolve_channel(guild, cfg.get("salon_logs"))
    if not log_ch:
        return
    log_embed = discord.Embed(title="📈 Changement de rang", color=0x2ECC71, timestamp=now_utc())
    log_embed.add_field(name="👤 Utilisateur", value=member.mention, inline=True)
    log_embed.add_field(name="🏅 Nouveau rang", value=tier["name"], inline=True)
    log_embed.add_field(name="📨 Invitations", value=str(active), inline=True)
    try:
        await log_ch.send(embed=log_embed)
    except Exception as e:
        print(f"[INVITE_REWARDS] Erreur log rang pour {member.id} : {e}")


async def process_inviter_rewards(guild: discord.Guild, inviter_id: int, *, notify: bool = True):
    """Vérifie le palier, met à jour les rôles, notifie si montée de rang."""
    member = guild.get_member(inviter_id)
    if not member or member.bot:
        return

    active = count_active_invitations(guild, inviter_id)
    new_tier = _tier_for_active_count(active)
    new_key = new_tier["key"] if new_tier else 0
    old_key = _db_get_stored_tier(guild.id, inviter_id)

    await _apply_tier_roles(member, new_tier)
    _db_set_stored_tier(guild.id, inviter_id, new_key)

    if notify and new_key > old_key and new_tier:
        await _notify_rank_up(guild, member, new_tier, active)


async def on_invite_chain_update(guild: discord.Guild, invited_id: int):
    """Après join/leave : recalculer l'inviteur du membre concerné."""
    inviter_id = db_get_inviter_for_member(guild.id, invited_id)
    if inviter_id:
        await process_inviter_rewards(guild, inviter_id, notify=True)


async def sync_guild_invite_rewards(guild: discord.Guild):
    """Synchronisation complète (tous les inviteurs connus)."""
    for inviter_id in get_distinct_inviter_ids(guild.id):
        try:
            await process_inviter_rewards(guild, inviter_id, notify=False)
        except Exception as e:
            print(f"[INVITE_REWARDS] Sync erreur inviter={inviter_id} guild={guild.id} : {e}")


async def invite_rewards_sync_loop():
    await bot.wait_until_ready()
    print(f"[INVITE_REWARDS] Boucle de sync démarrée ({SYNC_INTERVAL_SECS}s)")
    while not bot.is_closed():
        try:
            for guild in bot.guilds:
                await sync_guild_invite_rewards(guild)
        except Exception as e:
            print(f"[INVITE_REWARDS] Erreur boucle sync : {e}")
        await asyncio.sleep(SYNC_INTERVAL_SECS)
