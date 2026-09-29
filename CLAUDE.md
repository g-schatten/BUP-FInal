# Fuel Supply Intelligence & Resilience Platform

Stack: FastAPI (Python 3.12) backend + intelligence layer, React/Vite frontend, SQLite, Docker Compose, real simulator (`asifmahmoud414/bup-fuel-supply-simulator:1.0.0`) as a compose service on :8000.
Run: `docker compose up --build` (backend :8080, frontend :5173, simulator :8000/docs).
Layout: `backend/` (API, simulator client, intelligence), `frontend/` (operator dashboard), `problem/` (problem statement + simulator integration guide PDF), `tasks/` (plan.md, todo.md).

No tests unless asked. No new dependencies without asking first.
