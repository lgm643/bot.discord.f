"""
commands/recherche_slash.py — /recherche : équivalent slash de !recherche, avec autocomplete.

Les commandes préfixe `!` ne supportent pas l'autocomplete côté Discord (c'est
une fonctionnalité réservée aux slash commands). Plutôt que de tout migrer,
on ajoute cette unique commande slash pour la recherche d'articles — c'est
l'endroit où l'autocomplete apporte le plus (retrouver un nom exact dans un
catalogue qui peut contenir des dizaines d'articles).
"""
import discord
from discord import app_commands

from bot.core import bot
from bot.utils.market import load_catalogue, fuzzy_search
from bot.utils.helpers import now_utc


async def _item_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    if not interaction.guild:
        return []
    data  = load_catalogue(interaction.guild.id)
    items = data.get("items", {})
    if not current:
        noms = sorted({v["nom"] for v in items.values()})[:25]
        return [app_commands.Choice(name=n[:100], value=n) for n in noms]
    res = fuzzy_search(current, items)
    noms_vus = []
    for key, (item, score) in res.items():
        if item["nom"] not in noms_vus:
            noms_vus.append(item["nom"])
        if len(noms_vus) >= 25:
            break
    return [app_commands.Choice(name=n[:100], value=n) for n in noms_vus]


@bot.tree.command(name="recherche", description="Rechercher un article dans le catalogue (avec autocomplete)")
@app_commands.describe(article="Nom de l'article — les suggestions apparaissent en tapant")
@app_commands.autocomplete(article=_item_autocomplete)
async def recherche_slash(interaction: discord.Interaction, article: str):
    data  = load_catalogue(interaction.guild.id)
    items = data.get("items", {})
    resultats_raw = fuzzy_search(article, items)
    if not resultats_raw:
        await interaction.response.send_message(f"❌ Aucun article trouvé pour **{article}**.", ephemeral=True)
        return

    embed = discord.Embed(title=f"🔍 Résultats pour « {article} »", color=0x9B59B6, timestamp=now_utc())
    for key, (item, score) in list(resultats_raw.items())[:10]:
        vendeur_m = interaction.guild.get_member(item["vendeur_id"])
        vnom      = vendeur_m.display_name if vendeur_m else f"<@{item['vendeur_id']}>"
        embed.add_field(
            name=f"🔹 {item['nom']}",
            value=f"📦 **Stock :** {item['quantite']}\n💰 **Prix :** {item['prix']}\n👤 {vnom}",
            inline=True,
        )
    embed.set_footer(text="Utilise !commande ou !recherche pour passer commande")
    await interaction.response.send_message(embed=embed, ephemeral=True)
