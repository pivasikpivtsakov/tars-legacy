-- Moderator-assigned tier capping the maximum order amount a user may take.
-- Ordinal SMALLINT (compared with >=), not a PG enum. Defaults to 0 (most
-- restrictive); only a moderator can raise it.

ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS tier SMALLINT NOT NULL DEFAULT 0;
