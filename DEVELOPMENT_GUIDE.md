# Development Guide: EmailReader + Career Pilot Dashboard

This guide explains how to set up and run the full-stack application in development mode.

## Architecture Overview

```
EmailReader/                    # Main backend repository
├── app/                        # FastAPI backend
├── frontend/                   # React/Vite frontend (cloned from career-pilot-dash)
├── apply_worker/               # Browser automation worker
├── sqs_consumer/              # Job processing consumer
└── docker-compose.yml         # Full stack orchestration
```

## Quick Start

1. **Run the setup script:**
   ```bash
   ./setup-dev.sh
   ```

2. **Start all services:**
   ```bash
   docker compose up
   ```

3. **Access the applications:**
   - Frontend: http://localhost:5173
   - Backend API: http://localhost:8000
   - API Docs: http://localhost:8000/docs

## Development Modes

### Option 1: Full Docker (Recommended for testing)

All services run in Docker containers:

```bash
docker-compose up
```

**Pros:**
- Consistent environment
- All services integrated
- Easy to test production-like setup

**Cons:**
- Slower frontend development (requires container rebuild)
- Less responsive hot-reload

### Option 2: Hybrid Development (Recommended for frontend development)

Backend services in Docker, frontend running locally:

```bash
# Start backend services
docker compose up postgres redis api worker beat

# In another terminal, start frontend locally
cd frontend
npm run dev
```

**Pros:**
- Fast frontend development with hot-reload
- Real backend integration
- Easy debugging

**Cons:**
- Requires Node.js installed locally
- Need to manage two processes

### Option 3: Local Development

Run everything locally (requires more setup):

```bash
# Start databases
docker compose up postgres redis

# Start backend
uvicorn app.main:app --reload

# Start Celery worker
celery -A app.celery_app worker --loglevel=info

# Start frontend
cd frontend && npm run dev
```

## Service Details

### Backend Services (Docker)
- **postgres**: PostgreSQL database (port 5432)
- **redis**: Redis cache (port 6379)
- **api**: FastAPI backend (port 8000)
- **worker**: Celery worker for email processing
- **beat**: Celery beat scheduler
- **sqs_consumer**: Job URL processing
- **apply_worker**: Browser automation for job applications

### Frontend
- **Port**: 5173 (Vite dev server)
- **Environment**: Configured via `.env.local`
- **API Integration**: Points to backend at `http://localhost:8000`

## Environment Configuration

### Backend (.env)
```env
# Database
POSTGRES_URL=postgresql://emailreader:password@localhost:5432/emailreader_db
REDIS_URL=redis://localhost:6379/0

# Microsoft Graph
MICROSOFT_CLIENT_ID=your_client_id
MICROSOFT_CLIENT_SECRET=your_client_secret
MICROSOFT_TENANT_ID=your_tenant_id

# AWS (for SQS)
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_REGION=us-east-1
```

### Frontend (.env.local)
```env
VITE_API_BASE_URL=http://localhost:8000
VITE_USE_MOCKS=false
```

## API Integration

The frontend communicates with these backend endpoints:

### Authentication
- `GET /api/v1/auth/login` - OAuth login
- `POST /api/v1/auth/callback` - OAuth callback

### Job Management
- `GET /api/v1/jobs` - List jobs
- `POST /api/v1/jobs/ingest-url` - Add job
- `POST /api/v1/jobs/{id}/auto-apply` - Auto-apply

### Settings
- `GET /api/v1/settings/email-filter` - Get email settings
- `POST /api/v1/settings/email-filter` - Update settings
- `POST /api/v1/settings/email-filter/start` - Start filtering

### Integrations
- `GET /api/v1/integrations` - Integration status
- `POST /api/v1/integrations/outlook/connect` - Connect Outlook

## Development Workflow

1. **Make backend changes:**
   - Edit files in `app/`
   - Backend auto-reloads if using uvicorn directly
   - Rebuild container if using Docker: `docker-compose build api`

2. **Make frontend changes:**
   - Edit files in `frontend/src/`
   - Vite provides hot-reload automatically
   - No rebuild needed in hybrid mode

3. **Database changes:**
   - Create migration files in `migrations/`
   - Run migrations: `docker compose exec postgres psql -U emailreader -d emailreader_db -f /path/to/migration.sql`

## Troubleshooting

### Frontend can't connect to backend
- Check that backend is running on port 8000
- Verify `VITE_API_BASE_URL` in frontend `.env.local`
- Check CORS configuration in backend

### Database connection issues
- Ensure PostgreSQL is running: `docker compose ps postgres`
- Check connection string in backend `.env`
- Verify database exists: `docker compose exec postgres psql -U emailreader -l`

### Celery tasks not running
- Check worker is running: `docker compose logs worker`
- Verify Redis connection: `docker compose logs redis`
- Check task queue: `docker compose exec redis redis-cli monitor`

### Authentication issues
- Verify Microsoft OAuth credentials in `.env`
- Check redirect URLs in Azure app registration
- Ensure JWT secret is set

## Production Deployment

For production deployment, use the production docker-compose:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up
```

This will:
- Build optimized frontend with nginx
- Use production environment variables
- Serve frontend on port 80
- Proxy API requests to backend

## Useful Commands

```bash
# View logs
docker compose logs -f [service_name]

# Rebuild specific service
docker compose build [service_name]

# Access database
docker compose exec postgres psql -U emailreader -d emailreader_db

# Access Redis
docker compose exec redis redis-cli

# Run migrations
docker compose exec postgres psql -U emailreader -d emailreader_db -f /path/to/migration.sql

# Install frontend dependencies
cd frontend && npm install

# Run frontend tests
cd frontend && npm test

# Run backend tests
pytest
```
