DO $$ BEGIN
    CREATE TYPE external_order_status AS ENUM (
        'CREATED',
        'PROCESSING',
        'MANUAL_PROCESSING',
        'RESTART',
        'PENDING',
        'DEFERRED',
        'FAILED',
        'REDEEMED',
        'REJECTED',
        'CANCELLED'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

ALTER TABLE orders ADD COLUMN IF NOT EXISTS external_status external_order_status NOT NULL DEFAULT 'CREATED';
