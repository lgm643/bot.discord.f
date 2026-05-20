"""Lecture seule des stats d'invitations (même source que !invite)."""
from bot.utils.database import get_db
from bot.utils.invites import db_get_invitations


def count_invitations(guild, inviter_id: int) -> int:
    """Nombre total d'entrées en base (identique au total affiché par !invite)."""
    return len(db_get_invitations(guild.id, inviter_id))


def count_active_invitations(guild, inviter_id: int) -> int:
    """Membres invités encore présents sur le serveur (✅ dans !invite)."""
    rows = db_get_invitations(guild.id, inviter_id)
    return sum(1 for inv in rows if guild.get_member(inv["invited_id"]))


def db_get_inviter_for_member(guild_id: int, invited_id: int) -> int | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT inviter_id FROM invitations WHERE guild_id=? AND invited_id=? "
            "ORDER BY joined_at DESC LIMIT 1",
            (guild_id, invited_id),
        ).fetchone()
    return int(row["inviter_id"]) if row else None


def get_distinct_inviter_ids(guild_id: int) -> list[int]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT DISTINCT inviter_id FROM invitations WHERE guild_id=?",
            (guild_id,),
        ).fetchall()
    return [int(r["inviter_id"]) for r in rows]


def get_top_inviters_active(guild, limit: int = 10) -> list[tuple[int, int]]:
    """[(inviter_id, invitations_actives), ...] trié décroissant."""
    ranked = []
    for inviter_id in get_distinct_inviter_ids(guild.id):
        active = count_active_invitations(guild, inviter_id)
        if active > 0:
            ranked.append((inviter_id, active))
    ranked.sort(key=lambda x: x[1], reverse=True)
    return ranked[:limit]
