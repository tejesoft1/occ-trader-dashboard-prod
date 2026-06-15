-- Correr esto UNA VEZ contra el Postgres que usa occ-trader-multi.
-- Reemplazar 'tu_password_reader' por una contraseña nueva (distinta a la
-- del usuario 'occ' que usa occ-trader-multi), y guardarla como
-- DASH_DB_PASSWORD en el .env del dashboard.
--
-- Ejemplo de conexión (ajustar nombre de contenedor/host si corresponde):
--   docker exec -it <contenedor_postgres> psql -U occ -d occ_trader -f /ruta/a/este/archivo
-- o:
--   docker exec -it <contenedor_postgres> psql -U occ -d occ_trader

CREATE USER occ_reader WITH PASSWORD '0cc-d4shb04rd-user';

GRANT CONNECT ON DATABASE occ_trader TO occ_reader;
GRANT USAGE ON SCHEMA public TO occ_reader;

GRANT SELECT ON trades TO occ_reader;
GRANT SELECT ON capital_history TO occ_reader;
GRANT SELECT ON equity_snapshots TO occ_reader;

-- Si en el futuro se crean tablas nuevas y se quiere que occ_reader las
-- pueda leer automáticamente (opcional):
-- ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO occ_reader;

-- Verificación: occ_reader NO debe poder escribir.
-- Probar (debería fallar con "permission denied"):
--   SET ROLE occ_reader;
--   INSERT INTO trades (account_name, timestamp, symbol, side, signal,
--     price, quantity, notional, leverage, order_id)
--     VALUES ('x','x','x','x','x',0,0,0,1,'x');
--   RESET ROLE;
