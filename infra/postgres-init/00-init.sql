-- CyberEpi PostgreSQL bootstrap, run only for an empty data directory.
-- The image entrypoint creates POSTGRES_USER and POSTGRES_DB using the
-- credentials supplied to Compose. Services own their tables and migrations.

\connect cyberepi
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Keycloak owns a separate database using the same local database role.
\connect postgres
SELECT 'CREATE DATABASE keycloak OWNER cyberepi'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'keycloak')\gexec
GRANT ALL PRIVILEGES ON DATABASE keycloak TO cyberepi;
