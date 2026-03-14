#!/bin/bash

# Function to kill child processes on exit
cleanup() {
    echo "Stopping all servers..."
    kill $(jobs -p) 2>/dev/null
    exit
}

trap cleanup SIGINT SIGTERM


echo "Starting WritingBot + FastWrite..."

# Kill any existing processes on all used ports
echo "Checking for existing processes..."
lsof -ti:5001 | xargs kill -9 2>/dev/null
lsof -ti:3000 | xargs kill -9 2>/dev/null
lsof -ti:3002 | xargs kill -9 2>/dev/null
lsof -ti:3003 | xargs kill -9 2>/dev/null
sleep 1

# Check if conda environment is active or available
if [[ "$CONDA_DEFAULT_ENV" != "writingbot" ]]; then
    echo "Activating conda environment 'writingbot'..."
    # Try to source conda profile if available
    source $(conda info --base)/etc/profile.d/conda.sh 2>/dev/null
    conda activate writingbot
fi

# Start WritingBot Backend (FastAPI)
echo "Starting FastAPI Backend (Port 5001)..."
python -m uvicorn src.api.main:app \
    --host 0.0.0.0 --port 5001 --reload \
    --reload-exclude "data/*" --reload-exclude "web/*" --reload-exclude ".git/*" --reload-exclude "FastWrite/*" --reload-exclude ".env" &
BACKEND_PID=$!

# Wait for backend to be ready
sleep 3

# Start WritingBot Frontend
echo "Starting Next.js Frontend (Port 3000)..."
cd web
npm run dev &
FRONTEND_PID=$!
cd ..

# Start FastWrite Backend
echo "Starting FastWrite API Server (Port 3003)..."
cd FastWrite
PORT=3003 bun run --watch src/server.ts &
FASTWRITE_BACKEND_PID=$!

# Start FastWrite Frontend
echo "Starting FastWrite Web UI (Port 3002)..."
cd web
bun run dev --no-open &
FASTWRITE_FRONTEND_PID=$!
cd ../..

echo ""
echo "=========================================="
echo "  All services are running!"
echo "=========================================="
echo "  WritingBot Backend:  http://localhost:5001"
echo "  WritingBot Frontend: http://localhost:3000"
echo "  API Docs:            http://localhost:5001/docs"
echo "  FastWrite API:       http://localhost:3003"
echo "  FastWrite UI:        http://localhost:3002"
echo "=========================================="
echo "  Press Ctrl+C to stop all servers."
echo ""

# Auto-open WritingBot frontend
open http://localhost:3000

wait
