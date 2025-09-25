# pgAdmin Database Access Guide

## Accessing pgAdmin

1. **Open pgAdmin in your browser:**
   - URL: http://localhost:5050
   - Email: `admin@emailreader.com`
   - Password: `admin123`

## Setting up Database Connection

### Step 1: Add New Server
1. Right-click on "Servers" in the left panel
2. Select "Register" → "Server..."

### Step 2: General Tab
- **Name**: `EmailReader Database` (or any name you prefer)

### Step 3: Connection Tab
- **Host name/address**: `postgres` (Docker service name)
- **Port**: `5432`
- **Maintenance database**: `emailreader_db`
- **Username**: `emailreader`
- **Password**: `password`

> **Note**: If you get a "Name does not resolve" error, make sure all services are running on the same Docker network. Run `docker compose down && docker compose up -d postgres redis pgadmin` to restart with proper networking.

### Step 4: Save
Click "Save" to create the connection.

## Viewing Database Tables

Once connected, you can explore your database:

### Database Structure
```
EmailReader Database
├── Databases
│   └── emailreader_db
│       ├── Schemas
│       │   └── public
│       │       ├── Tables
│       │       │   ├── users
│       │       │   ├── auth_tokens
│       │       │   ├── jobs
│       │       │   ├── activity_events
│       │       │   ├── email_filter_settings
│       │       │   └── gmail_tokens
│       │       ├── Functions
│       │       └── Triggers
```

### Key Tables to Explore

1. **`users`** - User account information
   - View user registrations and login data
   - Check user IDs and email addresses

2. **`auth_tokens`** - OAuth integration tokens
   - See connected email providers (Outlook/Microsoft Graph)
   - Monitor token expiration dates

3. **`jobs`** - Job applications tracking
   - View all job URLs and application statuses
   - Check job details like company, location, technologies

4. **`activity_events`** - User activity logs
   - Monitor system activity and user actions
   - Track email scanning and job processing events

5. **`email_filter_settings`** - Email filtering configuration
   - View user-specific email filtering rules
   - Check keywords and sender whitelists

6. **`gmail_tokens`** - Gmail OAuth tokens
   - See Gmail integration status
   - Monitor Gmail API token health

## Useful Queries

### View All Users
```sql
SELECT user_id, email, name, created_at, is_active 
FROM users 
ORDER BY created_at DESC;
```

### View User's Jobs
```sql
SELECT j.*, u.email, u.name 
FROM jobs j 
JOIN users u ON j.user_id = u.user_id 
ORDER BY j.created_at DESC;
```

### Check OAuth Token Status
```sql
SELECT 
    u.email,
    at.provider,
    at.expires_at,
    at.last_seen_timestamp,
    CASE 
        WHEN at.expires_at > NOW() THEN 'Valid'
        ELSE 'Expired'
    END as token_status
FROM auth_tokens at
JOIN users u ON at.user_id = u.user_id;
```

### View Recent Activity
```sql
SELECT 
    u.email,
    ae.type,
    ae.title,
    ae.description,
    ae.created_at
FROM activity_events ae
JOIN users u ON ae.user_id = u.user_id
ORDER BY ae.created_at DESC
LIMIT 20;
```

## Troubleshooting

### Connection Issues
- Ensure PostgreSQL container is running: `docker compose ps postgres`
- Check if pgAdmin can reach the database: `docker compose logs pgadmin`

### Permission Issues
- Make sure you're using the correct credentials
- The database user `emailreader` has full access to the `emailreader_db` database

### Data Not Showing
- Run database migrations if tables are missing: `./setup-database.sh`
- Check if the user has data in the tables

## Security Notes

- The pgAdmin credentials are for development only
- In production, use strong passwords and restrict access
- Consider using environment variables for sensitive data

## Quick Access URLs

- **pgAdmin**: http://localhost:5050
- **API Documentation**: http://localhost:8000/docs
- **Frontend**: http://localhost:8080 (or check terminal for current port)
