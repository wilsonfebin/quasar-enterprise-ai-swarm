import threading

import requests

from config import BACKEND_URL


def get_json(path: str):
    try:
        response = requests.get(f"{BACKEND_URL}{path}", timeout=5)
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        return {"error": str(exc)}


def post_json(path: str, timeout: int = 10, payload: dict | None = None):
    try:
        response = requests.post(f"{BACKEND_URL}{path}", json=payload, timeout=timeout)
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        return {"error": str(exc)}


def health():
    return get_json("/health")


def latest_market():
    return get_json("/market/latest")


def market_candles(market_type: str, instrument: str, timeframe: str, limit: int = 20):
    return get_json(
        f"/market/candles?market_type={market_type}&instrument={instrument}&timeframe={timeframe}&limit={limit}"
    )


def smc_labels(market_type: str, instrument: str, timeframe: str, limit: int = 20):
    return get_json(
        f"/smc/labels?market_type={market_type}&instrument={instrument}&timeframe={timeframe}&limit={limit}"
    )


def multi_timeframe_intelligence(
    market_type: str,
    instrument: str,
    selected_timeframe: str = "1m",
):
    return get_json(
        "/market/intelligence/multi-timeframe"
        f"?market_type={market_type}&instrument={instrument}"
        f"&selected_timeframe={selected_timeframe}"
    )


def feed_status():
    return get_json("/market/ingestion/status")


def candle_health(market_type: str, instrument: str):
    return get_json(
        f"/market/candle-health?market_type={market_type}&instrument={instrument}&timeframe=1m"
    )


def sanity_check(market_type: str, instrument: str, timeframe: str = "1m"):
    return post_json(
        "/market/sanity-check",
        payload={
            "market_type": market_type,
            "instrument": instrument,
            "timeframe": timeframe,
        },
    )


def start_forex_ingestion():
    return post_json("/market/ingestion/start")


def pause_forex_ingestion():
    return post_json("/market/ingestion/stop")


def backfill_forex():
    return post_json(
        "/market/ingest/twelvedata/backfill?days=30&chunk_days=3&dry_run=false",
        timeout=300,
    )


def start_mcx_ingestion():
    return post_json("/market/mcx-ingestion/start")


def pause_mcx_ingestion():
    return post_json("/market/mcx-ingestion/stop")


def backfill_mcx():
    return post_json(
        "/market/ingest/zerodha/backfill?days=60&chunk_days=5&dry_run=false",
        timeout=600,
    )


def workflow_status():
    return get_json("/agents/workflow-status")


def workflow_details():
    return get_json("/agents/workflow/details")


def reset_workflow():
    return post_json("/agents/workflow/reset")


def band_status():
    return get_json("/agents/band/status")


def band_participants():
    return get_json("/agents/band/participants")


def log_lines(log_name: str):
    return get_json(f"/logs/{log_name}")


def start_workflow_thread(analysis_scope: str = "MCX"):
    def run_workflow():
        try:
            requests.post(
                f"{BACKEND_URL}/agents/band/run-quasar-workflow",
                params={"analysis_scope": analysis_scope},
                timeout=120,
            )
        except Exception:
            pass

    thread = threading.Thread(target=run_workflow, daemon=True)
    thread.start()
    return thread
