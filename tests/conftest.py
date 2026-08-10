# tests/conftest.py — Aislamiento de la suite
#
# Se ejecuta ANTES de importar cualquier módulo de agent/: `memory.py` lee
# DATABASE_URL al importarse, así que si no se fija acá los tests corren contra
# la base de desarrollo (o, con el .env cargado, contra la de PRODUCCIÓN).

import os
import tempfile

_DB = os.path.join(tempfile.gettempdir(), "fenix_tests.db")
# Efímera: si queda estado de una corrida anterior, los mensajes toman otro
# camino (menú vs brain) y el resultado deja de ser determinista.
try:
    os.remove(_DB)
except FileNotFoundError:
    pass
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_DB}"

# Credenciales de mentira: ningún test debe salir a la red. Los tests que
# ejercitan el flujo mockean Claude/Airtable/Meta/Telegram explícitamente.
os.environ.setdefault("ADMIN_PHONE", "595999999999")
os.environ.setdefault("META_ACCESS_TOKEN", "test")
os.environ.setdefault("META_PHONE_NUMBER_ID", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("AIRTABLE_API_KEY", "test")
os.environ.setdefault("AIRTABLE_BASE_ID", "apptest")
os.environ.setdefault("LINK_SECRET", "testsecret")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "")
