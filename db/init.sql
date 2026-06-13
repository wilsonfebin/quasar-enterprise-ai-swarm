CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS market_candles (
    id SERIAL PRIMARY KEY,
    instrument TEXT NOT NULL,
    market_type TEXT NOT NULL,
    source TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    ts TIMESTAMPTZ NOT NULL,
    open DOUBLE PRECISION,
    high DOUBLE PRECISION,
    low DOUBLE PRECISION,
    close DOUBLE PRECISION,
    volume DOUBLE PRECISION,
    fetched_at TIMESTAMPTZ,
    inserted_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS smc_labels (
    id SERIAL PRIMARY KEY,
    instrument TEXT NOT NULL,
    market_type TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    ts TIMESTAMPTZ NOT NULL,
    label_type TEXT NOT NULL,
    direction TEXT,
    price_level DOUBLE PRECISION,
    confidence DOUBLE PRECISION,
    metadata JSONB
);
