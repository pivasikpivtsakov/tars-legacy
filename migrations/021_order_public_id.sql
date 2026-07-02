-- User-facing opaque order handle (e.g. "C-12FV8K9P"). New orders get an
-- app-generated C-/NC- handle; legacy rows are backfilled with throwaway GUID
-- strings before the column is made NOT NULL so this runs on the existing DB too.
ALTER TABLE orders ADD COLUMN IF NOT EXISTS public_id TEXT;
UPDATE orders SET public_id = gen_random_uuid()::text WHERE public_id IS NULL;
ALTER TABLE orders ALTER COLUMN public_id SET NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS orders_public_id_key ON orders (public_id);

-- transactions was cleared, so NOT NULL can be added directly. This is
-- denormalized display data (never a lookup key), so it needs no index.
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS public_id TEXT NOT NULL;
