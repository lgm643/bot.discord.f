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

from bot.core import bot, active_pendu, active_morpion, pendu_tasks, morpion_tasks
from bot.utils.helpers import gk, save_games, load_user_data, get_user, save_user_data

PENDU_MOTS = [
    "horloge","montagne","riviere","ocean","plage","desert","foret","ile","vallee","colline",
    "nuage","orage","tempete","pluie","neige","vent","soleil","lune","etoile","ciel",
    "musique","chanson","instrument","guitare","piano","batterie","violon","concert","festival","spectacle",
    "film","cinema","acteur","realisateur","scene","camera","studio","projection","serie","episode",
    "livre","roman","auteur","lecture","bibliotheque","page","chapitre","histoire","conte","poeme",
    "faction","alliance","serveur","armure","epee","bouclier","ressource","territoire",
    "combat","recrue","officier","leader","victoire","forteresse","invasion","guilde",
    "diamant","emeraude","enchantement","potion","portail","zombie","squelette","creeper",
]

PENDU_ART = [
    "```\n  +---+\n      |\n      |\n      |\n      |\n=========```",
    "```\n  +---+\n  O   |\n      |\n      |\n      |\n=========```",
    "```\n  +---+\n  O   |\n  |   |\n      |\n      |\n=========```",
    "```\n  +---+\n  O   |\n /|   |\n      |\n      |\n=========```",
    "```\n  +---+\n  O   |\n /|\\  |\n      |\n      |\n=========```",
    "```\n  +---+\n  O   |\n /|\\  |\n /    |\n      |\n=========```",
    "```\n  +---+\n  O   |\n /|\\  |\n / \\  |\n      |\n=========```",
]


def build_pendu_embed(game: dict) -> discord.Embed:
    word      = game["word"]
    guessed   = set(game["guessed"])
    errors    = game["errors"]
    display   = " ".join(l if l in guessed else "_" for l in word)
    wrong     = [l for l in guessed if l not in word]
    remaining = max(0, int(game.get("end_time", 0) - time.time()))
    mins, secs = divmod(remaining, 60)
    won  = all(l in guessed for l in word)
    lost = errors >= 6
    color = 0x2ECC71 if won else (0xE74C3C if lost else 0x9B59B6)
    embed = discord.Embed(title="🎯 Pendu", color=color)
    embed.add_field(name="Mot",         value=f"`{display}`",                                                      inline=False)
    embed.add_field(name="Dessin",      value=PENDU_ART[min(errors, 6)],                                           inline=False)
    embed.add_field(name="❌ Erreurs",  value=f"{errors}/6 — `{''.join(wrong) or 'aucune'}`",                      inline=True)
    embed.add_field(name="✅ Trouvées", value=f"`{''.join(sorted(l for l in guessed if l in word)) or 'aucune'}`", inline=True)
    embed.add_field(name="⏱️ Temps",    value=f"{mins}m {secs:02d}s",                                              inline=True)
    if game.get("participants"):
        embed.add_field(name="👥 Joueurs", value=", ".join(f"<@{u}>" for u in game["participants"]), inline=False)
    embed.set_footer(text="!devine [lettre]  •  !mot [mot complet]")
    return embed


async def _start_pendu_timer(key: str, guild_id: int, remaining: float):
    if key in pendu_tasks: pendu_tasks[key].cancel()
    async def _run():
        await asyncio.sleep(remaining)
        game = active_pendu.pop(key, None)
        pendu_tasks.pop(key, None)
        if not game: return
        save_games(guild_id)
        channel = bot.get_channel(game.get("channel_id", 0))
        if channel:
            await channel.send(f"⏰ Temps écoulé ! Le mot était : **{game['word']}**")
            if game.get("msg_id"):
                try:
                    m = await channel.fetch_message(game["msg_id"]); await m.delete()
                except Exception: pass
    pendu_tasks[key] = asyncio.create_task(_run())
async def _end_pendu(channel, guild_id, game, won, winner_id=None):
    key = gk(guild_id, channel.id)
    active_pendu.pop(key, None)
    if key in pendu_tasks: pendu_tasks[key].cancel(); pendu_tasks.pop(key, None)
    save_games(guild_id)
    if game.get("msg_id"):
        try:
            msg = await channel.fetch_message(game["msg_id"]); await msg.edit(embed=build_pendu_embed(game))
        except Exception: pass
    if won:
        data = load_user_data(guild_id)
        if winner_id: get_user(data, winner_id)["xp"] += 150
        save_user_data(guild_id, data)
        await channel.send(f"🏆 <@{winner_id}> a trouvé le mot **{game['word']}** ! **+150 XP** 🎉" if winner_id else f"🏆 Mot trouvé : **{game['word']}** !")
    else:
        await channel.send(f"💀 Perdu ! Le mot était **{game['word']}**.")


async def _update_pendu(ctx, guild_id, game, winner_id=None):
    guessed = set(game["guessed"])
    won  = all(l in guessed for l in game["word"])
    lost = game["errors"] >= 6
    if game.get("msg_id"):
        try:
            msg = await ctx.channel.fetch_message(game["msg_id"]); await msg.edit(embed=build_pendu_embed(game))
        except discord.NotFound:
            key = gk(guild_id, ctx.channel.id)
            active_pendu.pop(key, None)
            if key in pendu_tasks: pendu_tasks[key].cancel(); pendu_tasks.pop(key, None)
            save_games(guild_id); return
        except Exception: pass
    if won:   await _end_pendu(ctx.channel, guild_id, game, won=True, winner_id=winner_id)
    elif lost: await _end_pendu(ctx.channel, guild_id, game, won=False)


# ═══════════════════════════════════════════════════════════════
#  MORPION
# ═══════════════════════════════════════════════════════════════

MORPION_EMOJIS = {None: "⬜", "X": "❌", "O": "⭕"}
WINS = [(0,1,2),(3,4,5),(6,7,8),(0,3,6),(1,4,7),(2,5,8),(0,4,8),(2,4,6)]

def check_winner(board):
    for a, b, c in WINS:
        if board[a] and board[a] == board[b] == board[c]: return board[a]
    return None

def build_morpion_embed(game):
    board    = game["board"]
    players  = game["players"]
    current  = game["current"]
    remaining = max(0, int(game.get("end_time", 0) - time.time()))
    mins, secs = divmod(remaining, 60)
    winner = check_winner(board)
    full   = all(c is not None for c in board)
    color  = 0x2ECC71 if winner else (0x95A5A6 if full else 0x3498DB)
    embed  = discord.Embed(title="❌⭕ Morpion", color=color)
    rows = ""
    for i in range(0, 9, 3):
        rows += "".join(MORPION_EMOJIS[board[i+j]] for j in range(3)) + "\n"
    embed.add_field(name="Plateau", value=rows, inline=False)
    if winner:
        winner_id = players[0] if winner == "X" else players[1]
        embed.add_field(name="🏆 Gagnant", value=f"<@{winner_id}>", inline=True)
    elif full:
        embed.add_field(name="Résultat", value="🤝 Égalité !", inline=True)
    else:
        cur_id = players[current]
        sym    = "❌" if current == 0 else "⭕"
        embed.add_field(name="Tour",     value=f"{sym} <@{cur_id}>",   inline=True)
        embed.add_field(name="⏱️ Temps", value=f"{mins}m {secs:02d}s", inline=True)
    embed.add_field(name="Joueurs", value=f"❌ <@{players[0]}>  vs  ⭕ <@{players[1]}>", inline=False)
    return embed


class MorpionView(discord.ui.View):
    def __init__(self, guild_id, channel_id):
        super().__init__(timeout=None)
        self.guild_id = guild_id; self.channel_id = channel_id
        self._rebuild()

    def _key(self): return gk(self.guild_id, self.channel_id)

    def _rebuild(self):
        self.clear_items()
        game  = active_morpion.get(self._key())
        board = game["board"] if game else [None]*9
        ended = game is None or check_winner(board) is not None or all(c is not None for c in board)
        for i in range(9):
            btn = discord.ui.Button(
                label=MORPION_EMOJIS[board[i]],
                style=discord.ButtonStyle.secondary if board[i] is None else discord.ButtonStyle.primary,
                disabled=(board[i] is not None or ended),
                row=i // 3,
                custom_id=f"morpion_{self.guild_id}_{self.channel_id}_{i}"
            )
            btn.callback = self._make_callback(i)
            self.add_item(btn)

    def _make_callback(self, cell):
        async def callback(interaction: discord.Interaction):
            key  = self._key()
            game = active_morpion.get(key)
            if not game: await interaction.response.send_message("❌ Partie terminée.", ephemeral=True); return
            uid     = interaction.user.id
            current = game["current"]
            players = game["players"]
            if uid != players[current]: await interaction.response.send_message("❌ Ce n'est pas ton tour.", ephemeral=True); return
            if game["board"][cell] is not None: await interaction.response.send_message("❌ Case déjà jouée.", ephemeral=True); return
            sym = "X" if current == 0 else "O"
            game["board"][cell] = sym
            game["current"] = 1 - current
            save_games(self.guild_id)
            winner = check_winner(game["board"])
            full   = all(c is not None for c in game["board"])
            if winner or full:
                active_morpion.pop(key, None)
                if key in morpion_tasks: morpion_tasks[key].cancel(); morpion_tasks.pop(key, None)
                save_games(self.guild_id)
                for item in self.children: item.disabled = True
                embed = build_morpion_embed(game)
                if winner:
                    winner_id = players[0] if winner == "X" else players[1]
                    data = load_user_data(self.guild_id)
                    get_user(data, winner_id)["xp"] += 50
                    save_user_data(self.guild_id, data)
                    revanche_view = RevancheView(loser_id=players[1] if winner == "X" else players[0], players=players, guild_id=self.guild_id, channel_id=self.channel_id)
                    await interaction.response.edit_message(embed=embed, view=revanche_view)
                    await interaction.followup.send(f"🎉 <@{winner_id}> a gagné ! **+50 XP** 🏆")
                else:
                    await interaction.response.edit_message(embed=embed, view=None)
                    await interaction.followup.send("🤝 Égalité !")
            else:
                self._rebuild()
                await interaction.response.edit_message(embed=build_morpion_embed(game), view=self)
        return callback


class RevancheView(discord.ui.View):
    def __init__(self, loser_id, players, guild_id, channel_id, timeout_sec=10):
        super().__init__(timeout=timeout_sec)
        self.loser_id = loser_id; self.players = players; self.guild_id = guild_id; self.channel_id = channel_id

    async def on_timeout(self):
        for item in self.children: item.disabled = True

    @discord.ui.button(label="🔁 Revanche", style=discord.ButtonStyle.green)
    async def revanche(self, interaction, button):
        if interaction.user.id != self.loser_id:
            await interaction.response.send_message("❌ Seul le perdant peut demander la revanche.", ephemeral=True); return
        self.stop()
        new_players = list(reversed(self.players))
        end_time    = time.time() + 5 * 60
        key         = gk(self.guild_id, self.channel_id)
        game = {"board": [None]*9, "players": new_players, "current": 0, "msg_id": None, "end_time": end_time}
        active_morpion[key] = game
        view  = MorpionView(self.guild_id, self.channel_id)
        embed = build_morpion_embed(game)
        await interaction.response.send_message(embed=embed, view=view)
        msg = await interaction.original_response()
        game["msg_id"] = msg.id
        save_games(self.guild_id)
        await _start_morpion_timer(key, self.guild_id, 5 * 60)


async def _start_morpion_timer(key, guild_id, remaining):
    if key in morpion_tasks: morpion_tasks[key].cancel()
    async def _run():
        await asyncio.sleep(remaining)
        game = active_morpion.pop(key, None)
        morpion_tasks.pop(key, None)
        if not game: return
        save_games(guild_id)
        _, ch_id = key.split(":")
        channel  = bot.get_channel(int(ch_id))
        if channel:
            await channel.send("⏰ Temps écoulé ! Partie de morpion annulée.")
            if game.get("msg_id"):
                try: m = await channel.fetch_message(game["msg_id"]); await m.edit(view=None)
                except Exception: pass
    morpion_tasks[key] = asyncio.create_task(_run())
