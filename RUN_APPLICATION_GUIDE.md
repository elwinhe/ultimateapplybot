# How to Run the EmailReader Application

This guide walks you through running the application for testing.

## Prerequisites

1. Docker Desktop running on your Mac
2. `.env` file configured with your credentials
3. Frontend dependencies installed

## Step-by-Step Guide

### 1. Start Core Backend Services

Start PostgreSQL and Redis first:
```bash
docker compose up -d postgres redis
```

Wait for them to be ready (about 10 seconds), then run database setup:
```bash
./setup-database.sh
```

### 2. Start Backend API Services

Start the API, worker, and scheduler:
```bash
docker compose up -d api worker beat
```

### 3. Start Email Processing Services

For SQL-based processing (recommended):
```bash
# Update docker-compose.yml first to use SQL versions:
# Change: command: python consumer.py → command: python consumer_sql.py
# Change: command: python worker.py → command: python worker_sql.py

docker compose up -d sqs_consumer apply_worker
```

Or start with specific commands:
```bash
docker compose run -d sqs_consumer python consumer_sql.py
docker compose run -d apply_worker python worker_sql.py
```

### 4. Start Frontend (Local Development)

Since you're having issues with the Docker node image, run the frontend locally:

```bash
cd frontend
npm install  # If not already done
npm run dev
```

The frontend will start at http://localhost:5173

### 5. Alternative: Start Everything Except Frontend

```bash
# Start all backend services
docker compose up -d postgres redis api worker beat sqs_consumer apply_worker

# Then run frontend locally
cd frontend && npm run dev
```

## Testing the Application

### 1. Check Service Health

```bash
# Check all services are running
docker compose ps

# Check API health
curl http://localhost:8000/healthcheck

# View API documentation
open http://localhost:8000/docs
```

### 2. Test Authentication Flow

1. Open frontend at http://localhost:5173
2. Click "Login" or "Connect Outlook"
3. Complete Microsoft OAuth flow
4. You'll be redirected back with a JWT token

### 3. Test Job Processing Flow

Option A: Through email scanning:
```bash
# Trigger email processing (requires auth)
curl -X POST http://localhost:8000/api/v1/emails/process \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

Option B: Manual job submission:
```bash
# Add a job manually
curl -X POST http://localhost:8000/api/v1/jobs/ingest-url \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://jobs.lever.co/example/123"}'
```

### 4. Monitor Processing

Watch logs in separate terminals:
```bash
# API logs
docker compose logs -f api

# Email processor logs
docker compose logs -f worker

# Job consumer logs
docker compose logs -f sqs_consumer

# Application worker logs
docker compose logs -f apply_worker
```

### 5. Check Results

In the frontend:
- Navigate to Jobs page to see processed jobs
- Check Activity page for processing history
- View job statuses (pending → processing → applied/failed)

Or via API:
```bash
# List jobs
curl http://localhost:8000/api/v1/jobs \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"

# Get activity log
curl http://localhost:8000/api/v1/activity \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

## Quick Testing Commands

```bash
# 1. Start minimal backend (for API testing)
docker compose up -d postgres redis api

# 2. Start full backend (without frontend)
docker compose up -d postgres redis api worker beat sqs_consumer apply_worker

# 3. Stop all services
docker compose down

# 4. View all logs
docker compose logs

# 5. Reset database
docker compose down -v  # Warning: Deletes all data
./setup-database.sh
```

## Troubleshooting

### Docker image pull issues
If you get "401 Unauthorized" for Docker images:
1. Open Docker Desktop
2. Sign in to Docker Hub (if required)
3. Or use local builds instead

### Frontend can't connect to backend
1. Check CORS settings in `app/main.py`
2. Verify `VITE_API_BASE_URL` in `frontend/.env.local`
3. Ensure backend is running on port 8000

### Database connection issues
```bash
# Test database connection
docker compose exec postgres psql -U emailreader -d emailreader_db -c "SELECT 1"

# View database logs
docker compose logs postgres
```

### No jobs appearing
1. Check email processing logs: `docker compose logs worker`
2. Verify SQS credentials in `.env`
3. Check consumer logs: `docker compose logs sqs_consumer`

## Development Tips

1. **Use SQL version for production**: The SQL-based consumers are more robust
2. **Monitor logs**: Keep log terminals open while testing
3. **Test incrementally**: Start with basic API, then add services
4. **Use mock data**: Set `VITE_USE_MOCKS=true` for frontend-only testing

The application is now running and ready for testing!
