import asyncio
import io
import os
import re
import time
import json
import random
import sqlite3
import difflib
from datetime import datetime, timezone
from collections import defaultdict
from pathlib import Path

import discord
from discord.ext import commands

from bot.core import bot

from bot.core import CATALOGUE_DIR, _catalogue_msg_ids, _commande_msg_ids, _catalogue_lock
from bot.utils.config import cfg_channel, load_config, resolve_channel
from bot.utils.helpers import now_utc

def _item_key(nom: str, vendeur_id: int) -> str:
    return f"{nom.lower().strip()}:{vendeur_id}"

def catalogue_path(guild_id: int) -> Path:
    return CATALOGUE_DIR / f"{guild_id}.json"

def load_catalogue(guild_id: int) -> dict:
    path = catalogue_path(guild_id)
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[CATALOGUE] Erreur lecture : {e}")
    return {"items": {}, "msg_id": None, "commande_msg_id": None}

def save_catalogue(guild_id: int, data: dict):
    path = catalogue_path(guild_id)
    tmp  = str(path) + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
    except Exception as e:
        print(f"[CATALOGUE] Erreur sauvegarde : {e}")

def _clean_ghost_items(items: dict) -> dict:
    return {k: v for k, v in items.items() if v.get("quantite", 0) > 0}

def build_catalogue_embed(items: dict) -> discord.Embed:
    embed = discord.Embed(title="🏪 Catalogue", description="Articles disponibles à la vente :", color=0xF1C40F, timestamp=now_utc())
    if not items:
        embed.add_field(name="📭 Aucun article", value="Le catalogue est vide.", inline=False)
    else:
        par_vendeur: dict[int, list] = defaultdict(list)
        for key, item in items.items():
            par_vendeur[item["vendeur_id"]].append(item)
        for vendeur_id, arts in par_vendeur.items():
            lignes = "\n".join(f"🔹 **{a['nom']}** — 📦 {a['quantite']} · 💰 {a['prix']}" for a in arts)
            embed.add_field(name=f"👤 <@{vendeur_id}>", value=lignes, inline=False)
    embed.set_footer(text="Utilisez !commande pour passer une commande")
    return embed

def _get_catalogue_lock(guild_id: int) -> asyncio.Lock:
    if guild_id not in _catalogue_lock:
        _catalogue_lock[guild_id] = asyncio.Lock()
    return _catalogue_lock[guild_id]

async def update_catalogue_message(guild: discord.Guild, items: dict):
    async with _get_catalogue_lock(guild.id):
        items = _clean_ghost_items(items)
        data  = load_catalogue(guild.id)
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
            cmd_embed  = _build_commande_embed_from_items(guild, items)
            from bot.views.market_view import CommandeView
            cmd_view   = CommandeView(guild.id, items)
            cmd_msg_id = data.get("commande_msg_id") or _commande_msg_ids.get(guild.id)
            if cmd_msg_id:
                try:
                    cmd_msg = await cmd_ch.fetch_message(cmd_msg_id)
                    await cmd_msg.edit(embed=cmd_embed, view=cmd_view)
                except Exception:
                    cmd_msg = await cmd_ch.send(embed=cmd_embed, view=cmd_view)
                    _commande_msg_ids[guild.id] = cmd_msg.id
                    data["commande_msg_id"] = cmd_msg.id
        data["items"] = items
        save_catalogue(guild.id, data)

async def send_notif(guild: discord.Guild, texte: str):
    channel = cfg_channel(guild, "salon_notifications")
    role    = cfg_role(guild, "role_acheteur_notif")
    if not channel:
        return
    mention = role.mention if role else ""
    await channel.send(f"{mention} {texte}")
def fuzzy_search(terme: str, items: dict, seuil: float = 0.5) -> dict:
    terme_lower = terme.lower().strip()
    resultats   = {}
    for key, item in items.items():
        nom_lower = item["nom"].lower()
        key_lower = key.lower()
        if terme_lower == nom_lower or terme_lower == key_lower:
            resultats[key] = (item, 1.0); continue
        if terme_lower in nom_lower or terme_lower in key_lower:
            resultats[key] = (item, 0.9); continue
        score = max(
            difflib.SequenceMatcher(None, terme_lower, nom_lower).ratio(),
            difflib.SequenceMatcher(None, terme_lower, key_lower).ratio()
        )
        if score >= seuil:
            resultats[key] = (item, score)
    return dict(sorted(resultats.items(), key=lambda x: x[1][1], reverse=True))
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
    protected = {data.get("msg_id"), data.get("commande_msg_id"), _catalogue_msg_ids.get(message.guild.id), _commande_msg_ids.get(message.guild.id)}
    protected.discard(None)
    if message.id in protected:
        return
    try:
        await message.delete()
    except Exception:
        pass
def _parse_prix_num(prix: str):
    nums = re.findall(r"[\d]+(?:[.,][\d]+)?", prix)
    if nums:
        try: return float(nums[0].replace(",", "."))
        except ValueError: pass
    return None
