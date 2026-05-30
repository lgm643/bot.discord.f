"""Démarrage du bot — point d'entrée Railway / local."""
import sys
import os

# Ajoute le répertoire courant au path pour que "import bot" fonctionne
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bot.main import main

if __name__ == "__main__":
    main()
