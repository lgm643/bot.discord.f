"""
utils/logs.py — Système de logs ultra-complet v3.

Catégories de salons config :
  salon_logs              → modération (ban/kick/mute…)
  salon_logs_messages     → messages (edit/delete/bulk…)
  salon_logs_membres      → membres (join/leave/update…)
  salon_logs_vocal        → vocal (join/leave/move/activité…)
  salon_logs_serveur      → serveur/salons/rôles/emojis…
  salon_logs_securite     → alertes sécurité
  salon_logs_debug        → erreurs Python / API Discord
"""
from __future__ import annotations
import time
from datetime import datetime, timezone
from typing import Optional
import discord
from bot.utils.helpers import now_utc

# ── Anti-doublon ──────────────────────────────────────────────────────────────
_sent_cache: dict[str, float] = {}
_DEDUP_TTL = 2.0

def _is_duplicate(key: str) -> bool:
    now = time.monotonic()
    if key in _sent_cache and now - _sent_cache[key] < _DEDUP_TTL:
        return True
    _sent_cache[key] = now
    if len(_sent_cache) > 500:
        cutoff = now - _DEDUP_TTL * 10
        for k in [k for k, v in list(_sent_cache.items()) if v < cutoff]:
            del _sent_cache[k]
    return False

# ── Routing salons ────────────────────────────────────────────────────────────
_CATEGORY_CHANNELS = {
    "moderation": "salon_logs",
    "messages":   "salon_logs_messages",
    "membres":    "salon_logs_membres",
    "vocal":      "salon_logs_vocal",
    "serveur":    "salon_logs_serveur",
    "securite":   "salon_logs_securite",
    "debug":      "salon_logs_debug",
}

async def _get_log_channel(guild: discord.Guild, category: str = "moderation"):
    from bot.utils.config import cfg_channel
    cfg_key = _CATEGORY_CHANNELS.get(category, "salon_logs")
    ch = cfg_channel(guild, cfg_key)
    if ch:
        return ch
    return cfg_channel(guild, "salon_logs")

async def get_log_channel(guild: discord.Guild):
    return await _get_log_channel(guild, "moderation")

async def send_log(guild: discord.Guild, embed: discord.Embed,
                   category: str = "moderation", content: str = "", dedup_key: str = ""):
    if dedup_key and _is_duplicate(dedup_key):
        return
    ch = await _get_log_channel(guild, category)
    if not ch:
        return
    try:
        await ch.send(content=content, embed=embed)
    except discord.Forbidden:
        print(f"[LOG] Permission refusée dans #{ch.name} (guild={guild.id})")
    except Exception as e:
        print(f"[LOG] Erreur : {e}")

async def send_debug(guild: discord.Guild, title: str, desc: str):
    from bot.utils.config import load_config
    if not load_config(guild.id).get("debug_enabled", False):
        return
    e = discord.Embed(title=f"🐛 DEBUG — {title}", description=f"```{desc[:1800]}```",
                      color=0x7F8C8D, timestamp=now_utc())
    e.set_footer(text=f"guild={guild.id}")
    await send_log(guild, e, category="debug")

def _footer(action_id: str, guild) -> str:
    gid = guild.id if hasattr(guild, "id") else guild
    return f"{action_id} · guild {gid}"

# ══════════════════════════════════════════════════════════════════
#  MODÉRATION
# ══════════════════════════════════════════════════════════════════

def log_ban(mod, cible, raison, jours=1):
    e = discord.Embed(title="🔨 BAN", color=0xC0392B, timestamp=now_utc())
    e.set_thumbnail(url=cible.display_avatar.url)
    e.add_field(name="🎯 Cible",       value=f"{cible.mention}\n`{cible}` · `{cible.id}`", inline=True)
    e.add_field(name="🛡️ Modérateur",  value=f"{mod.mention}\n`{mod}` · `{mod.id}`",       inline=True)
    e.add_field(name="🗑️ Messages",    value=f"{jours} jour(s) supprimés",                 inline=True)
    e.add_field(name="📝 Raison",       value=raison,                                       inline=False)
    e.add_field(name="📅 Compte créé", value=discord.utils.format_dt(cible.created_at, "D"), inline=True)
    e.set_footer(text=_footer(f"BAN-{cible.id}", mod.guild))
    return e

def log_unban(mod, user, raison):
    e = discord.Embed(title="✅ UNBAN", color=0x2ECC71, timestamp=now_utc())
    e.set_thumbnail(url=user.display_avatar.url)
    e.add_field(name="🎯 Cible",      value=f"`{user}` · `{user.id}`",    inline=True)
    e.add_field(name="🛡️ Modérateur", value=f"{mod.mention}\n`{mod.id}`", inline=True)
    e.add_field(name="📝 Raison",      value=raison,                       inline=False)
    e.set_footer(text=_footer(f"UNBAN-{user.id}", mod.guild))
    return e

def log_kick(mod, cible, raison):
    e = discord.Embed(title="👢 KICK", color=0xE67E22, timestamp=now_utc())
    e.set_thumbnail(url=cible.display_avatar.url)
    e.add_field(name="🎯 Cible",      value=f"{cible.mention}\n`{cible}` · `{cible.id}`", inline=True)
    e.add_field(name="🛡️ Modérateur", value=f"{mod.mention}\n`{mod}` · `{mod.id}`",       inline=True)
    e.add_field(name="📝 Raison",      value=raison,                                       inline=False)
    e.add_field(name="📅 Arrivé le",  value=discord.utils.format_dt(cible.joined_at, "D") if cible.joined_at else "?", inline=True)
    roles = [r.mention for r in reversed(cible.roles) if r.name != "@everyone"]
    e.add_field(name=f"🎭 Rôles ({len(roles)})", value=", ".join(roles[:10]) or "Aucun", inline=False)
    e.set_footer(text=_footer(f"KICK-{cible.id}", mod.guild))
    return e

def log_mute(mod, cible, raison, duree_str, expires_ts):
    e = discord.Embed(title="🔇 MUTE", color=0xF39C12, timestamp=now_utc())
    e.set_thumbnail(url=cible.display_avatar.url)
    e.add_field(name="🎯 Cible",      value=f"{cible.mention}\n`{cible}` · `{cible.id}`", inline=True)
    e.add_field(name="🛡️ Modérateur", value=f"{mod.mention}\n`{mod}` · `{mod.id}`",       inline=True)
    e.add_field(name="⏱️ Durée",       value=duree_str,                                    inline=True)
    e.add_field(name="⌛ Expiration",  value=f"<t:{int(expires_ts)}:F>" if expires_ts else "Permanent", inline=True)
    e.add_field(name="📝 Raison",      value=raison,                                       inline=False)
    e.set_footer(text=_footer(f"MUTE-{cible.id}", mod.guild))
    return e

def log_unmute(mod, cible, automatique=False):
    e = discord.Embed(title="🔊 UNMUTE" + (" (auto)" if automatique else ""), color=0x2ECC71, timestamp=now_utc())
    e.set_thumbnail(url=cible.display_avatar.url)
    e.add_field(name="🎯 Cible", value=f"{cible.mention}\n`{cible}` · `{cible.id}`", inline=True)
    if automatique:
        e.add_field(name="🤖 Source", value="Expiration automatique", inline=True)
    else:
        e.add_field(name="🛡️ Modérateur", value=f"{mod.mention}\n`{mod.id}`", inline=True)
    e.set_footer(text=_footer(f"UNMUTE-{cible.id}", mod.guild))
    return e

def log_warn(mod, cible, raison, total):
    e = discord.Embed(title="⚠️ AVERTISSEMENT", color=0xF1C40F, timestamp=now_utc())
    e.set_thumbnail(url=cible.display_avatar.url)
    e.add_field(name="🎯 Cible",        value=f"{cible.mention}\n`{cible}` · `{cible.id}`", inline=True)
    e.add_field(name="🛡️ Modérateur",   value=f"{mod.mention}\n`{mod.id}`",                 inline=True)
    e.add_field(name="🔢 Total warns",  value=str(total),                                   inline=True)
    e.add_field(name="📝 Raison",        value=raison,                                       inline=False)
    e.set_footer(text=_footer(f"WARN-{cible.id}", mod.guild))
    return e

def log_purge(mod, salon, nb):
    e = discord.Embed(title="🗑️ PURGE", color=0x95A5A6, timestamp=now_utc())
    e.add_field(name="🛡️ Modérateur", value=f"{mod.mention}\n`{mod}` · `{mod.id}`", inline=True)
    e.add_field(name="📍 Salon",       value=f"{salon.mention}\n`#{salon.name}`",    inline=True)
    e.add_field(name="🗑️ Supprimés",   value=str(nb),                               inline=True)
    e.set_footer(text=_footer(f"PURGE-{salon.id}", mod.guild))
    return e

def log_timeout(mod, cible, raison, until):
    e = discord.Embed(title="⏱️ TIMEOUT", color=0xE74C3C, timestamp=now_utc())
    e.set_thumbnail(url=cible.display_avatar.url)
    e.add_field(name="🎯 Cible",      value=f"{cible.mention}\n`{cible}` · `{cible.id}`", inline=True)
    e.add_field(name="🛡️ Modérateur", value=f"{mod.mention}\n`{mod.id}`",                 inline=True)
    e.add_field(name="⌛ Fin",        value=discord.utils.format_dt(until, "F") if until else "?", inline=True)
    e.add_field(name="📝 Raison",      value=raison,                                       inline=False)
    e.set_footer(text=_footer(f"TIMEOUT-{cible.id}", mod.guild))
    return e

def log_timeout_update(mod, cible, avant, apres):
    title = "⏱️ FIN DE TIMEOUT" if apres is None else "⏱️ TIMEOUT MODIFIÉ"
    color = 0x2ECC71 if apres is None else 0xE67E22
    e = discord.Embed(title=title, color=color, timestamp=now_utc())
    e.set_thumbnail(url=cible.display_avatar.url)
    e.add_field(name="🎯 Cible",      value=f"{cible.mention}\n`{cible}` · `{cible.id}`", inline=True)
    e.add_field(name="🛡️ Modérateur", value=f"{mod.mention}\n`{mod.id}`", inline=True)
    e.add_field(name="📝 Avant", value=discord.utils.format_dt(avant, "F") if avant else "Aucun", inline=True)
    e.add_field(name="📝 Après", value=discord.utils.format_dt(apres, "F") if apres else "Levé",  inline=True)
    e.set_footer(text=_footer(f"TIMEOUT-UPD-{cible.id}", mod.guild))
    return e

def log_slowmode(mod, salon, avant, apres):
    e = discord.Embed(title="🐌 SLOWMODE", color=0x3498DB, timestamp=now_utc())
    e.add_field(name="🛡️ Modérateur", value=f"{mod.mention}\n`{mod.id}`", inline=True)
    e.add_field(name="📍 Salon",       value=salon.mention,               inline=True)
    e.add_field(name="📝 Avant",        value=f"{avant}s",                inline=True)
    e.add_field(name="📝 Après",        value=f"{apres}s",                inline=True)
    e.set_footer(text=_footer(f"SLOWMODE-{salon.id}", mod.guild))
    return e

def log_antispam_warn(cible, nb, fenetre, n):
    e = discord.Embed(title="⚠️ ANTI-SPAM — Avertissement", color=0xF39C12, timestamp=now_utc())
    e.set_thumbnail(url=cible.display_avatar.url)
    e.add_field(name="🎯 Membre",        value=f"{cible.mention}\n`{cible}` · `{cible.id}`", inline=True)
    e.add_field(name="🤖 Source",         value="Système anti-spam",                          inline=True)
    e.add_field(name="📊 Déclencheur",    value=f"{nb} msgs en {fenetre}s",                  inline=True)
    e.add_field(name="🔢 Avertissement",  value=f"n°{n}",                                    inline=True)
    e.set_footer(text=_footer(f"SPAM-WARN-{cible.id}", cible.guild))
    return e

def log_antispam_kick(cible, nb, fenetre):
    e = discord.Embed(title="🚫 ANTI-SPAM — Kick auto", color=0xC0392B, timestamp=now_utc())
    e.set_thumbnail(url=cible.display_avatar.url)
    e.add_field(name="🎯 Membre",      value=f"{cible.mention}\n`{cible}` · `{cible.id}`", inline=True)
    e.add_field(name="📊 Déclencheur", value=f"{nb} msgs en {fenetre}s",                  inline=True)
    e.set_footer(text=_footer(f"SPAM-KICK-{cible.id}", cible.guild))
    return e

def log_antispam_mute(cible, nb, fenetre, duree):
    e = discord.Embed(title="🔇 ANTI-SPAM — Mute auto", color=0xE67E22, timestamp=now_utc())
    e.set_thumbnail(url=cible.display_avatar.url)
    e.add_field(name="🎯 Membre",     value=f"{cible.mention}\n`{cible}` · `{cible.id}`", inline=True)
    e.add_field(name="⏱️ Durée mute",  value=duree,                                        inline=True)
    e.add_field(name="📊 Déclencheur", value=f"{nb} msgs en {fenetre}s",                  inline=True)
    e.set_footer(text=_footer(f"SPAM-MUTE-{cible.id}", cible.guild))
    return e

def log_lien_bloque(membre, salon, contenu, domaine):
    e = discord.Embed(title="🔗 LIEN BLOQUÉ", color=0xE74C3C, timestamp=now_utc())
    e.set_thumbnail(url=membre.display_avatar.url)
    e.add_field(name="👤 Auteur",  value=f"{membre.mention}\n`{membre}` · `{membre.id}`", inline=True)
    e.add_field(name="📍 Salon",   value=f"{salon.mention}\n`#{salon.name}`",             inline=True)
    e.add_field(name="🌐 Domaine", value=f"`{domaine}`",                                  inline=True)
    e.add_field(name="💬 Contenu", value=f"```{contenu[:900]}```",                        inline=False)
    e.set_footer(text=_footer(f"LINK-{membre.id}", membre.guild))
    return e

# ══════════════════════════════════════════════════════════════════
#  MESSAGES
# ══════════════════════════════════════════════════════════════════

def log_message_delete(message, suppresseur=None):
    e = discord.Embed(title="🗑️ MESSAGE SUPPRIMÉ", color=0x7F8C8D, timestamp=now_utc())
    e.set_thumbnail(url=message.author.display_avatar.url)
    e.add_field(name="✍️ Auteur", value=f"{message.author.mention}\n`{message.author}` · `{message.author.id}`", inline=True)
    e.add_field(name="📍 Salon",  value=f"{message.channel.mention}\n`{message.channel.id}`",                    inline=True)
    if suppresseur and suppresseur.id != message.author.id:
        e.add_field(name="🛡️ Supprimé par", value=suppresseur.mention, inline=True)
    e.add_field(name="💬 Contenu", value=f"```{(message.content or '_vide_')[:900]}```", inline=False)
    if message.attachments:
        e.add_field(name=f"📎 Pièces jointes ({len(message.attachments)})",
                    value="\n".join(f"[{a.filename}]({a.url})" for a in message.attachments[:5]), inline=False)
    e.set_footer(text=f"Message ID : {message.id} · guild {message.guild.id}")
    return e

def log_message_edit(before, after):
    e = discord.Embed(title="✏️ MESSAGE MODIFIÉ", color=0x2980B9, timestamp=now_utc())
    e.set_thumbnail(url=before.author.display_avatar.url)
    e.add_field(name="✍️ Auteur", value=f"{before.author.mention}\n`{before.author}` · `{before.author.id}`", inline=True)
    e.add_field(name="📍 Salon",  value=f"{before.channel.mention}\n`{before.channel.id}`",                   inline=True)
    e.add_field(name="🔗 Lien",   value=f"[Aller au message]({after.jump_url})",                              inline=True)
    e.add_field(name="📝 Avant",  value=f"```{(before.content or '<vide>')[:400]}```", inline=False)
    e.add_field(name="📝 Après",  value=f"```{(after.content or '<vide>')[:400]}```",  inline=False)
    e.set_footer(text=f"Message ID : {before.id} · guild {before.guild.id}")
    return e

def log_bulk_delete(salon, messages, suppresseur=None):
    e = discord.Embed(title=f"🗑️ BULK DELETE — {len(messages)} messages", color=0xE74C3C, timestamp=now_utc())
    e.add_field(name="📍 Salon",    value=f"{salon.mention}\n`#{salon.name}`", inline=True)
    e.add_field(name="🗑️ Nombre",   value=str(len(messages)),                 inline=True)
    if suppresseur:
        e.add_field(name="🛡️ Par",  value=f"{suppresseur.mention}\n`{suppresseur.id}`", inline=True)
    auteurs: dict[int, int] = {}
    for m in messages:
        auteurs[m.author.id] = auteurs.get(m.author.id, 0) + 1
    top = sorted(auteurs.items(), key=lambda x: x[1], reverse=True)[:5]
    e.add_field(name="👥 Auteurs", value="\n".join(f"<@{uid}> · {n} msg(s)" for uid, n in top), inline=False)
    e.set_footer(text=_footer(f"BULK-{salon.id}", salon.guild))
    return e

def log_message_pin(message, pinner, action="épinglé"):
    color = 0xF1C40F if action == "épinglé" else 0x95A5A6
    e = discord.Embed(title=f"📌 MESSAGE {action.upper()}", color=color, timestamp=now_utc())
    e.add_field(name="📍 Salon", value=f"{message.channel.mention}\n`{message.channel.id}`", inline=True)
    if pinner:
        e.add_field(name="👤 Par", value=f"{pinner.mention}\n`{pinner.id}`", inline=True)
    e.add_field(name="🔗 Message", value=f"[Voir]({message.jump_url})", inline=True)
    e.set_footer(text=f"Message ID : {message.id}")
    return e

# ══════════════════════════════════════════════════════════════════
#  MEMBRES
# ══════════════════════════════════════════════════════════════════

def log_member_join(member, inviteur=None, code_invite=None):
    age = (datetime.now(timezone.utc) - member.created_at).days
    e = discord.Embed(title="📥 ARRIVÉE", color=0x2ECC71, timestamp=now_utc())
    e.set_thumbnail(url=member.display_avatar.url)
    e.add_field(name="👤 Membre",         value=f"{member.mention}\n`{member}` · `{member.id}`", inline=True)
    e.add_field(name="📅 Compte créé",    value=discord.utils.format_dt(member.created_at, "D"), inline=True)
    e.add_field(name="⏱️ Âge",            value=f"{age} jour(s)",                               inline=True)
    e.add_field(name="👥 Total membres",  value=str(member.guild.member_count),                 inline=True)
    if inviteur:
        e.add_field(name="📨 Invité par", value=f"{inviteur.mention}\n`{inviteur.id}`", inline=True)
    if code_invite:
        e.add_field(name="🔗 Code invite", value=f"`{code_invite}`", inline=True)
    e.set_footer(text=_footer(f"JOIN-{member.id}", member.guild))
    return e

def log_member_leave(member, raison="Départ volontaire", moderateur=None):
    duree = f"{(datetime.now(timezone.utc) - member.joined_at).days} jour(s)" if member.joined_at else "?"
    e = discord.Embed(title="📤 DÉPART", color=0xE74C3C, timestamp=now_utc())
    e.set_thumbnail(url=member.display_avatar.url)
    e.add_field(name="👤 Membre",            value=f"{member.mention}\n`{member}` · `{member.id}`", inline=True)
    e.add_field(name="📅 Arrivé le",          value=discord.utils.format_dt(member.joined_at, "D") if member.joined_at else "?", inline=True)
    e.add_field(name="⏳ Durée sur serveur",  value=duree, inline=True)
    e.add_field(name="👥 Total membres",     value=str(member.guild.member_count), inline=True)
    roles = [r.mention for r in reversed(member.roles) if r.name != "@everyone"]
    if roles:
        e.add_field(name=f"🎭 Rôles ({len(roles)})", value=", ".join(roles[:15]), inline=False)
    if moderateur:
        e.add_field(name="🛡️ Action par", value=f"{moderateur.mention} — `{raison}`", inline=False)
    e.set_footer(text=_footer(f"LEAVE-{member.id}", member.guild))
    return e

def log_roles_modifies(membre, ajoutes, retires, moderateur=None):
    e = discord.Embed(title="🎭 RÔLES MODIFIÉS", color=0x9B59B6, timestamp=now_utc())
    e.set_thumbnail(url=membre.display_avatar.url)
    e.add_field(name="👤 Membre", value=f"{membre.mention}\n`{membre}` · `{membre.id}`", inline=True)
    if moderateur:
        e.add_field(name="🛡️ Par", value=f"{moderateur.mention}\n`{moderateur.id}`", inline=True)
    if ajoutes:
        e.add_field(name="✅ Ajoutés",  value=", ".join(r.mention for r in ajoutes),  inline=False)
    if retires:
        e.add_field(name="❌ Retirés", value=", ".join(r.mention for r in retires), inline=False)
    e.set_footer(text=_footer(f"ROLES-{membre.id}", membre.guild))
    return e

def log_pseudo_modifie(membre, avant, apres):
    e = discord.Embed(title="📝 PSEUDO MODIFIÉ", color=0x3498DB, timestamp=now_utc())
    e.set_thumbnail(url=membre.display_avatar.url)
    e.add_field(name="👤 Membre", value=f"{membre.mention}\n`{membre}` · `{membre.id}`", inline=False)
    e.add_field(name="📝 Avant",  value=f"`{avant}`", inline=True)
    e.add_field(name="📝 Après",  value=f"`{apres}`", inline=True)
    e.set_footer(text=_footer(f"NICK-{membre.id}", membre.guild))
    return e

def log_avatar_modifie(membre, avant_url=None):
    e = discord.Embed(title="🖼️ AVATAR MODIFIÉ", color=0x1ABC9C, timestamp=now_utc())
    e.add_field(name="👤 Membre", value=f"{membre.mention}\n`{membre}` · `{membre.id}`", inline=False)
    e.set_thumbnail(url=membre.display_avatar.url)
    if avant_url:
        e.set_image(url=avant_url)
        e.add_field(name="ℹ️", value="Thumbnail = nouveau · Image = ancien", inline=False)
    e.set_footer(text=_footer(f"AVATAR-{membre.id}", membre.guild))
    return e

def log_timeout_member(mod, cible, avant, apres):
    title = "⏱️ FIN DE TIMEOUT" if apres is None else "⏱️ TIMEOUT MODIFIÉ"
    color = 0x2ECC71 if apres is None else 0xE67E22
    e = discord.Embed(title=title, color=color, timestamp=now_utc())
    e.set_thumbnail(url=cible.display_avatar.url)
    e.add_field(name="🎯 Cible",      value=f"{cible.mention}\n`{cible}` · `{cible.id}`", inline=True)
    e.add_field(name="🛡️ Modérateur", value=f"{mod.mention}\n`{mod.id}`", inline=True)
    e.add_field(name="📝 Avant", value=discord.utils.format_dt(avant, "F") if avant else "Aucun", inline=True)
    e.add_field(name="📝 Après", value=discord.utils.format_dt(apres, "F") if apres else "Levé",  inline=True)
    e.set_footer(text=_footer(f"TIMEOUT-UPD-{cible.id}", mod.guild))
    return e

# ══════════════════════════════════════════════════════════════════
#  VOCAL
# ══════════════════════════════════════════════════════════════════

def log_vocal_join(member, channel):
    e = discord.Embed(title="🔊 CONNEXION VOCALE", color=0x2ECC71, timestamp=now_utc())
    e.set_thumbnail(url=member.display_avatar.url)
    e.add_field(name="👤 Membre", value=f"{member.mention}\n`{member}` · `{member.id}`",         inline=True)
    e.add_field(name="📍 Salon",  value=f"{channel.mention}\n`{channel.name}` · `{channel.id}`", inline=True)
    e.set_footer(text=_footer(f"VC-JOIN-{member.id}", member.guild))
    return e

def log_vocal_leave(member, channel, duree_s=0):
    from bot.utils.helpers import fmt_voice
    e = discord.Embed(title="🔇 DÉCONNEXION VOCALE", color=0xE74C3C, timestamp=now_utc())
    e.set_thumbnail(url=member.display_avatar.url)
    e.add_field(name="👤 Membre",        value=f"{member.mention}\n`{member}` · `{member.id}`", inline=True)
    e.add_field(name="📍 Salon quitté",  value=f"`{channel.name}` · `{channel.id}`",           inline=True)
    if duree_s > 0:
        e.add_field(name="⏱️ Session", value=fmt_voice(duree_s), inline=True)
    e.set_footer(text=_footer(f"VC-LEAVE-{member.id}", member.guild))
    return e

def log_vocal_move(member, avant, apres, deplaceur=None):
    e = discord.Embed(title="🔄 DÉPLACEMENT VOCAL", color=0x3498DB, timestamp=now_utc())
    e.set_thumbnail(url=member.display_avatar.url)
    e.add_field(name="👤 Membre", value=f"{member.mention}\n`{member}` · `{member.id}`", inline=True)
    e.add_field(name="📤 Avant",  value=f"`{avant.name}`",                               inline=True)
    e.add_field(name="📥 Après",  value=f"{apres.mention}",                              inline=True)
    if deplaceur:
        e.add_field(name="🛡️ Déplacé par", value=f"{deplaceur.mention}\n`{deplaceur.id}`", inline=True)
    e.set_footer(text=_footer(f"VC-MOVE-{member.id}", member.guild))
    return e

def log_vocal_force_disconnect(member, channel, auteur=None):
    e = discord.Embed(title="⛔ DÉCONNEXION FORCÉE", color=0xC0392B, timestamp=now_utc())
    e.set_thumbnail(url=member.display_avatar.url)
    e.add_field(name="👤 Membre", value=f"{member.mention}\n`{member}` · `{member.id}`", inline=True)
    e.add_field(name="📍 Salon",  value=f"`{channel.name}`",                             inline=True)
    if auteur:
        e.add_field(name="🛡️ Par", value=f"{auteur.mention}\n`{auteur.id}`", inline=True)
    e.set_footer(text=_footer(f"VC-KICK-{member.id}", member.guild))
    return e

def log_vocal_state_change(member, action, channel, auteur=None):
    colors = {"Mute serveur":0xE74C3C,"Unmute serveur":0x2ECC71,"Sourd serveur":0xE74C3C,
              "Non-sourd serveur":0x2ECC71,"Self-mute":0xF39C12,"Self-unmute":0x2ECC71,
              "Self-sourd":0xF39C12,"Self-non-sourd":0x2ECC71,"Stream activé":0x9B59B6,
              "Stream désactivé":0x7F8C8D,"Caméra activée":0x1ABC9C,"Caméra désactivée":0x7F8C8D}
    icons  = {"Mute serveur":"🔇","Unmute serveur":"🔊","Sourd serveur":"🙉","Non-sourd serveur":"👂",
              "Self-mute":"🔕","Self-unmute":"🔔","Self-sourd":"🙉","Self-non-sourd":"👂",
              "Stream activé":"📺","Stream désactivé":"📺","Caméra activée":"📷","Caméra désactivée":"📷"}
    icon = icons.get(action, "🎙️")
    e = discord.Embed(title=f"{icon} {action.upper()}", color=colors.get(action, 0x95A5A6), timestamp=now_utc())
    e.set_thumbnail(url=member.display_avatar.url)
    e.add_field(name="👤 Membre", value=f"{member.mention}\n`{member}` · `{member.id}`", inline=True)
    e.add_field(name="📍 Salon",  value=f"`{channel.name}`",                             inline=True)
    if auteur:
        e.add_field(name="🛡️ Par", value=f"{auteur.mention}\n`{auteur.id}`", inline=True)
    e.set_footer(text=_footer(f"VC-STATE-{member.id}", member.guild))
    return e

def log_vocal_inactivity(member, channel, delay_min):
    e = discord.Embed(title="🔇 EXPULSION — Inactivité vocale", color=0xE67E22, timestamp=now_utc())
    e.set_thumbnail(url=member.display_avatar.url)
    e.add_field(name="👤 Utilisateur", value=f"{member.mention}\n`{member}` · `{member.id}`",         inline=True)
    e.add_field(name="🔊 Salon vocal", value=f"{channel.mention}\n`{channel.name}` · `{channel.id}`", inline=True)
    e.add_field(name="⏱️ Inactivité",  value=f"**{int(delay_min)} min**",                             inline=True)
    e.add_field(name="⚡ Action",      value="Déconnexion automatique",                               inline=False)
    e.set_footer(text=_footer(f"VOCAL-INACT-{member.id}", member.guild))
    return e

# ══════════════════════════════════════════════════════════════════
#  RÔLES
# ══════════════════════════════════════════════════════════════════

def log_role_create(role, createur=None):
    e = discord.Embed(title="✅ RÔLE CRÉÉ", color=role.color.value or 0x2ECC71, timestamp=now_utc())
    e.add_field(name="🎭 Rôle",       value=f"{role.mention}\n`{role.name}` · `{role.id}`", inline=True)
    if createur:
        e.add_field(name="👤 Par",    value=f"{createur.mention}\n`{createur.id}`",          inline=True)
    e.add_field(name="🎨 Couleur",    value=str(role.color),                                 inline=True)
    e.add_field(name="📌 Hoistable",  value="✅" if role.hoist else "❌",                    inline=True)
    e.add_field(name="🏷️ Mentionnable", value="✅" if role.mentionable else "❌",             inline=True)
    e.set_footer(text=_footer(f"ROLE-CREATE-{role.id}", role.guild))
    return e

def log_role_delete(role, suppresseur=None):
    e = discord.Embed(title="❌ RÔLE SUPPRIMÉ", color=0xE74C3C, timestamp=now_utc())
    e.add_field(name="🎭 Rôle", value=f"`{role.name}` · `{role.id}`", inline=True)
    if suppresseur:
        e.add_field(name="👤 Par", value=f"{suppresseur.mention}\n`{suppresseur.id}`", inline=True)
    e.set_footer(text=_footer(f"ROLE-DEL-{role.id}", role.guild))
    return e

def log_role_update(avant, apres, auteur=None):
    changes = []
    if avant.name != apres.name:
        changes.append(f"**Nom :** `{avant.name}` → `{apres.name}`")
    if avant.color != apres.color:
        changes.append(f"**Couleur :** `{avant.color}` → `{apres.color}`")
    if avant.hoist != apres.hoist:
        changes.append(f"**Hoistable :** `{avant.hoist}` → `{apres.hoist}`")
    if avant.mentionable != apres.mentionable:
        changes.append(f"**Mentionnable :** `{avant.mentionable}` → `{apres.mentionable}`")
    if avant.permissions != apres.permissions:
        added   = [p for p, v in apres.permissions  if v and not getattr(avant.permissions, p, False)]
        removed = [p for p, v in avant.permissions  if v and not getattr(apres.permissions, p, False)]
        if added:   changes.append(f"**Perms ajoutées :** {', '.join(added[:8])}")
        if removed: changes.append(f"**Perms retirées :** {', '.join(removed[:8])}")
    e = discord.Embed(title="✏️ RÔLE MODIFIÉ", color=apres.color.value or 0x9B59B6, timestamp=now_utc())
    e.add_field(name="🎭 Rôle",         value=f"{apres.mention}\n`{apres.name}` · `{apres.id}`", inline=True)
    if auteur:
        e.add_field(name="👤 Par",      value=f"{auteur.mention}\n`{auteur.id}`",                inline=True)
    e.add_field(name="📝 Changements",  value="\n".join(changes) or "_Aucun détecté_",           inline=False)
    e.set_footer(text=_footer(f"ROLE-UPD-{apres.id}", apres.guild))
    return e

# ══════════════════════════════════════════════════════════════════
#  SALONS / CATÉGORIES
# ══════════════════════════════════════════════════════════════════

def log_channel_create(channel, auteur=None):
    e = discord.Embed(title="📢 SALON CRÉÉ", color=0x2ECC71, timestamp=now_utc())
    e.add_field(name="📍 Nom",       value=f"`{channel.name}` · `{channel.id}`",                       inline=True)
    e.add_field(name="📂 Type",      value=str(channel.type),                                          inline=True)
    e.add_field(name="🗂️ Catégorie", value=channel.category.name if channel.category else "Aucune",   inline=True)
    if auteur:
        e.add_field(name="👤 Créé par", value=f"{auteur.mention}\n`{auteur.id}`", inline=True)
    e.set_footer(text=_footer(f"CH-CREATE-{channel.id}", channel.guild))
    return e

def log_channel_delete(channel, auteur=None):
    e = discord.Embed(title="🗑️ SALON SUPPRIMÉ", color=0xE74C3C, timestamp=now_utc())
    e.add_field(name="📍 Nom",       value=f"`{channel.name}` · `{channel.id}`",                       inline=True)
    e.add_field(name="📂 Type",      value=str(channel.type),                                          inline=True)
    e.add_field(name="🗂️ Catégorie", value=channel.category.name if channel.category else "Aucune",   inline=True)
    if auteur:
        e.add_field(name="👤 Supprimé par", value=f"{auteur.mention}\n`{auteur.id}`", inline=True)
    e.set_footer(text=_footer(f"CH-DEL-{channel.id}", channel.guild))
    return e

def log_channel_update(avant, apres, auteur=None):
    changes = []
    if avant.name != apres.name:
        changes.append(f"**Nom :** `{avant.name}` → `{apres.name}`")
    if hasattr(avant, "topic") and avant.topic != apres.topic:
        changes.append(f"**Topic :** `{avant.topic}` → `{apres.topic}`")
    if hasattr(avant, "slowmode_delay") and avant.slowmode_delay != apres.slowmode_delay:
        changes.append(f"**Slowmode :** `{avant.slowmode_delay}s` → `{apres.slowmode_delay}s`")
    if hasattr(avant, "nsfw") and avant.nsfw != apres.nsfw:
        changes.append(f"**NSFW :** `{avant.nsfw}` → `{apres.nsfw}`")
    if hasattr(avant, "bitrate") and avant.bitrate != apres.bitrate:
        changes.append(f"**Bitrate :** `{avant.bitrate}` → `{apres.bitrate}`")
    if hasattr(avant, "user_limit") and avant.user_limit != apres.user_limit:
        changes.append(f"**Limite users :** `{avant.user_limit}` → `{apres.user_limit}`")
    if avant.category != apres.category:
        av = avant.category.name if avant.category else "Aucune"
        ap = apres.category.name if apres.category else "Aucune"
        changes.append(f"**Catégorie :** `{av}` → `{ap}`")
    e = discord.Embed(title="✏️ SALON MODIFIÉ", color=0x3498DB, timestamp=now_utc())
    e.add_field(name="📍 Salon",       value=f"`{apres.name}` · `{apres.id}`",  inline=True)
    if auteur:
        e.add_field(name="👤 Par",     value=f"{auteur.mention}\n`{auteur.id}`", inline=True)
    e.add_field(name="📝 Changements", value="\n".join(changes) or "_Aucun_",   inline=False)
    e.set_footer(text=_footer(f"CH-UPD-{apres.id}", apres.guild))
    return e

# ══════════════════════════════════════════════════════════════════
#  EMOJIS / STICKERS
# ══════════════════════════════════════════════════════════════════

def log_emoji(action, emoji, auteur=None):
    color = {"créé":0x2ECC71,"supprimé":0xE74C3C,"modifié":0x3498DB}.get(action, 0x95A5A6)
    e = discord.Embed(title=f"😀 EMOJI {action.upper()}", color=color, timestamp=now_utc())
    e.set_thumbnail(url=emoji.url)
    e.add_field(name="😀 Emoji", value=f"`:{emoji.name}:` · `{emoji.id}`", inline=True)
    if auteur:
        e.add_field(name="👤 Par", value=f"{auteur.mention}\n`{auteur.id}`", inline=True)
    e.set_footer(text=_footer(f"EMOJI-{emoji.id}", emoji.guild))
    return e

def log_sticker(action, sticker, auteur=None):
    color = {"créé":0x2ECC71,"supprimé":0xE74C3C,"modifié":0x3498DB}.get(action, 0x95A5A6)
    e = discord.Embed(title=f"🎨 STICKER {action.upper()}", color=color, timestamp=now_utc())
    e.add_field(name="🎨 Sticker",     value=f"`{sticker.name}` · `{sticker.id}`", inline=True)
    e.add_field(name="📝 Description", value=sticker.description or "_vide_",      inline=True)
    if auteur:
        e.add_field(name="👤 Par", value=f"{auteur.mention}\n`{auteur.id}`", inline=True)
    e.set_footer(text=_footer(f"STICKER-{sticker.id}", sticker.guild))
    return e

# ══════════════════════════════════════════════════════════════════
#  WEBHOOKS / INVITATIONS
# ══════════════════════════════════════════════════════════════════

def log_webhook(action, guild, name, channel_name, auteur=None):
    color = {"créé":0x2ECC71,"supprimé":0xE74C3C,"modifié":0x3498DB}.get(action, 0x95A5A6)
    e = discord.Embed(title=f"🔗 WEBHOOK {action.upper()}", color=color, timestamp=now_utc())
    e.add_field(name="🔗 Nom",   value=f"`{name}`",          inline=True)
    e.add_field(name="📍 Salon", value=f"`#{channel_name}`", inline=True)
    if auteur:
        e.add_field(name="👤 Par", value=f"{auteur.mention}\n`{auteur.id}`", inline=True)
    e.set_footer(text=_footer(f"WH-{action.upper()}", guild))
    return e

def log_invite(action, invite, auteur=None):
    color = {"créée":0x2ECC71,"supprimée":0xE74C3C}.get(action, 0x95A5A6)
    e = discord.Embed(title=f"📨 INVITATION {action.upper()}", color=color, timestamp=now_utc())
    e.add_field(name="🔗 Code",          value=f"`{invite.code}`",                              inline=True)
    e.add_field(name="📍 Salon",         value=f"`#{invite.channel.name}`" if invite.channel else "?", inline=True)
    e.add_field(name="🔢 Utilisations",  value=str(invite.uses or 0),                          inline=True)
    e.add_field(name="⌛ Max",           value=str(invite.max_uses or "∞"),                    inline=True)
    if invite.max_age:
        e.add_field(name="⏳ Expiration", value=f"{invite.max_age // 3600}h",                  inline=True)
    if auteur:
        e.add_field(name="👤 Par",       value=f"{auteur.mention}\n`{auteur.id}`",             inline=True)
    e.set_footer(text=_footer(f"INVITE-{invite.code}", invite.guild))
    return e

# ══════════════════════════════════════════════════════════════════
#  SERVEUR
# ══════════════════════════════════════════════════════════════════

def log_guild_update(avant, apres, auteur=None):
    changes = []
    if avant.name != apres.name:
        changes.append(f"**Nom :** `{avant.name}` → `{apres.name}`")
    if avant.icon != apres.icon:
        changes.append("**Icône modifiée**")
    if avant.banner != apres.banner:
        changes.append("**Bannière modifiée**")
    if avant.verification_level != apres.verification_level:
        changes.append(f"**Vérification :** `{avant.verification_level}` → `{apres.verification_level}`")
    if avant.afk_channel != apres.afk_channel:
        av = avant.afk_channel.name if avant.afk_channel else "Aucun"
        ap = apres.afk_channel.name if apres.afk_channel else "Aucun"
        changes.append(f"**AFK :** `{av}` → `{ap}`")
    if avant.owner != apres.owner:
        changes.append(f"**Propriétaire :** `{avant.owner}` → `{apres.owner}`")
    e = discord.Embed(title="⚙️ SERVEUR MODIFIÉ", color=0x9B59B6, timestamp=now_utc())
    if apres.icon:
        e.set_thumbnail(url=apres.icon.url)
    if auteur:
        e.add_field(name="👤 Par", value=f"{auteur.mention}\n`{auteur.id}`", inline=True)
    e.add_field(name="📝 Changements", value="\n".join(changes) or "_Aucun_", inline=False)
    e.set_footer(text=_footer("GUILD-UPD", apres))
    return e

# ══════════════════════════════════════════════════════════════════
#  SÉCURITÉ
# ══════════════════════════════════════════════════════════════════

def log_security_alert(guild, titre, desc, auteur=None):
    e = discord.Embed(title=f"🚨 ALERTE SÉCURITÉ — {titre}", description=desc,
                      color=0xFF0000, timestamp=now_utc())
    if auteur:
        e.add_field(name="👤 Auteur suspecté", value=f"{auteur.mention}\n`{auteur.id}`", inline=True)
    e.set_footer(text=_footer("SECURITY", guild))
    return e

def log_dangerous_perm(membre, role, perms):
    e = discord.Embed(title="⚠️ PERMISSION DANGEREUSE ATTRIBUÉE", color=0xFF6B00, timestamp=now_utc())
    e.set_thumbnail(url=membre.display_avatar.url)
    e.add_field(name="👤 Membre",      value=f"{membre.mention}\n`{membre}` · `{membre.id}`", inline=True)
    e.add_field(name="🎭 Via le rôle", value=f"{role.mention}\n`{role.name}`",                inline=True)
    e.add_field(name="⚠️ Permissions", value="\n".join(f"• `{p}`" for p in perms),           inline=False)
    e.set_footer(text=_footer(f"DANGPERM-{membre.id}", membre.guild))
    return e