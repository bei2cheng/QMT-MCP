# MCP Auto Trade Implementation Plan

> **For agentic workers:** Implement task-by-task. Steps use checkbox syntax.

**Goal:** Add MCP-side scan + MA signal + optional auto order + scheduler.

**Architecture:** ScannerTool + AutoTradeEngine orchestrate TradingTool/MAStrategy; main.py registers tools.

**Tech Stack:** Python, FastMCP, XTQuant, pandas, threading

## Global Constraints

- Default `dry_run=True` for any path that can place orders
- Watchlist preferred; market scan via sector API with limit
- Windows + QMT for live trading; offline scan may fail without XTQuant data

---

### Task 1: Config + env

- Modify: `src/config.py`, `.env.example`, `config.json`
- Add `AutoTradeConfig`, `WATCHLIST` parsing, optional `.env` load

### Task 2: ScannerTool

- Create: `src/tools/scanner_tool.py`
- Scan symbols → MA signals → list of dicts

### Task 3: AutoTradeEngine

- Create: `src/tools/auto_trade_engine.py`
- `run_cycle`, scheduler start/stop/status, daily order limit

### Task 4: TradingTool risk + wire main

- Modify: `trading_tool.py` (max order value), `__init__.py`, `main.py`, `README.md`
