# Elwin's Trial Project: Outlook Email Scanner + Forwarder

This project is a robust, production-ready application designed to read and filter emails from Microsoft Outlook accounts, process them based on specific criteria, and archive them as `.eml` files in an S3 bucket, along with a reference to the S3 in the metadata saved in postgres. It is built with a scalable, multi-user architecture using FastAPI for the API layer and Celery for background task processing.

Video demo link: https://drive.google.com/file/d/1MTiT8AQjYtRn__-WnzXF9pSh8hrT5fQp/view?usp=sharing

## Core Architecture

The application is designed with a clean separation of concerns, dividing logic into distinct layers:

-   **API Layer**: Handles live HTTP requests for authentication and health monitoring.
-   **Service Layer**: Encapsulates all interactions with external services (Microsoft Graph, AWS S3, PostgreSQL).
-   **Task Layer**: Contains the core business logic for the asynchronous email processing workflow.

### Core Components

-   **`app/main.py` (Web Server Entrypoint)**: Initializes the FastAPI web application, registers all API routers, and manages the lifecycle of shared resources like the HTTP client and database connection pool using the lifespan manager. This is the "front door" for all live HTTP requests.
-   **`app/celery_app.py` (Background Task Scheduler)**: Configures the Celery background processing system. It connects Celery to the Redis task queue and sets up the `beat_schedule`, which periodically triggers the main dispatcher task to kick off the email processing workflow.
-   **`app/config.py` (Centralized Settings)**: Loads and validates all environment variables from a `.env` file using Pydantic. It provides a single, type-safe source of truth for all application settings and secrets.
-   **`app/api/v1/auth_router.py` (Authentication Flow)**: Handles the one-time, user-interactive OAuth 2.0 consent process. It provides the `/login` endpoint to redirect users to Microsoft for authentication and the `/callback` endpoint to handle the response and securely store the user's refresh token.
-   **`app/services/graph_client.py` (Microsoft Graph Service)**: Provides a clean interface for interacting with the Microsoft Graph API. The `GraphClient` uses an authenticator to get a valid access token for a specific user before making the authenticated API call to fetch their emails.
-   **`app/services/s3_client.py` (S3 Storage Service)**: Handles all file uploads to Amazon S3. The `S3Client` uses the `aioboto3` library to provide a simple, asynchronous `upload_eml_file` method, abstracting away the complexity of the AWS SDK.
-   **`app/services/postgres_client.py` (Database Service)**: Manages all interactions with the PostgreSQL database. The `PostgresClient` handles the database connection pool and provides generic methods like `execute` and `fetch_one`, as well as the specific helper functions needed to store and retrieve refresh tokens.
-   **`app/tasks/email_tasks.py` (Core Business Logic)**: Defines the background jobs using a "fan-out" pattern:
    -   `dispatch_email_processing`: The main scheduled task. It queries the database for all authenticated users and dispatches a separate worker task for each one.
    -   `process_single_mailbox`: The worker task. It receives a `user_id`, fetches and filters emails for that user, uploads the `.eml` files to S3, logs metadata to PostgreSQL, and updates a high-water mark in Redis.

### Design Choices
- **Persistent Authentication**: OAuth2 refresh tokens are stored in the database, allowing the application to maintain long-term access without requiring repeated user logins.
- **Concurrent Processing**: Background jobs are designed with a "fan-out" pattern, allowing multiple emails from different users to be processed in parallel for high throughput.
- **Idempotent Processing**: Redis is used as a cache to store the timestamp of the last processed email, preventing the system from fetching and processing the same emails multiple times.
- **Periodic Scheduling**: A Celery Beat task runs on a configurable schedule (e.g., every 15 minutes) to automatically trigger the email processing workflow.

## Getting Started (Local Development)

This setup runs all services locally using Docker containers, including a mock S3 service (`moto`) for safe testing.

### Prerequisites
- Docker
- Docker Compose

### 1. Setup Environment File

Create a `.env` file in the project root. For local development, you should define the following to use the local mock S3 service and the Dockerized Postgres database:

```
S3_ENDPOINT_URL=http://localhost:5002
DATABASE_URL=postgresql://emailreader:password@postgres:5432/emailreader_db
```

### 2. Run the Development Stack

This command builds the images and starts all services, including local Postgres, Redis, and Moto containers.

```bash
docker-compose up --build -d
```
The `-d` flag runs the services in the background.

### 3. Authenticate a User (One-Time Setup)

To allow the application to access an email account, you must complete the one-time OAuth 2.0 consent flow.

1.  In a web browser, navigate to: `http://localhost:8000/api/v1/auth/login`
2.  Sign in with the Microsoft account you wish to process emails for.
3.  Grant the requested permissions.

The application will store the necessary refresh token, and the background task will begin processing emails for that user.

## Running in Production

This setup is designed to connect the application containers to live, cloud-hosted services like AWS RDS and S3.

### 1. Setup Production Environment File

Create a `.env.production` file in the project root. This file should contain all the necessary secrets and configuration for your live environment.

-   **`DATABASE_URL`**: Must point to your production database (e.g., AWS RDS).
-   **`AWS_...`**: Must contain your production AWS credentials.
-   **Important**: Make sure this file does **not** contain an `S3_ENDPOINT_URL` variable, so the application connects to the real S3 service.

### 2. Run the Production Stack

This command uses an override file (`docker-compose.prod.yml`) to re-wire the containers to use the `.env.production` file and remove dependencies on local Postgres and Moto services.

```bash
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

### 3. Monitor the Services

You can view the logs for all running services. To watch the email processing worker specifically:

```bash
docker-compose -f docker-compose.yml -f docker-compose.prod.yml logs -f worker
```

## Testing

The project includes a comprehensive test suite using `pytest`. Tests are run inside the dedicated `test-runner` container, which has all necessary dev dependencies.

### Run All Tests

This command runs the complete suite (unit, integration, and E2E tests). It uses the standard `docker-compose.yml` which wires it to local mock services.

```bash
docker-compose run --rm test-runner pytest
```

### Run a Specific Test File

To run tests from a single file, specify the path:

```bash
docker-compose run --rm test-runner pytest tests/unit/services/test_s3_client.py
```

### Run Integration Tests Against Live Services

To run a test against your live AWS S3 bucket or RDS instance (use with caution), you can use the production compose file. This will use the credentials in `.env.production`.

```bash
docker-compose -f docker-compose.yml -f docker-compose.prod.yml run --rm test-runner pytest tests/integration/test_s3_upload.py
```

### Notes
- right now upon every new build, the session authentication token is wiped.
- upon every new build, all emails will be processed again

