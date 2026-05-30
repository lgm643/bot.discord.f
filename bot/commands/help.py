import discord

from bot.core import bot

from bot.views.help_view import HelpView
from bot.utils.permissions import is_staff

bot.remove_command("help")

def _help_embed_accueil(is_staff_user: bool) -> discord.Embed:
    embed = discord.Embed(
        title="📖 Aide — La Mystic Bot",
        description=(
            "Bienvenue dans l'aide du bot !\n"
            "Utilise le **menu déroulant** ci-dessous pour naviguer.\n\n"
            "**Légende :**\n"
            "🔒 Réservé au **Staff**\n"
            "🏷️ Réservé aux **Vendeurs certifiés** (ou Staff)\n"
            "👤 Accessible à **tous les membres**\n\n"
            "**Catégories disponibles :**\n"
            "👤 Général · 📨 Invitations · 🎫 Tickets · 🏪 Marché\n"
            "🎮 Mini-jeux · 🛡️ Protections" +
            ("\n🔨 Modération · ⚙️ Configuration" if is_staff_user else "")
        ),
        color=0x9B59B6
    )
    embed.set_footer(text="Sélectionne une catégorie dans le menu · Timeout 5 minutes")
    return embed


def _help_embed_general() -> discord.Embed:
    embed = discord.Embed(title="👤 Général", color=0x3498DB)
    embed.add_field(
        name="📊 `!level` · alias : `!lvl` `!xp`",
        value="Affiche ton niveau, XP, messages et temps vocal.\n**Usage :** `!level` ou `!level @membre`",
        inline=False
    )
    embed.add_field(
        name="🏆 `!classement` · alias : `!top` `!leaderboard` `!lb` `!rang` `!ranking`",
        value="Top 10 par messages, niveau, vocal et faction. La section **Top Faction** utilise automatiquement les rôles configurés dans le roster (`!config` → 🎖️ Roster).",
        inline=False
    )
    embed.add_field(
        name="🔍 `!info` · alias : `!profil` `!whois` `!user` `!membre`",
        value="Infos complètes d'un membre : rôles, statut, dates, permissions.\n**Usage :** `!info` ou `!info @membre`",
        inline=False
    )
    embed.add_field(
        name="🪙 `!pileouface` · alias : `!pof` `!coinflip`",
        value="Lance une pièce — Pile ou Face ? Résultat aléatoire instantané.",
        inline=False
    )
    embed.add_field(
        name="📣 `!pub` 🔒",
        value="Envoie le message de recrutement de la faction dans le salon actuel.",
        inline=False
    )
    embed.add_field(
        name="📣 `!say #salon message` · alias : `!dit` 🔒",
        value="Fait parler le bot dans n'importe quel salon.\n**Usage :** `!say #général Bonsoir !`",
        inline=False
    )
    embed.add_field(
        name="🎁 `!avantages` 🔒",
        value=(
            "Affiche l'embed des avantages membres de la faction.\n"
            "Posté dans le `salon_avantages` configuré, ou dans le salon actuel si non configuré."
        ),
        inline=False
    )
    embed.add_field(
        name="📖 `!help` · alias : `!aide` `!commandes`",
        value="Affiche ce menu d'aide interactif.",
        inline=False
    )
    embed.set_footer(text="👤 = accessible à tous sauf mentions 🔒")
    return embed


def _help_embed_invitations() -> discord.Embed:
    embed = discord.Embed(title="📨 Invitations", color=0x2ECC71)
    embed.add_field(
        name="📨 `!invite <pseudo>`",
        value=(
            "Affiche le nombre de membres invités par un joueur et la liste complète.\n"
            "**Usage :** `!invite LGM`\n"
            "✅ = encore présent · ❌ = parti\n"
            "Recherche floue : `LG` peut trouver `LGM`."
        ),
        inline=False
    )
    embed.add_field(
        name="🏆 `!topinvites`",
        value="Classement des **10 meilleurs inviteurs** (invitations actives — membres encore présents).",
        inline=False,
    )
    embed.add_field(
        name="🐦‍🔥 Paliers & récompenses",
        value=(
            "**5** invitations actives → Initié (−5% market)\n"
            "**10** → Marchand Elite (−10%)\n"
            "**20** → Maître Phénix (−20%)\n"
            "Rôles et logs configurables via `!config`."
        ),
        inline=False,
    )
    embed.add_field(
        name="📋 Logs automatiques",
        value=(
            "À chaque arrivée, un embed est envoyé dans les logs :\n"
            "• ✅ **Pseudo** a été invité par **Pseudo** (+ total invitations)\n"
            "• ⚠️ **Invitant inconnu** si lien vanity, DM Discord ou permission manquante"
        ),
        inline=False
    )
    embed.set_footer(text="👤 = accessible à tous")
    return embed


def _help_embed_tickets() -> discord.Embed:
    embed = discord.Embed(title="🎫 Tickets & Vendeur", color=0xE67E22)
    embed.add_field(
        name="🎫 `!ticket` · alias : `!tickets` `!support` 🔒",
        value=(
            "Poste le panneau de tickets avec 2 boutons :\n"
            "• **📋 Demande de recrutement** → ticket + formulaire complet\n"
            "• **📩 Autre demande** → ticket libre"
        ),
        inline=False
    )
    embed.add_field(
        name="🔒 `!fermer` · alias : `!close` `!closeticket`",
        value=(
            "Ferme le ticket actuel (30s de confirmation).\n"
            "Un **transcript HTML** est sauvegardé automatiquement dans les logs.\n"
            "Fonctionne aussi dans les tickets vendeur."
        ),
        inline=False
    )
    embed.add_field(
        name="🛒 `!vendeur` 🔒",
        value=(
            "Poste l'embed **Devenir Vendeur Certifié** dans le salon configuré.\n"
            "Les membres cliquent → formulaire → ticket créé automatiquement.\n"
            "Configure le salon via `!config` → 🔊 Salons → `salon_vendeur`."
        ),
        inline=False
    )
    embed.add_field(
        name="✅ `!accepter [raison]` 🔒",
        value=(
            "Dans un ticket vendeur : accepte la demande et attribue le rôle **Vendeur Certifié**.\n"
            "**Usage :** `!accepter Stock suffisant, profil sérieux`"
        ),
        inline=False
    )
    embed.add_field(
        name="❌ `!refuser [raison]` 🔒",
        value=(
            "Dans un ticket vendeur : refuse la demande et ferme le ticket.\n"
            "**Usage :** `!refuser Profil insuffisant pour le moment`"
        ),
        inline=False
    )
    embed.add_field(
        name="🎯 `!objectif` 🔒",
        value=(
            "Panneau interactif des objectifs du serveur.\n"
            "Boutons : ➕ Ajouter · 🗑 Supprimer · ✅ Marquer terminé"
        ),
        inline=False
    )
    embed.set_footer(text="🔒 = Staff · !fermer utilisable par tous dans un ticket")
    return embed


def _help_embed_marche() -> discord.Embed:
    embed = discord.Embed(title="🏪 Marché", color=0xF1C40F)
    embed.add_field(
        name="🔍 `!recherche <item>`",
        value=(
            "Recherche intelligente (floue) dans le catalogue.\n"
            "**Usage :** `!recherche paladium`\n"
            "Fonctionne avec un nom partiel ou approximatif."
        ),
        inline=False
    )
    embed.add_field(
        name="➕ `!catalogue <nom> <quantité> <prix>` 🏷️",
        value=(
            "Ajoute ou met à jour un article dans le catalogue.\n"
            "**Usage :** `!catalogue paladium ingot 10 500$`\n"
            "⚠️ La **quantité** (entier sans symbole) doit toujours précéder le **prix**.\n"
            "Si l'article existe déjà, le stock est additionné et le prix mis à jour.\n"
            "Alerte si ton prix est plus cher qu'un concurrent."
        ),
        inline=False
    )
    embed.add_field(
        name="🗑️ `!cataloguesupp` 🏷️",
        value="Supprime un de tes articles (liste numérotée, réponds avec le numéro ou le nom).",
        inline=False
    )
    embed.add_field(
        name="🗑️ `!cataloguesuppall` 🔒",
        value="Vide entièrement le catalogue. Demande confirmation avant suppression.",
        inline=False
    )
    embed.add_field(
        name="📦 `!stock [@membre]` 🏷️",
        value=(
            "Affiche les articles en vente d'un vendeur.\n"
            "**Usage :** `!stock` (ton stock) ou `!stock @membre`\n"
            "Dans le salon catalogue, accessible à **tous les membres** (réponse en DM).\n"
            "Hors catalogue, réservé aux vendeurs certifiés."
        ),
        inline=False
    )
    embed.add_field(
        name="⚙️ `!gestion` 🏷️",
        value=(
            "Interface interactive pour gérer ton stock étape par étape.\n"
            "Questions posées : nom → quantité → prix. Idéal pour éviter les erreurs."
        ),
        inline=False
    )
    embed.add_field(
        name="🛒 `!commande` 🔒",
        value="Poste l'embed de commande permanent (menu déroulant + recherche).",
        inline=False
    )
    embed.add_field(
        name="✅ `!vendu` 🏷️",
        value=(
            "Dans un ticket de commande market.\n"
            "• ✅ Vendu → déduit le stock, log la vente, ferme le ticket\n"
            "• ❌ Pas vendu → ferme le ticket sans modifier le stock"
        ),
        inline=False
    )
    embed.add_field(
        name="📋 `!catalogueview` 🔒",
        value=(
            "Poste l'embed catalogue permanent dans le salon catalogue configuré.\n"
            "Boutons : 🔀 Trier · 🔍 Rechercher. La commande `!catalogueview` est supprimée automatiquement après exécution."
        ),
        inline=False
    )
    embed.add_field(
        name="🗑️ `!cataloguesuppjoueur <pseudo>` 🔒",
        value=(
            "Supprime toutes les annonces d'un joueur du catalogue.\n"
            "**Usage :** `!cataloguesuppjoueur LGM` — Recherche floue acceptée. Demande confirmation."
        ),
        inline=False
    )
    embed.add_field(
        name="🔔 `!role` 🔒",
        value="Poste le bouton toggle des notifications marché dans le salon dédié.",
        inline=False
    )
    embed.set_footer(text="🏷️ = Vendeur certifié ou Staff · 🔒 = Staff uniquement")
    return embed


def _help_embed_jeux() -> discord.Embed:
    embed = discord.Embed(title="🎮 Mini-jeux", color=0x9B59B6)
    embed.add_field(
        name="🎯 Pendu",
        value=(
            "`!pendu` — Lance une partie (mot aléatoire ou personnalisé via DM)\n"
            "`!devine <lettre>` — Propose une lettre\n"
            "`!mot <mot>` — Tente de deviner le mot entier\n"
            "`!pendustop` 🔒 — Arrête la partie\n"
            "Durée max : **30 min** · Récompense : **+150 XP**"
        ),
        inline=False
    )
    embed.add_field(
        name="❌⭕ Morpion",
        value=(
            "`!morpion @joueur` — Lance une partie contre un membre\n"
            "`!morpionstop` 🔒 — Arrête la partie\n"
            "Le perdant peut demander une **revanche**.\n"
            "Durée max : **5 min** · Récompense : **+50 XP**"
        ),
        inline=False
    )
    embed.add_field(
        name="🪙 Pile ou Face",
        value="`!pileouface` · alias : `!pof` `!coinflip` — Résultat aléatoire.",
        inline=False
    )
    embed.add_field(
        name="🎉 Giveaways · alias : `!gw` 🔒",
        value=(
            "`!giveaway <durée> <récompense>`\n"
            "**Durées :** `10s` `5m` `2h` `1j` (ou combinés : `1h30m`)\n"
            "**Exemple :** `!giveaway 1h Pack de paladiums`\n"
            "Les membres cliquent pour participer, gagnant tiré au sort à la fin.\n\n"
            "`!reroll <messageID>`\n"
            "→ Relance un giveaway terminé et sélectionne un nouveau gagnant.\n"
            "*(Admin ou rôle staff giveaway — configurable via `!config`)*"
        ),
        inline=False
    )
    embed.set_footer(text="👤 = accessible à tous sauf mentions 🔒")
    return embed


def _help_embed_protections() -> discord.Embed:
    embed = discord.Embed(title="🛡️ Protections automatiques", color=0xE74C3C)
    embed.add_field(
        name="🔗 Anti-liens",
        value=(
            "Tout lien non autorisé est supprimé automatiquement.\n"
            "Domaines autorisés par défaut : `tenor.com`, `giphy.com`.\n"
            "Modifiable : `!config` → ⚙️ Sécurité → `allowed_domains`."
        ),
        inline=False
    )
    embed.add_field(
        name="⚡ Anti-spam",
        value=(
            "Si trop de messages en peu de temps :\n"
            "1. **Avertissement** public\n"
            "2. **Expulsion automatique** si ça recommence\n"
            "Seuils configurables via `!config` → ⚙️ Sécurité."
        ),
        inline=False
    )
    embed.add_field(
        name="🛡️ Anti-alt",
        value=(
            "À chaque arrivée, vérification :\n"
            "• Âge du compte Discord (défaut : < 30 jours = suspect)\n"
            "• Absence d'avatar\n"
            "Alerte envoyée dans les logs si suspect."
        ),
        inline=False
    )
    embed.add_field(
        name="🚨 Anti-raid",
        value=(
            "Si plusieurs comptes suspects rejoignent rapidement → alerte raid.\n"
            "Seuil et fenêtre configurables via `!config` → ⚙️ Sécurité."
        ),
        inline=False
    )
    embed.add_field(
        name="🗑️ Auto-suppression catalogue",
        value="Dans le salon catalogue, tout message non protégé est supprimé pour garder l'embed propre.",
        inline=False
    )
    embed.set_footer(text="Toutes ces protections sont automatiques, aucune commande requise")
    return embed


def _help_embed_moderation() -> discord.Embed:
    embed = discord.Embed(title="🔨 Modération 🔒", color=0xE74C3C)
    embed.add_field(
        name="🔨 `!ban @membre [raison]` · alias : `!bannir`",
        value="Bannit définitivement un membre. Les messages des 24 dernières heures sont supprimés.",
        inline=False
    )
    embed.add_field(
        name="👢 `!kick @membre [raison]` · alias : `!expulser` `!virer`",
        value="Expulse un membre (il peut revenir avec une invitation).",
        inline=False
    )
    embed.add_field(
        name="🔇 `!mute @membre [raison]` · alias : `!silence`",
        value="Rend un membre muet (ne peut plus écrire ni parler en vocal).",
        inline=False
    )
    embed.add_field(
        name="🔊 `!unmute @membre` · alias : `!desilence` `!parler`",
        value="Retire le mute d'un membre.",
        inline=False
    )
    embed.add_field(
        name="🗑️ `!effacer <n>` · alias : `!clear` `!purge` `!supprimer` `!clean`",
        value="Supprime les X derniers messages du salon (max 100).\n**Usage :** `!effacer 20`",
        inline=False
    )
    embed.add_field(
        name="📋 `!roster` · alias : `!membres` `!liste` `!faction`",
        value="Met à jour l'embed du roster dans le salon roster avec les membres par rôle.",
        inline=False
    )
    embed.add_field(
        name="📣 `!say #salon message` · alias : `!dit`",
        value=(
            "Fait parler le bot dans n'importe quel salon.\n"
            "**Usage :** `!say #général Bonsoir tout le monde !`"
        ),
        inline=False
    )
    embed.set_footer(text="🔒 = Staff uniquement")
    return embed


def _help_embed_config() -> discord.Embed:
    embed = discord.Embed(title="⚙️ Configuration 🔒 (Admin)", color=0x95A5A6)
    embed.add_field(
        name="⚙️ `!config`",
        value=(
            "Panneau de configuration interactif complet.\n"
            "Menus déroulants pour configurer salons, rôles, catégories et sécurité.\n"
            "Aucune syntaxe à retenir."
        ),
        inline=False
    )
    embed.add_field(
        name="🛠️ `!setup`",
        value="Rappel pour utiliser `!config`.",
        inline=False
    )
    embed.add_field(
        name="📋 Clés configurables",
        value=(
            "**🔊 Salons :** logs, bienvenue, roster, catalogue, commandes, notifications, vendeur, objectifs…\n"
            "**🎭 Rôles :** staff, visiteur, vendeur, recruteur, acheteur, officier, leader…\n"
            "**🎖️ Roster :** rôles affichés dans le roster (utilisés aussi par `!classement` Top Faction)\n"
            "**⚙️ Sécurité :** âge anti-alt, seuil anti-raid, limites anti-spam, domaines autorisés"
        ),
        inline=False
    )
    embed.set_footer(text="🔒 = Administrateur uniquement")
    return embed


HELP_CATEGORIES_PUBLIC = [
    ("👤 Général",             "general"),
    ("📨 Invitations",         "invitations"),
    ("🎫 Tickets & Vendeur",   "tickets"),
    ("🏪 Marché",              "marche"),
    ("🎮 Mini-jeux",           "jeux"),
    ("🛡️ Protections",        "protections"),
]
HELP_CATEGORIES_STAFF = [
    ("🔨 Modération",          "moderation"),
    ("⚙️ Configuration",      "config"),
]


class HelpSelect(discord.ui.Select):
    def __init__(self, is_staff_user: bool):
        self.is_staff_user = is_staff_user
        categories = HELP_CATEGORIES_PUBLIC + (HELP_CATEGORIES_STAFF if is_staff_user else [])
        options = [
            discord.SelectOption(label="🏠 Accueil", value="accueil", description="Page d'accueil de l'aide"),
        ] + [
            discord.SelectOption(label=label, value=value, description=f"Commandes : {label}")
            for label, value in categories
        ]
        super().__init__(
            placeholder="📂 Choisir une catégorie…",
            options=options,
            custom_id="help_select"
        )

    async def callback(self, interaction: discord.Interaction):
        choice = self.values[0]
        embed_map = {
            "accueil":     _help_embed_accueil(self.is_staff_user),
            "general":     _help_embed_general(),
            "invitations": _help_embed_invitations(),
            "tickets":     _help_embed_tickets(),
            "marche":      _help_embed_marche(),
            "jeux":        _help_embed_jeux(),
            "protections": _help_embed_protections(),
            "moderation":  _help_embed_moderation(),
            "config":      _help_embed_config(),
        }
        embed = embed_map.get(choice, _help_embed_accueil(self.is_staff_user))
        await interaction.response.edit_message(embed=embed, view=self.view)


class HelpView(discord.ui.View):
    def __init__(self, is_staff_user: bool, msg=None):
        super().__init__(timeout=300)
        self.msg = msg
        self.add_item(HelpSelect(is_staff_user))

    async def on_timeout(self):
        if self.msg:
            try:
                for item in self.children:
                    item.disabled = True
                await self.msg.edit(view=self)
            except Exception:
                pass


@bot.command(name="help", aliases=["aide", "commandes"])
async def help_cmd(ctx):
    staff = is_staff(ctx.author)
    embed = _help_embed_accueil(staff)
    view  = HelpView(staff)
    msg   = await ctx.send(embed=embed, view=view)
    view.msg = msg