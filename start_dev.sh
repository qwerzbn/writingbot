#!/bin/bash

# Function to kill child processes on exit
cleanup() {
    echo "Stopping servers..."
    kill $(jobs -p) 2>/dev/null
    exit
}

trap cleanup SIGINT SIGTERM

echo "Starting WritingBot..."

# Kill any existing processes on ports 5000 and 3000
echo "Checking for existing processes..."
lsof -ti:5000 | xargs kill -9 2>/dev/null
lsof -ti:3000 | xargs kill -9 2>/dev/null
sleep 1

# Check if conda environment is active or available
if [[ "$CONDA_DEFAULT_ENV" != "writingbot" ]]; then
    echo "Activating conda environment 'writingbot'..."
    # Try to source conda profile if available
    source $(conda info --base)/etc/profile.d/conda.sh 2>/dev/null
    conda activate writingbot
fi

# Start Backend
echo "Starting Flask Backend (Port 5000)..."
python server.py &
BACKEND_PID=$!

# Wait for backend to be ready
sleep 3

# Start Frontend
echo "Starting Next.js Frontend (Port 3000)..."
cd web
npm run dev &
FRONTEND_PID=$!

echo ""
echo "WritingBot is running!"
echo "Backend: http://localhost:5000"
echo "Frontend: http://localhost:3000"
echo "Press Ctrl+C to stop both servers."

wait
