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

## Specialist Persistence Verification

After Band credentials are configured and specialist agents are present in the
Band chat, send a mentioned workflow request in Band:

```text
@quasar-remote-agent Run Quasar enterprise specialist review
```

Then trigger the workflow from the backend:

```bash
curl -X POST "http://127.0.0.1:8001/agents/band/run-quasar-workflow?analysis_scope=MCX"
```

Inspect persisted specialist responses:

```bash
curl "http://127.0.0.1:8001/agents/specialists/latest?market=MCX&instrument=NATURALGAS"
curl "http://127.0.0.1:8001/agents/specialists/history?market=MCX&instrument=NATURALGAS"
```

Reset runtime state or restart the backend, then verify governance and audit
fallback:

```bash
curl -X POST http://127.0.0.1:8001/agents/workflow/reset
curl http://127.0.0.1:8001/agents/governance/evidence
curl "http://127.0.0.1:8001/agents/audit/decision-trace/latest?market=MCX&instrument=NATURALGAS"
```

Before one completed Band specialist workflow exists, missing-response warnings
are expected. After completion, persisted responses should remove false
missing-response warnings and show `response_source: persisted` after runtime
state is cleared.

Automated local verification:

```bash
python backend/scripts/verify_specialist_persistence.py --market MCX --instrument NATURALGAS --reset-runtime
```

To trigger the workflow as part of verification, use:

```bash
python backend/scripts/verify_specialist_persistence.py --market MCX --instrument NATURALGAS --run-workflow --reset-runtime
```
