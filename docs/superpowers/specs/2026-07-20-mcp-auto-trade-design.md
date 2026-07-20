# MCP 侧调度自动下单 — 设计规格

**日期:** 2026-07-20  
**状态:** 已确认

## 目标

在 MCP 进程内提供：自选/板块扫描 → 双均线信号 → 可选自动下单，以及可开关的后台定时调度。默认 `dry_run=True`。

## 架构

- `ScannerTool`：自选池与板块扫描，输出结构化信号
- `AutoTradeEngine`：一轮执行编排 + 线程调度
- `TradingTool`：真实下单/持仓；补齐单笔金额风控
- `main.py`：注册 MCP 工具

## MCP 工具

| 工具 | 说明 |
|------|------|
| `set_watchlist` / `get_watchlist` | 管理自选 |
| `scan_watchlist` | 扫自选（不下单） |
| `scan_market` | 扫板块（默认沪深A股，截断 limit） |
| `run_auto_trade_cycle` | 跑一轮；`source=watchlist\|market`，默认 dry_run |
| `start_scheduler` / `stop_scheduler` / `get_scheduler_status` | 定时调度 |
| `get_positions` | 持仓查询 |

## 规则

- 策略：双均线，最新 bar 金叉/死叉才触发
- 买入：无仓；卖出：有仓；数量默认 100；限价用最近收盘价
- 风控：`MAX_ORDER_VALUE`、交易状态、单日最大下单次数
- 自选优先；沪深扫描为独立接口

## 非目标（首版）

多策略组合、分钟级高频、AI 对话作为执行决策。
