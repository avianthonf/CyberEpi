-- Postgres compatible check for user/database
DO
$do$
BEGIN
   IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'cyberepi') THEN
      CREATE ROLE cyberepi WITH LOGIN PASSWORD 'devpassword';
   END IF;
   IF NOT EXISTS (SELECT FROM pg_database WHERE datname = 'cyberepi') THEN
      CREATE DATABASE cyberepi OWNER cyberepi;
   END IF;
END
$do$;
GRANT ALL PRIVILEGES ON DATABASE cyberepi TO cyberepi;
