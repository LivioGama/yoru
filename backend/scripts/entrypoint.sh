#!/bin/sh
# Auto-fix permissions for Docker volumes
# This ensures the non-root appuser can write to mounted volumes
if [ -d /app/data ]; then
    chown -R appuser:appuser /app/data 2>/dev/null || true
fi

# Run the main application
exec uvicorn apps.api.main:app --host 0.0.0.0 --port 8002
