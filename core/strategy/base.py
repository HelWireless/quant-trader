"""策略基类和策略注册表"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import pandas as pd


@dataclass
class Signal:
    """交易信号"""

    code: str
    action: str  # "buy" | "sell" | "hold"
    price: float
    reason: str = ""


class BaseStrategy(ABC):
    """所有策略的基类，继承后实现 on_bar 方法即可"""

    name: str = "base"
    description: str = ""

    @abstractmethod
    def on_bar(self, df: pd.DataFrame) -> Signal | None:
        """接收K线数据，返回交易信号"""
        ...

    def on_init(self) -> None:
        """策略初始化时的钩子，可选覆盖"""
        pass


class StrategyRegistry:
    """策略注册表，管理所有已注册的策略"""

    def __init__(self):
        self._strategies: dict[str, type[BaseStrategy]] = {}

    def register(self, strategy_cls: type[BaseStrategy]) -> None:
        self._strategies[strategy_cls.name] = strategy_cls

    def get(self, name: str) -> type[BaseStrategy] | None:
        return self._strategies.get(name)

    def list_strategies(self) -> list[dict]:
        return [
            {"name": cls.name, "description": cls.description}
            for cls in self._strategies.values()
        ]


# --- 示例策略 ---

class DualMAStrategy(BaseStrategy):
    """双均线策略: 短期均线上穿长期均线买入，下穿卖出"""

    name = "dual_ma"
    description = "双均线交叉策略"

    def __init__(self, short_window: int = 5, long_window: int = 20):
        self.short_window = short_window
        self.long_window = long_window

    def on_bar(self, df: pd.DataFrame) -> Signal | None:
        if len(df) < self.long_window + 1:
            return None

        close = df["收盘"]
        ma_short = close.rolling(self.short_window).mean()
        ma_long = close.rolling(self.long_window).mean()

        prev_short, curr_short = ma_short.iloc[-2], ma_short.iloc[-1]
        prev_long, curr_long = ma_long.iloc[-2], ma_long.iloc[-1]

        code = df.get("股票代码", pd.Series(["unknown"])).iloc[-1]
        price = close.iloc[-1]

        # 金叉: 短均线从下方穿越长均线
        if prev_short <= prev_long and curr_short > curr_long:
            return Signal(code=str(code), action="buy", price=price, reason="金叉")

        # 死叉: 短均线从上方穿越长均线
        if prev_short >= prev_long and curr_short < curr_long:
            return Signal(code=str(code), action="sell", price=price, reason="死叉")

        return Signal(code=str(code), action="hold", price=price)
