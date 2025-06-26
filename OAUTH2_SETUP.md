# OAuth2 Setup for Personal Microsoft Account Authentication

This guide explains how to set up OAuth2 authentication for personal Microsoft accounts to access the Microsoft Graph API.

## Overview

The application uses **delegated authentication** with **personal Microsoft accounts** (Outlook.com, Hotmail, etc.) to access the user's mailbox. This allows the application to:

- Fetch emails from the authenticated user's mailbox
- Download raw `.eml` content
- Process and archive emails based on filtering criteria

## Prerequisites

1. **Personal Microsoft Account**: An Outlook.com, Hotmail, or other personal Microsoft account
2. **Microsoft Entra ID (Azure AD) Application**: A registered application in the Microsoft Entra ID portal
3. **Redirect URI**: A callback URL for the OAuth2 flow

## Step 1: Register Application in Microsoft Entra ID

### 1.1 Access the Microsoft Entra ID Portal

1. Go to [Microsoft Entra ID Portal](https://portal.azure.com/#blade/Microsoft_AAD_RegisteredApps/ApplicationsListBlade)
2. Sign in with your Microsoft account (this can be a personal account or work account)

### 1.2 Create New Application Registration

1. Click **"New registration"**
2. Fill in the details:
   - **Name**: `EmailReader Personal Account`
   - **Supported account types**: Select **"Accounts in any organizational directory (Any Azure AD directory - Multitenant) and personal Microsoft accounts (e.g. Skype, Xbox)"**
   - **Redirect URI**: 
     - Type: **Web**
     - URI: `http://localhost:8000/api/v1/auth/callback`
3. Click **"Register"**

### 1.3 Configure Application Permissions

1. In your new application, go to **"API permissions"**
2. Click **"Add a permission"**
3. Select **"Microsoft Graph"**
4. Choose **"Delegated permissions"**
5. Search for and select:
   - `Mail.Read` - Read user mail
6. Click **"Add permissions"**
7. Click **"Grant admin consent"** (if available, otherwise skip)

### 1.4 Get Application Credentials

1. Go to **"Overview"** in your application
2. Copy the **"Application (client) ID"** - you'll need this for your `.env` file

## Step 2: Configure Environment Variables

Create or update your `.env` file with the following variables:

```env
# Microsoft Graph API (Personal Account Authentication)
CLIENT_ID=your-application-client-id-here

# OAuth2 Redirect URI (must match what you configured in Entra ID)
REDIRECT_URI=http://localhost:8000/api/v1/auth/callback

# Target user email (the personal account you want to authenticate)
TARGET_EXTERNAL_USER=your-personal-email@outlook.com

# Other required settings...
REDIS_URL=redis://localhost:6379
DATABASE_URL=postgresql://user:password@localhost:5432/emailreader
S3_BUCKET_NAME=your-bucket-name
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key
AWS_REGION=us-east-1
```

## Step 3: Authentication Flow

### 3.1 Initial Authentication

1. Start the application: `docker-compose up -d`
2. Visit: `http://localhost:8000/api/v1/auth/login`
3. You'll be redirected to Microsoft's login page
4. Sign in with your **personal Microsoft account** (Outlook.com, Hotmail, etc.)
5. Grant the requested permissions
6. You'll be redirected back to the callback URL
7. The application will store your refresh token in Redis

### 3.2 Subsequent Access

After the initial authentication:
- The application automatically uses the stored refresh token
- No manual re-authentication required
- Tokens are automatically refreshed when needed

## Step 4: Testing the Setup

### 4.1 Test Authentication

```bash
# Test the login endpoint
curl -v http://localhost:8000/api/v1/auth/login

# Should return a 307 redirect to Microsoft login
```

### 4.2 Test Email Processing

```bash
# Trigger the email processing task
curl -X POST http://localhost:8000/api/v1/emails/process

# Check the logs
docker-compose logs worker
```

## Troubleshooting

### Common Issues

1. **"Use work or school account instead" error**
   - **Solution**: Ensure you selected "Accounts in any organizational directory and personal Microsoft accounts" during app registration
   - **Solution**: Make sure you're using `PublicClientApplication` (which we now do)

2. **"Invalid client" error**
   - **Solution**: Verify your `CLIENT_ID` matches the Application (client) ID from Entra ID
   - **Solution**: Ensure the redirect URI exactly matches what's configured in Entra ID

3. **"Insufficient privileges" error**
   - **Solution**: Verify `Mail.Read` permission is granted in the app registration
   - **Solution**: Ensure you're signed in with the correct personal account

4. **"Redirect URI mismatch" error**
   - **Solution**: Double-check that `REDIRECT_URI` in your `.env` exactly matches the redirect URI in Entra ID
   - **Solution**: Include the full URL including protocol and port

### Debug Mode

To see detailed authentication logs:

```bash
# Check API logs
docker-compose logs api

# Check worker logs
docker-compose logs worker
```

## Security Considerations

1. **Token Storage**: Refresh tokens are stored in Redis (in production, consider more secure storage)
2. **HTTPS**: In production, always use HTTPS for the redirect URI
3. **Token Expiry**: Refresh tokens have a limited lifetime and will need renewal
4. **Scope Limitation**: The application only requests `Mail.Read` permission

## Production Deployment

For production deployment:

1. **Update Redirect URI**: Change from `http://localhost:8000/api/v1/auth/callback` to your production domain
2. **Use HTTPS**: Ensure all endpoints use HTTPS
3. **Secure Token Storage**: Consider using a more secure token storage solution
4. **Environment Variables**: Use proper secrets management for production credentials

## API Endpoints

- `GET /api/v1/auth/login` - Initiate OAuth2 login flow
- `GET /api/v1/auth/callback` - OAuth2 callback endpoint (handled automatically)
- `POST /api/v1/emails/process` - Trigger email processing task
- `GET /healthcheck` - Health check endpoint 