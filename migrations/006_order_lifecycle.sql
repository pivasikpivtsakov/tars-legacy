ALTER TABLE orders ADD COLUMN IF NOT EXISTS taken_at TIMESTAMPTZ;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS taken_by BIGINT;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS taken_price INTEGER;

ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS balance BIGINT NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS orders_taken_by_status_closed_at_idx
    ON orders (taken_by, status, closed_at DESC);

CREATE INDEX IF NOT EXISTS order_offers_user_id_idx
    ON order_offers (user_id);
