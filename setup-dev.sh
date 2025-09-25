#!/bin/bash

# Development Setup Script for EmailReader + Frontend
echo "🚀 Setting up EmailReader development environment..."

# Check if frontend directory exists
if [ ! -d "frontend" ]; then
    echo "❌ Frontend directory not found. Please clone the frontend repo first:"
    echo "git clone https://github.com/elwinhe/career-pilot-dash.git frontend"
    exit 1
fi

# Create frontend environment file
echo "📝 Creating frontend environment configuration..."
cat > frontend/.env.local << EOF
# Local development environment variables
VITE_API_BASE_URL=http://localhost:8000
VITE_USE_MOCKS=false
EOF

# Install frontend dependencies
echo "📦 Installing frontend dependencies..."
cd frontend
npm install
cd ..

# Run database migration
echo "🗄️ Setting up database..."
docker compose up -d postgres redis
sleep 10
docker compose exec postgres psql -U emailreader -d emailreader_db -f /docker-entrypoint-initdb.d/002_add_jobs_and_activity_tables.sql 2>/dev/null || echo "Migration may already exist"

echo "✅ Development environment setup complete!"
echo ""
echo "To start the full stack:"
echo "  docker compose up"
echo ""
echo "To start only backend services:"
echo "  docker compose up postgres redis api worker beat"
echo ""
echo "To start frontend separately (for development):"
echo "  cd frontend && npm run dev"
echo ""
echo "Frontend will be available at: http://localhost:5173"
echo "Backend API will be available at: http://localhost:8000"
echo "API Documentation at: http://localhost:8000/docs"
