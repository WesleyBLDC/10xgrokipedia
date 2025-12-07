#!/bin/bash

# 10xGrokipedia Setup Script
# Run this after cloning or pulling/rebasing

set -e

echo "=== 10xGrokipedia Setup ==="
echo ""

# Backend setup
echo "Installing backend dependencies..."
cd backend
pip install -r requirements.txt
cd ..
echo "Backend dependencies installed."
echo ""

# Frontend setup
echo "Installing frontend dependencies..."
cd frontend
rm -rf node_modules 2>/dev/null || true
npm install
cd ..
echo "Frontend dependencies installed."
echo ""

echo "=== Setup Complete ==="
echo ""
echo "To start the servers, run in separate terminals:"
echo "  Terminal 1: cd backend && uvicorn main:app --reload"
echo "  Terminal 2: cd frontend && npm run dev"
echo ""
echo "Backend: http://localhost:8000"
echo "Frontend: http://localhost:5173"
