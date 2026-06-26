-- Registration writes a profile row in a single atomic upsert only after every
-- field has been collected (partial progress lives in aiogram FSM, never here),
-- so a row's core fields are always populated. Promote that application-level
-- invariant into the schema. prices is always at least '{}' (empty for code
-- users); backfill any legacy NULLs from before 011 added the column.

BEGIN;

UPDATE user_profiles SET prices = '{}'::jsonb WHERE prices IS NULL;

ALTER TABLE user_profiles
    ALTER COLUMN prices SET DEFAULT '{}'::jsonb,
    ALTER COLUMN prices SET NOT NULL,
    ALTER COLUMN chat_addable SET NOT NULL,
    ALTER COLUMN withdrawal_method SET NOT NULL,
    ALTER COLUMN work_start SET NOT NULL,
    ALTER COLUMN work_end SET NOT NULL;

COMMIT;
