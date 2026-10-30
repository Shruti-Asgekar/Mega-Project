#!/usr/bin/env bash
# Local Development Startup Script for Linux/macOS
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
ROOT_DIR="$(dirname "$DIR")"

mkdir -p "$ROOT_DIR/uploads"

echo "Starting ML-Service on port 8001..."
(cd "$ROOT_DIR/ml-service" && python -m uvicorn main:app --host 0.0.0.0 --port 8001) &
ML_PID=$!

echo "Starting Backend on port 8000..."
(cd "$ROOT_DIR/backend" && python -m uvicorn main:app --host 0.0.0.0 --port 8000) &
BACKEND_PID=$!

trap "kill $ML_PID $BACKEND_PID 2>/dev/null; exit" SIGINT SIGTERM EXIT

echo "Services started:"
echo "Backend:    http://localhost:8000/api"
echo "Backend UI: http://localhost:8000/ui"
echo "ML-Service: http://localhost:8001/api/health"

wait
