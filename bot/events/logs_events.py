"""
events/logs_events.py — Événements Discord ultra-complets.

Couvre TOUS les événements non gérés ailleurs :
  - Rôles (create/delete/update)
  - Salons (create/delete/update)
  - Emojis / Stickers
  - Webhooks
  - Invitations
  - Serveur (guild_update)
  - Threads (create/delete/archive/unarchive/lock)
  - Messages (bulk_delete, pin)
  - Membres (timeout, avatar, global_name)
  - Sécurité anti-abus (création/suppression massive, spam ban/kick)
  - Permissions dangereuses
  - Debug (erreurs API)

Utilise l'Audit Log Discord pour détecter QUI a fait QUOI.
"""
import asyncio
import time
from collections import defaultdict

import discord

from bot.core import bot
from bot.utils.logs import (
    _get_log_channel,
    send_log, send_debug,
    log_role_create, log_role_delete, log_role_update,
    log_channel_create, log_channel_delete, log_channel_update,
    log_emoji, log_sticker,
    log_webhook, log_invite,
    log_guild_update,
    log_security_alert, log_dangerous_perm,
    log_bulk_delete, log_message_pin,
    log_avatar_modifie, log_timeout_member,
    log_roles_modifies, log_pseudo_modifie,
    log_vocal_join, log_vocal_leave, log_vocal_move,
    log_vocal_force_disconnect, log_vocal_state_change,
)

# ── Helper : lecture Audit Log avec timeout ───────────────────────────────────

async def _audit(guild: discord.Guild, action: discord.AuditLogAction, target_id: int = None, limit: int = 3):
    """Retourne la première entrée d'audit correspondante, ou None."""
    try:
        async for entry in guild.audit_logs(limit=limit, action=action):
            if target_id is None or (entry.target and entry.target.id == target_id):
                # Entrée datant de moins de 5s
                age = (discord.utils.utcnow() - entry.created_at).total_seconds()
                if age < 5:
                    return entry
    except discord.Forbidden:
        pass
    except Exception as e:
        print(f"[AUDIT] Erreur lecture audit log : {e}")
    return None


# ══════════════════════════════════════════════════════════════════
#  RÔLES
# ══════════════════════════════════════════════════════════════════

@bot.event
async def on_guild_role_create(role: discord.Role):
    await asyncio.sleep(1.5)
    entry   = await _audit(role.guild, discord.AuditLogAction.role_create, role.id)
    auteur  = entry.user if entry else None
    embed   = log_role_create(role, auteur)
    await send_log(role.guild, embed, category="serveur", dedup_key=f"role-create-{role.id}")

    # Alerte si permissions dangereuses dès la création
    dangerous = _check_dangerous_perms(role.permissions)
    if dangerous:
        alert = log_dangerous_perm(auteur or role.guild.me, role, dangerous)
        await send_log(role.guild, alert, category="securite",
                       content="@here", dedup_key=f"dangperm-create-{role.id}")


@bot.event
async def on_guild_role_delete(role: discord.Role):
    await asyncio.sleep(1.5)
    entry  = await _audit(role.guild, discord.AuditLogAction.role_delete, role.id)
    auteur = entry.user if entry else None
    embed  = log_role_delete(role, auteur)
    await send_log(role.guild, embed, category="serveur", dedup_key=f"role-delete-{role.id}")


@bot.event
async def on_guild_role_update(before: discord.Role, after: discord.Role):
    if before.name == after.name and before.color == after.color \
       and before.permissions == after.permissions and before.hoist == after.hoist \
       and before.mentionable == after.mentionable:
        return
    await asyncio.sleep(1.5)
    entry  = await _audit(after.guild, discord.AuditLogAction.role_update, after.id)
    auteur = entry.user if entry else None
    embed  = log_role_update(before, after, auteur)
    await send_log(after.guild, embed, category="serveur", dedup_key=f"role-update-{after.id}")

    # Alerte si permissions dangereuses nouvellement ajoutées
    if before.permissions != after.permissions:
        added_dangerous = _check_dangerous_perms_diff(before.permissions, after.permissions)
        if added_dangerous and auteur:
            # Trouver les membres qui ont ce rôle
            for member in after.guild.members:
                if after in member.roles:
                    alert = log_dangerous_perm(member, after, added_dangerous)
                    await send_log(after.guild, alert, category="securite",
                                   dedup_key=f"dangperm-role-{after.id}-{member.id}")
                    break  # Une alerte suffit pour le rôle


# ══════════════════════════════════════════════════════════════════
#  SALONS & CATÉGORIES
# ══════════════════════════════════════════════════════════════════

@bot.event
async def on_guild_channel_create(channel: discord.abc.GuildChannel):
    await asyncio.sleep(1.5)
    entry  = await _audit(channel.guild, discord.AuditLogAction.channel_create, channel.id)
    auteur = entry.user if entry else None
    embed  = log_channel_create(channel, auteur)
    await send_log(channel.guild, embed, category="serveur", dedup_key=f"ch-create-{channel.id}")
    # Anti-abus : création massive
    _record_action(channel.guild.id, "ch_create")
    if _is_abuse(channel.guild.id, "ch_create", threshold=5, window=10):
        alert = log_security_alert(
            channel.guild,
            "Création massive de salons",
            f"5+ salons créés en 10s — dernier : `{channel.name}`",
            auteur,
        )
        await send_log(channel.guild, alert, category="securite", content="@here",
                       dedup_key=f"abuse-ch-create-{channel.guild.id}")


@bot.event
async def on_guild_channel_delete(channel: discord.abc.GuildChannel):
    await asyncio.sleep(1.5)
    entry  = await _audit(channel.guild, discord.AuditLogAction.channel_delete, channel.id)
    auteur = entry.user if entry else None
    embed  = log_channel_delete(channel, auteur)
    await send_log(channel.guild, embed, category="serveur", dedup_key=f"ch-delete-{channel.id}")
    _record_action(channel.guild.id, "ch_delete")
    if _is_abuse(channel.guild.id, "ch_delete", threshold=5, window=10):
        alert = log_security_alert(
            channel.guild,
            "Suppression massive de salons",
            f"5+ salons supprimés en 10s — dernier : `{channel.name}`",
            auteur,
        )
        await send_log(channel.guild, alert, category="securite", content="@here",
                       dedup_key=f"abuse-ch-delete-{channel.guild.id}")


@bot.event
async def on_guild_channel_update(before: discord.abc.GuildChannel, after: discord.abc.GuildChannel):
    # Ignorer les changements de position seuls (trop fréquents, peu utiles)
    if before.name == after.name \
       and getattr(before, "topic", None) == getattr(after, "topic", None) \
       and getattr(before, "slowmode_delay", None) == getattr(after, "slowmode_delay", None) \
       and getattr(before, "nsfw", None) == getattr(after, "nsfw", None) \
       and getattr(before, "bitrate", None) == getattr(after, "bitrate", None) \
       and getattr(before, "user_limit", None) == getattr(after, "user_limit", None) \
       and before.category == after.category:
        return
    await asyncio.sleep(1.5)
    entry  = await _audit(after.guild, discord.AuditLogAction.channel_update, after.id)
    auteur = entry.user if entry else None
    embed  = log_channel_update(before, after, auteur)
    await send_log(after.guild, embed, category="serveur", dedup_key=f"ch-update-{after.id}")


# ══════════════════════════════════════════════════════════════════
#  EMOJIS
# ══════════════════════════════════════════════════════════════════

@bot.event
async def on_guild_emojis_update(guild: discord.Guild, before: list, after: list):
    before_ids = {e.id for e in before}
    after_ids  = {e.id for e in after}

    # Créés
    for emoji in after:
        if emoji.id not in before_ids:
            await asyncio.sleep(1.5)
            entry  = await _audit(guild, discord.AuditLogAction.emoji_create, emoji.id)
            auteur = entry.user if entry else None
            await send_log(guild, log_emoji("créé", emoji, auteur), category="serveur",
                           dedup_key=f"emoji-create-{emoji.id}")

    # Supprimés
    for emoji in before:
        if emoji.id not in after_ids:
            await asyncio.sleep(1.5)
            entry  = await _audit(guild, discord.AuditLogAction.emoji_delete, emoji.id)
            auteur = entry.user if entry else None
            await send_log(guild, log_emoji("supprimé", emoji, auteur), category="serveur",
                           dedup_key=f"emoji-delete-{emoji.id}")

    # Modifiés (nom changé)
    before_map = {e.id: e for e in before}
    for emoji in after:
        if emoji.id in before_map and emoji.name != before_map[emoji.id].name:
            await send_log(guild, log_emoji("modifié", emoji), category="serveur",
                           dedup_key=f"emoji-update-{emoji.id}")


# ══════════════════════════════════════════════════════════════════
#  STICKERS
# ══════════════════════════════════════════════════════════════════

@bot.event
async def on_guild_stickers_update(guild: discord.Guild, before: list, after: list):
    before_ids = {s.id for s in before}
    after_ids  = {s.id for s in after}

    for s in after:
        if s.id not in before_ids:
            await asyncio.sleep(1.5)
            entry  = await _audit(guild, discord.AuditLogAction.sticker_create, s.id)
            auteur = entry.user if entry else None
            await send_log(guild, log_sticker("créé", s, auteur), category="serveur",
                           dedup_key=f"sticker-create-{s.id}")

    for s in before:
        if s.id not in after_ids:
            await asyncio.sleep(1.5)
            entry  = await _audit(guild, discord.AuditLogAction.sticker_delete, s.id)
            auteur = entry.user if entry else None
            await send_log(guild, log_sticker("supprimé", s, auteur), category="serveur",
                           dedup_key=f"sticker-delete-{s.id}")

    before_map = {s.id: s for s in before}
    for s in after:
        if s.id in before_map and (s.name != before_map[s.id].name or s.description != before_map[s.id].description):
            await send_log(guild, log_sticker("modifié", s), category="serveur",
                           dedup_key=f"sticker-update-{s.id}")


# ══════════════════════════════════════════════════════════════════
#  WEBHOOKS
# ══════════════════════════════════════════════════════════════════

@bot.event
async def on_webhooks_update(channel: discord.TextChannel):
    await asyncio.sleep(1.5)
    guild = channel.guild
    for action, label in [
        (discord.AuditLogAction.webhook_create,  "créé"),
        (discord.AuditLogAction.webhook_delete,  "supprimé"),
        (discord.AuditLogAction.webhook_update,  "modifié"),
    ]:
        entry = await _audit(guild, action)
        if entry:
            name = getattr(entry.target, "name", "?") if entry.target else "?"
            embed = log_webhook(label, guild, name, channel.name, entry.user)
            await send_log(guild, embed, category="serveur",
                           dedup_key=f"wh-{label}-{channel.id}-{int(time.time())}")
            break


# ══════════════════════════════════════════════════════════════════
#  INVITATIONS
# ══════════════════════════════════════════════════════════════════

@bot.event
async def on_invite_create(invite: discord.Invite):
    embed = log_invite("créée", invite, invite.inviter)
    await send_log(invite.guild, embed, category="membres",
                   dedup_key=f"invite-create-{invite.code}")


@bot.event
async def on_invite_delete(invite: discord.Invite):
    await asyncio.sleep(1.5)
    entry  = await _audit(invite.guild, discord.AuditLogAction.invite_delete)
    auteur = entry.user if entry else None
    embed  = log_invite("supprimée", invite, auteur)
    await send_log(invite.guild, embed, category="membres",
                   dedup_key=f"invite-delete-{invite.code}")


# ══════════════════════════════════════════════════════════════════
#  SERVEUR (guild_update)
# ══════════════════════════════════════════════════════════════════

@bot.event
async def on_guild_update(before: discord.Guild, after: discord.Guild):
    if before.name == after.name and before.icon == after.icon \
       and before.banner == after.banner \
       and before.verification_level == after.verification_level \
       and before.afk_channel == after.afk_channel \
       and before.owner == after.owner:
        return
    await asyncio.sleep(1.5)
    entry  = await _audit(after, discord.AuditLogAction.guild_update)
    auteur = entry.user if entry else None
    embed  = log_guild_update(before, after, auteur)
    await send_log(after, embed, category="serveur", dedup_key=f"guild-update-{after.id}")


# ══════════════════════════════════════════════════════════════════
#  THREADS
# ══════════════════════════════════════════════════════════════════

@bot.event
async def on_thread_create(thread: discord.Thread):
    e = discord.Embed(title="🧵 THREAD CRÉÉ", color=0x2ECC71, timestamp=discord.utils.utcnow())
    e.add_field(name="📍 Thread",   value=f"{thread.mention}\n`{thread.name}` · `{thread.id}`", inline=True)
    e.add_field(name="📂 Salon parent", value=f"`{thread.parent.name}`" if thread.parent else "?", inline=True)
    if thread.owner:
        e.add_field(name="👤 Créé par", value=f"{thread.owner.mention}\n`{thread.owner.id}`", inline=True)
    e.set_footer(text=f"guild {thread.guild.id}")
    await send_log(thread.guild, e, category="messages", dedup_key=f"thread-create-{thread.id}")


@bot.event
async def on_thread_delete(thread: discord.Thread):
    e = discord.Embed(title="🗑️ THREAD SUPPRIMÉ", color=0xE74C3C, timestamp=discord.utils.utcnow())
    e.add_field(name="📍 Thread",       value=f"`{thread.name}` · `{thread.id}`", inline=True)
    e.add_field(name="📂 Salon parent", value=f"`{thread.parent.name}`" if thread.parent else "?", inline=True)
    e.set_footer(text=f"guild {thread.guild.id}")
    await send_log(thread.guild, e, category="messages", dedup_key=f"thread-delete-{thread.id}")


@bot.event
async def on_thread_update(before: discord.Thread, after: discord.Thread):
    changes = []
    if before.name != after.name:
        changes.append(f"**Nom :** `{before.name}` → `{after.name}`")
    if before.archived != after.archived:
        action = "archivé" if after.archived else "désarchivé"
        changes.append(f"**Statut :** {action}")
    if before.locked != after.locked:
        action = "verrouillé" if after.locked else "déverrouillé"
        changes.append(f"**Verrou :** {action}")
    if not changes:
        return
    e = discord.Embed(title="✏️ THREAD MODIFIÉ", color=0x3498DB, timestamp=discord.utils.utcnow())
    e.add_field(name="📍 Thread",       value=f"`{after.name}` · `{after.id}`", inline=True)
    e.add_field(name="📝 Changements",  value="\n".join(changes),               inline=False)
    e.set_footer(text=f"guild {after.guild.id}")
    await send_log(after.guild, e, category="messages", dedup_key=f"thread-update-{after.id}")


# ══════════════════════════════════════════════════════════════════
#  MESSAGES — bulk delete + pin
# ══════════════════════════════════════════════════════════════════

@bot.event
async def on_raw_bulk_message_delete(payload: discord.RawBulkMessageDeleteEvent):
    guild = bot.get_guild(payload.guild_id)
    if not guild:
        return
    channel = guild.get_channel(payload.channel_id)
    if not channel:
        return
    await asyncio.sleep(1.5)
    entry  = await _audit(guild, discord.AuditLogAction.message_bulk_delete)
    auteur = entry.user if entry else None

    class FakeMessage:
        def __init__(self, mid):
            self.id = mid
            self.author = guild.me
            self.content = ""
    fake_msgs = [FakeMessage(mid) for mid in payload.message_ids]
    embed = log_bulk_delete(channel, fake_msgs, auteur)
    await send_log(guild, embed, category="messages",
                   dedup_key=f"bulk-{payload.channel_id}-{int(time.time())}")


@bot.event
async def on_guild_channel_pins_update(channel: discord.TextChannel, last_pin):
    try:
        pins = await channel.pins()
        if pins:
            msg    = pins[0]
            embed  = log_message_pin(msg, None, "épinglé")
            await send_log(channel.guild, embed, category="messages",
                           dedup_key=f"pin-{channel.id}-{int(time.time())}")
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════
#  MEMBRES — timeout / avatar / global_name
# ══════════════════════════════════════════════════════════════════

@bot.event
async def on_member_update(before: discord.Member, after: discord.Member):
    from bot.utils.config import load_config, cfg_channel
    from bot.utils.embeds import build_roster_embed, refresh_roster_embed

    cfg = load_config(after.guild.id)

    # Mise à jour roster si rôle faction (roster) change — clés role_roster_*
    ROSTER_KEYS  = ["role_roster_leader", "role_roster_officier", "role_roster_confiance",
                    "role_roster_plus", "role_roster_membre", "role_roster_recrue"]
    roster_names = {cfg[k].lower() for k in ROSTER_KEYS if cfg.get(k)}
    before_r = {r.name.lower() for r in before.roles if r.name.lower() in roster_names}
    after_r  = {r.name.lower() for r in after.roles  if r.name.lower() in roster_names}
    if before_r != after_r:
        await refresh_roster_embed(after.guild)

    # Rôles ajoutés / retirés
    added   = set(after.roles)  - set(before.roles)
    removed = set(before.roles) - set(after.roles)
    if added or removed:
        await asyncio.sleep(1.5)
        entry = await _audit(after.guild, discord.AuditLogAction.member_role_update, after.id)
        mod   = entry.user if entry else None
        embed = log_roles_modifies(after, added, removed, mod)
        await send_log(after.guild, embed, category="membres",
                       dedup_key=f"roles-{after.id}-{int(time.time())}")

        # Alerte permissions dangereuses si rôle ajouté avec perms sensibles
        for role in added:
            dangerous = _check_dangerous_perms(role.permissions)
            if dangerous:
                alert = log_dangerous_perm(after, role, dangerous)
                await send_log(after.guild, alert, category="securite",
                               dedup_key=f"dangperm-member-{after.id}-{role.id}")

    # Pseudo
    if before.display_name != after.display_name:
        embed = log_pseudo_modifie(after, before.display_name, after.display_name)
        await send_log(after.guild, embed, category="membres",
                       dedup_key=f"nick-{after.id}")

    # Timeout
    if before.timed_out_until != after.timed_out_until:
        await asyncio.sleep(1.5)
        entry = await _audit(after.guild, discord.AuditLogAction.member_update, after.id)
        mod   = entry.user if entry else after.guild.me
        embed = log_timeout_member(mod, after, before.timed_out_until, after.timed_out_until)
        await send_log(after.guild, embed, category="moderation",
                       dedup_key=f"timeout-{after.id}")

    # Avatar serveur modifié
    if before.guild_avatar != after.guild_avatar:
        embed = log_avatar_modifie(after, str(before.guild_avatar.url) if before.guild_avatar else None)
        await send_log(after.guild, embed, category="membres",
                       dedup_key=f"avatar-{after.id}")


# ══════════════════════════════════════════════════════════════════
#  UNBAN
# ══════════════════════════════════════════════════════════════════

@bot.event
async def on_member_unban(guild: discord.Guild, user: discord.User):
    await asyncio.sleep(1.5)
    from bot.utils.logs import log_unban
    entry  = await _audit(guild, discord.AuditLogAction.unban, user.id)
    mod    = entry.user if entry else guild.me
    raison = entry.reason or "Aucune raison" if entry else "Aucune raison"
    embed  = log_unban(mod, user, raison)
    await send_log(guild, embed, category="moderation", dedup_key=f"unban-{user.id}")


# ══════════════════════════════════════════════════════════════════
#  VOCAL — événements d'état complets
# ══════════════════════════════════════════════════════════════════

_voice_join_times: dict[tuple, float] = {}

@bot.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    if member.bot:
        return

    import time as _time
    from bot.utils.voice_inactivity import record_voice_activity, clear_voice_activity
    from bot.utils.helpers import load_user_data, get_user, save_user_data
    from bot.utils.stats import record_voice_end

    gid = member.guild.id
    uid = member.id
    key = (gid, uid)

    # ── Stats XP vocal ────────────────────────────────────────────
    now_ts = _time.time()
    data   = load_user_data(gid)
    u      = get_user(data, uid)

    if before.channel is None and after.channel is not None:
        u["voice_join"] = now_ts
        _voice_join_times[key] = now_ts
    elif before.channel is not None and after.channel is None:
        if u.get("voice_join"):
            dur = now_ts - u["voice_join"]
            u["voice_time"] = u.get("voice_time", 0.0) + dur
            u["voice_join"] = None
            record_voice_end(gid, uid, dur)
        _voice_join_times.pop(key, None)
    save_user_data(gid, data)

    # ── Inactivité vocale ─────────────────────────────────────────
    if after.channel is not None:
        record_voice_activity(gid, uid)
    else:
        clear_voice_activity(gid, uid)

    # ── Logs vocaux ───────────────────────────────────────────────
    if before.channel is None and after.channel is not None:
        # Connexion
        await send_log(member.guild, log_vocal_join(member, after.channel),
                       category="vocal", dedup_key=f"vc-join-{uid}-{after.channel.id}")

    elif before.channel is not None and after.channel is None:
        # Déconnexion
        dur = now_ts - _voice_join_times.pop(key, now_ts)
        # Vérifier si déconnexion forcée via audit log
        # DEBUG : détecter déconnexion forcée
        await asyncio.sleep(2.0)
        force_auteur = None
        try:
            async for entry in member.guild.audit_logs(
                limit=5, action=discord.AuditLogAction.member_disconnect
            ):
                age = (discord.utils.utcnow() - entry.created_at).total_seconds()
                print(f"[DEBUG-DISCONNECT] user={entry.user} target={entry.target} age={age:.1f}s count={getattr(entry.extra, 'count', '?')}")
                if age < 5 and entry.user and entry.user.id != uid:
                    force_auteur = entry.user
                    break
        except Exception as e:
            print(f"[LOG] Erreur audit disconnect : {e}")

        print(f"[DEBUG-DISCONNECT] membre={member} force_auteur={force_auteur}")
        if force_auteur:
            embed = log_vocal_force_disconnect(member, before.channel, force_auteur)
        else:
            embed = log_vocal_leave(member, before.channel, dur)
        await send_log(member.guild, embed, category="vocal",
                       dedup_key=f"vc-leave-{uid}")

    elif before.channel is not None and after.channel is not None and before.channel != after.channel:
        # Déplacement
        await asyncio.sleep(1.5)
        entry     = await _audit(member.guild, discord.AuditLogAction.member_move, uid)
        deplaceur = entry.user if (entry and entry.user and entry.user.id != uid) else None
        embed     = log_vocal_move(member, before.channel, after.channel, deplaceur)
        await send_log(member.guild, embed, category="vocal",
                       dedup_key=f"vc-move-{uid}")

    # Changements d'état dans le même salon
    elif before.channel == after.channel and after.channel is not None:
        ch = after.channel
        states = []

        if before.mute != after.mute:
            if after.mute:
                await asyncio.sleep(1.5)
                entry = await _audit(member.guild, discord.AuditLogAction.member_update, uid)
                aut   = entry.user if (entry and entry.user and entry.user.id != uid) else None
                states.append(("Mute serveur", aut))
            else:
                states.append(("Unmute serveur", None))

        if before.deaf != after.deaf:
            if after.deaf:
                await asyncio.sleep(1.5)
                entry = await _audit(member.guild, discord.AuditLogAction.member_update, uid)
                aut   = entry.user if (entry and entry.user and entry.user.id != uid) else None
                states.append(("Sourd serveur", aut))
            else:
                states.append(("Non-sourd serveur", None))

        if before.self_mute != after.self_mute:
            states.append(("Self-mute" if after.self_mute else "Self-unmute", None))
        if before.self_deaf != after.self_deaf:
            states.append(("Self-sourd" if after.self_deaf else "Self-non-sourd", None))
        if before.self_stream != after.self_stream:
            states.append(("Stream activé" if after.self_stream else "Stream désactivé", None))
        if before.self_video != after.self_video:
            states.append(("Caméra activée" if after.self_video else "Caméra désactivée", None))

        for action, auteur in states:
            embed = log_vocal_state_change(member, action, ch, auteur)
            await send_log(member.guild, embed, category="vocal",
                           dedup_key=f"vc-state-{uid}-{action}")

        # Réinitialiser le compteur d'inactivité si activité détectée
        if any(a in ["Self-unmute", "Stream activé", "Caméra activée"] for a, _ in states):
            record_voice_activity(gid, uid)


# ══════════════════════════════════════════════════════════════════
#  SÉCURITÉ — Anti-abus (ban/kick/rôle massif)
# ══════════════════════════════════════════════════════════════════

_abuse_tracker: dict[str, list[float]] = defaultdict(list)

def _record_action(guild_id: int, action: str):
    key = f"{guild_id}:{action}"
    now = time.monotonic()
    _abuse_tracker[key].append(now)

def _is_abuse(guild_id: int, action: str, threshold: int = 5, window: float = 10.0) -> bool:
    key = f"{guild_id}:{action}"
    now = time.monotonic()
    _abuse_tracker[key] = [t for t in _abuse_tracker[key] if now - t < window]
    return len(_abuse_tracker[key]) >= threshold

_DANGEROUS_PERMS = [
    "administrator", "manage_guild", "manage_roles", "manage_channels",
    "ban_members", "kick_members", "manage_webhooks", "mention_everyone",
]

def _check_dangerous_perms(permissions: discord.Permissions) -> list[str]:
    return [p for p in _DANGEROUS_PERMS if getattr(permissions, p, False)]

def _check_dangerous_perms_diff(before: discord.Permissions, after: discord.Permissions) -> list[str]:
    return [p for p in _DANGEROUS_PERMS
            if not getattr(before, p, False) and getattr(after, p, False)]


@bot.event
async def on_member_ban(guild: discord.Guild, user: discord.User):
    _record_action(guild.id, "ban")
    if _is_abuse(guild.id, "ban", threshold=4, window=10):
        await asyncio.sleep(1.5)
        entry  = await _audit(guild, discord.AuditLogAction.ban, user.id)
        auteur = entry.user if entry else None
        alert  = log_security_alert(
            guild, "Spam de bans",
            f"4+ bans en 10s — dernier : `{user}`",
            auteur,
        )
        await send_log(guild, alert, category="securite", content="@here",
                       dedup_key=f"abuse-ban-{guild.id}-{int(time.time())}")


# ══════════════════════════════════════════════════════════════════
#  DEBUG — Erreurs globales
# ══════════════════════════════════════════════════════════════════

@bot.event
async def on_error(event: str, *args, **kwargs):
    import traceback, sys
    exc = sys.exc_info()
    tb  = "".join(traceback.format_exception(*exc)) if exc[0] else "Inconnu"
    print(f"[ERROR] Événement : {event}\n{tb}")
    for guild in bot.guilds:
        await send_debug(guild, f"Erreur événement : {event}", tb[:1800])


@bot.event
async def on_command_error(ctx, error):
    import traceback
    tb = "".join(traceback.format_exception(type(error), error, error.__traceback__))
    print(f"[CMD ERROR] {ctx.command} : {error}")
    if ctx.guild:
        await send_debug(ctx.guild, f"Erreur commande : !{ctx.command}", tb[:1800])
    if isinstance(error, discord.ext.commands.CommandNotFound):
        return
    if isinstance(error, discord.ext.commands.MissingPermissions):
        await ctx.send("❌ Permissions insuffisantes.", delete_after=5)
    elif isinstance(error, discord.ext.commands.MissingRequiredArgument):
        await ctx.send(f"❌ Argument manquant : `{error.param.name}`", delete_after=8)
    elif isinstance(error, discord.ext.commands.BadArgument):
        await ctx.send("❌ Argument invalide.", delete_after=8)