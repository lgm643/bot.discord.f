"""
utils/indispo_loop.py — Boucle qui retire automatiquement les indisponibilités
expirées (date de fin dépassée) et rafraîchit l'embed épinglé en conséquence.
"""
import asyncio
import time

from bot.utils.database import db_get_expired_indispos, db_delete_indispo
from bot.utils.indispo import refresh_indispo_embed

CHECK_INTERVAL = 900  # 15 minutes


async def _check_guild(guild):
    now = time.time()
    expired = db_get_expired_indispos(guild.id, now)
    if not expired:
        return
    for row in expired:
        db_delete_indispo(guild.id, row["user_id"])
        print(f"[INDISPO] Indisponibilité expirée retirée : user={row['user_id']} guild={guild.id}")
    await refresh_indispo_embed(guild)


async def indispo_expiration_loop(bot):
    await bot.wait_until_ready()
    while True:
        try:
            for guild in bot.guilds:
                await _check_guild(guild)
        except Exception as e:
            print(f"[INDISPO] Erreur boucle expiration : {e}")
        await asyncio.sleep(CHECK_INTERVAL)
