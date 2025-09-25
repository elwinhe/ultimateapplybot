-- Migration 004: Fix auth_tokens schema for proper multi-account support
-- This fixes the schema to properly support multiple Microsoft accounts per user

-- Step 1: Drop foreign key constraints that reference auth_tokens.user_id
DO $$
BEGIN
    -- Drop foreign keys that reference auth_tokens.user_id
    IF EXISTS (SELECT 1 FROM information_schema.table_constraints 
               WHERE constraint_name = 'jobs_user_id_fkey') THEN
        ALTER TABLE jobs DROP CONSTRAINT jobs_user_id_fkey;
    END IF;
    
    IF EXISTS (SELECT 1 FROM information_schema.table_constraints 
               WHERE constraint_name = 'activity_events_user_id_fkey') THEN
        ALTER TABLE activity_events DROP CONSTRAINT activity_events_user_id_fkey;
    END IF;
    
    IF EXISTS (SELECT 1 FROM information_schema.table_constraints 
               WHERE constraint_name = 'email_filter_settings_user_id_fkey') THEN
        ALTER TABLE email_filter_settings DROP CONSTRAINT email_filter_settings_user_id_fkey;
    END IF;
    
    IF EXISTS (SELECT 1 FROM information_schema.table_constraints 
               WHERE constraint_name = 'gmail_tokens_user_id_fkey') THEN
        ALTER TABLE gmail_tokens DROP CONSTRAINT gmail_tokens_user_id_fkey;
    END IF;
END $$;

-- Step 2: Drop the unique constraint on auth_tokens.user_id
ALTER TABLE auth_tokens DROP CONSTRAINT IF EXISTS auth_tokens_user_id_key;

-- Step 3: Remove microsoft_user_id column (not needed as per user request)
ALTER TABLE auth_tokens DROP COLUMN IF EXISTS microsoft_user_id;

-- Step 4: Add foreign key constraint to reference users table
ALTER TABLE auth_tokens ADD CONSTRAINT auth_tokens_user_id_fkey 
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE;

-- Step 5: Re-add foreign key constraints for other tables to reference users table
ALTER TABLE jobs ADD CONSTRAINT jobs_user_id_fkey 
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE;

ALTER TABLE activity_events ADD CONSTRAINT activity_events_user_id_fkey 
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE;

ALTER TABLE email_filter_settings ADD CONSTRAINT email_filter_settings_user_id_fkey 
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE;

ALTER TABLE gmail_tokens ADD CONSTRAINT gmail_tokens_user_id_fkey 
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE;

-- Step 6: Create index for better performance on multi-account queries
CREATE INDEX IF NOT EXISTS idx_auth_tokens_user_id_provider ON auth_tokens (user_id, provider);

-- Step 7: Add unique constraint to prevent duplicate provider accounts per email
ALTER TABLE auth_tokens ADD CONSTRAINT auth_tokens_user_email_provider_unique 
    UNIQUE (user_id, user_email, provider);

COMMENT ON TABLE auth_tokens IS 'Stores OAuth tokens for email providers (Microsoft, Google) associated with application users';
COMMENT ON COLUMN auth_tokens.user_id IS 'References users.user_id - the application user who owns this OAuth token';
COMMENT ON COLUMN auth_tokens.user_email IS 'The email address of the connected account (e.g., Microsoft/Gmail email)';
COMMENT ON COLUMN auth_tokens.provider IS 'OAuth provider: microsoft, google, etc.';
