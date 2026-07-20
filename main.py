#!/usr/bin/env python3
"""
QuantMCP Main Entry - 模块化架构主入口
提供智能策略生成、扫描选股、自动交易调度等功能
"""

import logging
import traceback
import os

from fastmcp import FastMCP

from src.config import config
from src.utils.xtquant_client import xt_client
from src.tools import TradingTool, QMTStrategyTool, ScannerTool, AutoTradeEngine

os.makedirs("logs", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("logs/quantmcp.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("quantmcp")


def init_system():
    """初始化系统"""
    logger.info("=" * 50)
    logger.info("QuantMCP 模块化架构 v2.0 启动中...")
    logger.info("=" * 50)

    logger.info("正在初始化XTQuant连接...")
    try:
        if xt_client.connect():
            logger.info("[OK] XTQuant连接成功")
        else:
            logger.warning("[WARNING] XTQuant连接失败，将在离线模式下运行")
    except Exception as e:
        logger.error(f"[ERROR] XTQuant初始化失败: {e}")

    logger.info(
        f"[OK] 自选池: {len(config.auto_trade.watchlist)} 只, "
        f"自动交易默认 dry_run={config.auto_trade.default_dry_run}"
    )
    logger.info("[OK] 系统初始化完成")


mcp = FastMCP("QuantMCP量化交易助手")

trading_tool = TradingTool()
qmt_tool = QMTStrategyTool()
scanner_tool = ScannerTool()
auto_trade_engine = AutoTradeEngine(scanner=scanner_tool, trading=trading_tool)


@mcp.tool()
def place_order(symbol: str, quantity: int, price: float, direction: str = "BUY") -> str:
    """简化下单工具

    Args:
        symbol: 股票代码，如 000001.SZ、600000.SH
        quantity: 买入股数（必须是100的整数倍）
        price: 下单价格
        direction: 交易方向，默认BUY买入，也可以是SELL卖出
    """
    try:
        logger.info(f"MCP调用: place_order({symbol}, {quantity}, {price}, {direction})")
        return trading_tool.place_order(
            symbol=symbol, quantity=quantity, price=price, direction=direction
        )
    except Exception as e:
        logger.error(f"place_order执行失败: {e}")
        return f"[ERROR] 下单失败: {str(e)}"


@mcp.tool()
def cancel_order(order_id: str) -> str:
    """撤单工具"""
    try:
        logger.info(f"MCP调用: cancel_order({order_id})")
        return trading_tool.cancel_order(order_id=order_id)
    except Exception as e:
        logger.error(f"cancel_order执行失败: {e}")
        return f"[ERROR] 撤单失败: {str(e)}"


@mcp.tool()
def get_positions(symbol: str = "") -> str:
    """查询持仓。传入股票代码查询单票；空字符串提示需指定代码。"""
    try:
        logger.info(f"MCP调用: get_positions({symbol!r})")
        return trading_tool.get_positions(symbol=symbol or None)
    except Exception as e:
        logger.error(f"get_positions执行失败: {e}")
        return f"[ERROR] 查询持仓失败: {str(e)}"


@mcp.tool()
def save_qmt_strategy(strategy_name: str, code: str) -> str:
    """保存自定义策略代码到 QMT 本地策略目录"""
    try:
        logger.info(f"MCP调用: save_qmt_strategy({strategy_name})")
        return qmt_tool.save_strategy(strategy_name, code)
    except Exception as e:
        logger.error(f"save_qmt_strategy 执行失败: {e}")
        return f"[ERROR] 保存策略失败: {str(e)}"


@mcp.tool()
def generate_ma_strategy(
    symbol: str = "000001.SZ",
    short_period: int = 5,
    long_period: int = 20,
    strategy_name: str | None = None,
) -> str:
    """生成并保存双均线策略示例到 QMT 策略目录"""
    try:
        logger.info("MCP调用: generate_ma_strategy")
        return qmt_tool.generate_ma_strategy(
            symbol, short_period, long_period, strategy_name
        )
    except Exception as e:
        logger.error(f"generate_ma_strategy 执行失败: {e}")
        return f"[ERROR] 生成策略失败: {str(e)}"


@mcp.tool()
def set_watchlist(symbols: str) -> str:
    """设置自选股票池。逗号分隔，如: 000001.SZ,600519.SH"""
    try:
        logger.info(f"MCP调用: set_watchlist({symbols})")
        return scanner_tool.set_watchlist(symbols)
    except Exception as e:
        logger.error(f"set_watchlist失败: {e}")
        return f"[ERROR] 设置自选失败: {str(e)}"


@mcp.tool()
def get_watchlist() -> str:
    """查看当前自选股票池"""
    try:
        return scanner_tool.get_watchlist()
    except Exception as e:
        return f"[ERROR] 获取自选失败: {str(e)}"


@mcp.tool()
def scan_watchlist(short_period: int = 5, long_period: int = 20) -> str:
    """扫描自选池，输出双均线金叉/死叉信号（不下单）"""
    try:
        logger.info("MCP调用: scan_watchlist")
        result = scanner_tool.scan_watchlist(
            short_period=short_period, long_period=long_period
        )
        return result.get("report") or str(result)
    except Exception as e:
        logger.error(f"scan_watchlist失败: {e}")
        return f"[ERROR] 扫描自选失败: {str(e)}"


@mcp.tool()
def scan_market(
    sector: str = "沪深A股",
    limit: int = 20,
    short_period: int = 5,
    long_period: int = 20,
) -> str:
    """扫描板块成分股（默认沪深A股），按 limit 截断，输出双均线信号（不下单）"""
    try:
        logger.info(f"MCP调用: scan_market(sector={sector}, limit={limit})")
        result = scanner_tool.scan_market(
            sector=sector,
            limit=limit,
            short_period=short_period,
            long_period=long_period,
        )
        return result.get("report") or str(result)
    except Exception as e:
        logger.error(f"scan_market失败: {e}")
        return f"[ERROR] 板块扫描失败: {str(e)}"


@mcp.tool()
def run_auto_trade_cycle(
    dry_run: bool = True,
    source: str = "watchlist",
    quantity: int = 100,
    short_period: int = 5,
    long_period: int = 20,
    sector: str = "沪深A股",
    limit: int = 20,
) -> str:
    """跑一轮自动交易：扫描 → 信号 → 可选下单。

    Args:
        dry_run: True 只报告不落单（默认 True，务必先模拟）
        source: watchlist 或 market
        quantity: 买入股数（卖出按持仓）
        short_period / long_period: 双均线参数
        sector / limit: source=market 时使用
    """
    try:
        logger.info(
            f"MCP调用: run_auto_trade_cycle(dry_run={dry_run}, source={source})"
        )
        return auto_trade_engine.run_cycle(
            dry_run=dry_run,
            source=source,
            quantity=quantity,
            short_period=short_period,
            long_period=long_period,
            sector=sector,
            limit=limit,
        )
    except Exception as e:
        logger.error(f"run_auto_trade_cycle失败: {e}")
        return f"[ERROR] 自动交易轮次失败: {str(e)}"


@mcp.tool()
def start_scheduler(
    interval_sec: int = 300,
    dry_run: bool = True,
    source: str = "watchlist",
    quantity: int = 100,
    short_period: int = 5,
    long_period: int = 20,
    sector: str = "沪深A股",
    limit: int = 20,
) -> str:
    """启动后台定时自动交易。默认 dry_run=True。interval_sec 最小 30。"""
    try:
        logger.info(
            f"MCP调用: start_scheduler(interval={interval_sec}, dry_run={dry_run})"
        )
        return auto_trade_engine.start_scheduler(
            interval_sec=interval_sec,
            dry_run=dry_run,
            source=source,
            quantity=quantity,
            short_period=short_period,
            long_period=long_period,
            sector=sector,
            limit=limit,
        )
    except Exception as e:
        logger.error(f"start_scheduler失败: {e}")
        return f"[ERROR] 启动调度器失败: {str(e)}"


@mcp.tool()
def stop_scheduler() -> str:
    """停止后台定时自动交易"""
    try:
        logger.info("MCP调用: stop_scheduler")
        return auto_trade_engine.stop_scheduler()
    except Exception as e:
        return f"[ERROR] 停止调度器失败: {str(e)}"


@mcp.tool()
def get_scheduler_status() -> str:
    """查看调度器状态与最近一轮结果"""
    try:
        return auto_trade_engine.get_scheduler_status()
    except Exception as e:
        return f"[ERROR] 获取调度状态失败: {str(e)}"


def main():
    """主函数"""
    try:
        init_system()

        logger.info("[INFO] QuantMCP服务器启动信息:")
        logger.info(
            f"   * 服务地址: http://{config.server.host}:{config.server.port}"
        )
        logger.info(f"   * 传输方式: {config.server.transport.upper()}")
        logger.info(
            f"   * XTQuant状态: {'已连接' if xt_client.is_connected() else '未连接'}"
        )
        logger.info("   * 架构版本: 模块化架构 v2.0 + AutoTrade")

        logger.info(
            f"[START] QuantMCP Server starting on "
            f"http://{config.server.host}:{config.server.port}"
        )

        mcp.run(
            transport=config.server.transport,
            host=config.server.host,
            port=config.server.port,
        )

    except KeyboardInterrupt:
        logger.info("[STOP] 用户中断，服务器正在关闭...")
    except Exception as e:
        logger.error(f"[ERROR] 服务器错误: {e}")
        logger.error(traceback.format_exc())
        raise
    finally:
        try:
            auto_trade_engine.stop_scheduler()
        except Exception:
            pass
        try:
            xt_client.disconnect()
            logger.info("[OK] 资源清理完成")
        except Exception:
            pass


if __name__ == "__main__":
    main()
