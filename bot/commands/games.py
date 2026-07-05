"""
commands/games.py — Mini-jeux : Pendu et Morpion.

!pendu          — Lance une partie (mot aléatoire ou perso via DM)
!devine <lettre> — Propose une lettre (pendu)
!mot <mot>       — Tente de deviner le mot entier (pendu)
!pendustop       — Arrête la partie (staff)

!morpion @joueur  — Lance une partie contre un membre
!morpionstop      — Arrête la partie (staff)
"""
import asyncio
import random
import unicodedata
from typing import Optional

import discord

from bot.core import bot
from bot.utils.helpers import load_user_data, get_user, save_user_data, now_utc
from bot.utils.permissions import is_staff

# ═══════════════════════════════════════════════════════════════
# ÉTAT GLOBAL PAR GUILD
# ═══════════════════════════════════════════════════════════════
_pendu_games: dict[int, dict] = {}    # guild_id → état pendu
_morpion_games: dict[int, dict] = {}  # guild_id → état morpion


# ═══════════════════════════════════════════════════════════════
# UTILITAIRE XP
# ═══════════════════════════════════════════════════════════════
async def _award_xp(guild: discord.Guild, member: discord.Member, xp: int):
    try:
        data = load_user_data(guild.id)
        u = get_user(data, member.id)
        u["xp"] = u.get("xp", 0) + xp
        save_user_data(guild.id, data)
    except Exception as e:
        print(f"[GAMES] Erreur award XP : {e}")


# ═══════════════════════════════════════════════════════════════
# ██████╗ ███████╗███╗   ██╗██████╗ ██╗   ██╗
# ██╔══██╗██╔════╝████╗  ██║██╔══██╗██║   ██║
# ██████╔╝█████╗  ██╔██╗ ██║██║  ██║██║   ██║
# ██╔═══╝ ██╔══╝  ██║╚██╗██║██║  ██║██║   ██║
# ██║     ███████╗██║ ╚████║██████╔╝╚██████╔╝
# ╚═╝     ╚══════╝╚═╝  ╚═══╝╚═════╝  ╚═════╝
# ═══════════════════════════════════════════════════════════════

MOTS_PENDU = [
    "python", "discord", "faction", "victoire", "strategie",
    "alliance", "champion", "tournoi", "mystique", "legende",
    "dragon", "chevalier", "sorcier", "guerrier", "paladin",
    "aventure", "donjon", "tresor", "artefact", "magie",
    "bataille", "conquete", "empire", "royaume", "territoire",
    "commandant", "recrue", "officier", "gardien", "eclaireur",
    "catapulte", "forteresse", "citadelle", "bastion", "rempart",
    "epee", "bouclier", "armure", "casque", "lame",
    "embuscade", "sabotage", "espion", "assassin", "mercenaire",
    "serveur", "message", "inviter", "commande", "catalogue",
]

PENDU_STAGES = [
    "```\n  +---+\n  |   |\n      |\n      |\n      |\n      |\n=========```",
    "```\n  +---+\n  |   |\n  O   |\n      |\n      |\n      |\n=========```",
    "```\n  +---+\n  |   |\n  O   |\n  |   |\n      |\n      |\n=========```",
    "```\n  +---+\n  |   |\n  O   |\n /|   |\n      |\n      |\n=========```",
    "```\n  +---+\n  |   |\n  O   |\n /|\\  |\n      |\n      |\n=========```",
    "```\n  +---+\n  |   |\n  O   |\n /|\\  |\n /    |\n      |\n=========```",
    "```\n  +---+\n  |   |\n  O   |\n /|\\  |\n / \\  |\n      |\n=========```",
]
MAX_ERREURS = 6


def _normalize(s: str) -> str:
    """Supprime les accents et met en minuscules."""
    return "".join(
        c for c in unicodedata.normalize("NFD", s.lower())
        if unicodedata.category(c) != "Mn"
    )


def _build_pendu_embed(game: dict) -> discord.Embed:
    word    = game["word"]
    guessed = game["guessed"]
    erreurs = game["erreurs"]
    joueur  = game["joueur"]

    # Afficher le mot avec les lettres trouvées
    displayed = " ".join(
        c if _normalize(c) in guessed or c in ("-", "'", " ") else r"\_"
        for c in word
    )

    # Séparer lettres correctes et ratées
    lettres_ok     = sorted(l for l in guessed if any(_normalize(c) == l for c in word))
    lettres_ratees = sorted(l for l in guessed if l not in lettres_ok)

    embed = discord.Embed(
        title="🎯 Pendu — La Mystic",
        color=0x9B59B6 if erreurs < MAX_ERREURS else 0xE74C3C,
        timestamp=now_utc(),
    )
    embed.description = PENDU_STAGES[erreurs]
    embed.add_field(name="🔤 Mot", value=f"`{displayed}`", inline=False)
    embed.add_field(
        name=f"❌ Mauvaises lettres ({erreurs}/{MAX_ERREURS})",
        value=" ".join(f"`{l}`" for l in lettres_ratees) or "*aucune*",
        inline=True,
    )
    embed.add_field(
        name="✅ Bonnes lettres",
        value=" ".join(f"`{l}`" for l in lettres_ok) or "*aucune*",
        inline=True,
    )
    embed.set_footer(
        text=f"Lancé par {joueur.display_name} · "
             f"!devine <lettre> | !mot <mot> · Timeout 30 min"
    )
    return embed


def _is_word_complete(game: dict) -> bool:
    word    = game["word"]
    guessed = game["guessed"]
    return all(_normalize(c) in guessed or c in ("-", "'", " ") for c in word)


async def _pendu_timeout_task(guild_id: int, channel_id: int):
    await asyncio.sleep(1800)  # 30 min
    game = _pendu_games.pop(guild_id, None)
    if game:
        try:
            guild   = bot.get_guild(guild_id)
            channel = guild and guild.get_channel(channel_id)
            if channel:
                embed = discord.Embed(
                    title="⏰ Pendu — Temps écoulé !",
                    description=f"Personne n'a trouvé le mot. Il s'agissait de : **{game['word']}**",
                    color=0xE74C3C,
                    timestamp=now_utc(),
                )
                await channel.send(embed=embed)
        except Exception:
            pass


# ── Commandes Pendu ──────────────────────────────────────────────────────────

@bot.hybrid_command(name="pendu")
async def pendu_cmd(ctx):
    gid = ctx.guild.id
    if gid in _pendu_games:
        await ctx.send(
            "⚠️ Une partie de pendu est déjà en cours ! "
            "Tape `!pendustop` pour l'arrêter (staff).",
            delete_after=10,
        )
        return

    mot = random.choice(MOTS_PENDU)

    # Proposer un mot personnalisé en DM (optionnel, 30 s)
    try:
        dm_embed = discord.Embed(
            title="🎯 Nouveau Pendu — mot personnalisé ?",
            description=(
                "Tu peux choisir un **mot personnalisé** pour cette partie.\n"
                "Envoie-le ici dans les **30 secondes** "
                "(lettres uniquement, 3–20 caractères).\n\n"
                "Ignore ce message pour utiliser un **mot aléatoire**."
            ),
            color=0x9B59B6,
        )
        await ctx.author.send(embed=dm_embed)

        def dm_check(m):
            return m.author.id == ctx.author.id and isinstance(m.channel, discord.DMChannel)

        try:
            dm_msg = await bot.wait_for("message", check=dm_check, timeout=30)
            custom = dm_msg.content.strip().lower()
            custom_norm = _normalize(custom)
            if custom_norm.isalpha() and 3 <= len(custom_norm) <= 20:
                mot = custom
                await ctx.author.send(
                    f"✅ Mot **{mot}** enregistré ! "
                    f"La partie commence dans **#{ctx.channel.name}**."
                )
            else:
                await ctx.author.send(
                    "⚠️ Mot invalide (lettres uniquement, 3–20 caractères). "
                    "Mot aléatoire utilisé à la place."
                )
        except asyncio.TimeoutError:
            await ctx.author.send("⏰ Temps écoulé. Mot aléatoire utilisé.")
    except discord.Forbidden:
        pass  # DMs fermés → mot aléatoire silencieusement

    task = asyncio.create_task(_pendu_timeout_task(gid, ctx.channel.id))
    _pendu_games[gid] = {
        "word":    mot,
        "guessed": set(),
        "erreurs": 0,
        "joueur":  ctx.author,
        "channel": ctx.channel.id,
        "task":    task,
    }

    embed = _build_pendu_embed(_pendu_games[gid])
    embed.add_field(
        name="📋 Commandes",
        value=(
            "`!devine <lettre>` → Proposer une lettre\n"
            "`!mot <mot>` → Deviner le mot entier\n"
            f"Le mot contient **{len(mot)}** lettre(s)."
        ),
        inline=False,
    )
    await ctx.send(embed=embed)


@bot.hybrid_command(name="devine")
async def devine_cmd(ctx, lettre: str = ""):
    gid  = ctx.guild.id
    game = _pendu_games.get(gid)

    if not game:
        await ctx.send("❌ Aucune partie de pendu en cours. Lance-en une avec `!pendu` !", delete_after=8)
        return
    if ctx.channel.id != game["channel"]:
        return  # Ignore les autres salons

    lettre = lettre.strip()
    if not lettre or len(lettre) != 1 or not lettre.isalpha():
        await ctx.send("⚠️ Envoie une seule lettre ! Exemple : `!devine a`", delete_after=6)
        return

    lettre_norm = _normalize(lettre)
    if lettre_norm in game["guessed"]:
        await ctx.send(f"⚠️ La lettre **{lettre}** a déjà été proposée.", delete_after=6)
        return

    game["guessed"].add(lettre_norm)
    word_norms = [_normalize(c) for c in game["word"]]

    if lettre_norm in word_norms:
        if _is_word_complete(game):
            # Victoire !
            game["task"].cancel()
            _pendu_games.pop(gid, None)
            await _award_xp(ctx.guild, ctx.author, 150)
            embed = discord.Embed(
                title="🎉 Bravo — Mot trouvé !",
                description=(
                    f"Le mot était : **{game['word']}**\n"
                    f"🏆 +**150 XP** attribués à {ctx.author.mention} !"
                ),
                color=0x2ECC71,
                timestamp=now_utc(),
            )
            await ctx.send(embed=embed)
        else:
            embed = _build_pendu_embed(game)
            embed.set_author(name=f"✅ Bonne lettre ! « {lettre} » est dans le mot !")
            await ctx.send(embed=embed)
    else:
        game["erreurs"] += 1
        if game["erreurs"] >= MAX_ERREURS:
            # Défaite
            game["task"].cancel()
            mot = game["word"]
            _pendu_games.pop(gid, None)
            embed = discord.Embed(
                title="💀 Perdu — Le pendu est mort !",
                color=0xE74C3C,
                timestamp=now_utc(),
            )
            embed.description = (
                PENDU_STAGES[MAX_ERREURS]
                + f"\n\nLe mot était : **{mot}**"
            )
            await ctx.send(embed=embed)
        else:
            embed = _build_pendu_embed(game)
            embed.set_author(name=f"❌ Mauvaise lettre ! « {lettre} » n'est pas dans le mot.")
            await ctx.send(embed=embed)


@bot.hybrid_command(name="mot")
async def mot_cmd(ctx, *, tentative: str = ""):
    gid  = ctx.guild.id
    game = _pendu_games.get(gid)

    if not game:
        await ctx.send("❌ Aucune partie de pendu en cours.", delete_after=8)
        return
    if ctx.channel.id != game["channel"]:
        return

    tentative = tentative.strip()
    if not tentative:
        await ctx.send("⚠️ Écris un mot ! Exemple : `!mot dragon`", delete_after=6)
        return

    if _normalize(tentative) == _normalize(game["word"]):
        # Victoire !
        game["task"].cancel()
        _pendu_games.pop(gid, None)
        await _award_xp(ctx.guild, ctx.author, 150)
        embed = discord.Embed(
            title="🎉 Bravo — Mot trouvé d'un seul coup !",
            description=(
                f"Le mot était : **{game['word']}**\n"
                f"🏆 +**150 XP** attribués à {ctx.author.mention} !"
            ),
            color=0x2ECC71,
            timestamp=now_utc(),
        )
        await ctx.send(embed=embed)
    else:
        game["erreurs"] += 1
        if game["erreurs"] >= MAX_ERREURS:
            game["task"].cancel()
            mot = game["word"]
            _pendu_games.pop(gid, None)
            embed = discord.Embed(
                title="💀 Mauvaise tentative — et le pendu est mort !",
                color=0xE74C3C,
                timestamp=now_utc(),
            )
            embed.description = (
                PENDU_STAGES[MAX_ERREURS]
                + f"\n\nLe mot était : **{mot}**"
            )
            await ctx.send(embed=embed)
        else:
            embed = _build_pendu_embed(game)
            embed.set_author(name=f"❌ « {tentative} » — ce n'est pas le bon mot !")
            await ctx.send(embed=embed)


@bot.hybrid_command(name="pendustop")
async def pendustop_cmd(ctx):
    if not is_staff(ctx.author):
        await ctx.send("❌ Cette commande est réservée au **staff**.", delete_after=6)
        return
    gid  = ctx.guild.id
    game = _pendu_games.pop(gid, None)
    if not game:
        await ctx.send("❌ Aucune partie de pendu en cours.", delete_after=6)
        return
    game["task"].cancel()
    await ctx.send(
        f"🛑 Partie arrêtée par le staff.\nLe mot était : **{game['word']}**",
        delete_after=20,
    )


# ═══════════════════════════════════════════════════════════════
# ███╗   ███╗ ██████╗ ██████╗ ██████╗ ██╗ ██████╗ ███╗   ██╗
# ████╗ ████║██╔═══██╗██╔══██╗██╔══██╗██║██╔═══██╗████╗  ██║
# ██╔████╔██║██║   ██║██████╔╝██████╔╝██║██║   ██║██╔██╗ ██║
# ██║╚██╔╝██║██║   ██║██╔══██╗██╔═══╝ ██║██║   ██║██║╚██╗██║
# ██║ ╚═╝ ██║╚██████╔╝██║  ██║██║     ██║╚██████╔╝██║ ╚████║
# ╚═╝     ╚═╝ ╚═════╝ ╚═╝  ╚═╝╚═╝     ╚═╝ ╚═════╝ ╚═╝  ╚═══╝
# ═══════════════════════════════════════════════════════════════

SYMBOLES = {1: "❌", 2: "⭕"}

# Mapping index → emoji de direction pour les cases vides
CASES_LABEL = {
    0: "↖", 1: "⬆", 2: "↗",
    3: "◀", 4: "⏺", 5: "▶",
    6: "↙", 7: "⬇", 8: "↘",
}

GAGNANT_COMBOS = [
    {0, 1, 2}, {3, 4, 5}, {6, 7, 8},  # lignes
    {0, 3, 6}, {1, 4, 7}, {2, 5, 8},  # colonnes
    {0, 4, 8}, {2, 4, 6},              # diagonales
]


def _check_winner(board: list) -> Optional[int]:
    for combo in GAGNANT_COMBOS:
        vals = [board[i] for i in combo]
        if vals[0] != 0 and all(v == vals[0] for v in vals):
            return vals[0]
    return None


def _board_full(board: list) -> bool:
    return all(c != 0 for c in board)


def _new_morpion_game(p1_id: int, p2_id: int) -> dict:
    return {
        "players": {1: p1_id, 2: p2_id},
        "board":   [0] * 9,
        "turn":    1,
        "task":    None,
        "msg":     None,
    }


def _build_morpion_embed(game: dict, titre_extra: str = "") -> discord.Embed:
    p1_id = game["players"][1]
    p2_id = game["players"][2]
    turn  = game["turn"]

    if titre_extra:
        title = f"❌⭕ Morpion — {titre_extra}"
        color = 0x2ECC71
    else:
        current_id = game["players"][turn]
        title = f"❌⭕ Morpion — Tour de <@{current_id}> {SYMBOLES[turn]}"
        color = 0x9B59B6

    embed = discord.Embed(title=title, color=color, timestamp=now_utc())
    embed.add_field(
        name="Joueurs",
        value=f"❌ <@{p1_id}> **vs** ⭕ <@{p2_id}>",
        inline=False,
    )
    embed.set_footer(text="Clique sur une case pour jouer · Timeout 5 min")
    return embed


async def _morpion_timeout_task(guild_id: int):
    await asyncio.sleep(300)  # 5 min
    game = _morpion_games.pop(guild_id, None)
    if game and game.get("msg"):
        try:
            embed = discord.Embed(
                title="⏰ Morpion — Temps écoulé !",
                description="La partie a été annulée faute d'activité.",
                color=0xE74C3C,
            )
            await game["msg"].edit(embed=embed, view=None)
        except Exception:
            pass


class MorpionView(discord.ui.View):
    def __init__(self, game: dict):
        super().__init__(timeout=300)
        self.game = game
        self._rebuild()

    def _rebuild(self):
        self.clear_items()
        board = self.game["board"]
        for i in range(9):
            val = board[i]
            if val == 0:
                btn = discord.ui.Button(
                    label=CASES_LABEL[i],
                    style=discord.ButtonStyle.grey,
                    row=i // 3,
                    custom_id=f"mrp_{i}",
                )
            elif val == 1:
                btn = discord.ui.Button(
                    label="❌",
                    style=discord.ButtonStyle.red,
                    row=i // 3,
                    custom_id=f"mrp_{i}",
                    disabled=True,
                )
            else:
                btn = discord.ui.Button(
                    label="⭕",
                    style=discord.ButtonStyle.blurple,
                    row=i // 3,
                    custom_id=f"mrp_{i}",
                    disabled=True,
                )
            btn.callback = self._make_cb(i)
            self.add_item(btn)

    def _make_cb(self, index: int):
        async def callback(interaction: discord.Interaction):
            game = self.game
            gid  = interaction.guild.id

            # Vérifier que c'est le bon joueur
            current_id = game["players"][game["turn"]]
            if interaction.user.id != current_id:
                await interaction.response.send_message(
                    "❌ Ce n'est pas ton tour !", ephemeral=True
                )
                return

            # Case déjà jouée (sécurité)
            if game["board"][index] != 0:
                await interaction.response.send_message(
                    "❌ Cette case est déjà prise !", ephemeral=True
                )
                return

            game["board"][index] = game["turn"]
            winner = _check_winner(game["board"])

            if winner:
                game["task"].cancel()
                _morpion_games.pop(gid, None)

                gagnant = interaction.guild.get_member(game["players"][winner])
                perdant_turn = 1 if winner == 2 else 2
                perdant = interaction.guild.get_member(game["players"][perdant_turn])

                if gagnant:
                    await _award_xp(interaction.guild, gagnant, 50)

                self._disable_all()
                embed = _build_morpion_embed(
                    game,
                    f"🏆 {gagnant.display_name if gagnant else '?'} gagne ! (+50 XP)",
                )

                revanche = RevancheView(
                    game["players"][1],
                    game["players"][2],
                    gid,
                )
                await interaction.response.edit_message(embed=embed, view=revanche)
                revanche.message = interaction.message

            elif _board_full(game["board"]):
                game["task"].cancel()
                _morpion_games.pop(gid, None)
                self._disable_all()
                embed = _build_morpion_embed(game, "🤝 Match nul !")
                embed.color = 0xF39C12
                await interaction.response.edit_message(embed=embed, view=None)

            else:
                game["turn"] = 2 if game["turn"] == 1 else 1
                self._rebuild()
                embed = _build_morpion_embed(game)
                await interaction.response.edit_message(embed=embed, view=self)

        return callback

    def _disable_all(self):
        for item in self.children:
            item.disabled = True

    async def on_timeout(self):
        gid = None
        for g_id, g in list(_morpion_games.items()):
            if g is self.game:
                gid = g_id
                break
        if gid:
            _morpion_games.pop(gid, None)
        self._disable_all()
        try:
            await self.game["msg"].edit(
                embed=discord.Embed(
                    title="⏰ Morpion — Temps écoulé !",
                    color=0xE74C3C,
                ),
                view=self,
            )
        except Exception:
            pass


class RevancheView(discord.ui.View):
    def __init__(self, p1_id: int, p2_id: int, guild_id: int):
        super().__init__(timeout=60)
        self.p1_id    = p1_id
        self.p2_id    = p2_id
        self.guild_id = guild_id
        self.message  = None

    @discord.ui.button(label="🔄 Revanche !", style=discord.ButtonStyle.green)
    async def revanche(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in (self.p1_id, self.p2_id):
            await interaction.response.send_message(
                "❌ Seuls les joueurs peuvent demander une revanche.", ephemeral=True
            )
            return
        if self.guild_id in _morpion_games:
            await interaction.response.send_message(
                "⚠️ Une partie est déjà en cours.", ephemeral=True
            )
            return

        # Le perdant commence (inverser les joueurs)
        game = _new_morpion_game(self.p2_id, self.p1_id)
        task = asyncio.create_task(_morpion_timeout_task(self.guild_id))
        game["task"] = task
        _morpion_games[self.guild_id] = game

        view  = MorpionView(game)
        embed = _build_morpion_embed(game, "🔄 Revanche !")
        embed.color = 0x9B59B6
        await interaction.response.edit_message(embed=embed, view=view)
        game["msg"] = interaction.message
        view.game["msg"] = interaction.message

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        try:
            if self.message:
                await self.message.edit(view=self)
        except Exception:
            pass


class _ConfirmMorpionView(discord.ui.View):
    def __init__(self, challenger_id: int, challenged_id: int):
        super().__init__(timeout=60)
        self.challenger_id = challenger_id
        self.challenged_id = challenged_id
        self.accepted      = False
        self.message       = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.challenged_id:
            await interaction.response.send_message(
                "❌ Seul l'adversaire peut répondre à cette invitation.",
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.button(label="✅ Accepter", style=discord.ButtonStyle.green)
    async def accepter(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.accepted = True
        self.stop()
        await interaction.response.defer()

    @discord.ui.button(label="❌ Refuser", style=discord.ButtonStyle.red)
    async def refuser(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.accepted = False
        self.stop()
        await interaction.response.defer()

    async def on_timeout(self):
        self.accepted = False
        self.stop()
        if self.message:
            try:
                await self.message.edit(
                    embed=discord.Embed(
                        title="⏰ Invitation expirée.",
                        description="L'adversaire n'a pas répondu dans les temps.",
                        color=0x95A5A6,
                    ),
                    view=None,
                )
            except Exception:
                pass


# ── Commandes Morpion ────────────────────────────────────────────────────────

@bot.hybrid_command(name="morpion")
async def morpion_cmd(ctx, adversaire: discord.Member = None):
    gid = ctx.guild.id

    if gid in _morpion_games:
        await ctx.send("⚠️ Une partie de morpion est déjà en cours !", delete_after=10)
        return

    if not adversaire:
        await ctx.send(
            "❌ Mentionne un adversaire ! Exemple : `!morpion @pseudo`",
            delete_after=8,
        )
        return
    if adversaire.bot:
        await ctx.send("❌ Impossible de jouer contre un bot.", delete_after=8)
        return
    if adversaire.id == ctx.author.id:
        await ctx.send("❌ Tu ne peux pas jouer contre toi-même.", delete_after=8)
        return

    # Invitation avec confirmation
    inv_embed = discord.Embed(
        title="❌⭕ Invitation Morpion",
        description=(
            f"{ctx.author.mention} te défie au **Morpion** !\n\n"
            f"Acceptes-tu le défi ?"
        ),
        color=0x9B59B6,
    )
    confirm_view = _ConfirmMorpionView(ctx.author.id, adversaire.id)
    confirm_msg  = await ctx.send(
        content=adversaire.mention,
        embed=inv_embed,
        view=confirm_view,
    )
    confirm_view.message = confirm_msg

    await confirm_view.wait()

    if not confirm_view.accepted:
        try:
            await confirm_msg.edit(
                embed=discord.Embed(
                    title="❌ Invitation refusée.",
                    color=0xE74C3C,
                ),
                view=None,
            )
        except Exception:
            pass
        return

    if gid in _morpion_games:
        try:
            await confirm_msg.edit(
                embed=discord.Embed(
                    title="⚠️ Une partie a démarré entre-temps.",
                    color=0xE67E22,
                ),
                view=None,
            )
        except Exception:
            pass
        return

    game = _new_morpion_game(ctx.author.id, adversaire.id)
    task = asyncio.create_task(_morpion_timeout_task(gid))
    game["task"] = task
    _morpion_games[gid] = game

    view  = MorpionView(game)
    embed = _build_morpion_embed(game)
    msg   = await ctx.send(embed=embed, view=view)
    game["msg"] = msg
    view.game["msg"] = msg

    try:
        await confirm_msg.delete()
    except Exception:
        pass


@bot.hybrid_command(name="morpionstop")
async def morpionstop_cmd(ctx):
    if not is_staff(ctx.author):
        await ctx.send("❌ Cette commande est réservée au **staff**.", delete_after=6)
        return

    gid  = ctx.guild.id
    game = _morpion_games.pop(gid, None)
    if not game:
        await ctx.send("❌ Aucune partie de morpion en cours.", delete_after=6)
        return

    if game.get("task"):
        game["task"].cancel()
    if game.get("msg"):
        try:
            await game["msg"].edit(
                embed=discord.Embed(
                    title="🛑 Morpion arrêté par le staff.",
                    color=0xE74C3C,
                ),
                view=None,
            )
        except Exception:
            pass
    await ctx.send("🛑 Partie de morpion arrêtée.", delete_after=15)
