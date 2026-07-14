#!/bin/sh
set -eu

test_db="${POSTGRES_TEST_DB:-repofix_test}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<SQL
SELECT 'CREATE DATABASE ${test_db}'
WHERE NOT EXISTS (
    SELECT FROM pg_database WHERE datname = '${test_db}'
)\\gexec
SQL
