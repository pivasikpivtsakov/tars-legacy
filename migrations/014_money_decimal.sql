-- Money becomes decimal (2 dp). Widen integer money columns to NUMERIC so balances
-- and taken prices can hold per-pack decimal pricing. Existing values are preserved
-- exactly (e.g. 600 -> 600.00); pack prices live in the prices JSONB column already.

ALTER TABLE orders
    ALTER COLUMN taken_price TYPE NUMERIC(12, 2);

ALTER TABLE user_profiles
    ALTER COLUMN balance TYPE NUMERIC(14, 2),
    ALTER COLUMN balance SET DEFAULT 0;
