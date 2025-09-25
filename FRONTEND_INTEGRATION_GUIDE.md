# Frontend Integration Guide

This guide explains how to integrate the Career Pilot Dashboard frontend with the EmailReader backend.

## Backend API Endpoints

The EmailReader backend now provides all the API endpoints required by the frontend:

### 📋 Core Job Management
- `GET /api/v1/jobs` - Get jobs list with filtering and pagination
- `POST /api/v1/jobs/ingest-url` - Add new job from URL
- `POST /api/v1/jobs/{id}/auto-apply` - Trigger auto-apply for specific job

### 📊 Activity/Events
- `GET /api/v1/activity` - Get activity log with optional filters

### ⚙️ Settings & Configuration
- `GET /api/v1/settings/email-filter` - Get email filter settings
- `POST /api/v1/settings/email-filter` - Update email filter settings
- `POST /api/v1/settings/email-filter/start` - Start email filtering
- `POST /api/v1/settings/email-filter/stop` - Stop email filtering
- `POST /api/v1/settings/clear-cache` - Clear application cache

### 🔗 Integration Endpoints
- `GET /api/v1/integrations` - Get all integration statuses
- `POST /api/v1/integrations/gmail/connect` - Connect Gmail (placeholder)
- `POST /api/v1/integrations/gmail/disconnect` - Disconnect Gmail
- `POST /api/v1/integrations/outlook/connect` - Connect Outlook account
- `POST /api/v1/integrations/outlook/disconnect` - Disconnect Outlook

### 🔧 Existing Endpoints
- `GET /healthcheck` - Health check endpoint
- `GET /api/v1/auth/login` - Initiate OAuth login
- `POST /api/v1/auth/callback` - Handle OAuth callback
- `POST /api/v1/emails/process` - Trigger email processing
- `GET /api/v1/emails/me` - Get user's emails

## Frontend Configuration

1. **Update Environment Variables**
   In your frontend's `.env` file:
   ```env
   VITE_API_BASE_URL=http://localhost:8000  # Local development
   # or
   VITE_API_BASE_URL=https://your-backend-domain.com  # Production
   VITE_USE_MOCKS=false  # Disable mock mode
   ```

2. **Authentication Setup**
   The backend uses JWT tokens for authentication. Update your frontend API client to:
   - Include the JWT token in the Authorization header: `Bearer <token>`
   - Handle token refresh when needed
   - Redirect to `/api/v1/auth/login` for initial authentication

3. **CORS Configuration**
   The backend is configured to accept requests from:
   - `http://localhost:3000`
   - `http://localhost:5173`
   - `https://career-pilot-dash.vercel.app`
   
   Add your production domain to the CORS origins in `app/main.py` if needed.

## Database Setup

Run the migration to create the required tables:
```bash
psql -U your_user -d your_database -f migrations/002_add_jobs_and_activity_tables.sql
```

## Integration Flow

1. **User Authentication**
   - Frontend redirects to `/api/v1/auth/login`
   - User authenticates with Microsoft
   - Backend stores tokens and returns JWT
   - Frontend stores JWT for subsequent requests

2. **Email Processing**
   - Jobs are automatically discovered via email scanning
   - Manual job ingestion available via `/api/v1/jobs/ingest-url`
   - Jobs are queued in SQS for processing

3. **Auto-Apply Flow**
   - Frontend triggers auto-apply via `/api/v1/jobs/{id}/auto-apply`
   - Backend creates Celery task for browser automation
   - Status updates via activity events

## Notes

- Resume management endpoints are not yet implemented
- Gmail integration is a placeholder - only Outlook is currently supported
- The backend expects a PostgreSQL database with proper schema
- Redis is required for caching and task management
- Celery workers must be running for async tasks

## Testing

1. Start the backend:
   ```bash
   uvicorn app.main:app --reload
   ```

2. Start Celery workers:
   ```bash
   celery -A app.celery_app worker --loglevel=info
   ```

3. Update frontend to point to local backend and disable mocks

4. Test the integration by:
   - Authenticating via Microsoft OAuth
   - Manually ingesting a job URL
   - Checking the activity log
   - Testing email filter settings
