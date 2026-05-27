-- Durable, user-centric form data gathered via the /form FSM flow.
-- Kept separate from aiogram_fsm so FSM state remains transient while
-- collected values survive state.clear() and chat changes.

DO $$ BEGIN
    CREATE TYPE user_profile_status AS ENUM ('inactive', 'active', 'banned');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS user_profiles (
    user_id            BIGINT              PRIMARY KEY,
    works_alone        BOOLEAN,
    packages           INTEGER[],
    withdrawal_method  TEXT,
    work_start         TIMETZ,
    work_end           TIMETZ,
    is_online          BOOLEAN             NOT NULL DEFAULT FALSE,
    with_codes         BOOLEAN             NOT NULL DEFAULT FALSE,
    status             user_profile_status NOT NULL DEFAULT 'inactive',
    created_at         TIMESTAMPTZ         NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMPTZ         NOT NULL DEFAULT NOW()
);
