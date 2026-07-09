"""
commands/indispo.py — !indispo : déclarer une indisponibilité.

Poste un embed avec un bouton "📝 Se déclarer indisponible" ; cliquer dessus
ouvre un formulaire (Modal) au format imposé. La soumission enregistre
l'indispo en base, met à jour l'embed épinglé du salon configuré
(salon_indispos via !config), et se retire toute seule à la date de fin
(voir utils/indispo_loop.py).
"""
import discord
from discord import app_commands

from bot.core import bot
from bot.utils.database import db_save_indispo, db_delete_indispo, db_get_indispo
from bot.utils.indispo import parse_date_fr, refresh_indispo_embed
from bot.utils.config import cfg_channel


class IndispoModal(discord.ui.Modal, title="🚫 Déclarer une indisponibilité"):
    date_debut = discord.ui.TextInput(
        label="Date de début",
        placeholder="ex: lundi 25 juillet",
        max_length=50,
    )
    date_fin = discord.ui.TextInput(
        label="Date de fin",
        placeholder="ex: samedi 30 juillet",
        max_length=50,
    )
    raison = discord.ui.TextInput(
        label="Raison",
        placeholder="ex: vacances",
        max_length=200,
    )
    partielle = discord.ui.TextInput(
        label="Disponibilité partielle ?",
        placeholder="oui / non",
        max_length=10,
    )
    presence_discord = discord.ui.TextInput(
        label="Présence Discord possible ?",
        placeholder="oui / non",
        max_length=10,
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            date_fin_ts = parse_date_fr(self.date_fin.value)
            db_save_indispo(
                interaction.guild.id,
                interaction.user.id,
                self.date_debut.value.strip(),
                self.date_fin.value.strip(),
                date_fin_ts,
                self.raison.value.strip(),
                self.partielle.value.strip(),
                self.presence_discord.value.strip(),
            )
            await refresh_indispo_embed(interaction.guild)

            avertissement = ""
            if date_fin_ts is None:
                avertissement = (
                    "\n\n⚠️ Je n'ai pas réussi à comprendre la date de fin — "
                    "elle ne se retirera pas automatiquement. Un staff pourra la retirer avec `!finindispo`."
                )
            await interaction.response.send_message(
                f"✅ Ton indisponibilité a bien été enregistrée !{avertissement}",
                ephemeral=True,
            )
        except Exception as e:
            print(f"[INDISPO] Erreur enregistrement : {e}")
            try:
                await interaction.response.send_message("❌ Erreur lors de l'enregistrement, réessaie.", ephemeral=True)
            except Exception:
                pass


class IndispoPromptView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="📝 Se déclarer indisponible", style=discord.ButtonStyle.blurple, custom_id="indispo_declarer")
    async def declarer(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(IndispoModal())


@bot.hybrid_command(name="indispo", aliases=["indisponible", "indisponibilite"])
async def indispo_cmd(ctx):
    """Déclare une période où tu ne seras pas disponible pour la faction."""
    channel = cfg_channel(ctx.guild, "salon_indispos")
    if not channel:
        await ctx.send(
            "❌ Aucun salon `salon_indispos` configuré. Configure-le via `!config` → 🚫 Indisponibilités.",
            delete_after=8,
        )
        return
    embed = discord.Embed(
        title="🚫 Déclarer une indisponibilité",
        description="Clique ci-dessous pour remplir le formulaire (dates, raison, disponibilité).",
        color=0xE67E22,
    )
    await ctx.send(embed=embed, view=IndispoPromptView())


@bot.hybrid_command(name="finindispo")
@app_commands.describe(membre="Le membre dont retirer l'indisponibilité (toi-même par défaut)")
async def finindispo_cmd(ctx, membre: discord.Member = None):
    """Retire une indisponibilité avant sa date de fin (la tienne, ou celle d'un membre si staff)."""
    from bot.utils.permissions import is_staff

    cible = membre or ctx.author
    if cible.id != ctx.author.id and not is_staff(ctx.author):
        await ctx.send("❌ Tu ne peux retirer que ta propre indisponibilité.", delete_after=5)
        return

    row = db_get_indispo(ctx.guild.id, cible.id)
    if not row:
        await ctx.send(f"ℹ️ {cible.mention} n'a aucune indisponibilité enregistrée.", delete_after=6)
        return

    db_delete_indispo(ctx.guild.id, cible.id)
    await refresh_indispo_embed(ctx.guild)
    await ctx.send(f"✅ Indisponibilité de {cible.mention} retirée.", delete_after=6)
