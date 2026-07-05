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

from bot.core import bot, active_giveaways
from bot.utils.helpers import now_utc


def build_giveaway_embed(gw):
    ends      = discord.utils.format_dt(datetime.fromtimestamp(gw["ends_at"], tz=timezone.utc), style="R")
    ends_full = discord.utils.format_dt(datetime.fromtimestamp(gw["ends_at"], tz=timezone.utc), style="F")
    nb          = len(gw["participants"])
    min_invites = gw.get("min_invites", 0)
    nb_gagnants = gw.get("nb_gagnants", 1)

    desc = f"🎁 **Récompense :** {gw['reward']}\n"
    desc += f"⏰ **Fin :** {ends_full} ({ends})\n"
    desc += f"👥 **Participants :** {nb}\n"
    if nb_gagnants > 1:
        desc += f"🏆 **Nombre de gagnants :** {nb_gagnants}\n"
    if min_invites > 0:
        desc += f"📨 **Condition :** avoir invité **{min_invites} membre(s) actif(s)** sur le serveur\n"
    desc += "\n> Clique sur **🎉 Participer** pour tenter ta chance !\n> Reclique pour **te retirer**."

    titre_emoji = "🎉"
    guild_id = gw.get("guild_id")
    if guild_id:
        guild = bot.get_guild(guild_id)
        if guild:
            from bot.utils.emojis import get_emoji
            titre_emoji = get_emoji(guild, "giveaway")

    embed = discord.Embed(
        title=f"{titre_emoji} GIVEAWAY EN COURS",
        description=desc,
        color=0xF1C40F
    )
    embed.set_footer(text=f"Organisé par {gw['host']}")
    return embed


PARTICIPANTS_PAR_PAGE = 20


class _ParticipantsView(discord.ui.View):
    """Vue éphémère paginée listant les participants d'un giveaway."""

    def __init__(self, guild: discord.Guild, participant_ids: list[int]):
        super().__init__(timeout=120)
        self.guild = guild
        # Dédupliqué, ordre d'inscription conservé
        self.ids  = list(dict.fromkeys(participant_ids))
        self.page = 0
        self.pages = [
            self.ids[i:i + PARTICIPANTS_PAR_PAGE]
            for i in range(0, len(self.ids), PARTICIPANTS_PAR_PAGE)
        ] or [[]]
        self._sync_buttons()

    def _sync_buttons(self):
        self.prev_page.disabled = self.page == 0
        self.next_page.disabled = self.page >= len(self.pages) - 1

    def build_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="👥 Participants au giveaway",
            description=f"**{len(self.ids)}** participant(s) · Page **{self.page + 1}**/**{len(self.pages)}**",
            color=0xF1C40F,
        )
        page_ids = self.pages[self.page]
        if not page_ids:
            embed.add_field(name="📭 Aucun participant", value="—", inline=False)
        else:
            lignes = []
            for i, uid in enumerate(page_ids, start=self.page * PARTICIPANTS_PAR_PAGE + 1):
                m = self.guild.get_member(uid)
                lignes.append(f"`{i}.` {m.mention if m else f'<@{uid}>'}")
            embed.add_field(name="📋 Liste", value="\n".join(lignes), inline=False)
        return embed

    @discord.ui.button(label="◀", style=discord.ButtonStyle.grey)
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page -= 1
        self._sync_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.grey)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page += 1
        self._sync_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)


class GiveawayView(discord.ui.View):
    def __init__(self, msg_id: int):
        super().__init__(timeout=None)
        self.msg_id = msg_id
        btn = discord.ui.Button(
            label="🎉 Participer",
            style=discord.ButtonStyle.green,
            custom_id=f"giveaway_participer_{msg_id}",
        )
        btn.callback = self._participer_callback
        self.add_item(btn)

        voir_btn = discord.ui.Button(
            label="👥 Voir les participants",
            style=discord.ButtonStyle.grey,
            custom_id=f"giveaway_participants_{msg_id}",
        )
        voir_btn.callback = self._voir_participants_callback
        self.add_item(voir_btn)

    async def _voir_participants_callback(self, interaction: discord.Interaction):
        gw = active_giveaways.get(self.msg_id)
        if not gw:
            await interaction.response.send_message("❌ Ce giveaway est terminé.", ephemeral=True)
            return
        view = _ParticipantsView(interaction.guild, gw.get("participants", []))
        await interaction.response.send_message(embed=view.build_embed(), view=view, ephemeral=True)

    async def _participer_callback(self, interaction: discord.Interaction):
        gw = active_giveaways.get(self.msg_id)
        if not gw:
            await interaction.response.send_message("❌ Ce giveaway est terminé.", ephemeral=True)
            return

        uid   = interaction.user.id
        guild = interaction.guild

        # ── Vérification condition d'invitations ──────────────────────────────
        min_invites = gw.get("min_invites", 0)
        if min_invites > 0:
            try:
                from bot.utils.invite_stats import count_active_invitations
                count = count_active_invitations(guild, uid)
                if count < min_invites:
                    await interaction.response.send_message(
                        f"❌ Tu ne remplis pas la condition pour participer.\n"
                        f"**Invitations requises :** {min_invites} · **Tes invitations actives :** {count}\n"
                        f"Invite des membres pour pouvoir participer !",
                        ephemeral=True
                    )
                    return
            except Exception as e:
                print(f"[GW] Erreur vérif invites : {e}")
                await interaction.response.send_message(
                    "❌ Impossible de vérifier tes invitations. Réessaie dans un instant.",
                    ephemeral=True
                )
                return

        # ── Inscription / désinscription ──────────────────────────────────────
        if uid in gw["participants"]:
            gw["participants"].remove(uid)
            await interaction.response.send_message("❌ Tu t'es retiré du giveaway.", ephemeral=True)
        else:
            gw["participants"].append(uid)
            nb_gagnants = gw.get("nb_gagnants", 1)
            msg_extra = f" ({nb_gagnants} gagnants seront tirés au sort)" if nb_gagnants > 1 else ""
            await interaction.response.send_message(
                f"✅ Tu participes au giveaway !{msg_extra}",
                ephemeral=True
            )

        try:
            msg = await interaction.channel.fetch_message(self.msg_id)
            await msg.edit(embed=build_giveaway_embed(gw))
        except Exception:
            pass
