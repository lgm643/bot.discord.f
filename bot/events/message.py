import asyncio
import random
import re
import time

import discord

from bot.core import bot, spam_tracker, spam_warned
from bot.utils.market import _auto_delete_in_marche
from bot.utils.helpers import xp_cooldowns, now_utc, load_user_data, get_user, save_user_data, xp_for_level
from bot.utils.config import load_config
from bot.utils.permissions import is_staff
from bot.utils.logs import send_log


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
    cfg = load_config(message.guild.id)
    url_pattern = re.compile(r"(https?://|www\.)\S+", re.IGNORECASE)
    if url_pattern.search(message.content) and not member.guild_permissions.administrator:
        allowed_domains = cfg.get("allowed_domains", ["tenor.com", "giphy.com"])
        domain_match = re.search(r"(?:https?://|www\.)([^/\s]+)", message.content, re.IGNORECASE)
        domain = domain_match.group(1).lower() if domain_match else ""
        if not any(domain == d or domain.endswith("." + d) for d in allowed_domains):
            try:
                await message.delete()
                await message.channel.send(
                    f"❌ {member.mention} Tu n'as pas la permission d'envoyer des liens ici.",
                    delete_after=6,
                )
                embed = discord.Embed(title="🔗 Lien bloqué", color=0xE74C3C, timestamp=now_utc())
                embed.add_field(name="👤 Auteur", value=f"{member} ({member.id})", inline=True)
                embed.add_field(name="📍 Salon", value=message.channel.mention, inline=True)
                embed.add_field(name="💬 Contenu", value=message.content[:500], inline=False)
                await send_log(message.guild, embed)
            except Exception:
                pass
            return
    if not is_staff(member):
        spam_limit = cfg.get("spam_limit", 4)
        spam_window = cfg.get("spam_window", 6.0)
        gid = message.guild.id
        uid = member.id
        now_m = time.monotonic()
        spam_tracker[gid][uid].append(now_m)
        spam_tracker[gid][uid] = [t for t in spam_tracker[gid][uid] if now_m - t <= spam_window]
        if len(spam_tracker[gid][uid]) > spam_limit:
            if uid in spam_warned[gid]:
                spam_warned[gid].discard(uid)
                spam_tracker[gid].pop(uid, None)
                try:
                    await member.kick(reason="Anti-spam automatique")
                    await message.channel.send(
                        f"🚫 {member.mention} expulsé pour spam répété.",
                        delete_after=10,
                    )
                    embed = discord.Embed(title="🚫 Kick Anti-Spam", color=0xE74C3C, timestamp=now_utc())
                    embed.add_field(name="👤 Membre", value=f"{member} ({member.id})", inline=True)
                    await send_log(message.guild, embed)
                except discord.Forbidden:
                    pass
            else:
                spam_warned[gid].add(uid)
                spam_tracker[gid][uid] = []
                await message.channel.send(
                    f"⚠️ {member.mention} **Stop le spam !** Prochaine fois = **expulsion automatique**.",
                    delete_after=10,
                )
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
    u = get_user(data, uid)
    u["message_count"] += 1
    u["xp"] += random.randint(5, 15)
    required = xp_for_level(u["level"] + 1)
    if u["xp"] >= required:
        u["level"] += 1
        u["xp"] -= required
        save_user_data(gid, data)
        msg = await message.channel.send(
            f"🎉 {message.author.mention} passe niveau **{u['level']}** ! GG 🔥"
        )
        await asyncio.sleep(2)
        try:
            await msg.delete()
        except Exception:
            pass
        return
    save_user_data(gid, data)


@bot.event
async def on_message_delete(message: discord.Message):
    if message.author.bot or not message.guild:
        return
    embed = discord.Embed(title="🗑️ Message supprimé", color=0x95A5A6, timestamp=now_utc())
    embed.add_field(name="👤 Auteur", value=f"{message.author} ({message.author.id})", inline=True)
    embed.add_field(name="📍 Salon", value=message.channel.mention, inline=True)
    embed.add_field(name="💬 Contenu", value=message.content[:1000] or "<vide>", inline=False)
    await send_log(message.guild, embed)


@bot.event
async def on_message_edit(before, after):
    if before.author.bot or not before.guild or before.content == after.content:
        return
    embed = discord.Embed(title="✏️ Message modifié", color=0x3498DB, timestamp=now_utc())
    embed.add_field(name="👤 Auteur", value=f"{before.author} ({before.author.id})", inline=True)
    embed.add_field(name="📍 Salon", value=before.channel.mention, inline=True)
    embed.add_field(name="📝 Avant", value=before.content[:500] or "<vide>", inline=False)
    embed.add_field(name="📝 Après", value=after.content[:500] or "<vide>", inline=False)
    embed.add_field(name="🔗 Lien", value=f"[Voir]({after.jump_url})", inline=True)
    await send_log(before.guild, embed)
