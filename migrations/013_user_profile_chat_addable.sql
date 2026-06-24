-- Rename works_alone -> chat_addable, inverting the stored meaning.
-- Old works_alone=TRUE (solo) becomes chat_addable=FALSE (won't add bot to a
-- group chat) and vice versa. Idempotent: only acts while the old column still
-- exists and the new one does not.

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'user_profiles' AND column_name = 'works_alone'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'user_profiles' AND column_name = 'chat_addable'
    ) THEN
        ALTER TABLE user_profiles RENAME COLUMN works_alone TO chat_addable;
        UPDATE user_profiles SET chat_addable = NOT chat_addable WHERE chat_addable IS NOT NULL;
    END IF;
END $$;
