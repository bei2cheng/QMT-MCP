"""
配置管理模块
统一管理QuantMCP的所有配置参数
支持环境变量与可选 .env 文件
"""

import os
from dataclasses import dataclass, field
from typing import List


def _load_dotenv(path: str = ".env") -> None:
    """轻量加载 .env（不依赖 python-dotenv）"""
    if not os.path.isfile(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                # 行内注释
                if " #" in value:
                    value = value.split(" #", 1)[0].rstrip()
                if key and key not in os.environ:
                    os.environ[key] = value
    except OSError:
        pass


_load_dotenv()


def _parse_watchlist(raw: str | None) -> List[str]:
    if not raw:
        return []
    return [s.strip().upper() for s in raw.replace(";", ",").split(",") if s.strip()]


@dataclass
class ServerConfig:
    """服务器配置"""
    host: str = os.getenv("QUANTMCP_HOST", "127.0.0.1")
    port: int = int(os.getenv("QUANTMCP_PORT", "8000"))
    transport: str = os.getenv("QUANTMCP_TRANSPORT", "sse")


@dataclass
class StrategyConfig:
    """策略配置"""
    default_symbol: str = os.getenv("DEFAULT_SYMBOL", "000001.SZ")
    default_start_date: str = os.getenv("DEFAULT_START_DATE", "20240101")
    default_end_date: str = os.getenv("DEFAULT_END_DATE", "20241201")
    default_short_period: int = int(os.getenv("DEFAULT_SHORT_PERIOD", "5"))
    default_long_period: int = int(os.getenv("DEFAULT_LONG_PERIOD", "20"))


@dataclass
class ScreeningConfig:
    """筛选配置"""
    default_stock_list: List[str] = None
    default_date_range: str = "20241101-20241201"
    max_stocks_scan: int = int(os.getenv("MAX_STOCKS_SCAN", "500"))
    default_scan_limit: int = int(os.getenv("DEFAULT_SCAN_LIMIT", "20"))

    def __post_init__(self):
        if self.default_stock_list is None:
            env_list = _parse_watchlist(os.getenv("WATCHLIST"))
            self.default_stock_list = env_list or [
                "000001.SZ",
                "000002.SZ",
                "600000.SH",
                "600036.SH",
            ]


@dataclass
class TradingConfig:
    """交易配置"""
    qmt_path: str = os.getenv("QMT_PATH", r"D:\国金QMT交易端模拟\userdata_mini")
    session_id: int = int(os.getenv("QMT_SESSION_ID", "13579"))
    account_id: str = os.getenv("QMT_ACCOUNT_ID", "55012417")

    max_order_value: float = float(os.getenv("MAX_ORDER_VALUE", "100000.0"))
    max_position_value: float = float(os.getenv("MAX_POSITION_VALUE", "500000.0"))
    min_order_quantity: int = int(os.getenv("MIN_ORDER_QUANTITY", "100"))

    default_strategy_name: str = "QuantMCP"
    default_remark: str = "MCP_Auto_Order"
    market_order_spread: float = float(os.getenv("MARKET_ORDER_SPREAD", "0.1"))


@dataclass
class AutoTradeConfig:
    """MCP 侧自动交易配置"""
    default_quantity: int = int(os.getenv("AUTO_TRADE_QUANTITY", "100"))
    max_orders_per_day: int = int(os.getenv("AUTO_TRADE_MAX_ORDERS_PER_DAY", "10"))
    scheduler_interval_sec: int = int(os.getenv("AUTO_TRADE_INTERVAL_SEC", "300"))
    lookback_calendar_days: int = int(os.getenv("AUTO_TRADE_LOOKBACK_DAYS", "120"))
    default_dry_run: bool = os.getenv("AUTO_TRADE_DRY_RUN", "true").lower() in (
        "1",
        "true",
        "yes",
    )
    default_sector: str = os.getenv("AUTO_TRADE_DEFAULT_SECTOR", "沪深A股")
    watchlist: List[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.watchlist:
            env_list = _parse_watchlist(os.getenv("WATCHLIST"))
            self.watchlist = env_list or [
                "000001.SZ",
                "000002.SZ",
                "600000.SH",
                "600036.SH",
            ]


class Config:
    """全局配置管理器"""

    def __init__(self):
        self.server = ServerConfig()
        self.strategy = StrategyConfig()
        self.screening = ScreeningConfig()
        self.trading = TradingConfig()
        self.auto_trade = AutoTradeConfig()

    @classmethod
    def from_file(cls, config_path: str):
        """从配置文件加载配置"""
        return cls()


# 全局配置实例
config = Config()
