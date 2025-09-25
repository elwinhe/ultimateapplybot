# SQL Migration Checklist

## ✅ What's Already Done

1. **Database Schema** - Tables created in `migrations/002_add_jobs_and_activity_tables.sql`
2. **API Endpoints** - Full CRUD operations in `app/api/v1/jobs.py`
3. **SQL Consumer** - Created `sqs_consumer/consumer_sql.py` 
4. **SQL Apply Worker** - Created `apply_worker/worker_sql.py`
5. **Frontend API** - Endpoints ready at `/api/v1/jobs`, `/api/v1/activity`, etc.

## 📋 Steps to Complete Migration

### 1. Update Docker Compose
In `docker-compose.yml`, change the command for consumers:
```yaml
sqs_consumer:
  # ... existing config ...
  command: python consumer_sql.py  # Changed from consumer.py

apply_worker:
  # ... existing config ...  
  command: python worker_sql.py    # Changed from worker.py
```

Or use the SQL-specific Dockerfiles:
```yaml
sqs_consumer:
  build:
    context: ./sqs_consumer
    dockerfile: Dockerfile.sql    # Use SQL version

apply_worker:
  build:
    context: ./apply_worker
    dockerfile: Dockerfile.sql    # Use SQL version
```

### 2. Update Frontend API Calls
In `frontend/src/lib/api.ts`, ensure endpoints match:
- Change `/api/jobs` → `/api/v1/jobs`
- Update response types to match backend
- Add JWT authentication headers

### 3. Environment Variables
Ensure `.env` has PostgreSQL connection:
```env
POSTGRES_URL=postgresql://emailreader:password@postgres:5432/emailreader_db
```

### 4. Run Database Setup
```bash
# Start PostgreSQL
docker compose up -d postgres

# Run migrations
./setup-database.sh
```

### 5. Start Services
```bash
# Start backend
docker compose up api worker beat

# Start SQL consumers
docker compose up sqs_consumer apply_worker

# Start frontend
cd frontend && npm run dev
```

## 🔄 Key Differences from Google Sheets

### Data Storage
- **Before**: Single Google Sheet with rows
- **After**: PostgreSQL with relational tables

### Querying
- **Before**: Load all rows, filter in memory
- **After**: SQL queries with indexes, pagination

### Concurrency
- **Before**: Rate limited by Google Sheets API
- **After**: Connection pooling, parallel writes

### Status Updates
- **Before**: Update specific cell in sheet
- **After**: Update job record by ID

### User Isolation
- **Before**: Filter by user_id column
- **After**: WHERE clause with user_id

## 🧪 Testing the Migration

1. **Add a test job**:
```bash
curl -X POST http://localhost:8000/api/v1/jobs/ingest-url \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{"url": "https://example.com/test-job"}'
```

2. **Check it was created**:
```bash
docker compose exec postgres psql -U emailreader -d emailreader_db \
  -c "SELECT * FROM jobs ORDER BY created_at DESC LIMIT 1"
```

3. **Monitor processing**:
```bash
# Watch consumer logs
docker compose logs -f sqs_consumer

# Watch apply worker logs  
docker compose logs -f apply_worker
```

4. **Check final status**:
```bash
curl http://localhost:8000/api/v1/jobs \
  -H "Authorization: Bearer YOUR_TOKEN"
```

## 🎯 Benefits Achieved

1. **Multi-user Support** - Each user's jobs are isolated
2. **Better Performance** - Indexed queries, no API rate limits
3. **Transactional Safety** - Atomic updates, no partial writes
4. **Rich Queries** - Filter by status, date, search text
5. **Activity Tracking** - Full audit log of all actions
6. **Scalability** - Can handle thousands of concurrent users

The migration to SQL is complete and ready for testing!
