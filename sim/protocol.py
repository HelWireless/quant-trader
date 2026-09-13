# -*- coding: utf-8 -*-
"""双系统模拟交易 —— 通信协议（两系统唯一接口）。

设计原则：策略系统（A）与撮合系统（B）各自独立，
**只通过本文件定义的数据结构通信**，互不 import 对方内部状态。

一个容易被忽略的点：出场也必须是「条件单」模式。
因为止损是盘中触发，如果 A 自己判断出场，它就得读 T 日价格 —— 数据边界被击穿。
所以 A 盘前只下发「条件单描述」，B 用 T 日 OHLC 判断是否触发。
"""
from dataclasses import dataclass, field
from datetime import date
from typing import Optional


# ------------------------------------------------------------------ 条件单类型
COND_STOP = 'STOP'              # 价格 <= cond_price 卖出（硬止损）
COND_ARM_TRAIL = 'ARM_TRAIL'    # 价格 >= arm_price 激活，之后自峰值回落 trail_pct% 卖出
COND_REBOUND = 'REBOUND'        # 价格 <= loss_arm 记低点，反弹 rebound_pct% 卖出
COND_OPEN_SELL = 'OPEN_SELL'    # 开盘价直接卖出（超时）


@dataclass
class OrderRequest:
    """系统 A → 系统 B：一笔委托。"""
    date: date
    kind: str                        # 'BUY' | 'SELL'
    code: str
    shares: int
    reason: str = ''

    # ---- 仅 SELL 使用：条件单描述 ----
    cond_kind: Optional[str] = None
    cond_price: Optional[float] = None      # STOP 的止损价
    arm_price: Optional[float] = None       # ARM_TRAIL 的激活价
    trail_pct: Optional[float] = None       # ARM_TRAIL 的回落幅度
    peak: Optional[float] = None            # 截至昨日的峰值（A 维护，供 B 用）
    loss_arm: Optional[float] = None        # REBOUND 的破位价
    rebound_pct: Optional[float] = None     # REBOUND 的反弹幅度
    trough: Optional[float] = None          # REBOUND 的已知低点
    armed: bool = False                     # 是否已武装（ARM_TRAIL 生效中）
    fallback_kind: Optional[str] = None     # ARM_TRAIL 未武装时回退到哪种条件（STOP/REBOUND）

    # ---- 仅 BUY 使用 ----
    ref_price: Optional[float] = None       # A 的参考价（信号日收盘），仅供 B 记录
    budget: Optional[float] = None          # 单笔金额预算（元）—— B 按实际成交价决定手数
    available_cash: Optional[float] = None  # A 当前可用现金，供 B 约束股数


@dataclass
class FillReport:
    """系统 B → 系统 A：一笔回报。"""
    date: date
    code: str
    kind: str                        # 'BUY' | 'SELL'
    status: str                      # 'FILLED' | 'MISSED' | 'REJECTED'
    fill_price: Optional[float] = None
    shares: int = 0
    fee: float = 0.0
    deviation: str = 'OK'            # 见 broker_sim 的标签
    reason: str = ''
    market: dict = field(default_factory=dict)   # {'open','high','low','close'} 当日行情快照
    note: str = ''                   # 人类可读的说明


# 偏差标签（用于统计）
DEV_OK = 'OK'
DEV_SLIP_UP = 'SLIP_UP'            # 买入追高
DEV_LUCKY_LOW = 'LUCKY_LOW'        # 买在当日最低
DEV_BUY_MISSED = 'BUY_MISSED'      # 随机买入失败
DEV_LIMIT_UP_BLOCK = 'LIMIT_UP_BLOCK'    # 涨停买不进（结构性）
DEV_SLIP_DOWN = 'SLIP_DOWN'        # 卖出割肉
DEV_LUCKY_HIGH = 'LUCKY_HIGH'      # 卖在当日最高
DEV_SELL_MISSED = 'SELL_MISSED'    # 随机卖出失败
DEV_LIMIT_DOWN_BLOCK = 'LIMIT_DOWN_BLOCK'  # 跌停卖不出（结构性）

DEV_LABELS = {
    DEV_OK: '正常成交',
    DEV_SLIP_UP: '买入追高',
    DEV_LUCKY_LOW: '买在当日最低',
    DEV_BUY_MISSED: '买入失败(随机)',
    DEV_LIMIT_UP_BLOCK: '涨停买不进',
    DEV_SLIP_DOWN: '卖出割肉',
    DEV_LUCKY_HIGH: '卖在当日最高',
    DEV_SELL_MISSED: '卖出漏单(随机)',
    DEV_LIMIT_DOWN_BLOCK: '跌停卖不出',
}
