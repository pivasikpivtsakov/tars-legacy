CREATE TABLE IF NOT EXISTS orders (
    id SERIAL PRIMARY KEY,
    original_id INTEGER NOT NULL,
    shop_access_key VARCHAR(255),
    status VARCHAR(255),
    status_reason VARCHAR(255),
    amount INTEGER NOT NULL,
    pubg_id BIGINT,
    codes JSON NOT NULL DEFAULT '{}',
    unused_codes JSON NOT NULL DEFAULT '{}',
    broken_codes VARCHAR(255)[] NOT NULL DEFAULT '{}',
    redeemed_codes VARCHAR(255)[] NOT NULL DEFAULT '{}',
    additional_data JSON NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);