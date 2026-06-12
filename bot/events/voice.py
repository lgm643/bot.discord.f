"""
events/voice.py — Événements vocaux.

CORRECTIONS v3 :
  - on_voice_state_update supprimé d'ici.
    Il est désormais géré uniquement dans logs_events.py
    qui s'occupe de :
      * Stats XP vocal
      * Suivi inactivité vocale
      * Logs vocaux (join/leave/move/état)
    Évite le double calcul XP et les logs en double.
"""
# Ce fichier est intentionnellement vide d'handlers.
# Tout est dans bot/events/logs_events.py.