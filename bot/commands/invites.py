from bot.utils.invites import db_get_invitations
from bot.utils.helpers import now_utc
import difflib

import discord

from bot.core import bot

@bot.command(name="invite")
async def invite_cmd(ctx, *, pseudo: str = None):
    """
    Affiche le nombre d'invitations d'un joueur et la liste des membres invités.
    Usage : !invite [pseudo]
    """
    if pseudo is None:
        await ctx.send("❌ `!invite [pseudo]`\nExemple : `!invite LGM`", delete_after=8)
        return

    guild      = ctx.guild
    pseudo_low = pseudo.lower().strip()
    cible      = None

    # Exact → commence par → contient → fuzzy
    cible = discord.utils.find(
        lambda m: m.display_name.lower() == pseudo_low or m.name.lower() == pseudo_low,
        guild.members
    )
    if cible is None:
        cible = discord.utils.find(
            lambda m: m.display_name.lower().startswith(pseudo_low) or m.name.lower().startswith(pseudo_low),
            guild.members
        )
    if cible is None:
        cible = discord.utils.find(
            lambda m: pseudo_low in m.display_name.lower() or pseudo_low in m.name.lower(),
            guild.members
        )
    if cible is None:
        best_score, best_member = 0.0, None
        for m in guild.members:
            score = max(
                difflib.SequenceMatcher(None, pseudo_low, m.display_name.lower()).ratio(),
                difflib.SequenceMatcher(None, pseudo_low, m.name.lower()).ratio()
            )
            if score > best_score:
                best_score, best_member = score, m
        if best_score >= 0.5:
            cible = best_member

    if cible is None:
        await ctx.send(embed=discord.Embed(
            title="❌ Joueur introuvable",
            description=f"Aucun membre trouvé pour **{pseudo}**.",
            color=0xE74C3C
        ), delete_after=8)
        return

    invitations = db_get_invitations(guild.id, cible.id)
    total       = len(invitations)

    embed = discord.Embed(
        title=f"📨 Invitations de {cible.display_name}",
        color=cible.color if cible.color != discord.Color.default() else 0x3498DB,
        timestamp=now_utc()
    )
    embed.set_thumbnail(url=cible.display_avatar.url)
    embed.add_field(
        name="📊 Total d'invitations",
        value=f"**{total}** membre(s) invité(s)",
        inline=False
    )

    if not invitations:
        embed.add_field(
            name="👥 Membres invités",
            value="_Ce joueur n'a invité personne pour l'instant._",
            inline=False
        )
    else:
        lignes = []
        for inv in invitations:
            m      = guild.get_member(inv["invited_id"])
            nom    = m.display_name if m else inv["invited_name"]
            statut = "✅" if m else "❌ (parti)"
            dt     = datetime.fromtimestamp(inv["joined_at"], tz=timezone.utc)
            lignes.append(f"{statut} **{nom}** — rejoint le {discord.utils.format_dt(dt, style='d')}")

        chunk, chunks = "", []
        for l in lignes:
            if len(chunk) + len(l) + 1 > 1000:
                chunks.append(chunk)
                chunk = l
            else:
                chunk = (chunk + "\n" + l).strip()
        if chunk:
            chunks.append(chunk)

        for idx, c in enumerate(chunks):
            embed.add_field(
                name="👥 Membres invités" if idx == 0 else "\u200b",
                value=c,
                inline=False
            )

    embed.set_footer(text=f"✅ = encore présent · ❌ = a quitté · Demandé par {ctx.author.display_name}")
    await ctx.send(embed=embed)
