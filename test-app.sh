#!/bin/bash

echo "🚀 Testing EmailReader Application"
echo ""

# Check backend API
echo "1. Checking Backend API..."
if curl -s http://localhost:8000/healthcheck | grep -q "ok"; then
    echo "✅ Backend API is running"
else
    echo "❌ Backend API is not responding"
    echo "   Run: docker compose up api"
    exit 1
fi

# Check frontend
echo ""
echo "2. Checking Frontend..."
if ! curl -s -o /dev/null -w "%{http_code}" http://localhost:5173 | grep -q "200"; then
    echo "⚠️  Frontend not running, starting it now..."
    cd frontend && npm run dev &
    echo "   Waiting for frontend to start..."
    sleep 5
fi

# Open in browser
echo ""
echo "3. Opening applications in browser..."
echo ""

# Open API documentation
echo "📚 API Documentation: http://localhost:8000/docs"
open http://localhost:8000/docs 2>/dev/null || xdg-open http://localhost:8000/docs 2>/dev/null

# Open frontend
echo "🎨 Frontend Application: http://localhost:5173"
open http://localhost:5173 2>/dev/null || xdg-open http://localhost:5173 2>/dev/null

echo ""
echo "✅ Applications opened in your browser!"
echo ""
echo "📋 Quick Test Guide:"
echo "1. In the frontend, try to connect Outlook (requires Microsoft account)"
echo "2. Check the API docs to test endpoints directly"
echo "3. Monitor logs with: docker compose logs -f"
echo ""
echo "🛑 To stop services: docker compose down"
