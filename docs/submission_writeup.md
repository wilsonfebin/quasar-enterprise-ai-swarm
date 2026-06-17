# Submission Write-up

## Project Summary

Quasar Enterprise AI Delivery Swarm is an advisory-only market intelligence and governance system for regulated, high-stakes review workflows. It combines live MCX and Forex market data, multi-timeframe intelligence, governance evidence, Band specialist review, and a decision audit trail.

Live demo:

```text
https://quasar.quasarlabs.in
```

## Problem

Market intelligence systems often stop at raw labels, candle values, or isolated confidence scores. In high-stakes environments, that is not enough. Reviewers need to understand:

- What question is being evaluated.
- Which evidence supports or contradicts the current thesis.
- Whether data is fresh and suitable for review.
- What risks prevent confirmation.
- Why the final advisory state exists.
- How the decision can be audited later.

## Solution

Quasar turns live market data into an advisory intelligence briefing. It uses deterministic intelligence engines and Band specialist review to produce an executive assessment with confidence attribution, validation conditions, governance evidence, and audit stages.

The system does not place trades, does not generate execution instructions, and does not produce buy/sell signals.

## Band Agent Workflow

Band specialists act as role-based reviewers:

| Specialist | Responsibility |
| --- | --- |
| Requirement | Defines the market question being evaluated. |
| Market Intelligence | Produces dominant and alternative advisory theses. |
| System Readiness | Reviews freshness, session state, and evidence quality. |
| Risk Governance | Reviews confidence, conflict, and validation risk. |
| Delivery Planning | Identifies the validation focus required next. |
| Final Review | Produces the executive advisory assessment. |

The workflow demonstrates how specialist agents can transform Quasar intelligence artifacts into a reviewed, evidence-linked advisory conclusion.

## Regulated/High-Stakes Fit

Quasar is built for reviewability rather than automation. It preserves a clear safety boundary and presents market intelligence as advisory context only. The system emphasizes:

- Auditability.
- Evidence traceability.
- Specialist review.
- Explicit safety status.
- Runtime and persistence verification.
- No execution language.

## Architecture

The core pipeline is:

```text
Market Data Providers -> Ingestion Workers -> TimescaleDB -> SMC Engine -> Multi-Timeframe Intelligence -> Scenario Engine -> Hierarchy Engine -> Market Memory -> Governance Evidence -> Band Specialist Review -> Decision Audit Trail -> Streamlit UI
```

Deployment path:

```text
User -> HTTPS -> Nginx -> Streamlit -> FastAPI -> TimescaleDB
```

See [architecture.md](architecture.md) for diagrams.

## Safety and Governance

Quasar is advisory-only:

- No order placement.
- No broker execution.
- No buy/sell signals.
- No entry, exit, target, or stop-loss instructions.
- No automated trading recommendations.

Safety status is surfaced in the UI and readiness endpoint as:

```text
ADVISORY_ONLY
```

## Auditability

The System Audit and Governance Console provides:

- Deployment readiness score and state.
- Readiness verification breakdown.
- Agent workflow timeline.
- Governance evidence summary.
- Decision audit trail.
- Raw logs as secondary supporting material.
- Enterprise review notes.

The current verified deployment reports:

- Readiness score: 100
- Readiness state: READY
- Governance evidence available
- Decision audit trail available
- Specialist responses persisted

## Live Demo

Production URL:

```text
https://quasar.quasarlabs.in
```

Demo flow:

1. Show live MCX and Forex intelligence charts.
2. Explain chart timeframe as visual context only.
3. Run Agent Swarm Review.
4. Review specialist cards.
5. Review Final Advisory Assessment.
6. Open Confidence Attribution.
7. Navigate to System Audit and Governance Console.
8. Show readiness score, governance evidence, and decision audit trail.
9. Reinforce advisory-only safety mode.

## Future Roadmap

- Add final production screenshots to the documentation package.
- Expand readiness proof across multiple instruments.
- Add richer historical workflow comparison.
- Add exportable audit packets for compliance review.
- Improve governance evidence filtering and search.
- Continue strengthening UI language sanitization for judge-facing demos.
