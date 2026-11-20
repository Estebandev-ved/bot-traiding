-- TimescaleDB: precios, libro de órdenes, funding y open interest
CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE TABLE IF NOT EXISTS candles (ts timestamptz NOT NULL, exchange text, symbol text, tf text,
  open double precision, high double precision, low double precision, close double precision, volume double precision,
  PRIMARY KEY (exchange, symbol, tf, ts));
CREATE TABLE IF NOT EXISTS funding (ts timestamptz NOT NULL, exchange text, symbol text, rate double precision,
  PRIMARY KEY (exchange, symbol, ts));
CREATE TABLE IF NOT EXISTS open_interest (ts timestamptz NOT NULL, exchange text, symbol text, contracts double precision,
  PRIMARY KEY (exchange, symbol, ts));
CREATE TABLE IF NOT EXISTS book_top (ts timestamptz NOT NULL, exchange text, symbol text,
  bid double precision, bid_size double precision, ask double precision, ask_size double precision);
SELECT create_hypertable('candles','ts',if_not_exists=>true);
SELECT create_hypertable('funding','ts',if_not_exists=>true);
SELECT create_hypertable('open_interest','ts',if_not_exists=>true);
SELECT create_hypertable('book_top','ts',if_not_exists=>true);
