import discord

from bot.core import bot
from bot.utils.invites import _invite_cache, _get_invite_lock


@bot.event
async def on_invite_create(invite: discord.Invite):
    """Met à jour le cache quand une invitation est créée."""
    if not invite.guild:
        return
    guild_id = invite.guild.id
    lock = _get_invite_lock(guild_id)
    async with lock:
        if guild_id not in _invite_cache:
            _invite_cache[guild_id] = {}
        _invite_cache[guild_id][invite.code] = {
            "uses":       invite.uses or 0,
            "inviter_id": invite.inviter.id if invite.inviter else None,
            "max_uses":   invite.max_uses,
        }
    print(f"[INVITE] Nouvelle invitation créée : {invite.code} (guild={guild_id})")


@bot.event
async def on_invite_delete(invite: discord.Invite):
    """Met à jour le cache quand une invitation est supprimée."""
    if not invite.guild:
        return
    guild_id = invite.guild.id
    lock = _get_invite_lock(guild_id)
    async with lock:
        if guild_id in _invite_cache:
            _invite_cache[guild_id].pop(invite.code, None)
    print(f"[INVITE] Invitation supprimée : {invite.code} (guild={guild_id})")
