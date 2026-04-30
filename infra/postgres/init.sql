-- PostgreSQL initialization — runs once when the container is first created
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'thrift_user') THEN
        CREATE USER thrift_user WITH PASSWORD 'thrift_pass';
    END IF;
END
$$;

CREATE DATABASE thrift_store OWNER thrift_user;
CREATE DATABASE thrift_store_test OWNER thrift_user;

GRANT ALL PRIVILEGES ON DATABASE thrift_store TO thrift_user;
GRANT ALL PRIVILEGES ON DATABASE thrift_store_test TO thrift_user;

\c thrift_store
GRANT ALL ON SCHEMA public TO thrift_user;

\c thrift_store_test
GRANT ALL ON SCHEMA public TO thrift_user;
