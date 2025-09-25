-- Migration: Add jobs and activity tracking tables
-- Date: 2025-09-25

-- Jobs table to track job applications
CREATE TABLE IF NOT EXISTS jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(255) NOT NULL REFERENCES auth_tokens(user_id) ON DELETE CASCADE,
    url TEXT NOT NULL,
    title VARCHAR(500),
    company VARCHAR(255),
    location VARCHAR(255),
    status VARCHAR(50) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'applied', 'failed', 'rejected')),
    sheet_row INTEGER,
    technologies TEXT,
    seniority VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    applied_at TIMESTAMP WITH TIME ZONE,
    UNIQUE(user_id, url)
);

-- Create indexes for performance
CREATE INDEX idx_jobs_user_id ON jobs(user_id);
CREATE INDEX idx_jobs_status ON jobs(status);
CREATE INDEX idx_jobs_created_at ON jobs(created_at);

-- Activity events table for tracking user actions
CREATE TABLE IF NOT EXISTS activity_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(255) NOT NULL REFERENCES auth_tokens(user_id) ON DELETE CASCADE,
    type VARCHAR(50) NOT NULL,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for activity events
CREATE INDEX idx_activity_events_user_id ON activity_events(user_id);
CREATE INDEX idx_activity_events_type ON activity_events(type);
CREATE INDEX idx_activity_events_created_at ON activity_events(created_at);

-- Email filter settings table
CREATE TABLE IF NOT EXISTS email_filter_settings (
    user_id VARCHAR(255) PRIMARY KEY REFERENCES auth_tokens(user_id) ON DELETE CASCADE,
    enabled BOOLEAN DEFAULT true,
    keywords TEXT[] DEFAULT ARRAY[]::TEXT[],
    sender_whitelist TEXT[] DEFAULT ARRAY[]::TEXT[],
    check_interval_minutes INTEGER DEFAULT 30 CHECK (check_interval_minutes >= 5 AND check_interval_minutes <= 1440),
    last_checked TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Gmail tokens table (for future Gmail integration)
CREATE TABLE IF NOT EXISTS gmail_tokens (
    user_id VARCHAR(255) PRIMARY KEY REFERENCES auth_tokens(user_id) ON DELETE CASCADE,
    email VARCHAR(255) NOT NULL,
    access_token TEXT NOT NULL,
    refresh_token TEXT NOT NULL,
    token_type VARCHAR(50) DEFAULT 'Bearer',
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    scopes TEXT[],
    last_sync TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Function to update the updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create triggers for auto-updating updated_at
CREATE TRIGGER update_jobs_updated_at BEFORE UPDATE ON jobs
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_email_filter_settings_updated_at BEFORE UPDATE ON email_filter_settings
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_gmail_tokens_updated_at BEFORE UPDATE ON gmail_tokens
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
