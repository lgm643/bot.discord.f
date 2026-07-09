"""
utils/indispo.py — Système d'indisponibilités.

Parsing de dates françaises en texte libre ("lundi 25 juillet", "25/07", "3 août"),
construction de l'embed persistant, et helpers de rafraîchissement.
"""
import re
import time
import unicodedata
from datetime import datetime, timezone

import discord

from bot.core import bot
from bot.utils.config import cfg_channel
from bot.utils.helpers import now_utc
from bot.utils.database import (
    db_get_indispos, db_get_indispo_embed, db_save_indispo_embed,
)

_MOIS = {
    "janvier": 1, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
    "juillet": 7, "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11, "decembre": 12,
}


def _strip_accents(txt: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", txt) if unicodedata.category(c) != "Mn")


def parse_date_fr(texte: str):
    """
    Essaie d'extraire une date d'un texte libre français.
    Retourne un timestamp UTC (fin de journée, 23:59) ou None si non reconnu.
    Supporte : "lundi 25 juillet", "25 juillet 2026", "25/07", "25-07-2026"...
    """
    if not texte:
        return None
    txt = _strip_accents(texte.lower().strip())

    # Format JJ/MM ou JJ-MM(-AAAA)
    m = re.search(r"\b(\d{1,2})[/\-](\d{1,2})(?:[/\-](\d{2,4}))?\b", txt)
    if m:
        jour, mois = int(m.group(1)), int(m.group(2))
        annee = int(m.group(3)) if m.group(3) else datetime.now(timezone.utc).year
        if annee < 100:
            annee += 2000
        return _build_ts(jour, mois, annee)

    # Format "25 juillet" ou "25 juillet 2026"
    m = re.search(r"\b(\d{1,2})\s+([a-z]+)(?:\s+(\d{4}))?\b", txt)
    if m:
        jour = int(m.group(1))
        mois_nom = m.group(2)
        mois = _MOIS.get(mois_nom)
        if mois:
            annee = int(m.group(3)) if m.group(3) else datetime.now(timezone.utc).year
            return _build_ts(jour, mois, annee)

    return None


def _build_ts(jour: int, mois: int, annee: int):
    try:
        dt = datetime(annee, mois, jour, 23, 59, 0, tzinfo=timezone.utc)
    except ValueError:
        return None
    now = datetime.now(timezone.utc)
    # Si la date est déjà passée cette année (sans année précisée), on suppose l'année prochaine
    if dt < now:
        try:
            dt = dt.replace(year=annee + 1)
        except ValueError:
            return None
    return dt.timestamp()


def build_indispo_embed(guild: discord.Guild) -> discord.Embed:
    rows  = db_get_indispos(guild.id)
    embed = discord.Embed(title="🚫 Indisponibilités en cours", color=0xE67E22, timestamp=now_utc())
    if not rows:
        embed.description = "_Aucune indisponibilité en cours._\nUtilise `!indispo` pour te déclarer indisponible."
    else:
        for row in rows:
            member = guild.get_member(row["user_id"])
            nom = member.display_name if member else f"Membre parti (`{row['user_id']}`)"
            valeur = (
                f"➤ **Date de début :** {row['date_debut_txt']}\n"
                f"➤ **Date de fin :** {row['date_fin_txt']}\n"
                f"➤ **Raison :** {row['raison']}\n"
                f"➤ **Disponibilité partielle ?** {row['partielle']}\n"
                f"➤ **Présence Discord possible ?** {row['presence_discord']}"
            )
            embed.add_field(name=f"👤 {nom}", value=valeur, inline=False)
    embed.set_footer(text=f"{len(rows)} indisponibilité(s) en cours · Se retire automatiquement à la date de fin")
    return embed


async def refresh_indispo_embed(guild: discord.Guild):
    channel = cfg_channel(guild, "salon_indispos")
    if not channel:
        return
    embed = build_indispo_embed(guild)
    row = db_get_indispo_embed(guild.id)
    if row and row["msg_id"]:
        try:
            msg = await channel.fetch_message(row["msg_id"])
            await msg.edit(embed=embed)
            return
        except Exception:
            pass
    try:
        msg = await channel.send(embed=embed)
        try:
            await msg.pin(reason="Embed indisponibilités")
        except Exception:
            pass
        db_save_indispo_embed(guild.id, channel.id, msg.id)
    except Exception as e:
        print(f"[INDISPO] Erreur post embed : {e}")
