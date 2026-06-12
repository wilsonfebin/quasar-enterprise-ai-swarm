# Quasar Enterprise AI Delivery Swarm

Band-powered multi-agent platform for regulated financial AI workflows.

## Current Status

Phase 1 Complete

### Features

- FastAPI backend
- Streamlit dashboard
- TimescaleDB
- Docker Compose
- Mock MCX Intelligence
- Mock Forex Intelligence
- Agent Swarm Monitor
- Log Viewer
- DB-backed candle and SMC label APIs

## Run

docker compose up --build -d

UI:
http://localhost:8601

Backend:
http://localhost:8001/docs

## Environment Variables

Copy `.env.example` to `.env` and populate credentials.

```bash
docker compose up --build -d
```
