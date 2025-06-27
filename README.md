Email Processing Service

This project is a robust, production-ready application designed to read and filter emails from Microsoft Outlook accounts, process them based on specific criteria, and archive them as .eml files in an S3 bucket. It is built with a scalable, multi-user architecture using FastAPI for the API layer and Celery for background task processing.
Core Architecture

The application is designed with a clean separation of concerns, dividing logic into distinct layers:

    API Layer: Handles live HTTP requests for authentication and health monitoring.

    Service Layer: Encapsulates all interactions with external services (Microsoft Graph, AWS S3, PostgreSQL).

    Task Layer: Contains the core business logic for the asynchronous email processing workflow.

Core Components
Application & Configuration

    app/main.py (Web Server Entrypoint): Initializes the FastAPI web application, registers all API routers, and manages the lifecycle of shared resources like the HTTP client and database connection pool using the lifespan manager. This is the "front door" for all live HTTP requests.

    app/celery_app.py (Background Task Scheduler): Configures the Celery background processing system. It connects Celery to the Redis task queue and sets up the beat_schedule, which periodically triggers the main dispatcher task to kick off the email processing workflow.

    app/config.py (Centralized Settings): Loads and validates all environment variables from a .env file using Pydantic. It provides a single, type-safe source of truth for all application settings and secrets.

API Routers (The User-Facing Layer)

    app/api/v1/auth_router.py (Authentication Flow): Handles the one-time, user-interactive OAuth 2.0 consent process. It provides the /login endpoint to redirect users to Microsoft for authentication and the /callback endpoint to handle the response and securely store the user's refresh token.

    app/api/v1/email.py (Email Data API): Provides a secure /me/emails endpoint for fetching email data. It requires a valid JWT for authentication, validates the token to identify the user, and then calls the GraphClient to fetch emails for that specific user.

    app/api/v1/health.py (Health Monitoring): Defines the /healthcheck endpoint, which actively checks the status of critical dependencies like PostgreSQL and Redis. It returns a 200 OK if all services are healthy or a 503 Service Unavailable if a dependency is down, enabling automated monitoring.

Services (The Logic Layer)

    app/auth/graph_auth.py (Authentication Logic): Handles the low-level details of the OAuth 2.0 flow. The DelegatedGraphAuthenticator class contains the async methods to exchange authorization codes for tokens and to use refresh tokens to get new access tokens from Microsoft's identity platform, persisting the tokens in PostgreSQL.

    app/services/graph_client.py (Microsoft Graph Service): Provides a clean interface for interacting with the Microsoft Graph API. The GraphClient uses the DelegatedGraphAuthenticator to get a valid access token for a specific user before making the authenticated API call to fetch their emails.

    app/services/s3_client.py (S3 Storage Service): Handles all file uploads to Amazon S3. The S3Client uses the aioboto3 library to provide a simple, asynchronous upload_eml_file method, abstracting away the complexity of the AWS SDK.

    app/services/postgres_client.py (Database Service): Manages all interactions with the PostgreSQL database. The PostgresClient handles the database connection pool and provides generic methods like execute and fetch_all, as well as the specific helper functions needed by the authentication system to store and retrieve refresh tokens.

Data Models and Background Tasks

    app/models/email.py (Data Contract): Defines the structure and validation rules for email data using Pydantic models. It parses the raw JSON from the Graph API into clean, validated, and type-safe Python objects, ensuring data integrity.

    app/tasks/email_tasks.py (Core Business Logic): Defines the background jobs using a "fan-out" pattern:

        dispatch_email_processing: The main scheduled task. It queries the database for all authenticated users and dispatches a separate worker task for each one.

        process_single_mailbox: The worker task. It receives a user_id, uses the GraphClient to fetch and filter emails for that user, uploads the .eml files to S3, logs metadata to PostgreSQL, and updates the user's high-water mark in Redis.

Getting Started
Prerequisites

    Docker

    Docker Compose

1. Setup Environment Variables

Create a .env file in the project root by copying the .env.example template. Fill in the required values for your Microsoft App Registration, AWS, and PostgreSQL credentials.
2. Run the Application

Start the entire application stack (API, worker, beat, Redis, Postgres) using Docker Compose.

docker-compose up --build -d

The -d flag runs the services in the background.
3. Authenticate a User (One-Time Setup)

To allow the application to access an email account, you must complete the one-time OAuth 2.0 consent flow.

    In a web browser, navigate to: http://localhost:8000/api/v1/auth/login

    Sign in with the Microsoft account you wish to process emails for.

    Grant the requested permissions.

The application will then store the necessary refresh token, and the background task will begin processing emails for that user on its schedule.
4. Monitor the Services

You can view the logs for all running services with:

docker-compose logs -f

Running Tests

The project includes a comprehensive test suite.
Run All Tests

To run the complete suite (unit, integration, and E2E tests), use the test-runner service defined in docker-compose.yml.

docker-compose run --rm test-runner pytest

Run a Specific Test File

To run tests from a single file, specify the path:

docker-compose run --rm test-runner pytest tests/unit/services/test_s3_client.py

