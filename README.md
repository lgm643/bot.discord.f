# La Mystic Discord Bot (modulaire)

## Structure

```
bot/
├── main.py              # Point d'entrée
├── core.py              # Instance bot, chemins, état global
├── commands/            # Commandes !prefix
├── events/              # Événements Discord
├── views/               # Boutons / menus persistants
├── modals/              # Formulaires Discord
├── utils/               # Config, DB, market, logs…
├── data/                # Données locales (optionnel)
└── assets/              # Fichiers statiques
```

Les données runtime (DB, configs, catalogues) restent sous `/app/data/` comme avant (Docker).

## Lancement

```bash
set DISCORD_TOKEN=votre_token
python -m bot.main
```

ou :

```bash
python bot.py
```

## Modifier une fonctionnalité

| Système | Fichier(s) |
|---------|------------|
| Marché / catalogue | `commands/market.py`, `views/market_view.py`, `utils/market.py` |
| Invitations | `commands/invites.py`, `utils/invites.py` |
| Tickets | `views/ticket_view.py`, `commands/moderation.py` |
| Vendeur certifié | `commands/vendeur.py`, `views/vendeur_view.py`, `modals/vendeur_modal.py` |
| Config `!config` | `commands/config_cmd.py`, `views/config_views.py`, `utils/config_panel.py` |
| Help | `commands/help.py`, `views/help_view.py` |
| Giveaways | `commands/giveaway.py`, `views/giveaway_view.py` |

Le fichier original complet est conservé dans `bot_legacy.py`.
