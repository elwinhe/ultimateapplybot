# Frontend-Backend Integration Testing Guide

This guide helps you verify that the frontend is properly connected to the backend API.

## Prerequisites

1. Backend services running: `docker compose up`
2. Frontend environment configured: `.env.local` with correct API URL
3. Database migrations applied

## Quick Test

Run the automated test script:
```bash
./test-integration.sh
```

## Manual Testing Steps

### 1. Database Setup

First, ensure the database is properly configured:

```bash
./setup-database.sh
```

This will:
- Start PostgreSQL if not running
- Create necessary tables
- Run migrations
- Verify schema

### 2. Backend API Testing

#### Check if backend is running:
```bash
curl http://localhost:8000/healthcheck
```

Expected response:
```json
{
  "status": "ok",
  "postgres_status": "ok",
  "redis_status": "ok"
}
```

#### Test API endpoints without auth:
```bash
# Health check
curl http://localhost:8000/healthcheck

# API documentation
open http://localhost:8000/docs
```

### 3. Frontend-Backend Connection

#### Start the frontend:
```bash
cd frontend
npm run dev
```

#### Check frontend environment:
```bash
cat frontend/.env.local
```

Should contain:
```
VITE_API_BASE_URL=http://localhost:8000
VITE_USE_MOCKS=false
```

### 4. Authentication Flow

Since most endpoints require authentication, you need to:

1. **Get OAuth URL** (backend running):
   ```bash
   curl http://localhost:8000/api/v1/auth/login -L
   ```
   This will redirect to Microsoft OAuth

2. **Complete OAuth flow**:
   - Login with Microsoft account
   - Backend will store tokens and return JWT

3. **Use JWT for API calls**:
   ```bash
   # Example with JWT token
   curl -H "Authorization: Bearer YOUR_JWT_TOKEN" \
        http://localhost:8000/api/v1/jobs
   ```

### 5. Test Each Integration Point

#### Jobs API:
```bash
# List jobs (requires auth)
curl -H "Authorization: Bearer YOUR_JWT_TOKEN" \
     http://localhost:8000/api/v1/jobs

# Add job URL
curl -X POST http://localhost:8000/api/v1/jobs/ingest-url \
     -H "Authorization: Bearer YOUR_JWT_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"url": "https://example.com/job"}'
```

#### Activity API:
```bash
curl -H "Authorization: Bearer YOUR_JWT_TOKEN" \
     http://localhost:8000/api/v1/activity
```

#### Settings API:
```bash
# Get email filter settings
curl -H "Authorization: Bearer YOUR_JWT_TOKEN" \
     http://localhost:8000/api/v1/settings/email-filter

# Update settings
curl -X POST http://localhost:8000/api/v1/settings/email-filter \
     -H "Authorization: Bearer YOUR_JWT_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"enabled": true, "keywords": ["job", "hiring"], "sender_whitelist": [], "check_interval_minutes": 30}'
```

#### Integrations API:
```bash
curl -H "Authorization: Bearer YOUR_JWT_TOKEN" \
     http://localhost:8000/api/v1/integrations
```

### 6. Frontend Console Testing

Open browser developer console and test API calls:

```javascript
// Test without auth (will fail for protected endpoints)
fetch('http://localhost:8000/api/v1/jobs')
  .then(r => r.json())
  .then(console.log)
  .catch(console.error);

// Test with mock token (replace with real JWT)
const token = 'YOUR_JWT_TOKEN';
fetch('http://localhost:8000/api/v1/jobs', {
  headers: {
    'Authorization': `Bearer ${token}`
  }
})
  .then(r => r.json())
  .then(console.log)
  .catch(console.error);
```

## Common Issues & Solutions

### Frontend can't connect to backend

1. **CORS error**: Check browser console for CORS errors
   - Verify frontend URL is in CORS origins in `app/main.py`
   - Ensure backend is running on expected port

2. **Connection refused**: Backend not running
   - Run `docker compose up`
   - Check `docker compose ps`

3. **401 Unauthorized**: Missing or invalid JWT token
   - Complete OAuth flow first
   - Check token expiration

### Database connection issues

1. **Tables don't exist**: Run migrations
   ```bash
   ./setup-database.sh
   ```

2. **Connection refused**: PostgreSQL not running
   ```bash
   docker compose up postgres
   ```

3. **Authentication failed**: Wrong credentials
   - Check `.env` file for correct database URL

### API Response Mismatches

The frontend expects certain response formats. Key differences:

1. **Jobs endpoint**: Returns array directly, not `{items: [], total: n}`
2. **Activity endpoint**: Returns array directly, not `{items: []}`
3. **Integrations**: Returns `{integrations: []}` not array directly

Use the corrected API client in `frontend/src/lib/api-fixes.ts` for proper integration.

## Development Workflow

1. **Start backend first**:
   ```bash
   docker compose up
   ```

2. **Run database setup**:
   ```bash
   ./setup-database.sh
   ```

3. **Start frontend**:
   ```bash
   cd frontend
   npm run dev
   ```

4. **Test integration**:
   ```bash
   ./test-integration.sh
   ```

5. **Monitor logs**:
   ```bash
   # Backend logs
   docker compose logs -f api

   # Worker logs
   docker compose logs -f worker

   # All logs
   docker compose logs -f
   ```

## Authentication Setup for Development

For development, you can:

1. **Use real OAuth flow**: Set up Microsoft app registration
2. **Create test JWT**: For testing without OAuth:

```python
# Generate test JWT (run in Python)
import jwt
from datetime import datetime, timedelta

secret = "your-secret-key"  # Same as JWT_SECRET_KEY in .env
payload = {
    "sub": "test-user-id",
    "email": "test@example.com",
    "exp": datetime.utcnow() + timedelta(days=1)
}
token = jwt.encode(payload, secret, algorithm="HS256")
print(f"Test JWT: {token}")
```

Then use this token in API calls or set it in localStorage for the frontend.
