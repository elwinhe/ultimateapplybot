# SQL-Based Job Tracking Setup Guide

This guide helps you set up the EmailReader to use PostgreSQL for job tracking instead of Google Sheets.

## Architecture Overview

```
Email Scanner → SQS Queue → SQL Consumer → PostgreSQL Database
                                              ↓
                        Apply Queue → Apply Worker → Update Job Status
```

## Quick Start

### 1. Database Setup

Run the database setup script:
```bash
./setup-database.sh
```

This will:
- Start PostgreSQL container
- Create the database
- Run migrations to create tables:
  - `auth_tokens` - User authentication
  - `jobs` - Job applications tracking
  - `activity_events` - Activity log
  - `email_filter_settings` - Email filtering preferences

### 2. Update Configuration

Create/update your `.env` file:
```env
# Database
POSTGRES_URL=postgresql://emailreader:password@localhost:5432/emailreader_db

# Redis
REDIS_URL=redis://localhost:6379/0

# AWS SQS
AWS_ACCESS_KEY_ID=your_key
AWS_SECRET_ACCESS_KEY=your_secret
AWS_REGION=us-east-1
SQS_QUEUE_URL=https://sqs.us-east-1.amazonaws.com/123456789/job-queue
SQS_APPLY_QUEUE_URL=https://sqs.us-east-1.amazonaws.com/123456789/apply-queue

# Microsoft OAuth
MICROSOFT_CLIENT_ID=your_client_id
MICROSOFT_CLIENT_SECRET=your_client_secret
MICROSOFT_TENANT_ID=your_tenant_id

# JWT
JWT_SECRET_KEY=your-secret-key
```

### 3. Update Docker Compose

The existing `docker-compose.yml` already includes PostgreSQL. For the SQL-based workers, update:

```yaml
sqs_consumer:
  build:
    context: .
    dockerfile: sqs_consumer/Dockerfile
  container_name: emailreader_sqs_consumer_sql
  restart: unless-stopped
  env_file:
    - .env
  command: python consumer_sql.py  # Use SQL version
  depends_on:
    - postgres
    - moto

apply_worker:
  build:
    context: ./apply_worker
    dockerfile: Dockerfile
  container_name: emailreader_apply_worker_sql
  restart: unless-stopped
  env_file:
    - .env
  command: python worker_sql.py  # Use SQL version
  depends_on:
    - postgres
    - moto
```

### 4. Start Services

```bash
# Start all services
docker compose up

# Or start specific services
docker compose up postgres redis api worker beat
docker compose up sqs_consumer apply_worker
```

## API Endpoints

The backend provides these endpoints for the frontend:

### Jobs Management
- `GET /api/v1/jobs` - List all jobs for authenticated user
- `POST /api/v1/jobs/ingest-url` - Add a new job URL
- `POST /api/v1/jobs/{id}/auto-apply` - Trigger auto-apply

### Activity Tracking
- `GET /api/v1/activity` - Get activity log

### Settings
- `GET /api/v1/settings/email-filter` - Get email filter settings
- `POST /api/v1/settings/email-filter` - Update settings
- `POST /api/v1/settings/email-filter/start` - Start email filtering
- `POST /api/v1/settings/email-filter/stop` - Stop email filtering

### Integrations
- `GET /api/v1/integrations` - Get integration status
- `POST /api/v1/integrations/outlook/connect` - Connect Outlook

## Data Flow

1. **Email Processing**:
   - Email scanner finds job emails
   - Extracts URLs and sends to SQS queue
   - SQL consumer reads from queue
   - Checks for duplicates in PostgreSQL
   - Inserts new jobs with status 'pending'

2. **Auto-Apply Process**:
   - SQL consumer forwards messages to apply queue
   - Apply worker picks up job
   - Updates status to 'processing'
   - Runs browser automation
   - Updates job with results (applied/failed)
   - Logs activity events

3. **Frontend Integration**:
   - Frontend calls API endpoints
   - API queries PostgreSQL
   - Returns jobs with filtering/pagination
   - Real-time status updates

## Database Schema

### Jobs Table
```sql
CREATE TABLE jobs (
    id UUID PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    url TEXT NOT NULL,
    title VARCHAR(500),
    company VARCHAR(255),
    location VARCHAR(255),
    status VARCHAR(50) DEFAULT 'pending',
    technologies TEXT,
    seniority VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    applied_at TIMESTAMP WITH TIME ZONE,
    UNIQUE(user_id, url)
);
```

### Activity Events Table
```sql
CREATE TABLE activity_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(255) NOT NULL,
    type VARCHAR(50) NOT NULL,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

## Testing

### 1. Test Database Connection
```bash
docker compose exec postgres psql -U emailreader -d emailreader_db -c "SELECT 1"
```

### 2. Test API Endpoints
```bash
# Get health check
curl http://localhost:8000/healthcheck

# Get API docs
open http://localhost:8000/docs
```

### 3. Test Job Flow
```bash
# Manually add a job (requires auth token)
curl -X POST http://localhost:8000/api/v1/jobs/ingest-url \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com/job"}'
```

### 4. Monitor Logs
```bash
# API logs
docker compose logs -f api

# Consumer logs
docker compose logs -f sqs_consumer

# Apply worker logs
docker compose logs -f apply_worker
```

## Advantages of SQL over Google Sheets

1. **Performance**: Faster queries with proper indexing
2. **Concurrency**: Multiple workers can write simultaneously
3. **Relationships**: Link jobs to users, activities, etc.
4. **Queries**: Complex filtering, aggregations, full-text search
5. **Transactions**: Atomic operations, no partial writes
6. **Scalability**: Can handle millions of records
7. **Security**: Role-based access, encrypted connections

## Troubleshooting

### Database Connection Issues
```bash
# Check if PostgreSQL is running
docker compose ps postgres

# View PostgreSQL logs
docker compose logs postgres

# Connect manually
docker compose exec postgres psql -U emailreader -d emailreader_db
```

### Consumer Not Processing Jobs
```bash
# Check consumer logs
docker compose logs sqs_consumer

# Verify SQS connection
# Check AWS credentials in .env
```

### Jobs Not Being Applied
```bash
# Check apply worker logs
docker compose logs apply_worker

# Verify job exists in database
docker compose exec postgres psql -U emailreader -d emailreader_db \
  -c "SELECT * FROM jobs ORDER BY created_at DESC LIMIT 10"
```

## Next Steps

1. Ensure all services are configured for SQL
2. Test the complete flow from email to application
3. Update frontend to use SQL-based API endpoints
4. Set up monitoring and alerting
5. Configure backups for PostgreSQL

The SQL-based system is now ready for production use!
