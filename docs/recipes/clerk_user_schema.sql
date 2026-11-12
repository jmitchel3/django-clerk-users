-- Columns, constraints, and indexes of the Clerk user table (PostgreSQL).
-- Replace django_clerk_users_clerkuser if you subclass AbstractClerkUser.
SELECT 'column' AS kind,
       column_name AS name,
       data_type || CASE WHEN is_nullable = 'YES' THEN ' NULL' ELSE ' NOT NULL' END
           AS definition
FROM information_schema.columns
WHERE table_schema = current_schema()
  AND table_name = 'django_clerk_users_clerkuser'
UNION ALL
SELECT 'constraint', conname, pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid = 'django_clerk_users_clerkuser'::regclass
UNION ALL
SELECT 'index', indexname, indexdef
FROM pg_indexes
WHERE schemaname = current_schema()
  AND tablename = 'django_clerk_users_clerkuser'
ORDER BY 1, 2;
