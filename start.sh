#!/bin/bash
set -e

echo "=== Submission & Approval Workflow API ==="

# Run seed script first (idempotent — skips existing users)
echo "Seeding demo users..."
python seed.py

echo "Starting FastAPI server..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
