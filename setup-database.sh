#!/bin/bash

# Database Setup Script
echo "🗄️ Setting up EmailReader Database..."

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Check if PostgreSQL is running
echo "Checking if PostgreSQL is running..."
if ! docker compose ps postgres | grep -q "running"; then
    echo -e "${YELLOW}PostgreSQL is not running. Starting it now...${NC}"
    docker compose up -d postgres
    echo "Waiting for PostgreSQL to be ready..."
    sleep 10
fi

# Test database connection
echo "Testing database connection..."
if docker compose exec -T postgres psql -U emailreader -d emailreader_db -c "SELECT 1" > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Database connection successful${NC}"
else
    echo -e "${RED}✗ Failed to connect to database${NC}"
    echo "Creating database..."
    docker compose exec -T postgres psql -U emailreader -c "CREATE DATABASE emailreader_db" 2>/dev/null || true
fi

# Copy migration file to container
echo "Copying migration files to container..."
docker compose exec -T postgres mkdir -p /migrations 2>/dev/null || true
docker cp migrations/002_add_jobs_and_activity_tables.sql emailreader_postgres:/migrations/

# Run migrations
echo "Running database migrations..."

# First, check if auth_tokens table exists (from initial setup)
if ! docker compose exec -T postgres psql -U emailreader -d emailreader_db -c "\dt auth_tokens" 2>&1 | grep -q "auth_tokens"; then
    echo "Running initial migration..."
    # Create initial schema
    docker compose exec -T postgres psql -U emailreader -d emailreader_db << 'EOF'
-- Initial schema for auth tokens
CREATE TABLE IF NOT EXISTS auth_tokens (
    user_id VARCHAR(255) PRIMARY KEY,
    user_email VARCHAR(255) NOT NULL,
    refresh_token TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_seen_timestamp TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_auth_tokens_email ON auth_tokens(user_email);
EOF
fi

# Run the new migration
echo "Running jobs and activity tables migration..."
docker compose exec -T postgres psql -U emailreader -d emailreader_db -f /migrations/002_add_jobs_and_activity_tables.sql 2>&1 | grep -v "already exists" || true

# Verify tables
echo ""
echo "Verifying database schema..."
tables=("auth_tokens" "jobs" "activity_events" "email_filter_settings" "gmail_tokens")
all_good=true

for table in "${tables[@]}"; do
    if docker compose exec -T postgres psql -U emailreader -d emailreader_db -c "\dt $table" 2>&1 | grep -q "$table"; then
        echo -e "${GREEN}✓${NC} Table '$table' exists"
    else
        echo -e "${RED}✗${NC} Table '$table' missing"
        all_good=false
    fi
done

# Show table schemas
echo ""
echo "Database schema details:"
docker compose exec -T postgres psql -U emailreader -d emailreader_db -c "\d+ jobs" 2>/dev/null || true

echo ""
if [ "$all_good" = true ]; then
    echo -e "${GREEN}✅ Database setup complete!${NC}"
else
    echo -e "${YELLOW}⚠️  Some tables are missing. Please check the migration logs above.${NC}"
fi

echo ""
echo "📋 Database Info:"
echo "  Host: localhost"
echo "  Port: 5432"
echo "  Database: emailreader_db"
echo "  Username: emailreader"
echo "  Password: password"
echo ""
echo "To connect manually:"
echo "  docker compose exec postgres psql -U emailreader -d emailreader_db"
