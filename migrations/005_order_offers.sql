DO $$ BEGIN
    CREATE TYPE order_status AS ENUM (
        'pending',
        'offering',
        'taken',
        'completed',
        'cancelled',
        'no_takers'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE order_offer_status AS ENUM (
        'offered',
        'taken',
        'declined',
        'expired'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

UPDATE orders SET status = 'pending' WHERE status IS NULL;

ALTER TABLE orders
    ALTER COLUMN status DROP DEFAULT,
    ALTER COLUMN status TYPE order_status USING status::order_status,
    ALTER COLUMN status SET NOT NULL,
    ALTER COLUMN status SET DEFAULT 'pending';

ALTER TABLE orders ADD COLUMN IF NOT EXISTS offered_at TIMESTAMPTZ;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS closed_at TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS order_offers (
    order_id    INTEGER            NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    user_id     BIGINT             NOT NULL,
    status      order_offer_status NOT NULL DEFAULT 'offered',
    offered_at  TIMESTAMPTZ        NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMPTZ,
    PRIMARY KEY (order_id, user_id)
);
