-- Migration 005: Add filter_start_date column to email_filter_settings
-- This column allows users to override the high watermark for email filtering

ALTER TABLE email_filter_settings 
ADD COLUMN IF NOT EXISTS filter_start_date TIMESTAMP WITH TIME ZONE;

COMMENT ON COLUMN email_filter_settings.filter_start_date IS 'Start date for email filtering (high watermark override)';
