"""
events/member_update.py — Modification d'un membre (rôles, pseudo).

CORRECTIONS v2 :
  - Utilise les helpers log_roles_modifies() et log_pseudo_modifie()
    pour des logs ultra-précis (mention + ID + avant/après).
"""
import discord

from bot.core import bot
from bot.utils.config import load_config, cfg_channel
from bot.utils.embeds import build_roster_embed
from bot.utils.logs import send_log, log_roles_modifies, log_pseudo_modifie


@bot.event
async def on_member_update(before: discord.Member, after: discord.Member):
    cfg = load_config(after.guild.id)

    # ── Mise à jour du roster si un rôle faction change ──────────────────────
    roster_cfg   = cfg.get("roster_roles", [])
    roster_names = {entry["nom"].lower() for entry in roster_cfg}
    before_roster = {r.name.lower() for r in before.roles if r.name.lower() in roster_names}
    after_roster  = {r.name.lower() for r in after.roles  if r.name.lower() in roster_names}
    if before_roster != after_roster:
        channel = cfg_channel(after.guild, "salon_roster")
        if channel:
            try:
                embed = build_roster_embed(after.guild)
                async for msg in channel.history(limit=20):
                    if msg.author == bot.user and msg.embeds:
                        await msg.edit(embed=embed)
                        break
                else:
                    await channel.send(embed=embed)
            except Exception:
                pass

    # ── Log des changements de rôles ─────────────────────────────────────────
    added   = set(after.roles) - set(before.roles)
    removed = set(before.roles) - set(after.roles)
    if added or removed:
        # Tenter de trouver qui a modifié les rôles via l'audit log
        moderateur = None
        try:
            async for entry in after.guild.audit_logs(limit=3, action=discord.AuditLogAction.member_role_update):
                if entry.target and entry.target.id == after.id:
                    moderateur = entry.user
                    break
        except Exception:
            pass
        await send_log(after.guild, log_roles_modifies(after, added, removed, moderateur))

    # ── Log du changement de pseudo ───────────────────────────────────────────
    if before.display_name != after.display_name:
        await send_log(after.guild, log_pseudo_modifie(after, before.display_name, after.display_name))