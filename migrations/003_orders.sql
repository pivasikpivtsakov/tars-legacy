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
    last_update TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    creation_date DATE NOT NULL DEFAULT CURRENT_DATE,
    creation_timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);