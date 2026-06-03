"""
events/member_remove.py — Départ d'un membre.

CORRECTIONS v2 :
  - Log ultra-précis : durée passée sur le serveur, rôles qu'il avait,
    distinction départ volontaire / kick / ban (via audit log Discord).
"""
import discord

from bot.core import bot
from bot.utils.logs import send_log, log_member_leave


@bot.event
async def on_member_remove(member: discord.Member):
    # Màj des récompenses d'invitation
    try:
        from bot.utils.invite_rewards import on_invite_chain_update
        await on_invite_chain_update(member.guild, member.id)
    except Exception as e:
        print(f"[INVITE_REWARDS] Erreur après leave pour {member.name} : {e}")

    # Tenter de détecter si c'est un kick ou un ban via l'audit log
    raison     = "Départ volontaire"
    moderateur = None
    try:
        # On lit les 5 dernières entrées de l'audit log pour trouver un kick/ban récent
        async for entry in member.guild.audit_logs(limit=5):
            if entry.target and entry.target.id == member.id:
                if entry.action == discord.AuditLogAction.kick:
                    raison     = f"Kick — {entry.reason or 'Aucune raison fournie'}"
                    moderateur = entry.user
                elif entry.action == discord.AuditLogAction.ban:
                    raison     = f"Ban — {entry.reason or 'Aucune raison fournie'}"
                    moderateur = entry.user
                break
    except discord.Forbidden:
        pass   # Pas la permission de lire l'audit log — on reste sur "Départ volontaire"
    except Exception as e:
        print(f"[LEAVE] Erreur lecture audit log : {e}")

    await send_log(member.guild, log_member_leave(member, raison, moderateur))