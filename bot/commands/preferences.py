"""
commands/preferences.py — !preferences : notifs DM (giveaway/candidature) + mode d'embed.

Ajouté pour la QoL "UX / Discord natif" :
  - notifications DM opt-in pour giveaways gagnés / candidature vendeur traitée
  - mode d'embed "compact" pour mobile (moins de champs, plus condensé)
"""
import discord

from bot.core import bot
from bot.utils.prefs import get_prefs, set_pref


class _PreferencesView(discord.ui.View):
    def __init__(self, guild_id: int, user_id: int):
        super().__init__(timeout=120)
        self.guild_id = guild_id
        self.user_id  = user_id
        self._sync_labels()

    def _sync_labels(self):
        prefs = get_prefs(self.guild_id, self.user_id)
        self.toggle_giveaway.label    = f"🎉 DM giveaways : {'ON' if prefs['dm_giveaway'] else 'OFF'}"
        self.toggle_candidature.label = f"🛒 DM candidature : {'ON' if prefs['dm_candidature'] else 'OFF'}"
        self.toggle_embed.label       = f"📱 Embed : {'Compact' if prefs['embed_mode'] == 'compact' else 'Complet'}"

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user_id

    def _build_embed(self) -> discord.Embed:
        prefs = get_prefs(self.guild_id, self.user_id)
        embed = discord.Embed(
            title="⚙️ Tes préférences",
            description=(
                "🎉 **DM giveaways** — reçois un message privé quand tu gagnes un giveaway\n"
                "🛒 **DM candidature** — reçois un message privé quand ta demande vendeur est traitée\n"
                "📱 **Embed compact** — affichage condensé, pratique sur mobile\n\n"
                f"État actuel :\n"
                f"• DM giveaways : **{'activé' if prefs['dm_giveaway'] else 'désactivé'}**\n"
                f"• DM candidature : **{'activé' if prefs['dm_candidature'] else 'désactivé'}**\n"
                f"• Mode embed : **{'compact' if prefs['embed_mode'] == 'compact' else 'complet'}**"
            ),
            color=0x3498DB,
        )
        return embed

    @discord.ui.button(label="🎉 DM giveaways", style=discord.ButtonStyle.blurple, row=0)
    async def toggle_giveaway(self, interaction: discord.Interaction, button: discord.ui.Button):
        prefs = get_prefs(self.guild_id, self.user_id)
        set_pref(self.guild_id, self.user_id, dm_giveaway=not prefs["dm_giveaway"])
        self._sync_labels()
        await interaction.response.edit_message(embed=self._build_embed(), view=self)

    @discord.ui.button(label="🛒 DM candidature", style=discord.ButtonStyle.blurple, row=0)
    async def toggle_candidature(self, interaction: discord.Interaction, button: discord.ui.Button):
        prefs = get_prefs(self.guild_id, self.user_id)
        set_pref(self.guild_id, self.user_id, dm_candidature=not prefs["dm_candidature"])
        self._sync_labels()
        await interaction.response.edit_message(embed=self._build_embed(), view=self)

    @discord.ui.button(label="📱 Embed", style=discord.ButtonStyle.grey, row=1)
    async def toggle_embed(self, interaction: discord.Interaction, button: discord.ui.Button):
        prefs   = get_prefs(self.guild_id, self.user_id)
        nouveau = "full" if prefs["embed_mode"] == "compact" else "compact"
        set_pref(self.guild_id, self.user_id, embed_mode=nouveau)
        self._sync_labels()
        await interaction.response.edit_message(embed=self._build_embed(), view=self)


@bot.command(name="preferences", aliases=["prefs", "notifdm", "embedmode"])
async def preferences_cmd(ctx):
    """Ouvre le panneau de préférences personnelles (DM + affichage)."""
    view = _PreferencesView(ctx.guild.id, ctx.author.id)
    await ctx.send(embed=view._build_embed(), view=view)
