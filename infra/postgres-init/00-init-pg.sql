-- Postgres compatible check for user/database
DO
$do$
BEGIN
   IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'cyberepi') THEN
      CREATE ROLE cyberepi WITH LOGIN PASSWORD 'devpassword';
   END IF;
END
$do$;
SELECT 'CREATE DATABASE cyberepi OWNER cyberepi'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'cyberepi')\gexec
GRANT ALL PRIVILEGES ON DATABASE cyberepi TO cyberepi;
