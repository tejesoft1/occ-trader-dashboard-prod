# CONTEXT.md — OCC Trader / Estado del proyecto
# Última actualización: 2026-06-16

---

## 1. Servidor

- **Proveedor**: DigitalOcean (droplet)
- **Host**: `o14-trading-ams3-2024-03-29`
- **Todo bajo**: `/root/`
- **nginx**: corre en el host (systemd, no docker), habilitado y activo

### Dominios y nginx
| Dominio | Config nginx | Upstream | Proyecto |
|---------|-------------|----------|----------|
| `trading-flask.tejesoft.cl` | `trading-flask.cl` | `localhost:5002` | occ-trader bot |
| `occ-dashboard.tejesoft.cl` | `occ-dashboard.tejesoft.cl` | `localhost:5004` | occ-trader dashboard |

---

## 2. Bases de datos (PostgreSQL)

### Contenedor `db` (postgres:15, puerto host 5433)
- Credenciales: usuario `odoo`, password `odoo`, DB default `postgres`
- Lleva +2 años funcionando. **No modificar sin análisis previo.**

| Base de datos | Owner | Usuario acceso | Quién la usa |
|---------------|-------|----------------|--------------|
| `redberry`    | odoo  | odoo           | Bot spot (redberry-binance-2) |
| `occ_trader`  | odoo  | odoo, occ, occ_reader | Bot futuros + dashboard |
| `postgres`    | odoo  | odoo           | Sistema (default) |

### Usuarios PostgreSQL en `occ_trader`
- `occ` — usuario del bot (lectura/escritura)
- `occ_reader` — usuario del dashboard (solo lectura, password: `0cc-d4shb04rd-user`)
  - Script de creación: `/root/occ-trader-dashboard/create_readonly_user.sql`
  - Permisos: SELECT en `trades`, `capital_history`, `equity_snapshots`

### Contenedor `occ-db-dev` (postgres:15, puerto host 5434)
- Credenciales: usuario `occ_dev`
- Volumen: `occ_db_dev_data`
- Red: `occ-dev-net`
- Restart policy: `unless-stopped` ✅

| Base de datos    | Owner   | Quién la usa    |
|------------------|---------|-----------------|
| `occ_trader_dev` | occ_dev | occ-trader-dev  |

---

## 3. Contenedores Docker activos

| Contenedor                  | Imagen                    | Puerto host | Restart          | Proyecto           |
|-----------------------------|---------------------------|-------------|------------------|--------------------|
| `occ-trader-multi`          | occ-trader-multi:develop  | 5002        | `unless-stopped` | occ-trader bot testnet |
| `occ-trader-dev`            | occ-trader-dev:latest     | 5003        | `unless-stopped` | occ-trader bot dev |
| `occ-db-dev`                | postgres:15               | 5434        | `unless-stopped` | occ-trader dev DB  |
| `occ-dashboard`             | (build local)             | 5004        | `unless-stopped` | occ-trader dashboard |
| `db`                        | postgres:15               | 5433        | (verificar)      | spot + futuros     |
| `odoo-redberry`             | odoo-redberry:antes-cambio-password | 8069 | ?           | bot spot backoffice|
| `redberry-binance-2_web_1`  | redberry-binance-2_web    | 5010        | ?                | bot spot           |
| `thingsboard`               | tb-postgres:latest        | 8080→9090   | ?                | terceros           |

### Redes Docker
- `occ-net`: contiene `db`, `occ-trader-multi`, `occ-dashboard`
- `occ-dev-net`: contiene `occ-db-dev`, `occ-trader-dev`

---

## 4. Proyectos occ-trader

### 4.1 Bot — `/root/occ-trader/`
- **Repo GitHub**: `tejesoft1/occ-trader` (antes `occ-trader-multi`)
- **Branch**: solo `main`
- **Stack**: Python + Flask + Gunicorn + PostgreSQL
- **Estrategia**: OCC Strat R5.2 w/lateral v71 (Pine Script v5, APTUSDT.P, 3min, Binance Futures)

#### Archivos clave
- `docker-compose.yml` — compose ambiente testnet
- `docker-compose.dev.yml` — compose ambiente dev (documentación reproducible)
- `CONTEXT.md` — este archivo
- `.env` — variables testnet (no versionado)
- `.env.dev` — variables dev (no versionado)
- `accounts.ini` — config no sensible de cuentas (versionado)

#### Ambientes
| Contenedor         | Branch | Binance | Puerto | DB                          | Restart          |
|--------------------|--------|---------|--------|-----------------------------|------------------|
| `occ-trader-multi` | `main` | testnet | 5002   | `db:occ_trader` (usuario `occ`) | `unless-stopped` |
| `occ-trader-dev`   | ?      | testnet | 5003   | `occ-db-dev:occ_trader_dev` | `unless-stopped` |

#### Cuentas (`accounts.ini`)
- `owner`: `enabled=true`, `testnet=true`, `leverage=3`, `capital_percent=0.20`
- Resto: `enabled=false`, `testnet=true`

#### Flujo de branches
```
feature/nombre → (PR/merge) → main → git pull + docker compose up -d --build en /root/occ-trader/
```

### 4.2 Dashboard — `/root/occ-trader-dashboard/`
- **Repo GitHub**: `tejesoft1/occ-trader-dashboard`
- **Frontend**: GitHub Pages → `https://tejesoft1.github.io/occ-trader-dashboard/`
- **Backend**: Flask → `https://occ-dashboard.tejesoft.cl/`
- **Branch**: `main`
- **Stack**: HTML/JS (frontend) + Python Flask (backend)

#### Archivos clave
- `app_dashboard.py` — API Flask (endpoints: `/api/capital-curve`, `/api/reconciliation`, `/api/health`)
- `docker-compose.yml` — levanta `occ-dashboard` en puerto 5004, red `occ-net`
- `.env.dashboard` — variables del dashboard (no versionado)
- `.env.dashboard.example` — template (versionado)
- `config.js` — precarga URL del API en el frontend (versionado, sin token)
- `create_readonly_user.sql` — script para crear `occ_reader` en postgres

#### Variables `.env.dashboard`
```
DASH_DB_HOST=db
DASH_DB_PORT=5432
DASH_DB_NAME=occ_trader
DASH_DB_USER=occ_reader
DASH_DB_PASSWORD=0cc-d4shb04rd-user
DASH_ACCOUNT_NAME=owner
DASH_SYMBOL=APTUSDT
DASH_BINANCE_API_KEY=<key read-only testnet>
DASH_BINANCE_API_SECRET=<secret read-only testnet>
DASH_BINANCE_TESTNET=true
DASH_CORS_ORIGIN=https://tejesoft1.github.io
DASH_API_TOKEN=  (vacío — sin autenticación, endpoint solo lectura)
DOCKER_NETWORK=occ-net
```

#### Decisiones de diseño del dashboard
- **Sin token**: endpoint solo lectura, sin autenticación (token eliminado 2026-06-16)
- **Gráfico**: solo puntos con `unrealized_pnl=0` (trades cerrados, no posiciones abiertas)
- **Fecha fin**: siempre hoy (no se guarda en localStorage)
- **Peak equity**: eliminado del gráfico (no aportaba valor)
- **Separación transaccional/analítica**: dashboard usa usuario `occ_reader` (solo lectura), nunca toca el bot

#### Si se cae el contenedor `occ-dashboard`
```bash
cd /root/occ-trader-dashboard
docker compose up -d --build
```

#### Si se pierde el usuario `occ_reader`
```bash
docker exec -i db psql -U odoo -d occ_trader < /root/occ-trader-dashboard/create_readonly_user.sql
```

---

## 5. Inventario completo de `/root/`

| Directorio/Archivo          | Proyecto                        | Estado       | Notas |
|-----------------------------|---------------------------------|--------------|-------|
| `occ-trader/`               | bot futuros                     | activo ✅    | antes `occ-trader-multi/` |
| `occ-trader-dashboard/`     | dashboard web futuros           | activo ✅    | levantado 2026-06-16 |
| `redberry-binance-2/`       | bot spot                        | activo ✅    | no tocar |
| `redberry-binance-2_old/`   | bot spot viejo                  | obsoleto     | pendiente borrar |
| `profit_front_redberry/`    | front profit redberry           | desarrollo   | sin repo GitHub |
| `profit_manager_redberry/`  | backoffice profit redberry      | desarrollo   | sin repo GitHub |
| `flask_webhook_tradingview/`| webhook notificaciones TV       | activo ✅    | Discord/Telegram/Slack/Twitter |
| `webhook.cl` / `webhook.tar`| webhook bot spot                | activo ✅    | no tocar |
| `sintec/`                   | producto Odoo (Hotmart)         | independiente| no tocar |
| `thingsboard/`              | terceros                        | activo ✅    | no tocar |
| `odoo_setup_dependencies/`  | instalador odoo                 | obsoleto     | pendiente archivar |
| `creo_snapshots.sh`         | snapshots automáticos DO        | activo ✅    | cron, usa doctl-token.txt |
| `doctl-token.txt`           | token DigitalOcean              | activo ✅    | usado por creo_snapshots.sh |
| `do_dashboard.py`           | dashboard droplets DO           | utilitario   | |

---

## 6. Repos en GitHub

| Repo | Proyecto | Estado |
|------|----------|--------|
| `tejesoft1/occ-trader` | bot futuros | activo ✅ |
| `tejesoft1/occ-trader-dashboard` | dashboard web futuros | activo ✅ |
| `tejesoft1/redberry-binance-2` | bot spot | existe |
| `tejesoft1/CalcInver` | calculadora inversiones HTML | existe |

### Sin repo GitHub
- `flask_webhook_tradingview/`
- `profit_front_redberry/`
- `profit_manager_redberry/`
- `sintec/`

---

## 7. Estrategia Pine Script — OCC Strat R5.2 v71

- **Par**: APTUSDT.P (Binance Futures, 3 min)
- **Backtest** Apr 26 – Jun 12, 2026: PnL +73.41%, 150 trades, WR 60%, PF 4.597, DD 1.78%
- **Mecanismos**: OCC + HalfTrend + filtro lateral ADX + colchón Chandelier + entradaHT + Run Extendido
- **Pendiente**: más forward testing en testnet antes de activar capital real

---

## 8. Incidente 2026-06-15

- Droplet restaurado → contenedores no levantaron solos
- Webhook caído 13:00-17:32 UTC → trade huérfano (short abierto 13:15, cerrado implícitamente 21:48)
- Spike visible en gráfico dashboard el 15-06 — dato real del incidente, no bug

---

## 9. Pendientes

- [ ] Verificar restart policy de `db`, `odoo-redberry`, `redberry-binance-2_web_1`, `thingsboard`
- [ ] Borrar `redberry-binance-2_old/`
- [ ] Archivar `odoo_setup_dependencies/`
- [ ] Decidir si `occ_trader` migra a postgres propio (hoy comparte `db` con bot spot)
- [ ] Agregar `depends_on` con healthcheck en `docker-compose.yml` de testnet
- [ ] Crear repos GitHub para `flask_webhook_tradingview`, `profit_front_redberry`, `profit_manager_redberry`
- [ ] Activar producción (mainnet) cuando el forward testing en testnet convenza

---

## 10. Cómo usar este archivo

Al iniciar una nueva sesión con Claude:
1. Cargar `CONTEXT.md` + archivos relevantes del proyecto
2. Iniciar con: *"Lee el CONTEXT.md y continuamos desde los pendientes"*
3. Al finalizar, actualizar y commitear:
```bash
git add CONTEXT.md
git commit -m "Actualiza CONTEXT.md - [fecha]"
git push origin main
```

