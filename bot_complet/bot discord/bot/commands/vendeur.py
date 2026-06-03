import asyncio
import discord

from bot.core import bot

from bot.views.vendeur_view import VendeurView
from bot.modals.vendeur_modal import VendeurModal
from bot.utils.permissions import is_staff
from bot.utils.config import cfg_channel, cfg_role
from bot.utils.helpers import now_utc
from bot.utils.logs import send_log
from bot.utils.tickets import send_ticket_log

@bot.command(name="vendeur")
async def vendeur_cmd(ctx):
    """Poste l'embed de candidature Vendeur Certifié dans le salon dédié."""
    if not is_staff(ctx.author):
        await ctx.send("❌ Réservé au staff.", delete_after=5)
        return

    # Priorité : salon_vendeur → fallback salon_role_toggle
    channel = cfg_channel(ctx.guild, "salon_vendeur")
    if not channel:
        channel = cfg_channel(ctx.guild, "salon_role_toggle")
    if not channel:
        await ctx.send(
            "❌ Aucun salon configuré. Configure `salon_vendeur` via `!config` → 🔊 Salons.",
            delete_after=8
        )
        return

    embed = discord.Embed(
        title="🛒 Devenir Vendeur Certifié",
        description=(
            "Tu veux vendre tes ressources sur le marché de la Mystic ?\n\n"
            "**Clique sur le bouton ci-dessous** pour soumettre ta candidature.\n"
            "Un formulaire s'ouvrira et un ticket sera créé automatiquement.\n\n"
            "**Avantages du rôle Vendeur Certifié :**\n"
            "• Accès aux commandes `!catalogue`, `!gestion`, `!vendu`\n"
            "• Ton stock visible dans le catalogue officiel\n"
            "• Accès au salon de gestion de stock\n\n"
            "📋 Un staff examinera ta demande et te contactera dans le ticket."
        ),
        color=0xF1C40F
    )
    embed.set_footer(text="La Mystic — Système de marché")
    await channel.send(embed=embed, view=VendeurView())
    await ctx.send(f"✅ Embed vendeur posté dans {channel.mention} !", delete_after=5)


@bot.command(name="accepter")
async def accepter_cmd(ctx, *, raison: str = "Demande acceptée par le staff."):
    """Accepte une demande vendeur dans un ticket vendeur."""
    if not is_staff(ctx.author):
        await ctx.send("❌ Réservé au staff.", delete_after=5)
        return
    topic = getattr(ctx.channel, "topic", None) or ""
    if not topic.startswith("vendeur_certifie"):
        await ctx.send("❌ Cette commande s'utilise uniquement dans un **ticket vendeur**.", delete_after=6)
        return

    parts  = topic.split("|")
    try:
        membre_id = int(parts[1]) if len(parts) > 1 else None
    except ValueError:
        membre_id = None

    membre = ctx.guild.get_member(membre_id) if membre_id else None

    # Attribuer le rôle vendeur
    role_vendeur = cfg_role(ctx.guild, "role_vendeur")
    if role_vendeur and membre:
        try:
            await membre.add_roles(role_vendeur, reason=f"Vendeur certifié accepté par {ctx.author}")
        except Exception as e:
            await ctx.send(f"⚠️ Impossible d'attribuer le rôle : {e}", delete_after=8)

    embed = discord.Embed(
        title="✅ Demande acceptée !",
        description=(
            f"{membre.mention if membre else 'Le membre'} est maintenant **Vendeur Certifié** !\n\n"
            f"📝 **Raison :** {raison}\n"
            f"🛡️ **Staff :** {ctx.author.mention}\n\n"
            "Le ticket sera fermé dans **10 secondes**."
        ),
        color=0x2ECC71,
        timestamp=now_utc()
    )
    await ctx.send(embed=embed)

    # Log
    await send_log(ctx.guild, discord.Embed(
        title="✅ Vendeur Certifié — Demande acceptée",
        description=f"{membre.mention if membre else f'ID {membre_id}'} accepté par {ctx.author.mention}\nRaison : {raison}",
        color=0x2ECC71,
        timestamp=now_utc()
    ))

    await asyncio.sleep(10)
    await send_ticket_log(ctx.guild, ctx.channel, ctx.author)
    try:
        await ctx.channel.delete(reason="Demande vendeur acceptée")
    except Exception:
        pass


@bot.command(name="refuser")
async def refuser_cmd(ctx, *, raison: str = "Demande refusée par le staff."):
    """Refuse une demande vendeur dans un ticket vendeur."""
    if not is_staff(ctx.author):
        await ctx.send("❌ Réservé au staff.", delete_after=5)
        return
    topic = getattr(ctx.channel, "topic", None) or ""
    if not topic.startswith("vendeur_certifie"):
        await ctx.send("❌ Cette commande s'utilise uniquement dans un **ticket vendeur**.", delete_after=6)
        return

    parts = topic.split("|")
    try:
        membre_id = int(parts[1]) if len(parts) > 1 else None
    except ValueError:
        membre_id = None

    membre = ctx.guild.get_member(membre_id) if membre_id else None

    embed = discord.Embed(
        title="❌ Demande refusée",
        description=(
            f"{membre.mention if membre else 'Le membre'}, ta demande de **Vendeur Certifié** a été refusée.\n\n"
            f"📝 **Raison :** {raison}\n"
            f"🛡️ **Staff :** {ctx.author.mention}\n\n"
            "Tu peux réessayer plus tard. Le ticket sera fermé dans **10 secondes**."
        ),
        color=0xE74C3C,
        timestamp=now_utc()
    )
    await ctx.send(embed=embed)

    # Log
    await send_log(ctx.guild, discord.Embed(
        title="❌ Vendeur Certifié — Demande refusée",
        description=f"{membre.mention if membre else f'ID {membre_id}'} refusé par {ctx.author.mention}\nRaison : {raison}",
        color=0xE74C3C,
        timestamp=now_utc()
    ))

    await asyncio.sleep(10)
    await send_ticket_log(ctx.guild, ctx.channel, ctx.author)
    try:
        await ctx.channel.delete(reason="Demande vendeur refusée")
    except Exception:
        pass