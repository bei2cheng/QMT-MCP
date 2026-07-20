"""
股票扫描工具
支持自选列表与板块（如沪深A股）扫描，输出双均线信号
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from ..config import config
from ..strategies.ma_strategy import MAStrategy
from ..utils.data_handler import DataHandler
from ..utils.xtquant_client import xt_client

logger = logging.getLogger(__name__)


class ScannerTool:
    """股票池扫描：自选优先，亦可扫板块"""

    def __init__(self):
        self.data_handler = DataHandler()
        self._watchlist: List[str] = list(config.auto_trade.watchlist)

    # ------------------------------------------------------------------
    # 自选管理
    # ------------------------------------------------------------------
    def set_watchlist(self, symbols: str | List[str]) -> str:
        """设置自选池。symbols 可为逗号分隔字符串或列表。"""
        if isinstance(symbols, str):
            parsed = [s.strip().upper() for s in symbols.replace(";", ",").split(",") if s.strip()]
        else:
            parsed = [str(s).strip().upper() for s in symbols if str(s).strip()]

        invalid = [s for s in parsed if not self.data_handler.validate_symbol(s)]
        if invalid:
            return f"[ERROR] 股票代码格式无效: {', '.join(invalid)}"
        if not parsed:
            return "[ERROR] 自选列表不能为空"

        self._watchlist = parsed
        config.auto_trade.watchlist = list(parsed)
        return f"[OK] 自选已更新，共 {len(self._watchlist)} 只: {', '.join(self._watchlist)}"

    def get_watchlist(self) -> str:
        if not self._watchlist:
            return "[INFO] 自选列表为空，请先调用 set_watchlist"
        return f"[WATCHLIST] 共 {len(self._watchlist)} 只\n" + "\n".join(
            f"  - {s}" for s in self._watchlist
        )

    def get_watchlist_symbols(self) -> List[str]:
        return list(self._watchlist)

    # ------------------------------------------------------------------
    # 扫描
    # ------------------------------------------------------------------
    def scan_watchlist(
        self,
        short_period: Optional[int] = None,
        long_period: Optional[int] = None,
    ) -> Dict[str, Any]:
        """扫描自选列表，返回结构化结果。"""
        symbols = self.get_watchlist_symbols()
        if not symbols:
            return {
                "success": False,
                "error": "自选列表为空",
                "signals": [],
                "report": "[ERROR] 自选列表为空，请先 set_watchlist",
            }
        return self.scan_symbols(symbols, short_period=short_period, long_period=long_period)

    def scan_market(
        self,
        sector: Optional[str] = None,
        limit: Optional[int] = None,
        short_period: Optional[int] = None,
        long_period: Optional[int] = None,
    ) -> Dict[str, Any]:
        """扫描板块成分股（默认沪深A股），按 limit / max_stocks_scan 截断。"""
        sector = sector or config.auto_trade.default_sector
        max_scan = config.screening.max_stocks_scan
        limit = limit if limit is not None else config.screening.default_scan_limit
        limit = max(1, min(int(limit), max_scan))

        if not xt_client.is_connected():
            if not xt_client.connect():
                return {
                    "success": False,
                    "error": "XTQuant未连接",
                    "signals": [],
                    "report": "[ERROR] XTQuant未连接，无法获取板块成分股",
                }

        try:
            stock_list = xt_client.get_stock_list(sector) or []
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "signals": [],
                "report": f"[ERROR] 获取板块失败: {e}",
            }

        # 过滤为带市场后缀的 A 股代码
        filtered = []
        for s in stock_list:
            code = str(s).strip().upper()
            if self.data_handler.validate_symbol(code):
                filtered.append(code)
            elif len(code) == 6 and code.isdigit():
                # 部分接口只返回纯数字，尝试补后缀
                suffix = "SH" if code.startswith(("5", "6", "9")) else "SZ"
                candidate = f"{code}.{suffix}"
                if self.data_handler.validate_symbol(candidate):
                    filtered.append(candidate)

        symbols = filtered[:limit]
        result = self.scan_symbols(symbols, short_period=short_period, long_period=long_period)
        result["sector"] = sector
        result["universe_size"] = len(filtered)
        result["scanned"] = len(symbols)
        if result.get("report"):
            result["report"] = (
                f"[MARKET] 板块={sector} 成分约{len(filtered)}只，本次扫描{len(symbols)}只\n"
                + result["report"]
            )
        return result

    def scan_symbols(
        self,
        symbols: List[str],
        short_period: Optional[int] = None,
        long_period: Optional[int] = None,
    ) -> Dict[str, Any]:
        """对给定股票列表计算双均线最新信号。"""
        short_period = short_period or config.strategy.default_short_period
        long_period = long_period or config.strategy.default_long_period

        if short_period >= long_period:
            return {
                "success": False,
                "error": "short_period 必须小于 long_period",
                "signals": [],
                "report": f"[ERROR] 短期均线({short_period})必须小于长期均线({long_period})",
            }

        if not xt_client.is_connected():
            if not xt_client.connect():
                return {
                    "success": False,
                    "error": "XTQuant未连接",
                    "signals": [],
                    "report": "[ERROR] XTQuant未连接，无法获取行情",
                }

        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (
            datetime.now() - timedelta(days=config.auto_trade.lookback_calendar_days)
        ).strftime("%Y%m%d")

        strategy = MAStrategy(short_period=short_period, long_period=long_period)
        signals: List[Dict[str, Any]] = []
        errors: List[str] = []

        for symbol in symbols:
            try:
                item = self._scan_one(symbol, start_date, end_date, strategy)
                if item is None:
                    errors.append(f"{symbol}: 无有效数据或信号")
                else:
                    signals.append(item)
            except Exception as e:
                logger.warning(f"扫描 {symbol} 失败: {e}")
                errors.append(f"{symbol}: {e}")

        actionable = [s for s in signals if s.get("action") in ("BUY", "SELL")]
        report = self._format_report(
            signals=signals,
            actionable=actionable,
            errors=errors,
            short_period=short_period,
            long_period=long_period,
            start_date=start_date,
            end_date=end_date,
        )

        return {
            "success": True,
            "signals": signals,
            "actionable": actionable,
            "errors": errors,
            "short_period": short_period,
            "long_period": long_period,
            "start_date": start_date,
            "end_date": end_date,
            "report": report,
        }

    def _scan_one(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        strategy: MAStrategy,
    ) -> Optional[Dict[str, Any]]:
        data = xt_client.get_market_data(symbol, start_date, end_date)
        if data is None or data.empty:
            return None
        if not self.data_handler.validate_market_data(data):
            return None

        data = self.data_handler.clean_market_data(data)
        if data is None or data.empty or len(data) < strategy.long_period + 1:
            return None

        import pandas as pd

        with_signals = strategy.calculate_signals(data)
        last = with_signals.iloc[-1]
        close = float(last["close"])
        ma_short = float(last["ma_short"]) if pd.notna(last["ma_short"]) else None
        ma_long = float(last["ma_long"]) if pd.notna(last["ma_long"]) else None

        buy = bool(last["buy_signal"]) if pd.notna(last["buy_signal"]) else False
        sell = bool(last["sell_signal"]) if pd.notna(last["sell_signal"]) else False
        if buy:
            action = "BUY"
        elif sell:
            action = "SELL"
        else:
            action = "HOLD"

        signal_val = int(last["signal"]) if pd.notna(last["signal"]) else 0

        return {
            "symbol": symbol,
            "action": action,
            "close": close,
            "ma_short": ma_short,
            "ma_long": ma_long,
            "signal": signal_val,
            "buy_signal": buy,
            "sell_signal": sell,
        }

    @staticmethod
    def _format_report(
        signals: List[Dict[str, Any]],
        actionable: List[Dict[str, Any]],
        errors: List[str],
        short_period: int,
        long_period: int,
        start_date: str,
        end_date: str,
    ) -> str:
        lines = [
            "[SCAN] 双均线扫描结果",
            f"参数: MA({short_period}/{long_period})  数据: {start_date}-{end_date}",
            f"成功: {len(signals)}  可交易信号: {len(actionable)}  失败: {len(errors)}",
            "",
        ]
        if actionable:
            lines.append("[ACTIONABLE]")
            for s in actionable:
                lines.append(
                    f"  {s['action']:4} {s['symbol']}  close={s['close']:.2f}  "
                    f"ma_s={s['ma_short']:.2f}  ma_l={s['ma_long']:.2f}"
                )
            lines.append("")

        holds = [s for s in signals if s.get("action") == "HOLD"]
        if holds:
            lines.append(f"[HOLD] {len(holds)} 只无金叉/死叉（略）")
            preview = ", ".join(h["symbol"] for h in holds[:10])
            lines.append(f"  示例: {preview}" + (" ..." if len(holds) > 10 else ""))
            lines.append("")

        if errors:
            lines.append("[ERRORS]")
            for e in errors[:20]:
                lines.append(f"  - {e}")
            if len(errors) > 20:
                lines.append(f"  ... 另有 {len(errors) - 20} 条")

        return "\n".join(lines)
