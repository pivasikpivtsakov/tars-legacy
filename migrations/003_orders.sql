CREATE TABLE IF NOT EXISTS orders (
    id SERIAL PRIMARY KEY,
    original_id INTEGER NOT NULL,
    shop_access_key VARCHAR(255),
    status VARCHAR(255),
    status_reason VARCHAR(255),
    amount INTEGER,
    pubg_id BIGINT,
    codes JSON,
    unused_codes JSON,
    broken_codes VARCHAR(255)[] DEFAULT '{}',
    redeemed_codes VARCHAR(255)[] DEFAULT '{}',
    additional_data JSON,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);