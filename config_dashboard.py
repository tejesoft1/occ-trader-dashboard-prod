import os
from dotenv import load_dotenv

load_dotenv()

# ── Config del dashboard (read-only) ─────────────────────────────────────
# Variables de entorno PROPIAS, separadas de las que usa occ-trader-multi,
# para no compartir credenciales entre el proceso que opera dinero real
# y el proceso que solo lee/muestra datos.
#
# .env (en el servidor, junto al de occ-trader-multi pero con estas claves
# nuevas):
#   DASH_DB_HOST=...
#   DASH_DB_PORT=...
#   DASH_DB_NAME=...
#   DASH_DB_USER=occ_reader        <- usuario Postgres SOLO LECTURA (ver SQL)
#   DASH_DB_PASSWORD=...
#
#   DASH_ACCOUNT_NAME=owner        <- nombre de la cuenta a mostrar (accounts.ini)
#   DASH_BINANCE_API_KEY=...       <- API key NUEVA, permiso "Read Info" SOLAMENTE
#   DASH_BINANCE_API_SECRET=...
#   DASH_BINANCE_TESTNET=true      <- true/false según corresponda a esa cuenta
#   DASH_SYMBOL=APTUSDT
#
#   DASH_CORS_ORIGIN=https://<tu-usuario>.github.io
#   DASH_API_TOKEN=...             <- token simple para proteger el endpoint

DB_HOST     = os.getenv('DASH_DB_HOST', 'postgres')
DB_PORT     = int(os.getenv('DASH_DB_PORT', 5432))
DB_NAME     = os.getenv('DASH_DB_NAME', 'occ_trader')
DB_USER     = os.getenv('DASH_DB_USER', 'occ_reader')
DB_PASSWORD = os.getenv('DASH_DB_PASSWORD', '')

ACCOUNT_NAME    = os.getenv('DASH_ACCOUNT_NAME', 'owner')
SYMBOL          = os.getenv('DASH_SYMBOL', 'APTUSDT')
BINANCE_API_KEY    = os.getenv('DASH_BINANCE_API_KEY')
BINANCE_API_SECRET = os.getenv('DASH_BINANCE_API_SECRET')
BINANCE_TESTNET    = os.getenv('DASH_BINANCE_TESTNET', 'true').lower() == 'true'

CORS_ORIGIN = os.getenv('DASH_CORS_ORIGIN', '*')
API_TOKEN   = os.getenv('DASH_API_TOKEN', '')
