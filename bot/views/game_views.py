import asyncio
import discord

from bot.core import bot

from bot.core import bot, active_pendu, active_morpion
from bot.utils.helpers import gk, save_games, load_user_data, get_user, save_user_data
from bot.utils.games import (
    PENDU_ART, PENDU_MOTS, build_pendu_embed, build_morpion_embed,
    check_winner, MORPION_EMOJIS, WINS,
    _start_pendu_timer, _start_morpion_timer, _end_pendu, _update_pendu,
)

class PenduView(discord.ui.View):
    def __init__(self, guild_id, channel_id, creator_id):
        super().__init__(timeout=60)
        self.guild_id = guild_id; self.channel_id = channel_id; self.creator_id = creator_id

    def _game_key(self): return gk(self.guild_id, self.channel_id)

    @discord.ui.button(label="🎲 Mot aléatoire", style=discord.ButtonStyle.green)
    async def random_word(self, interaction, button):
        if interaction.user.id != self.creator_id:
            await interaction.response.send_message("❌ Seul le créateur peut choisir.", ephemeral=True); return
        await self._launch(interaction, random.choice(PENDU_MOTS))

    @discord.ui.button(label="✍️ Mot personnalisé", style=discord.ButtonStyle.blurple)
    async def custom_word(self, interaction, button):
        if interaction.user.id != self.creator_id:
            await interaction.response.send_message("❌ Seul le créateur peut choisir.", ephemeral=True); return
        await interaction.response.edit_message(content="📩 DM envoyé pour le mot !", view=None)
        try:
            dm = await interaction.user.create_dm()
            await dm.send("✍️ Entre le mot (lettres minuscules, sans accents) :")
            def chk(m): return m.author.id == interaction.user.id and isinstance(m.channel, discord.DMChannel)
            dm_msg = await bot.wait_for("message", check=chk, timeout=60)
            word   = dm_msg.content.strip().lower()
            if not word.isalpha(): await dm.send("❌ Mot invalide."); return
            key     = self._game_key()
            channel = bot.get_channel(self.channel_id)
            if channel and key not in active_pendu:
                end_time = time.time() + 30 * 60
                game = {"word": word, "guessed": [], "errors": 0, "creator": interaction.user.id,
                        "participants": [], "msg_id": None, "letter_cd": {}, "end_time": end_time, "channel_id": self.channel_id}
                active_pendu[key] = game
                msg = await channel.send(embed=build_pendu_embed(game))
                game["msg_id"] = msg.id
                save_games(self.guild_id)
                await _start_pendu_timer(key, self.guild_id, 30 * 60)
                await dm.send(f"✅ Partie lancée avec le mot `{word}` !")
        except asyncio.TimeoutError: pass

    async def _launch(self, interaction, word):
        self.stop()
        key      = self._game_key()
        end_time = time.time() + 30 * 60
        game = {"word": word, "guessed": [], "errors": 0, "creator": interaction.user.id,
                "participants": [], "msg_id": None, "letter_cd": {}, "end_time": end_time, "channel_id": self.channel_id}
        active_pendu[key] = game
        await interaction.response.edit_message(content=None, embed=build_pendu_embed(game), view=None)
        msg = await interaction.original_response()
        game["msg_id"] = msg.id
        save_games(self.guild_id)
        await _start_pendu_timer(key, self.guild_id, 30 * 60)
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