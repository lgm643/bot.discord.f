"""
events/message.py — Événements messages v3.

CORRECTIONS :
  [1] on_message_delete utilise le helper log_message_delete() (mention+ID+attachments)
      et détecte qui a supprimé via l'Audit Log.
  [2] on_message_edit utilise le helper log_message_edit().
  [3] Les logs messages vont dans la catégorie "messages" (salon_logs_messages).
  [4] Anti-spam utilise les helpers log_antispam_warn/kick/mute.
  [5] Liens bloqués utilisent log_lien_bloque().
"""
import asyncio
import random
import re
import time

import discord

from bot.core import bot, spam_tracker, spam_warned
from bot.utils.market import _auto_delete_in_marche
from bot.utils.helpers import xp_cooldowns, now_utc, load_user_data, get_user, save_user_data, xp_for_level
from bot.utils.config import load_config, resolve_channel
from bot.utils.permissions import is_staff
from bot.utils.logs import (
    send_log,
    log_message_delete, log_message_edit,
    log_lien_bloque, log_antispam_warn, log_antispam_kick, log_antispam_mute,
)
from bot.utils.stats import record_message


@bot.event
async def on_message(message: discord.Message):
    if not message.guild:
        if not message.author.bot:
            await bot.process_commands(message)
        return
    asyncio.create_task(_auto_delete_in_marche(message))
    if message.author.bot:
        return

    member = message.author
    cfg    = load_config(message.guild.id)
    gid    = message.guild.id
    uid    = member.id

    # ── Filtrage liens ────────────────────────────────────────────
    url_pattern = re.compile(r"(https?://|www\.)\S+", re.IGNORECASE)
    if url_pattern.search(message.content) and not member.guild_permissions.administrator and not is_staff(member):
        allowed = cfg.get("allowed_domains", ["tenor.com", "giphy.com"])
        domain_match = re.search(r"(?:https?://|www\.)([^/\s]+)", message.content, re.IGNORECASE)
        domain = domain_match.group(1).lower() if domain_match else ""
        if not any(domain == d or domain.endswith("." + d) for d in allowed):
            try:
                await message.delete()
                await message.channel.send(
                    f"❌ {member.mention} Tu n'as pas la permission d'envoyer des liens ici.",
                    delete_after=6,
                )
                await send_log(message.guild,
                               log_lien_bloque(member, message.channel, message.content, domain),
                               category="messages")
            except Exception:
                pass
            return

    # ── Anti-spam ─────────────────────────────────────────────────
    if not is_staff(member):
        spam_limit  = cfg.get("spam_limit", 4)
        spam_window = float(cfg.get("spam_window", 6.0))
        now_m       = time.monotonic()
        spam_tracker[gid][uid].append(now_m)
        spam_tracker[gid][uid] = [t for t in spam_tracker[gid][uid] if now_m - t <= spam_window]

        if len(spam_tracker[gid][uid]) > spam_limit:
            if uid in spam_warned[gid]:
                spam_warned[gid].discard(uid)
                spam_tracker[gid].pop(uid, None)
                spam_action = cfg.get("spam_action", "mute")

                if spam_action == "kick":
                    try:
                        await member.kick(reason="Anti-spam automatique")
                        await message.channel.send(
                            f"🚫 {member.mention} expulsé pour spam répété.", delete_after=10)
                        await send_log(message.guild,
                                       log_antispam_kick(member, spam_limit + 1, spam_window),
                                       category="moderation")
                    except discord.Forbidden:
                        pass
                else:
                    try:
                        mute_role = discord.utils.get(message.guild.roles, name="Muted")
                        if mute_role:
                            await member.add_roles(mute_role, reason="Anti-spam (mute 5 min)")
                            await message.channel.send(
                                f"🔇 {member.mention} muté **5 minutes** pour spam excessif.", delete_after=10)
                            await send_log(message.guild,
                                           log_antispam_mute(member, spam_limit + 1, spam_window, "5 minutes"),
                                           category="moderation")
                            from bot.commands.moderation import _schedule_unmute
                            asyncio.create_task(_schedule_unmute(message.guild, member, mute_role, 300, "5 minutes"))
                        else:
                            await send_log(message.guild,
                                           log_antispam_kick(member, spam_limit + 1, spam_window),
                                           category="moderation")
                    except discord.Forbidden:
                        pass
            else:
                spam_warned[gid].add(uid)
                spam_tracker[gid][uid] = []
                await message.channel.send(
                    f"⚠️ {member.mention} **Stop le spam !** Prochaine fois = action automatique.",
                    delete_after=10,
                )
                await send_log(message.guild,
                               log_antispam_warn(member, spam_limit + 1, spam_window, 1),
                               category="moderation")

    await bot.process_commands(message)


@bot.listen("on_message")
async def xp_on_message(message: discord.Message):
    if message.author.bot or not message.guild:
        return
    uid = message.author.id
    gid = message.guild.id
    key = f"{gid}:{uid}"
    now = time.monotonic()
    if now - xp_cooldowns.get(key, 0) < 10:
        return
    xp_cooldowns[key] = now
    data = load_user_data(gid)
    u    = get_user(data, uid)
    u["message_count"] += 1
    xp_gained = random.randint(5, 15)
    u["xp"]   += xp_gained
    record_message(gid, uid, xp_gained)
    required = xp_for_level(u["level"] + 1)
    if u["xp"] >= required:
        u["level"] += 1
        u["xp"]    -= required
        save_user_data(gid, data)
        msg = await message.channel.send(
            f"🎉 {message.author.mention} passe niveau **{u['level']}** ! GG 🔥")
        await asyncio.sleep(2)
        try:
            await msg.delete()
        except Exception:
            pass
        return
    save_user_data(gid, data)


@bot.event
async def on_message_delete(message: discord.Message):
    if not message.guild or message.author.bot:
        return
    if not message.content and not message.attachments:
        return
    # Ignorer les salons catalogue/commandes
    cfg    = load_config(message.guild.id)
    cat_ch = resolve_channel(message.guild, cfg.get("salon_catalogue"))
    cmd_ch = resolve_channel(message.guild, cfg.get("salon_commandes"))
    if (cat_ch and message.channel.id == cat_ch.id) or \
       (cmd_ch and message.channel.id == cmd_ch.id):
        return
    # Détecter qui a supprimé via l'audit log
    suppresseur = None
    try:
        await asyncio.sleep(0.5)
        async for entry in message.guild.audit_logs(
            limit=3, action=discord.AuditLogAction.message_delete
        ):
            if (entry.target and entry.target.id == message.author.id and
                    entry.extra.channel.id == message.channel.id):
                age = (discord.utils.utcnow() - entry.created_at).total_seconds()
                if age < 5:
                    suppresseur = entry.user
                break
    except Exception:
        pass
    await send_log(message.guild,
                   log_message_delete(message, suppresseur),
                   category="messages",
                   dedup_key=f"msg-del-{message.id}")


@bot.event
async def on_message_edit(before: discord.Message, after: discord.Message):
    if before.author.bot or not before.guild:
        return
    if before.content == after.content:
        return
    await send_log(before.guild,
                   log_message_edit(before, after),
                   category="messages",
                   dedup_key=f"msg-edit-{before.id}")