-- FSM storage backing bot.storage.postgres.PostgresStorage.
-- One row per StorageKey (chat+user+...) built by aiogram's KeyBuilder.

CREATE TABLE IF NOT EXISTS aiogram_fsm (
    key        TEXT        PRIMARY KEY,
    state      TEXT,
    data       JSONB       NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
