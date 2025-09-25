#!/bin/bash

# Integration Testing Script
echo "🧪 Testing Frontend-Backend Integration..."

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Backend URL
API_URL="http://localhost:8000"

# Function to test endpoint
test_endpoint() {
    local method=$1
    local endpoint=$2
    local description=$3
    local data=$4
    
    echo -n "Testing $description ($method $endpoint)... "
    
    if [ "$method" = "GET" ]; then
        response=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL$endpoint")
    else
        response=$(curl -s -o /dev/null -w "%{http_code}" -X $method "$API_URL$endpoint" \
            -H "Content-Type: application/json" \
            -d "$data")
    fi
    
    if [ "$response" = "200" ] || [ "$response" = "201" ] || [ "$response" = "401" ] || [ "$response" = "422" ]; then
        echo -e "${GREEN}✓${NC} ($response)"
    else
        echo -e "${RED}✗${NC} ($response)"
    fi
}

echo "1️⃣ Checking if backend is running..."
health_response=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/healthcheck")
if [ "$health_response" != "200" ] && [ "$health_response" != "503" ]; then
    echo -e "${RED}Backend is not running! Please start it with: docker compose up${NC}"
    exit 1
fi
echo -e "${GREEN}Backend is accessible${NC}"

echo ""
echo "2️⃣ Testing API Endpoints..."

# Health check
test_endpoint "GET" "/healthcheck" "Health Check"

# Jobs endpoints
test_endpoint "GET" "/api/v1/jobs" "List Jobs"
test_endpoint "POST" "/api/v1/jobs/ingest-url" "Ingest Job URL" '{"url":"https://example.com/job"}'
test_endpoint "POST" "/api/v1/jobs/123/auto-apply" "Auto Apply Job" '{}'

# Activity endpoint
test_endpoint "GET" "/api/v1/activity" "Get Activity"

# Settings endpoints
test_endpoint "GET" "/api/v1/settings/email-filter" "Get Email Settings"
test_endpoint "POST" "/api/v1/settings/email-filter" "Update Email Settings" '{"enabled":true,"keywords":[]}'
test_endpoint "POST" "/api/v1/settings/email-filter/start" "Start Email Filtering"
test_endpoint "POST" "/api/v1/settings/email-filter/stop" "Stop Email Filtering"
test_endpoint "POST" "/api/v1/settings/clear-cache" "Clear Cache"

# Integration endpoints
test_endpoint "GET" "/api/v1/integrations" "Get Integrations"
test_endpoint "POST" "/api/v1/integrations/outlook/connect" "Connect Outlook"
test_endpoint "POST" "/api/v1/integrations/outlook/disconnect" "Disconnect Outlook"

echo ""
echo "3️⃣ Testing Database Connection..."
db_test=$(docker compose exec -T postgres psql -U emailreader -d emailreader_db -c "SELECT 1" 2>&1)
if echo "$db_test" | grep -q "1"; then
    echo -e "${GREEN}Database connection successful${NC}"
    
    # Check if tables exist
    echo "Checking required tables..."
    tables=("auth_tokens" "jobs" "activity_events" "email_filter_settings")
    for table in "${tables[@]}"; do
        if docker compose exec -T postgres psql -U emailreader -d emailreader_db -c "\dt $table" 2>&1 | grep -q "$table"; then
            echo -e "  ${GREEN}✓${NC} Table '$table' exists"
        else
            echo -e "  ${RED}✗${NC} Table '$table' missing - run migrations!"
        fi
    done
else
    echo -e "${RED}Database connection failed${NC}"
fi

echo ""
echo "4️⃣ Frontend Configuration..."
if [ -f "frontend/.env.local" ]; then
    echo -e "${GREEN}✓${NC} Frontend .env.local exists"
    grep "VITE_API_BASE_URL" frontend/.env.local
    grep "VITE_USE_MOCKS" frontend/.env.local
else
    echo -e "${RED}✗${NC} Frontend .env.local missing"
fi

echo ""
echo "📋 Summary:"
echo "- Backend API: $API_URL"
echo "- Frontend: http://localhost:5173"
echo "- API Docs: $API_URL/docs"
echo ""
echo "🚀 To start development:"
echo "  1. Ensure database migrations are run: docker compose exec postgres psql -U emailreader -d emailreader_db -f /path/to/migrations/002_add_jobs_and_activity_tables.sql"
echo "  2. Start backend: docker compose up"
echo "  3. Start frontend: cd frontend && npm run dev"
echo "  4. For auth, you'll need to get a JWT token first via /api/v1/auth/login"
