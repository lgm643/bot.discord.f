"""
utils/market.py — Gestion du catalogue et des commandes market.

CORRECTIONS v2 :
  [1] PERFORMANCE — Cache mémoire pour load_catalogue() / save_catalogue().
      Avant : chaque appel de commande market lisait le fichier JSON depuis
      le disque. Maintenant : cache par guild_id invalidé à chaque save.
      Pattern identique au cache user_data existant.

  [2] SÉCURITÉ — Validation de longueur sur les champs catalogue.
      validate_item_fields() lève ValueError avec message clair si un champ
      dépasse les limites Discord (1024 chars/field, 100 pour le nom).
      À appeler dans les commandes !gestion avant toute insertion.

  [3] Unification des fins de ligne CRLF → LF (fichier d'origine avait \r\n).
"""
from pathlib import Path
import json
import os
import re
import difflib
import asyncio
import discord

from bot.core import bot
from bot.core import CATALOGUE_DIR, _catalogue_msg_ids, _commande_msg_ids, _catalogue_lock
from bot.utils.config import cfg_channel, cfg_role, load_config, resolve_channel
from bot.utils.helpers import now_utc

# ── Cache mémoire catalogue ───────────────────────────────────────────────────
# [1] dict[guild_id: int -> catalogue_data: dict]
_catalogue_cache: dict[int, dict] = {}


def _item_key(nom: str, vendeur_id: int) -> str:
    return f"{nom.lower().strip()}:{vendeur_id}"


def catalogue_path(guild_id: int) -> Path:
    return CATALOGUE_DIR / f"{guild_id}.json"


def load_catalogue(guild_id: int) -> dict:
    """[1] Charge depuis le cache mémoire. Si absent, lit le fichier disque."""
    if guild_id in _catalogue_cache:
        return _catalogue_cache[guild_id]
    path = catalogue_path(guild_id)
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            _catalogue_cache[guild_id] = data
            return data
        except Exception as e:
            print(f"[CATALOGUE] Erreur lecture : {e}")
    empty = {"items": {}, "msg_id": None, "commande_msg_id": None}
    _catalogue_cache[guild_id] = empty
    return empty


def save_catalogue(guild_id: int, data: dict):
    """[1] Sauvegarde sur disque et invalide le cache mémoire."""
    path = catalogue_path(guild_id)
    tmp  = str(path) + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
        # Invalide le cache après écriture réussie
        _catalogue_cache[guild_id] = data
    except Exception as e:
        print(f"[CATALOGUE] Erreur sauvegarde : {e}")


# ── Validation des champs ─────────────────────────────────────────────────────

# Limites Discord : un champ embed = 1024 chars max, nom d'article affiché dans
# le titre d'un select menu = 100 chars max.
_MAX_NOM    = 100
_MAX_PRIX   = 80
_MAX_DESC   = 900   # marge de sécurité sous la limite embed de 1024


def validate_item_fields(nom: str, prix: str, description: str = "") -> None:
    """
    [2] Valide la longueur des champs d'un article catalogue.
    Lève ValueError avec un message explicite si un champ est trop long.
    """
    if len(nom) > _MAX_NOM:
        raise ValueError(
            f"Le nom de l'article est trop long ({len(nom)} caractères). "
            f"Maximum : {_MAX_NOM} caractères."
        )
    if len(prix) > _MAX_PRIX:
        raise ValueError(
            f"Le prix est trop long ({len(prix)} caractères). "
            f"Maximum : {_MAX_PRIX} caractères."
        )
    if description and len(description) > _MAX_DESC:
        raise ValueError(
            f"La description est trop longue ({len(description)} caractères). "
            f"Maximum : {_MAX_DESC} caractères."
        )
    if not nom.strip():
        raise ValueError("Le nom de l'article ne peut pas être vide.")
    if not prix.strip():
        raise ValueError("Le prix ne peut pas être vide.")


# ── Nettoyage et construction embed ──────────────────────────────────────────

def _clean_ghost_items(items: dict) -> dict:
    return {k: v for k, v in items.items() if v.get("quantite", 0) > 0}


def build_catalogue_embed(items: dict) -> discord.Embed:
    """Embed statique (utilisé pour les mises à jour automatiques sans view interactive)."""
    items_clean = _clean_ghost_items(items)
    embed = discord.Embed(
        title="🏪 Catalogue",
        description=f"**{len(items_clean)}** article(s) disponible(s)",
        color=0xF1C40F, timestamp=now_utc()
    )
    if not items_clean:
        embed.add_field(name="📭 Aucun article", value="Le catalogue est vide.", inline=False)
    else:
        sorted_items = sorted(items_clean.values(), key=lambda x: x["nom"].lower())
        chunk, chunks = "", []
        for item in sorted_items:
            ligne = f"🔹 **{item['nom']}** — 📦 {item['quantite']}x · 💰 {item['prix']}"
            if len(chunk) + len(ligne) + 1 > 1000:
                chunks.append(chunk)
                chunk = ligne
            else:
                chunk = (chunk + "\n" + ligne).strip()
        if chunk:
            chunks.append(chunk)
        for idx, c in enumerate(chunks):
            embed.add_field(
                name="\u200b" if idx > 0 else "📋 Articles (A→Z)",
                value=c,
                inline=False
            )
    embed.set_footer(text="Tri et recherche disponibles via les boutons du catalogue interactif")
    return embed


def _get_catalogue_lock(guild_id: int) -> asyncio.Lock:
    if guild_id not in _catalogue_lock:
        _catalogue_lock[guild_id] = asyncio.Lock()
    return _catalogue_lock[guild_id]


async def update_catalogue_message(guild: discord.Guild, items: dict):
    async with _get_catalogue_lock(guild.id):
        items = _clean_ghost_items(items)
        data  = load_catalogue(guild.id)   # [1] depuis le cache
        cat_ch = cfg_channel(guild, "salon_catalogue")
        if cat_ch:
            embed  = build_catalogue_embed(items)
            msg_id = data.get("msg_id") or _catalogue_msg_ids.get(guild.id)
            if msg_id:
                try:
                    msg = await cat_ch.fetch_message(msg_id)
                    await msg.edit(embed=embed)
                except Exception:
                    msg = await cat_ch.send(embed=embed)
                    _catalogue_msg_ids[guild.id] = msg.id
                    data["msg_id"] = msg.id
            else:
                msg = await cat_ch.send(embed=embed)
                _catalogue_msg_ids[guild.id] = msg.id
                data["msg_id"] = msg.id
        cmd_ch = cfg_channel(guild, "salon_commandes")
        if cmd_ch:
            from bot.views.market_view import CommandeView, _build_commande_embed_from_items
            cmd_embed  = _build_commande_embed_from_items(guild, items)
            cmd_view   = CommandeView(guild.id, items)
            cmd_msg_id = data.get("commande_msg_id") or _commande_msg_ids.get(guild.id)
            if cmd_msg_id:
                try:
                    cmd_msg = await cmd_ch.fetch_message(cmd_msg_id)
                    await cmd_msg.edit(embed=cmd_embed, view=cmd_view)
                    bot.add_view(cmd_view, message_id=cmd_msg_id)
                except Exception:
                    cmd_msg = await cmd_ch.send(embed=cmd_embed, view=cmd_view)
                    _commande_msg_ids[guild.id] = cmd_msg.id
                    data["commande_msg_id"] = cmd_msg.id
                    bot.add_view(cmd_view, message_id=cmd_msg.id)
        data["items"] = items
        save_catalogue(guild.id, data)   # [1] invalide le cache après écriture


async def send_notif(guild: discord.Guild, texte: str):
    channel = cfg_channel(guild, "salon_notifications")
    role    = cfg_role(guild, "role_acheteur_notif")
    if not channel:
        return
    mention = role.mention if role else ""
    await channel.send(f"{mention} {texte}")


# ── Recherche fuzzy ───────────────────────────────────────────────────────────

def fuzzy_search(terme: str, items: dict, seuil: float = 0.5) -> dict:
    terme_lower = terme.lower().strip()
    resultats   = {}
    for key, item in items.items():
        nom_lower = item["nom"].lower()
        key_lower = key.lower()
        if terme_lower == nom_lower or terme_lower == key_lower:
            resultats[key] = (item, 1.0)
            continue
        if terme_lower in nom_lower or terme_lower in key_lower:
            resultats[key] = (item, 0.9)
            continue
        score = max(
            difflib.SequenceMatcher(None, terme_lower, nom_lower).ratio(),
            difflib.SequenceMatcher(None, terme_lower, key_lower).ratio()
        )
        if score >= seuil:
            resultats[key] = (item, score)
    return dict(sorted(resultats.items(), key=lambda x: x[1][1], reverse=True))


# ── Auto-suppression dans les salons marché ───────────────────────────────────

async def _auto_delete_in_marche(message: discord.Message):
    if not message.guild:
        return
    cfg    = load_config(message.guild.id)
    cat_ch = resolve_channel(message.guild, cfg.get("salon_catalogue"))
    cmd_ch = resolve_channel(message.guild, cfg.get("salon_commandes"))
    in_cat = cat_ch and message.channel.id == cat_ch.id
    in_cmd = cmd_ch and message.channel.id == cmd_ch.id
    if not (in_cat or in_cmd):
        return
    await asyncio.sleep(1)
    data      = load_catalogue(message.guild.id)
    protected = {
        data.get("msg_id"),
        data.get("commande_msg_id"),
        _catalogue_msg_ids.get(message.guild.id),
        _commande_msg_ids.get(message.guild.id),
    }
    protected.discard(None)
    if message.id in protected:
        return
    try:
        await message.delete()
    except Exception:
        pass


# ── Parsing prix ──────────────────────────────────────────────────────────────

def _parse_prix_num(prix: str):
    nums = re.findall(r"[\d]+(?:[.,][\d]+)?", prix)
    if nums:
        try:
            return float(nums[0].replace(",", "."))
        except ValueError:
            pass
    return None