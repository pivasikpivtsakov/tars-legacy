-- Durable, user-centric form data gathered via the /form FSM flow.
-- Kept separate from aiogram_fsm so FSM state remains transient while
-- collected values survive state.clear() and chat changes.

CREATE TABLE IF NOT EXISTS user_profiles (
    user_id    BIGINT      PRIMARY KEY,
    name       TEXT        NOT NULL,
    language   TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
