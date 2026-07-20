"""
MCP 侧自动交易引擎
扫描 → 信号 → 风控 →（可选）下单；支持后台定时调度
"""

from __future__ import annotations

import logging
import threading
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from ..config import config
from .scanner_tool import ScannerTool
from .trading_tool import TradingTool

logger = logging.getLogger(__name__)


class AutoTradeEngine:
    """自动交易编排与调度"""

    def __init__(
        self,
        scanner: Optional[ScannerTool] = None,
        trading: Optional[TradingTool] = None,
    ):
        self.scanner = scanner or ScannerTool()
        self.trading = trading or TradingTool()

        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        self._running = False
        self._dry_run = True
        self._source = "watchlist"
        self._interval_sec = config.auto_trade.scheduler_interval_sec
        self._short_period = config.strategy.default_short_period
        self._long_period = config.strategy.default_long_period
        self._market_limit = config.screening.default_scan_limit
        self._sector = config.auto_trade.default_sector
        self._quantity = config.auto_trade.default_quantity

        self._orders_today = 0
        self._orders_day: Optional[date] = None
        self._last_result: Optional[str] = None
        self._last_run_at: Optional[str] = None
        self._cycle_count = 0

    # ------------------------------------------------------------------
    # 一轮执行
    # ------------------------------------------------------------------
    def run_cycle(
        self,
        dry_run: Optional[bool] = None,
        source: str = "watchlist",
        quantity: Optional[int] = None,
        short_period: Optional[int] = None,
        long_period: Optional[int] = None,
        sector: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> str:
        """执行一轮：扫描 → 过滤 → 可选下单。"""
        if dry_run is None:
            dry_run = config.auto_trade.default_dry_run
        quantity = quantity or config.auto_trade.default_quantity
        source = (source or "watchlist").lower().strip()

        if source not in ("watchlist", "market"):
            return "[ERROR] source 必须是 watchlist 或 market"

        with self._lock:
            if source == "watchlist":
                scan_fn = lambda: self.scanner.scan_watchlist(
                    short_period=short_period, long_period=long_period
                )
            else:
                scan_fn = lambda: self.scanner.scan_market(
                    sector=sector or self._sector,
                    limit=limit if limit is not None else self._market_limit,
                    short_period=short_period,
                    long_period=long_period,
                )

        # 扫描在锁外执行，避免阻塞 status / 调度启停
        scan = scan_fn()

        with self._lock:
            if not scan.get("success"):
                report = scan.get("report") or scan.get("error") or "扫描失败"
                self._last_result = report
                self._last_run_at = datetime.now().isoformat(timespec="seconds")
                return report

            actionable: List[Dict[str, Any]] = list(scan.get("actionable") or [])
            lines = [
                "[AUTO] 自动交易一轮",
                f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                f"来源: {source}  dry_run={dry_run}  quantity={quantity}",
                "",
                scan.get("report", ""),
                "",
            ]

            if not actionable:
                lines.append("[INFO] 本轮无可执行买卖信号，跳过下单")
                result = "\n".join(lines)
                self._last_result = result
                self._last_run_at = datetime.now().isoformat(timespec="seconds")
                self._cycle_count += 1
                return result

            lines.append("[EXEC]")
            for item in actionable:
                exec_line = self._execute_signal(item, dry_run=dry_run, quantity=quantity)
                lines.append(f"  {exec_line}")

            result = "\n".join(lines)
            self._last_result = result
            self._last_run_at = datetime.now().isoformat(timespec="seconds")
            self._cycle_count += 1
            return result

    def _execute_signal(self, item: Dict[str, Any], dry_run: bool, quantity: int) -> str:
        symbol = item["symbol"]
        action = item["action"]
        price = float(item.get("close") or 0)
        if price <= 0:
            return f"{symbol} {action}: 无效价格，跳过"

        # 持仓判断
        pos = self.trading.get_position_dict(symbol)
        pos_qty = int(pos["quantity"]) if pos else 0

        if action == "BUY" and pos_qty > 0:
            return f"{symbol} BUY: 已有持仓 {pos_qty}股，跳过"
        if action == "SELL" and pos_qty <= 0:
            return f"{symbol} SELL: 无持仓，跳过"

        sell_qty = pos_qty if action == "SELL" and pos_qty > 0 else quantity
        order_qty = sell_qty if action == "SELL" else quantity

        # 对齐最小手数
        min_q = config.trading.min_order_quantity
        if order_qty < min_q:
            return f"{symbol} {action}: 数量 {order_qty} < 最小 {min_q}，跳过"
        order_qty = (order_qty // min_q) * min_q

        order_value = price * order_qty
        if order_value > config.trading.max_order_value:
            return (
                f"{symbol} {action}: 金额 {order_value:.2f} 超过 "
                f"MAX_ORDER_VALUE={config.trading.max_order_value}，跳过"
            )

        if dry_run:
            return (
                f"[DRY_RUN] {action} {symbol} {order_qty}股 @{price:.2f} "
                f"(金额≈{order_value:.2f})"
            )

        if self.trading.trading_state != "NORMAL":
            return f"{symbol} {action}: 交易状态={self.trading.trading_state}，跳过"

        if not self._consume_daily_quota():
            return (
                f"{symbol} {action}: 已达单日最大下单次数 "
                f"{config.auto_trade.max_orders_per_day}，跳过"
            )

        try:
            msg = self.trading.place_order(
                symbol=symbol,
                quantity=order_qty,
                price=price,
                direction=action,
            )
            return f"{symbol} {action}: {msg}"
        except Exception as e:
            logger.error(f"自动下单失败 {symbol}: {e}")
            return f"{symbol} {action}: 异常 {e}"

    def _consume_daily_quota(self) -> bool:
        today = date.today()
        if self._orders_day != today:
            self._orders_day = today
            self._orders_today = 0
        if self._orders_today >= config.auto_trade.max_orders_per_day:
            return False
        self._orders_today += 1
        return True

    # ------------------------------------------------------------------
    # 调度器
    # ------------------------------------------------------------------
    def start_scheduler(
        self,
        interval_sec: Optional[int] = None,
        dry_run: Optional[bool] = None,
        source: str = "watchlist",
        quantity: Optional[int] = None,
        short_period: Optional[int] = None,
        long_period: Optional[int] = None,
        sector: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> str:
        if dry_run is None:
            dry_run = config.auto_trade.default_dry_run
        interval_sec = int(interval_sec or config.auto_trade.scheduler_interval_sec)
        if interval_sec < 30:
            return "[ERROR] interval_sec 不能小于 30 秒"

        source = (source or "watchlist").lower().strip()
        if source not in ("watchlist", "market"):
            return "[ERROR] source 必须是 watchlist 或 market"

        with self._lock:
            if self._running:
                return "[WARNING] 调度器已在运行，请先 stop_scheduler"

            self._dry_run = bool(dry_run)
            self._source = source
            self._interval_sec = interval_sec
            self._quantity = quantity or config.auto_trade.default_quantity
            self._short_period = short_period or config.strategy.default_short_period
            self._long_period = long_period or config.strategy.default_long_period
            self._sector = sector or config.auto_trade.default_sector
            self._market_limit = (
                limit if limit is not None else config.screening.default_scan_limit
            )

            self._stop_event.clear()
            self._running = True

        self._thread = threading.Thread(
            target=self._scheduler_loop,
            name="AutoTradeScheduler",
            daemon=True,
        )
        self._thread.start()

        warn = ""
        if not self._dry_run:
            warn = "\n[WARNING] dry_run=False，将真实提交委托！请确认模拟盘/风控。"

        logger.info(
            f"调度器启动: interval={interval_sec}s source={source} dry_run={self._dry_run}"
        )
        return (
            f"[OK] 调度器已启动\n"
            f"  interval_sec={interval_sec}\n"
            f"  source={source}\n"
            f"  dry_run={self._dry_run}\n"
            f"  quantity={self._quantity}"
            f"{warn}"
        )

    def stop_scheduler(self) -> str:
        with self._lock:
            if not self._running:
                return "[INFO] 调度器未在运行"
            self._stop_event.set()
            self._running = False
            thread = self._thread

        if thread and thread.is_alive():
            thread.join(timeout=5)

        logger.info("调度器已停止")
        return "[OK] 调度器已停止"

    def get_scheduler_status(self) -> str:
        with self._lock:
            lines = [
                "[SCHEDULER]",
                f"  running: {self._running}",
                f"  dry_run: {self._dry_run}",
                f"  source: {self._source}",
                f"  interval_sec: {self._interval_sec}",
                f"  quantity: {self._quantity}",
                f"  cycle_count: {self._cycle_count}",
                f"  orders_today: {self._orders_today}/{config.auto_trade.max_orders_per_day}",
                f"  last_run_at: {self._last_run_at or '-'}",
            ]
            if self._last_result:
                preview = self._last_result if len(self._last_result) <= 800 else (
                    self._last_result[:800] + "\n  ... (截断)"
                )
                lines.append("  last_result:")
                lines.append(preview)
            return "\n".join(lines)

    def _scheduler_loop(self) -> None:
        # 启动后先跑一轮，再按间隔等待
        while not self._stop_event.is_set():
            try:
                self.run_cycle(
                    dry_run=self._dry_run,
                    source=self._source,
                    quantity=self._quantity,
                    short_period=self._short_period,
                    long_period=self._long_period,
                    sector=self._sector,
                    limit=self._market_limit,
                )
            except Exception as e:
                logger.error(f"调度轮次异常: {e}")
                self._last_result = f"[ERROR] 调度轮次异常: {e}"
                self._last_run_at = datetime.now().isoformat(timespec="seconds")

            if self._stop_event.wait(self._interval_sec):
                break

        with self._lock:
            self._running = False
            self._thread = None
