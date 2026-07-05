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
from bot.utils.prefs import wants_dm_candidature


async def _dm_candidat(membre: discord.Member, accepte: bool, raison: str):
    if not membre:
        return
    if not wants_dm_candidature(membre.guild.id, membre.id):
        return
    try:
        if accepte:
            await membre.send(f"✅ Ta demande de **Vendeur Certifié** sur **{membre.guild.name}** a été acceptée !\n📝 {raison}")
        else:
            await membre.send(f"❌ Ta demande de **Vendeur Certifié** sur **{membre.guild.name}** a été refusée.\n📝 {raison}")
    except discord.Forbidden:
        pass


async def process_acceptation(guild: discord.Guild, channel, membre_id: int | None, staff: discord.Member, raison: str):
    """Logique partagée entre `!accepter` et le bouton ✅ Accepter du ticket vendeur."""
    membre = guild.get_member(membre_id) if membre_id else None

    role_vendeur = cfg_role(guild, "role_vendeur")
    if role_vendeur and membre:
        try:
            await membre.add_roles(role_vendeur, reason=f"Vendeur certifié accepté par {staff}")
        except Exception as e:
            await channel.send(f"⚠️ Impossible d'attribuer le rôle : {e}", delete_after=8)

    embed = discord.Embed(
        title="✅ Demande acceptée !",
        description=(
            f"{membre.mention if membre else 'Le membre'} est maintenant **Vendeur Certifié** !\n\n"
            f"📝 **Raison :** {raison}\n"
            f"🛡️ **Staff :** {staff.mention}\n\n"
            "Le ticket sera fermé dans **10 secondes**."
        ),
        color=0x2ECC71,
        timestamp=now_utc()
    )
    await channel.send(embed=embed)
    await _dm_candidat(membre, True, raison)

    await send_log(guild, discord.Embed(
        title="✅ Vendeur Certifié — Demande acceptée",
        description=f"{membre.mention if membre else f'ID {membre_id}'} accepté par {staff.mention}\nRaison : {raison}",
        color=0x2ECC71,
        timestamp=now_utc()
    ))

    await asyncio.sleep(10)
    await send_ticket_log(guild, channel, staff)
    try:
        await channel.delete(reason="Demande vendeur acceptée")
    except Exception:
        pass


async def process_refus(guild: discord.Guild, channel, membre_id: int | None, staff: discord.Member, raison: str):
    """Logique partagée entre `!refuser` et le bouton ❌ Refuser du ticket vendeur."""
    membre = guild.get_member(membre_id) if membre_id else None

    embed = discord.Embed(
        title="❌ Demande refusée",
        description=(
            f"{membre.mention if membre else 'Le membre'}, ta demande de **Vendeur Certifié** a été refusée.\n\n"
            f"📝 **Raison :** {raison}\n"
            f"🛡️ **Staff :** {staff.mention}\n\n"
            "Tu peux réessayer plus tard. Le ticket sera fermé dans **10 secondes**."
        ),
        color=0xE74C3C,
        timestamp=now_utc()
    )
    await channel.send(embed=embed)
    await _dm_candidat(membre, False, raison)

    await send_log(guild, discord.Embed(
        title="❌ Vendeur Certifié — Demande refusée",
        description=f"{membre.mention if membre else f'ID {membre_id}'} refusé par {staff.mention}\nRaison : {raison}",
        color=0xE74C3C,
        timestamp=now_utc()
    ))

    await asyncio.sleep(10)
    await send_ticket_log(guild, channel, staff)
    try:
        await channel.delete(reason="Demande vendeur refusée")
    except Exception:
        pass


def parse_membre_id_from_topic(topic: str) -> int | None:
    parts = (topic or "").split("|")
    try:
        return int(parts[1]) if len(parts) > 1 else None
    except ValueError:
        return None


@bot.hybrid_command(name="vendeur")
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


@bot.hybrid_command(name="accepter")
async def accepter_cmd(ctx, *, raison: str = "Demande acceptée par le staff."):
    """Accepte une demande vendeur dans un ticket vendeur. (Astuce : un bouton ✅ fait pareil sans taper de commande.)"""
    if not is_staff(ctx.author):
        await ctx.send("❌ Réservé au staff.", delete_after=5)
        return
    topic = getattr(ctx.channel, "topic", None) or ""
    if not topic.startswith("vendeur_certifie"):
        await ctx.send("❌ Cette commande s'utilise uniquement dans un **ticket vendeur**.", delete_after=6)
        return
    membre_id = parse_membre_id_from_topic(topic)
    await process_acceptation(ctx.guild, ctx.channel, membre_id, ctx.author, raison)


@bot.hybrid_command(name="refuser")
async def refuser_cmd(ctx, *, raison: str = "Demande refusée par le staff."):
    """Refuse une demande vendeur dans un ticket vendeur. (Astuce : un bouton ❌ fait pareil sans taper de commande.)"""
    if not is_staff(ctx.author):
        await ctx.send("❌ Réservé au staff.", delete_after=5)
        return
    topic = getattr(ctx.channel, "topic", None) or ""
    if not topic.startswith("vendeur_certifie"):
        await ctx.send("❌ Cette commande s'utilise uniquement dans un **ticket vendeur**.", delete_after=6)
        return
    membre_id = parse_membre_id_from_topic(topic)
    await process_refus(ctx.guild, ctx.channel, membre_id, ctx.author, raison)