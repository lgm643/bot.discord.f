"""
events/member_update.py — Modification d'un membre.

CORRECTIONS v3 :
  - on_member_update supprimé d'ici.
    Géré uniquement dans logs_events.py qui couvre :
      * Rôles ajoutés/retirés (avec audit log)
      * Pseudo modifié
      * Timeout
      * Avatar serveur modifié
      * Mise à jour roster faction
    Supprime les imports inutiles (io, os, random, sqlite3, difflib, json).
"""
# Ce fichier est intentionnellement vide d'handlers.
# Tout est dans bot/events/logs_events.py.