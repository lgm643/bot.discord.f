"""
utils/permissions.py — Vérification des permissions membres.

CORRECTIONS v2 :
  [1] SÉCURITÉ CRITIQUE — Élévation de privilèges via nom de rôle corrigée.
      is_vendeur() et is_staff_market() utilisent désormais resolve_role() qui
      cherche d'abord par ID Discord (int), puis par nom en fallback. Stocker
      l'ID dans la config (ex: "role_vendeur": 123456789) est désormais la
      méthode recommandée et la seule réellement sécurisée.

      Pourquoi c'était dangereux : si la config stockait "Vendeur Certifié"
      (une chaîne de caractères), n'importe quel administrateur pouvait créer
      un rôle Discord portant exactement ce nom, l'attribuer à qui il voulait
      et contourner entièrement le système de permissions sans toucher à la
      config. resolve_role() cherche maintenant en priorité par ID.

  [2] Ajout de warnings logs quand la résolution se fait par nom (fallback
      non sécurisé) pour alerter l'administrateur du bot.

  [3] is_staff() reste inchangé : guild_permissions.administrator est natif
      Discord et ne peut pas être contourné par nom.
"""
import discord

from bot.utils.config import load_config, resolve_role, resolve_roles


def _warn_name_fallback(guild: discord.Guild, cfg_key: str, value):
    """Log un avertissement si la config utilise un nom au lieu d'un ID."""
    if value and not _is_id(value):
        print(
            f"[SECURITY] ⚠️  guild={guild.id} — `{cfg_key}` utilise un nom "
            f"(`{value}`) au lieu d'un ID Discord. "
            f"Risque d'élévation de privilèges. "
            f"Remplacez par l'ID numérique du rôle dans !config."
        )


def _is_id(value) -> bool:
    """Retourne True si la valeur ressemble à un ID Discord (entier ou chaîne numérique)."""
    try:
        int(value)
        return True
    except (ValueError, TypeError):
        return False


def is_staff(member: discord.Member) -> bool:
    """
    Vérifie si le membre est staff.
    Priorité : permission Discord administrator (impossible à contourner) →
    puis rôles staff définis dans la config (par ID de préférence).
    """
    if member.guild_permissions.administrator:
        return True
    cfg = load_config(member.guild.id)
    staff_names = cfg.get("role_staff", [])
    if isinstance(staff_names, (str, int)):
        staff_names = [staff_names]
    for val in staff_names:
        _warn_name_fallback(member.guild, "role_staff", val)
    return any(r in member.roles for r in resolve_roles(member.guild, staff_names))


def is_staff_market(member: discord.Member) -> bool:
    """
    Vérifie si le membre est staff market ou vendeur.
    Résolution par ID en priorité (sécurisé), nom en fallback (avec warning).
    """
    cfg = load_config(member.guild.id)

    staff_market_val = cfg.get("role_staff_market")
    vendeur_val      = cfg.get("role_vendeur")

    _warn_name_fallback(member.guild, "role_staff_market", staff_market_val)
    _warn_name_fallback(member.guild, "role_vendeur", vendeur_val)

    role_sm  = resolve_role(member.guild, staff_market_val)
    role_v   = resolve_role(member.guild, vendeur_val)

    if role_sm and role_sm in member.roles:
        return True
    if role_v and role_v in member.roles:
        return True
    return is_staff(member)


def is_vendeur(member: discord.Member) -> bool:
    """
    Vérifie si le membre est vendeur certifié.
    Résolution par ID en priorité (sécurisé), nom en fallback (avec warning).
    """
    cfg = load_config(member.guild.id)
    vendeur_val = cfg.get("role_vendeur")
    _warn_name_fallback(member.guild, "role_vendeur", vendeur_val)
    role = resolve_role(member.guild, vendeur_val)
    return (role and role in member.roles) or is_staff(member)