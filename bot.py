"""
Point d'entrée legacy — redirige vers le package modulaire bot/.

Lancement :
  python bot.py
  python -m bot.main
  python run_bot.py
"""
from bot.main import main

if __name__ == "__main__":
    main()
