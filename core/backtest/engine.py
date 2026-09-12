"""回测引擎 (骨架)"""

from dataclasses import dataclass, field

import pandas as pd
from loguru import logger

from core.strategy.base import BaseStrategy, Signal


@dataclass
class BacktestResult:
    """回测结果"""

    total_return: float = 0.0
    win_rate: float = 0.0
    max_drawdown: float = 0.0
    trade_count: int = 0
    trades: list[dict] = field(default_factory=list)


class BacktestEngine:
    """简易回测引擎"""

    def __init__(self, initial_capital: float = 100_000.0):
        self.initial_capital = initial_capital

    def run(self, strategy: BaseStrategy, df: pd.DataFrame) -> BacktestResult:
        """对给定数据运行策略，返回回测结果"""
        capital = self.initial_capital
        position = 0
        trades: list[dict] = []

        strategy.on_init()

        for i in range(len(df)):
            window = df.iloc[: i + 1]
            signal = strategy.on_bar(window)

            if signal is None:
                continue

            if signal.action == "buy" and position == 0:
                shares = int(capital // signal.price)
                if shares > 0:
                    position = shares
                    capital -= shares * signal.price
                    trades.append({
                        "type": "buy",
                        "price": signal.price,
                        "shares": shares,
                        "reason": signal.reason,
                    })

            elif signal.action == "sell" and position > 0:
                capital += position * signal.price
                trades.append({
                    "type": "sell",
                    "price": signal.price,
                    "shares": position,
                    "reason": signal.reason,
                })
                position = 0

        # 计算最终收益
        final_price = df["收盘"].iloc[-1] if "收盘" in df.columns else 0
        total_value = capital + position * final_price
        total_return = (total_value - self.initial_capital) / self.initial_capital

        # 简单胜率
        buy_prices = [t["price"] for t in trades if t["type"] == "buy"]
        sell_prices = [t["price"] for t in trades if t["type"] == "sell"]
        wins = sum(1 for b, s in zip(buy_prices, sell_prices) if s > b)
        win_rate = wins / len(sell_prices) if sell_prices else 0.0

        result = BacktestResult(
            total_return=round(total_return, 4),
            win_rate=round(win_rate, 4),
            trade_count=len(trades),
            trades=trades,
        )
        logger.info(f"Backtest done: {result}")
        return result
