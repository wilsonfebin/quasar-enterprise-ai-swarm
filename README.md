# Quasar Enterprise AI Delivery Swarm

Quasar is an advisory-only enterprise market intelligence and governance system. It does not place trades, does not generate execution instructions, and does not produce buy/sell signals.

## Hackathon Track

Band of Agents Hackathon: Regulated and High-Stakes Systems

## Live Demo

Production deployment:

https://quasar.quasarlabs.in

Current verified state:

- AWS deployed
- HTTPS enabled with custom domain
- Streamlit UI live
- FastAPI backend live
- TimescaleDB running
- Readiness score: 100
- Readiness state: READY
- Safety status: ADVISORY_ONLY
- Band specialist workflow persists responses
- Governance evidence and decision audit trail available

## Problem Statement

Financial market tools often expose raw indicators, candle values, or structure labels without explaining whether the evidence is fresh, aligned, persistent, auditable, or suitable for high-stakes review. This creates a gap between market data and enterprise-grade decision governance.

Quasar addresses that gap by turning live market structure into reviewed, advisory-only intelligence with specialist reasoning, evidence tracking, audit stages, and deployment readiness visibility.

## Solution Overview

Quasar combines live MCX and Forex market data, TimescaleDB storage, market-structure intelligence, multi-timeframe analysis, scenario reasoning, hierarchy evaluation, market memory, and Band specialist review.

The result is a reviewed advisory briefing rather than a raw technical-label dashboard. The system explains the current decision state, confidence attribution, dominant and alternative hypotheses, validation conditions, and governance evidence without producing execution instructions.

## Why Band Agents

Band agents are used as specialist reviewers rather than generic chat responders. Each specialist contributes a distinct review layer:

- Requirement Specialist: defines the market question being evaluated.
- Market Intelligence Specialist: compares dominant and alternative market theses.
- System Readiness Specialist: reviews freshness, session state, and evidence quality.
- Risk Governance Specialist: reviews confidence, conflict, and validation risk.
- Delivery Planning Specialist: identifies the validation focus required next.
- Final Review Specialist: produces the executive advisory assessment.

This workflow demonstrates how specialized agents can transform raw intelligence artifacts into an auditable high-stakes review process.

## Architecture Overview

Quasar uses live ingestion workers, TimescaleDB, FastAPI, Streamlit, and Band specialist orchestration.

Core intelligence flow:

Market Data Providers -> Ingestion Workers -> TimescaleDB -> SMC Engine -> Multi-Timeframe Intelligence -> Scenario Engine -> Hierarchy Engine -> Market Memory -> Governance Evidence -> Band Specialist Review -> Decision Audit Trail -> Streamlit UI

See [docs/architecture.md](docs/architecture.md) for Mermaid diagrams.

## Core Features

- Live MCX NATURALGAS and Forex XAUUSD intelligence panels.
- Plotly candlestick charts with compact OHLC summaries.
- Timeframe controls for visual chart context.
- Multi-timeframe market intelligence snapshot.
- Scenario engine and hierarchy engine outputs.
- Market memory and structure evolution tracking.
- Agent Swarm Review powered by Band specialists.
- Final Advisory Assessment with confidence attribution.
- Validation conditions and structure evolution audit sections.
- System Audit, Governance Console and audit proof.
- Persistent specialist responses after workflow completion.
- Advisory-only safety posture throughout the UI and API output.

## Safety Constraints

Quasar is intentionally advisory-only.

- No order placement.
- No broker execution.
- No buy/sell signals.
- No entry, exit, target, or stop-loss instructions.
- No automated trading recommendations.
- Market intelligence is presented as governance-reviewed advisory context only.

## Demo Endpoints

Production UI:

```text
https://quasar.quasarlabs.in
```

Local UI:

```text
http://localhost:8601
```

Local FastAPI docs:

```text
http://localhost:8001/docs
```

Readiness snapshot:

```bash
curl "http://localhost:8001/submission/readiness?market=MCX&instrument=NATURALGAS"
```

Latest specialist responses:

```bash
curl "http://localhost:8001/agents/specialists/latest?market=MCX&instrument=NATURALGAS"
```

Governance evidence:

```bash
curl "http://localhost:8001/agents/governance/evidence"
```

Latest decision audit trail:

```bash
curl "http://localhost:8001/agents/audit/decision-trace/latest?market=MCX&instrument=NATURALGAS"
```

## Deployment Instructions

Local development:

```bash
docker compose up --build -d
```

Then open:

```text
http://localhost:8601
```

Environment configuration:

1. Copy `.env.example` to `.env` if available in the deployment environment.
2. Populate provider credentials and deployment settings outside source control.
3. Start the Docker Compose stack.
4. Verify backend, Streamlit, and TimescaleDB health.
5. Confirm readiness with the submission readiness endpoint.

Production deployment currently runs on AWS behind HTTPS and the custom domain:

```text
https://quasar.quasarlabs.in
```

## Screenshots

Screenshot references are listed in [docs/screenshots.md](docs/screenshots.md).

Expected assets:

- `docs/assets/live-intelligence.png`
- `docs/assets/agent-swarm-review.png`
- `docs/assets/final-advisory-assessment.png`
- `docs/assets/audit-console.png`

## Known Limitations

- The system is advisory-only and does not perform execution.
- Live feed freshness depends on upstream market data provider availability and rate limits.
- MCX and Forex market sessions differ, so candle availability can vary by instrument and time.
- Specialist review is intentionally user-triggered to avoid presenting intermediate analysis as final review.
- The current package documents the production deployment state but does not expose secrets, credentials, or raw provider payloads.

## Future Roadmap

1. Real-Time Streaming Intelligence

- Replace polling-based refresh with WebSocket/SSE streaming.
- Live candle updates directly from market feeds into charts.
- Real-time agent review triggers on significant market structure changes.
- Continuous governance monitoring and alerting.

2. Enterprise Multi-Agent Orchestration

- Expand from 6 specialists to domain-specific specialist swarms.
- Portfolio Risk Agent, Compliance Agent, Scenario Stress Testing Agent, Market Regime Agent.
- Cross-agent memory and long-term intelligence persistence.

3. Institutional Governance & Explainability

- Full audit replay capability for every decision.
- Regulatory reporting and compliance packs.
- Explainable confidence attribution with visual decision trees.

4. Multi-Asset & Multi-Market Intelligence

- Expand beyond XAUUSD and MCX NATURALGAS.
- Equities, Commodities, Forex, Crypto, Fixed Income.
- Cross-market correlation intelligence.
- Global macro-event impact analysis across asset classes.