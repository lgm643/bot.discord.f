"""
utils/ticket_relance.py — Boucle qui détecte les tickets recrutement restés
sans réponse d'un recruteur/staff depuis plus de X heures, et poste
automatiquement le bouton "🔄 Relancer les recruteurs" (une seule fois par
période, pour éviter le spam).
"""
import asyncio
import time

import discord

from bot.utils.database import db_get_open_tickets, db_update_ticket_relance, db_delete_ticket_meta
from bot.utils.config import load_config, cfg_role, cfg_roles

CHECK_INTERVAL = 900  # 15 minutes


def _est_reponse_staff(message: discord.Message, recruteur_role, staff_roles) -> bool:
    """True si le dernier message vient d'un recruteur/staff (donc le ticket a déjà une réponse)."""
    if message is None or message.author.bot:
        return False
    author_roles = getattr(message.author, "roles", [])
    if recruteur_role and recruteur_role in author_roles:
        return True
    return any(r in author_roles for r in staff_roles)


async def _check_guild(guild: discord.Guild):
    cfg           = load_config(guild.id)
    seuil_heures  = cfg.get("relance_ticket_heures", 2)
    if not seuil_heures or seuil_heures <= 0:
        return  # relance désactivée si 0
    seuil_secs    = seuil_heures * 3600
    recruteur     = cfg_role(guild, "role_recruteur")
    staff_roles   = cfg_roles(guild, "role_staff")

    rows = db_get_open_tickets(guild.id, type_ticket="recrutement")
    now  = time.time()

    for row in rows:
        channel_id      = row["channel_id"]
        created_at      = row["created_at"]
        last_relance_at = row["last_relance_at"] or 0

        channel = guild.get_channel(channel_id) or guild.get_thread(channel_id)
        if channel is None:
            # Ticket fermé/supprimé sans passer par !fermer -> on nettoie
            db_delete_ticket_meta(channel_id)
            continue

        derniere_action = max(created_at, last_relance_at)
        if now - derniere_action < seuil_secs:
            continue  # pas encore assez vieux depuis la création ou la dernière relance

        try:
            dernier_message = None
            async for m in channel.history(limit=1):
                dernier_message = m
        except Exception:
            continue

        if _est_reponse_staff(dernier_message, recruteur, staff_roles):
            continue  # déjà répondu, rien à faire

        # Sans réponse depuis trop longtemps -> on propose la relance
        from bot.views.ticket_view import RelanceRecruteurView
        ping = recruteur.mention if recruteur else (" ".join(r.mention for r in staff_roles) or "@Staff")
        embed = discord.Embed(
            title="⏰ Toujours sans réponse",
            description=(
                f"Ce ticket de recrutement est ouvert depuis plus de **{seuil_heures}h** "
                f"sans réponse de {ping}.\n\nClique ci-dessous pour relancer."
            ),
            color=0xE67E22,
        )
        try:
            # Le ping doit être dans le "content" pour déclencher une vraie notif :
            # un mention placé uniquement dans un embed ne notifie jamais personne.
            await channel.send(
                content=ping,
                embed=embed,
                view=RelanceRecruteurView(),
                allowed_mentions=discord.AllowedMentions(roles=True, users=False, everyone=False),
            )
            db_update_ticket_relance(channel_id, now)
        except Exception as e:
            print(f"[TICKET-RELANCE] Erreur envoi relance ({channel_id}) : {e}")


async def ticket_relance_loop(bot):
    await bot.wait_until_ready()
    while True:
        try:
            for guild in bot.guilds:
                await _check_guild(guild)
        except Exception as e:
            print(f"[TICKET-RELANCE] Erreur boucle : {e}")
        await asyncio.sleep(CHECK_INTERVAL)