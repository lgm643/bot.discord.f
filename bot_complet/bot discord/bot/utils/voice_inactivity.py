"""
utils/voice_inactivity.py — Système avancé de gestion de l'inactivité vocale.

Fonctionnement :
  - Une tâche asyncio tourne toutes les 30s et vérifie chaque membre vocal.
  - L'inactivité est détectée via les flags Discord : self_mute, self_deaf,
    suppress (stage), ainsi que l'absence de stream/caméra.
  - Un compteur _last_activity[guild_id][member_id] est remis à jour dès
    qu'une activité est détectée (parole, caméra, stream, changement de salon).
  - Exemptions : salons exclus, rôles exclus, membres exclus (tous configurables).
  - Anti double-expulsion : _pending_disconnect empêche deux déconnexions simultanées.
  - Robustesse : vérifie les permissions avant d'agir, log les erreurs en debug.

Configuration dans !config (groupe 🎙️ Inactivité Vocale) :
  vocal_inactivity_enabled     : bool  (0/1)
  vocal_inactivity_delay       : int   minutes avant expulsion
  vocal_inactivity_exempt_channels : list  IDs/noms salons exclus
  vocal_inactivity_exempt_roles    : list  IDs/noms rôles exclus
  vocal_inactivity_exempt_users    : list  IDs membres exclus
  salon_logs_vocal_inactivity  : str   salon de logs dédié (ou fallback salon_logs)
"""
import asyncio
import time
from datetime import datetime, timezone

import discord

from bot.utils.config import load_config, resolve_channel, resolve_role
from bot.utils.helpers import now_utc

# ── État en mémoire ───────────────────────────────────────────────────────────
# {guild_id: {member_id: timestamp_derniere_activite}}
_last_activity:       dict[int, dict[int, float]] = {}

# Membres en cours de déconnexion (anti double-expulsion)
_pending_disconnect:  dict[int, set[int]]          = {}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_active(member: discord.Member) -> bool:
    """
    Retourne True si le membre montre une activité vocale détectable :
    - Pas muté (ni self_mute ni supprimé par le serveur)
    - Pas sourd (self_deaf)
    - Caméra ou stream actif
    Discord ne expose pas le niveau audio en temps réel via l'API bot,
    donc on se base sur ces flags comme proxy fiable de présence active.
    """
    vs = member.voice
    if not vs:
        return False
    # Flux vidéo ou screen-share = actif
    if vs.self_video or vs.self_stream:
        return True
    # Non muté ET non sourd = potentiellement en train de parler
    if not vs.self_mute and not vs.self_deaf and not vs.suppress:
        return True
    return False


def _get_delay_seconds(cfg: dict) -> float:
    """Retourne le délai d'inactivité en secondes depuis la config (en minutes)."""
    minutes = cfg.get("vocal_inactivity_delay", 15)
    try:
        minutes = float(minutes)
    except (ValueError, TypeError):
        minutes = 15.0
    return max(1.0, minutes) * 60.0


def _is_exempt(member: discord.Member, channel: discord.VoiceChannel, cfg: dict) -> bool:
    """Retourne True si le membre est exempté de l'expulsion."""
    # Exemption par salon
    exempt_channels = cfg.get("vocal_inactivity_exempt_channels", [])
    if isinstance(exempt_channels, (str, int)):
        exempt_channels = [exempt_channels]
    for val in exempt_channels:
        ch = resolve_channel(member.guild, val)
        if ch and ch.id == channel.id:
            return True

    # Exemption par rôle
    exempt_roles = cfg.get("vocal_inactivity_exempt_roles", [])
    if isinstance(exempt_roles, (str, int)):
        exempt_roles = [exempt_roles]
    for val in exempt_roles:
        role = resolve_role(member.guild, val)
        if role and role in member.roles:
            return True

    # Exemption par utilisateur
    exempt_users = cfg.get("vocal_inactivity_exempt_users", [])
    if isinstance(exempt_users, (str, int)):
        exempt_users = [exempt_users]
    for val in exempt_users:
        try:
            if int(val) == member.id:
                return True
        except (ValueError, TypeError):
            pass

    return False


async def _get_inactivity_log_channel(guild: discord.Guild, cfg: dict) -> discord.TextChannel | None:
    """Retourne le salon de logs dédié à l'inactivité, ou le salon_logs principal."""
    dedicated = cfg.get("salon_logs_vocal_inactivity")
    if dedicated:
        ch = resolve_channel(guild, dedicated)
        if ch:
            return ch
    # Fallback sur le salon_logs principal
    fallback = resolve_channel(guild, cfg.get("salon_logs"))
    return fallback


def _build_inactivity_log_embed(
    member: discord.Member,
    channel: discord.VoiceChannel,
    delay_minutes: float,
) -> discord.Embed:
    """Construit l'embed de log d'expulsion pour inactivité vocale."""
    embed = discord.Embed(
        title="🔇 Expulsion pour inactivité vocale",
        color=0xE67E22,
        timestamp=now_utc(),
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(
        name="👤 Utilisateur",
        value=f"{member.mention}\n`{member}` — ID `{member.id}`",
        inline=True,
    )
    embed.add_field(
        name="🔊 Salon vocal",
        value=f"{channel.mention}\n`{channel.name}` — ID `{channel.id}`",
        inline=True,
    )
    embed.add_field(
        name="⏱️ Temps d'inactivité atteint",
        value=f"**{int(delay_minutes)} minute(s)**",
        inline=True,
    )
    embed.add_field(
        name="⚡ Action",
        value="Déconnexion automatique du salon vocal",
        inline=False,
    )
    embed.set_footer(text=f"Système inactivité vocale · ID : VOCAL-INACT-{member.id}")
    return embed


# ── Mise à jour de l'activité (appelée depuis on_voice_state_update) ──────────

def record_voice_activity(guild_id: int, member_id: int):
    """Remet le compteur d'inactivité à zéro pour ce membre."""
    if guild_id not in _last_activity:
        _last_activity[guild_id] = {}
    _last_activity[guild_id][member_id] = time.monotonic()


def clear_voice_activity(guild_id: int, member_id: int):
    """Supprime le suivi d'un membre qui a quitté le vocal."""
    _last_activity.get(guild_id, {}).pop(member_id, None)
    _pending_disconnect.get(guild_id, set()).discard(member_id)


# ── Boucle de vérification ────────────────────────────────────────────────────

async def voice_inactivity_loop(bot: discord.Client):
    """
    Boucle principale : vérifie toutes les 30s les membres inactifs.
    Appelée via asyncio.create_task() dans ready.py.
    Gère les redémarrages : les membres déjà en vocal sont initialisés
    avec un timestamp "maintenant" (pas d'expulsion immédiate au démarrage).
    """
    print("[VOCAL-INACT] Boucle démarrée")

    # Initialisation au démarrage : enregistrer tous les membres actuellement en vocal
    for guild in bot.guilds:
        cfg = load_config(guild.id)
        if not cfg.get("vocal_inactivity_enabled", False):
            continue
        for channel in guild.voice_channels:
            for member in channel.members:
                if not member.bot:
                    record_voice_activity(guild.id, member.id)

    while not bot.is_closed():
        await asyncio.sleep(30)
        try:
            await _check_all_guilds(bot)
        except Exception as e:
            print(f"[VOCAL-INACT] Erreur boucle principale : {e}")


async def _check_all_guilds(bot: discord.Client):
    for guild in bot.guilds:
        cfg = load_config(guild.id)
        if not cfg.get("vocal_inactivity_enabled", False):
            continue
        delay_s       = _get_delay_seconds(cfg)
        delay_minutes = delay_s / 60.0
        now           = time.monotonic()

        for channel in guild.voice_channels:
            for member in channel.members:
                if member.bot:
                    continue

                gid = guild.id
                mid = member.id

                # Initialiser si nouveau membre en vocal (reconnexion, etc.)
                if gid not in _last_activity or mid not in _last_activity.get(gid, {}):
                    record_voice_activity(gid, mid)
                    continue

                # Si le membre est actif, remettre son compteur à jour
                if _is_active(member):
                    record_voice_activity(gid, mid)
                    continue

                # Vérifier l'exemption
                if _is_exempt(member, channel, cfg):
                    continue

                # Anti double-expulsion
                if gid not in _pending_disconnect:
                    _pending_disconnect[gid] = set()
                if mid in _pending_disconnect[gid]:
                    continue

                # Vérifier si le délai est atteint
                last = _last_activity[gid].get(mid, now)
                inactive_s = now - last
                if inactive_s < delay_s:
                    continue

                # Vérifier que le membre est toujours dans le même salon
                current_vs = member.voice
                if not current_vs or current_vs.channel != channel:
                    clear_voice_activity(gid, mid)
                    continue

                # Vérifier les permissions du bot
                bot_member = guild.me
                if not channel.permissions_for(bot_member).move_members:
                    print(
                        f"[VOCAL-INACT] ⚠️ Permission move_members manquante "
                        f"dans {channel.name} (guild={guild.id})"
                    )
                    continue

                # Marquer comme en cours de déconnexion
                _pending_disconnect[gid].add(mid)

                asyncio.create_task(
                    _disconnect_inactive_member(
                        bot, guild, member, channel, delay_minutes
                    )
                )


async def _disconnect_inactive_member(
    bot: discord.Client,
    guild: discord.Guild,
    member: discord.Member,
    channel: discord.VoiceChannel,
    delay_minutes: float,
):
    """Déconnecte un membre inactif et envoie le log dédié."""
    try:
        # Vérification finale : toujours dans le même salon ?
        current_vs = member.voice
        if not current_vs or current_vs.channel != channel:
            print(f"[VOCAL-INACT] {member} a déjà changé de salon — annulé")
            return

        await member.move_to(None, reason=f"Inactivité vocale ({int(delay_minutes)} min)")
        print(f"[VOCAL-INACT] {member} déconnecté de {channel.name} ({int(delay_minutes)} min d'inactivité)")

        # Log
        cfg        = load_config(guild.id)
        log_ch     = await _get_inactivity_log_channel(guild, cfg)
        if log_ch:
            embed = _build_inactivity_log_embed(member, channel, delay_minutes)
            try:
                await log_ch.send(embed=embed)
            except Exception as e:
                print(f"[VOCAL-INACT] Erreur envoi log : {e}")

    except discord.Forbidden:
        print(f"[VOCAL-INACT] ⚠️ Permission refusée pour déconnecter {member} de {channel.name}")
    except discord.HTTPException as e:
        print(f"[VOCAL-INACT] Erreur HTTP lors de la déconnexion de {member} : {e}")
    except Exception as e:
        print(f"[VOCAL-INACT] Erreur inattendue pour {member} : {e}")
    finally:
        # Nettoyer dans tous les cas
        clear_voice_activity(guild.id, member.id)