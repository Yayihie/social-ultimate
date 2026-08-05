#!/bin/bash
# Quickstart for Social Ultimate.
# Usage: ./run.sh [local|docker|test|stop]

set -e
cd "$(dirname "$0")"

CMD="${1:-local}"

# Pick Python 3.12+
for py in python3.12 python3.11 python3; do
  if command -v "$py" >/dev/null 2>&1; then
    PY="$py"
    break
  fi
done

case "$CMD" in
  local)
    echo "==> Setting up local Python environment..."
    if [ ! -d ".venv" ]; then
      "$PY" -m venv .venv
    fi
    source .venv/bin/activate
    pip install --quiet --upgrade pip
    pip install --quiet -r requirements.txt
    if [ ! -f ".env" ]; then
      cp .env.example .env
      echo "==> Created .env from template (edit it to add Instagram creds)"
    fi
    export DATABASE_URL="sqlite:///./social_ultimate.db"
    export SECRET_KEY="${SECRET_KEY:-dev-secret-change-me}"
    export EXPERIMENTAL_ENABLED=false
    echo "==> Starting server at http://localhost:8000"
    echo "    Press Ctrl+C to stop"
    exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
    ;;

  docker)
    echo "==> Starting Docker stack..."
    cd docker && docker compose up --build
    ;;

  test)
    echo "==> Running tests..."
    source .venv/bin/activate 2>/dev/null || "$PY" -m venv .venv && source .venv/bin/activate && pip install --quiet -r requirements.txt
    rm -f _test.db
    DATABASE_URL='sqlite:///./_test.db' EXPERIMENTAL_ENABLED=false SECRET_KEY=test python -m pytest tests/
    ;;

  stop)
    echo "==> Killing any uvicorn on port 8000..."
    lsof -ti:8000 | xargs kill -9 2>/dev/null || true
    lsof -ti:8765 | xargs kill -9 2>/dev/null || true
    echo "Done."
    ;;

  *)
    echo "Usage: $0 [local|docker|test|stop]"
    exit 1
    ;;
esac