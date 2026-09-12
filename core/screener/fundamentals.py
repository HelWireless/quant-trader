"""M6: 基本面筛选模块

数据来源: AkShare (东方财富)
  - stock_zh_a_spot_em(): 全市场实时行情 + PE/PB/市值 (单次调用获取全部A股)
  - stock_individual_fund_flow(): 个股资金流向 (主力/超大/大/中/小单)
  - stock_lhb_detail_em(): 龙虎榜详情
  - stock_hsgt_north_net_flow_in_em(): 北向资金净流入

使用方式:
    from core.screener.fundamentals import FundamentalScreener, CombinedScreener

    # 纯基本面筛选
    fs = FundamentalScreener(strategy="value")
    results = fs.screen_all(top_n=30)

    # 技术面 + 基本面综合筛选
    cs = CombinedScreener(tech_strategy="bull_trend", fund_strategy="value")
    results = cs.screen(df_dict, name_map, top_n=30)
"""

import time
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd
from loguru import logger

from core.screener.screener import (
    FilterCondition,
    ScreeningResult,
    StockScreener,
    PRESET_STRATEGIES as TECH_PRESETS,
)


# ---------------------------------------------------------------------------
# 基本面数据模型
# ---------------------------------------------------------------------------

@dataclass
class FundamentalData:
    """单只股票基本面数据"""
    code: str
    name: str
    price: float = 0.0
    pct_change: float = 0.0       # 涨跌幅 %
    pe_ratio: float = 0.0         # 市盈率 TTM
    pb_ratio: float = 0.0         # 市净率
    total_market_cap: float = 0.0  # 总市值 (元)
    circ_market_cap: float = 0.0   # 流通市值 (元)
    volume_ratio: float = 0.0     # 量比
    turnover_rate: float = 0.0    # 换手率 %
    amplitude: float = 0.0        # 振幅 %
    amount: float = 0.0           # 成交额 (元)
    high_52w: float = 0.0         # 52周最高 (年初至今最高)
    low_52w: float = 0.0          # 52周最低 (年初至今最低)
    change_60d: float = 0.0       # 60日涨跌幅 %
    change_ytd: float = 0.0       # 年初至今涨跌幅 %


# ---------------------------------------------------------------------------
# 基本面数据获取 (带缓存)
# ---------------------------------------------------------------------------

class FundamentalFetcher:
    """基本面数据获取器

    使用 akshare 获取全市场实时数据，单次 API 调用获取全部 A 股。
    内置缓存机制避免频繁调用。
    """

    def __init__(self):
        self._spot_cache: Optional[pd.DataFrame] = None
        self._cache_time: float = 0
        self._cache_ttl: float = 300  # 5 分钟缓存

    def _is_cache_valid(self) -> bool:
        return self._spot_cache is not None and (time.time() - self._cache_time) < self._cache_ttl

    def get_all_spot(self) -> pd.DataFrame:
        """获取全市场 A 股实时行情 + 基本面指标

        返回包含 PE/PB/市值/换手率等字段的 DataFrame。
        使用列位置索引 (不依赖中文列名) 提高兼容性。
        """
        if self._is_cache_valid():
            return self._spot_cache.copy()

        try:
            import akshare as ak
            df = ak.stock_zh_a_spot_em()
        except Exception as e:
            logger.error(f"获取全市场行情数据失败: {e}")
            if self._spot_cache is not None:
                logger.info("使用过期缓存数据")
                return self._spot_cache.copy()
            return pd.DataFrame()

        if df.empty:
            logger.warning("AkShare 返回空数据")
            return pd.DataFrame()

        cols = df.columns.tolist()
        logger.info(f"获取全市场行情: {len(df)} 只股票, {len(cols)} 个字段")
        logger.debug(f"字段列表: {cols}")

        # 构建标准化 DataFrame —— 通过列位置访问核心字段
        # stock_zh_a_spot_em() 典型列序 (可能随版本变化):
        #   0:序号, 1:代码, 2:名称, 3:最新价, 4:涨跌幅, 5:涨跌额,
        #   6:成交量, 7:成交额, 8:振幅, 9:最高, 10:最低, 11:今开, 12:昨收,
        #   13:量比, 14:换手率, 15:市盈率动态, 16:市净率,
        #   17:总市值, 18:流通市值, 19:涨速, 20:5分钟涨跌,
        #   21:60日涨跌幅, 22:年初至今涨跌幅
        result = pd.DataFrame()
        result["code"] = df.iloc[:, 1].astype(str).str.zfill(6) if df.shape[1] > 1 else ""
        result["name"] = df.iloc[:, 2] if df.shape[1] > 2 else ""
        result["price"] = pd.to_numeric(df.iloc[:, 3], errors="coerce").fillna(0) if df.shape[1] > 3 else 0
        result["pct_change"] = pd.to_numeric(df.iloc[:, 4], errors="coerce").fillna(0) if df.shape[1] > 4 else 0
        result["amount"] = pd.to_numeric(df.iloc[:, 7], errors="coerce").fillna(0) if df.shape[1] > 7 else 0
        result["amplitude"] = pd.to_numeric(df.iloc[:, 8], errors="coerce").fillna(0) if df.shape[1] > 8 else 0
        result["volume_ratio"] = pd.to_numeric(df.iloc[:, 13], errors="coerce").fillna(0) if df.shape[1] > 13 else 0
        result["turnover_rate"] = pd.to_numeric(df.iloc[:, 14], errors="coerce").fillna(0) if df.shape[1] > 14 else 0
        result["pe_ratio"] = pd.to_numeric(df.iloc[:, 15], errors="coerce").fillna(0) if df.shape[1] > 15 else 0
        result["pb_ratio"] = pd.to_numeric(df.iloc[:, 16], errors="coerce").fillna(0) if df.shape[1] > 16 else 0
        result["total_market_cap"] = pd.to_numeric(df.iloc[:, 17], errors="coerce").fillna(0) if df.shape[1] > 17 else 0
        result["circ_market_cap"] = pd.to_numeric(df.iloc[:, 18], errors="coerce").fillna(0) if df.shape[1] > 18 else 0
        result["change_60d"] = pd.to_numeric(df.iloc[:, 21], errors="coerce").fillna(0) if df.shape[1] > 21 else 0
        result["change_ytd"] = pd.to_numeric(df.iloc[:, 22], errors="coerce").fillna(0) if df.shape[1] > 22 else 0

        self._spot_cache = result
        self._cache_time = time.time()

        # 统计
        valid_pe = (result["pe_ratio"] != 0).sum()
        valid_pb = (result["pb_ratio"] != 0).sum()
        logger.info(f"基本面数据就绪: PE有效={valid_pe}, PB有效={valid_pb}")

        return result.copy()

    def get_stock_fundamental(self, code: str) -> Optional[FundamentalData]:
        """获取单只股票基本面数据"""
        df = self.get_all_spot()
        if df.empty:
            return None
        row = df[df["code"] == code]
        if row.empty:
            return None
        r = row.iloc[0]
        return FundamentalData(
            code=str(r.get("code", "")),
            name=str(r.get("name", "")),
            price=float(r.get("price", 0)),
            pct_change=float(r.get("pct_change", 0)),
            pe_ratio=float(r.get("pe_ratio", 0)),
            pb_ratio=float(r.get("pb_ratio", 0)),
            total_market_cap=float(r.get("total_market_cap", 0)),
            circ_market_cap=float(r.get("circ_market_cap", 0)),
            volume_ratio=float(r.get("volume_ratio", 0)),
            turnover_rate=float(r.get("turnover_rate", 0)),
            amplitude=float(r.get("amplitude", 0)),
            amount=float(r.get("amount", 0)),
            change_60d=float(r.get("change_60d", 0)),
            change_ytd=float(r.get("change_ytd", 0)),
        )

    def get_batch_fundamental(self, codes: list) -> pd.DataFrame:
        """批量获取基本面数据 (返回 DataFrame)"""
        df = self.get_all_spot()
        if df.empty:
            return df
        return df[df["code"].isin(codes)].copy()

    def clear_cache(self):
        """清除缓存"""
        self._spot_cache = None
        self._cache_time = 0


# ---------------------------------------------------------------------------
# 基本面筛选条件
# ---------------------------------------------------------------------------

def _fund_pe_range(spot_row: pd.Series, min_pe: float = 0, max_pe: float = 100) -> bool:
    """PE 市盈率范围筛选 (排除亏损股 PE<0)"""
    pe = spot_row.get("pe_ratio", 0)
    if pd.isna(pe) or pe <= 0:
        return False
    return min_pe <= pe <= max_pe


def _fund_pb_range(spot_row: pd.Series, min_pb: float = 0, max_pb: float = 10) -> bool:
    """PB 市净率范围筛选"""
    pb = spot_row.get("pb_ratio", 0)
    if pd.isna(pb) or pb <= 0:
        return False
    return min_pb <= pb <= max_pb


def _fund_market_cap_range(
    spot_row: pd.Series, min_cap: float = 0, max_cap: float = float("inf")
) -> bool:
    """流通市值范围 (亿元)"""
    cap = spot_row.get("circ_market_cap", 0)
    if pd.isna(cap) or cap <= 0:
        return False
    cap_yi = cap / 1e8
    return min_cap <= cap_yi <= max_cap


def _fund_pct_change_range(
    spot_row: pd.Series, min_pct: float = -100, max_pct: float = 100
) -> bool:
    """当日涨跌幅范围 (%)"""
    pct = spot_row.get("pct_change", 0)
    if pd.isna(pct):
        return False
    return min_pct <= pct <= max_pct


def _fund_volume_ratio_min(spot_row: pd.Series, min_vr: float = 1.0) -> bool:
    """量比下限"""
    vr = spot_row.get("volume_ratio", 0)
    if pd.isna(vr) or vr <= 0:
        return False
    return vr >= min_vr


def _fund_turnover_range(
    spot_row: pd.Series, min_tr: float = 0, max_tr: float = 100
) -> bool:
    """换手率范围 (%)"""
    tr = spot_row.get("turnover_rate", 0)
    if pd.isna(tr) or tr <= 0:
        return False
    return min_tr <= tr <= max_tr


def _fund_amplitude_max(spot_row: pd.Series, max_amp: float = 10) -> bool:
    """振幅上限 (%)"""
    amp = spot_row.get("amplitude", 0)
    if pd.isna(amp) or amp < 0:
        return False
    return amp <= max_amp


def _fund_price_range(
    spot_row: pd.Series, min_price: float = 0, max_price: float = float("inf")
) -> bool:
    """股价范围"""
    price = spot_row.get("price", 0)
    if pd.isna(price) or price <= 0:
        return False
    return min_price <= price <= max_price


def _fund_amount_min(spot_row: pd.Series, min_amount: float = 0) -> bool:
    """成交额下限 (元)"""
    amt = spot_row.get("amount", 0)
    if pd.isna(amt) or amt < 0:
        return False
    return amt >= min_amount


def _fund_60d_change_range(
    spot_row: pd.Series, min_pct: float = -100, max_pct: float = 100
) -> bool:
    """60日涨跌幅范围 (%)"""
    pct = spot_row.get("change_60d", 0)
    if pd.isna(pct):
        return False
    return min_pct <= pct <= max_pct


# ---------------------------------------------------------------------------
# 辅助: 创建预绑定参数的筛选函数
# ---------------------------------------------------------------------------

def make_pe_filter(min_pe: float = 0, max_pe: float = 100):
    """创建 PE 筛选函数"""
    return lambda row: _fund_pe_range(row, min_pe, max_pe)


def make_pb_filter(min_pb: float = 0, max_pb: float = 10):
    """创建 PB 筛选函数"""
    return lambda row: _fund_pb_range(row, min_pb, max_pb)


def make_cap_filter(min_cap: float = 0, max_cap: float = float("inf")):
    """创建市值筛选函数 (亿元)"""
    return lambda row: _fund_market_cap_range(row, min_cap, max_cap)


def make_pct_filter(min_pct: float = -100, max_pct: float = 100):
    """创建涨跌幅筛选函数"""
    return lambda row: _fund_pct_change_range(row, min_pct, max_pct)


def make_vr_filter(min_vr: float = 1.0):
    """创建量比筛选函数"""
    return lambda row: _fund_volume_ratio_min(row, min_vr)


def make_turnover_filter(min_tr: float = 0, max_tr: float = 100):
    """创建换手率筛选函数"""
    return lambda row: _fund_turnover_range(row, min_tr, max_tr)


def make_amount_filter(min_amount: float = 0):
    """创建成交额筛选函数 (元)"""
    return lambda row: _fund_amount_min(row, min_amount)


# ---------------------------------------------------------------------------
# 预设基本面策略
# ---------------------------------------------------------------------------

FUND_PRESETS = {
    "value": {
        "name": "价值低估",
        "description": "低PE低PB + 中等市值以上 + 有成交",
        "conditions": [
            FilterCondition("pe_low", "PE 5-25", make_pe_filter(5, 25), weight=2.0),
            FilterCondition("pb_low", "PB 0.5-3", make_pb_filter(0.5, 3), weight=2.0),
            FilterCondition("cap_mid", "流通市值>50亿", make_cap_filter(50), weight=1.5),
            FilterCondition("amount_ok", "成交额>5000万", make_amount_filter(5e7), weight=1.0),
        ],
        "min_score": 4.0,
    },
    "momentum": {
        "name": "量价齐升",
        "description": "当日涨幅适中 + 换手活跃 + 放量 + 振幅可控",
        "conditions": [
            FilterCondition("pct_up", "涨幅2-7%", make_pct_filter(2, 7), weight=2.0),
            FilterCondition("turnover", "换手率3-15%", make_turnover_filter(3, 15), weight=1.5),
            FilterCondition("vr_high", "量比>1.5", make_vr_filter(1.5), weight=1.5),
            FilterCondition("amp_ok", "振幅<10%", lambda row: _fund_amplitude_max(row, 10), weight=1.0),
        ],
        "min_score": 3.5,
    },
    "small_growth": {
        "name": "小盘成长",
        "description": "小市值 + PE适中 + 换手活跃 + 中期涨幅可控",
        "conditions": [
            FilterCondition("cap_small", "流通市值20-200亿", make_cap_filter(20, 200), weight=2.0),
            FilterCondition("pe_mid", "PE 10-50", make_pe_filter(10, 50), weight=1.5),
            FilterCondition("turnover", "换手率>2%", make_turnover_filter(2), weight=1.5),
            FilterCondition("60d_ok", "60日涨幅<30%", lambda row: _fund_60d_change_range(row, -100, 30), weight=1.0),
        ],
        "min_score": 3.5,
    },
    "blue_chip": {
        "name": "大盘蓝筹",
        "description": "大市值 + 低PE + 低PB + 股价适中",
        "conditions": [
            FilterCondition("cap_big", "流通市值>500亿", make_cap_filter(500), weight=2.5),
            FilterCondition("pe_low", "PE 5-20", make_pe_filter(5, 20), weight=2.0),
            FilterCondition("pb_low", "PB<5", make_pb_filter(0, 5), weight=1.5),
            FilterCondition("price_ok", "股价5-100", lambda row: _fund_price_range(row, 5, 100), weight=1.0),
        ],
        "min_score": 4.0,
    },
    "turnaround": {
        "name": "底部反转",
        "description": "中期跌幅大 + 今日放量反弹 + 量比放大",
        "conditions": [
            FilterCondition("60d_drop", "60日跌幅>20%", lambda row: _fund_60d_change_range(row, -100, -20), weight=2.5),
            FilterCondition("pct_up", "今日涨幅>1%", make_pct_filter(1, 10), weight=2.0),
            FilterCondition("vr_high", "量比>2", make_vr_filter(2.0), weight=1.5),
            FilterCondition("turnover", "换手率>1%", make_turnover_filter(1), weight=1.0),
        ],
        "min_score": 3.5,
    },
}


# ---------------------------------------------------------------------------
# 基本面筛选器
# ---------------------------------------------------------------------------

class FundamentalScreener:
    """基本面筛选器

    使用方式:
        fs = FundamentalScreener(strategy="value")
        results = fs.screen_all(top_n=30)

        # 自定义条件
        fs = FundamentalScreener()
        fs.add_condition(FilterCondition("my_pe", "低PE", make_pe_filter(5, 15), weight=2.0))
        results = fs.screen_all()
    """

    def __init__(self, strategy: str = ""):
        self.conditions: list[FilterCondition] = []
        self.min_score: float = 0.0
        self.fetcher = FundamentalFetcher()

        if strategy and strategy in FUND_PRESETS:
            self.load_preset(strategy)

    def load_preset(self, strategy_name: str):
        """加载预设策略"""
        preset = FUND_PRESETS.get(strategy_name)
        if not preset:
            raise ValueError(
                f"未知策略: {strategy_name}. 可用: {list(FUND_PRESETS.keys())}"
            )
        self.conditions = preset["conditions"]
        self.min_score = preset["min_score"]
        logger.info(f"加载基本面策略: {preset['name']} - {preset['description']}")

    def add_condition(self, condition: FilterCondition):
        """添加自定义条件"""
        self.conditions.append(condition)

    def screen_all(self, top_n: int = 50) -> list[ScreeningResult]:
        """全市场基本面筛选

        一次 API 调用获取全部 A 股数据，然后逐行筛选。
        """
        df = self.fetcher.get_all_spot()
        if df.empty:
            return []

        # 过滤无效数据 (无价格、停牌)
        df = df[df["price"] > 0].copy()
        logger.info(f"有效股票数: {len(df)}")

        results = []
        for _, row in df.iterrows():
            score = 0.0
            signals = []
            for cond in self.conditions:
                try:
                    if cond.check_func(row):
                        score += cond.weight
                        signals.append(cond.description)
                except Exception:
                    pass

            if score >= self.min_score:
                results.append(ScreeningResult(
                    code=str(row["code"]),
                    name=str(row["name"]),
                    score=round(score, 2),
                    signals=signals,
                    price=float(row.get("price", 0)),
                    pct_change=float(row.get("pct_change", 0)),
                ))

        results.sort(key=lambda x: x.score, reverse=True)
        logger.info(
            f"基本面筛选完成: {len(results)} 只命中 / {len(df)} 只有效"
        )
        return results[:top_n]

    def screen_codes(self, codes: list, top_n: int = 50) -> list[ScreeningResult]:
        """对指定股票列表做基本面筛选"""
        df = self.fetcher.get_batch_fundamental(codes)
        if df.empty:
            return []

        results = []
        for _, row in df.iterrows():
            score = 0.0
            signals = []
            for cond in self.conditions:
                try:
                    if cond.check_func(row):
                        score += cond.weight
                        signals.append(cond.description)
                except Exception:
                    pass

            if score >= self.min_score:
                results.append(ScreeningResult(
                    code=str(row["code"]),
                    name=str(row["name"]),
                    score=round(score, 2),
                    signals=signals,
                    price=float(row.get("price", 0)),
                    pct_change=float(row.get("pct_change", 0)),
                ))

        results.sort(key=lambda x: x.score, reverse=True)
        return results[:top_n]

    @staticmethod
    def get_available_strategies() -> list[dict]:
        """获取所有可用策略"""
        return [
            {"name": k, "description": v["description"], "min_score": v["min_score"]}
            for k, v in FUND_PRESETS.items()
        ]


# ---------------------------------------------------------------------------
# 资金流向筛选
# ---------------------------------------------------------------------------

def get_stock_fund_flow(code: str) -> Optional[dict]:
    """获取个股资金流向 (AkShare)

    Returns:
        dict with keys: main_net, super_large_net, large_net, medium_net, small_net
        单位: 元
    """
    try:
        import akshare as ak
        df = ak.stock_individual_fund_flow(stock=code, market="sh")
    except Exception:
        try:
            import akshare as ak
            df = ak.stock_individual_fund_flow(stock=code, market="sz")
        except Exception as e:
            logger.debug(f"获取资金流向失败 {code}: {e}")
            return None

    if df.empty:
        return None

    # 取最近一条记录 (最新交易日)
    latest = df.iloc[-1]
    cols = df.columns.tolist()

    # 尝试按列名匹配 (AkShare 版本兼容)
    result = {"code": code}
    for col in cols:
        col_lower = col.lower()
        if "主力" in col and "净" in col:
            result["main_net"] = float(latest[col]) if pd.notna(latest[col]) else 0
        elif "超大" in col and "净" in col:
            result["super_large_net"] = float(latest[col]) if pd.notna(latest[col]) else 0
        elif "大单" in col and "净" in col and "超" not in col:
            result["large_net"] = float(latest[col]) if pd.notna(latest[col]) else 0
        elif "中单" in col and "净" in col:
            result["medium_net"] = float(latest[col]) if pd.notna(latest[col]) else 0
        elif "小单" in col and "净" in col:
            result["small_net"] = float(latest[col]) if pd.notna(latest[col]) else 0

    return result if len(result) > 1 else None


def get_batch_fund_flow(codes: list, delay: float = 0.1) -> dict:
    """批量获取资金流向

    Args:
        codes: 股票代码列表
        delay: 每次请求间隔 (秒), 避免被限流

    Returns:
        {code: fund_flow_dict}
    """
    results = {}
    total = len(codes)
    for i, code in enumerate(codes):
        flow = get_stock_fund_flow(code)
        if flow:
            results[code] = flow
        if (i + 1) % 50 == 0:
            logger.info(f"资金流向获取进度: {i+1}/{total}, 有效: {len(results)}")
        if delay > 0:
            time.sleep(delay)

    logger.info(f"资金流向获取完成: {len(results)}/{total} 有效")
    return results


def filter_by_fund_flow(
    codes: list,
    min_main_net: float = 0,
    delay: float = 0.1,
) -> list[dict]:
    """按主力资金净流入筛选

    Args:
        codes: 候选股票代码列表
        min_main_net: 主力净流入下限 (元), 默认 > 0
        delay: 请求间隔

    Returns:
        符合条件的 [{code, main_net, ...}] 列表, 按主力净流入降序
    """
    flows = get_batch_fund_flow(codes, delay=delay)
    matched = []
    for code, flow in flows.items():
        main_net = flow.get("main_net", 0)
        if main_net >= min_main_net:
            matched.append(flow)

    matched.sort(key=lambda x: x.get("main_net", 0), reverse=True)
    logger.info(f"资金流向筛选: {len(matched)}/{len(flows)} 主力净流入")
    return matched


# ---------------------------------------------------------------------------
# 龙虎榜
# ---------------------------------------------------------------------------

def get_dragon_tiger_list(date: str = "") -> pd.DataFrame:
    """获取龙虎榜数据

    Args:
        date: 日期字符串 "YYYYMMDD", 空则取最近交易日

    Returns:
        DataFrame with dragon-tiger list entries
    """
    try:
        import akshare as ak
        if date:
            df = ak.stock_lhb_detail_em(start_date=date, end_date=date)
        else:
            # 默认取最近 5 天
            from datetime import datetime, timedelta
            end = datetime.now().strftime("%Y%m%d")
            start = (datetime.now() - timedelta(days=5)).strftime("%Y%m%d")
            df = ak.stock_lhb_detail_em(start_date=start, end_date=end)
        logger.info(f"龙虎榜数据: {len(df)} 条")
        return df
    except Exception as e:
        logger.error(f"获取龙虎榜失败: {e}")
        return pd.DataFrame()


def filter_by_dragon_tiger(codes: list, date: str = "") -> list[str]:
    """筛选近期上过龙虎榜的股票

    Returns:
        在龙虎榜上出现的 code 列表
    """
    df = get_dragon_tiger_list(date)
    if df.empty:
        return []

    # 龙虎榜 DataFrame 中查找代码列
    lhb_codes = set()
    for col in df.columns:
        if "代码" in col or "code" in col.lower():
            lhb_codes = set(df[col].astype(str).str.zfill(6).tolist())
            break

    if not lhb_codes:
        return []

    matched = [c for c in codes if c in lhb_codes]
    logger.info(f"龙虎榜命中: {len(matched)}/{len(codes)}")
    return matched


# ---------------------------------------------------------------------------
# 北向资金
# ---------------------------------------------------------------------------

def get_northbound_flow(days: int = 10) -> pd.DataFrame:
    """获取近 N 日北向资金净流入

    Returns:
        DataFrame with date and north_net_flow columns
    """
    try:
        import akshare as ak
        df = ak.stock_hsgt_north_net_flow_in_em()
        if df.empty:
            return df
        # 取最近 N 天
        return df.tail(days)
    except Exception as e:
        logger.error(f"获取北向资金数据失败: {e}")
        return pd.DataFrame()


# ---------------------------------------------------------------------------
# 综合筛选器: 技术面 + 基本面
# ---------------------------------------------------------------------------

class CombinedScreener:
    """技术面 + 基本面综合筛选器

    先用技术面筛选缩小范围，再用基本面加分/减分，综合排名。

    使用方式:
        cs = CombinedScreener(tech_strategy="bull_trend", fund_strategy="value")
        results = cs.screen(df_dict, name_map, top_n=30)
    """

    def __init__(
        self,
        tech_strategy: str = "bull_trend",
        fund_strategy: str = "",
        tech_weight: float = 1.0,
        fund_weight: float = 1.0,
    ):
        self.tech_screener = StockScreener(strategy=tech_strategy)
        self.fund_screener = FundamentalScreener(strategy=fund_strategy) if fund_strategy else None
        self.tech_weight = tech_weight
        self.fund_weight = fund_weight
        self.fund_fetcher = FundamentalFetcher()

    def screen(
        self,
        df_dict: dict,
        name_map: dict = None,
        top_n: int = 50,
    ) -> list[ScreeningResult]:
        """综合筛选流程

        1. 技术面筛选: 对全部候选做技术指标筛选
        2. 基本面加分: 对技术面命中的股票叠加基本面评分
        3. 综合排名: tech_score * tech_weight + fund_score * fund_weight
        """
        if name_map is None:
            name_map = {}

        # Step 1: 技术面筛选
        tech_results = self.tech_screener.screen_batch(df_dict, name_map, top_n=top_n * 3)
        if not tech_results:
            logger.warning("技术面筛选无命中")
            return []

        tech_codes = {r.code for r in tech_results}
        logger.info(f"技术面命中 {len(tech_codes)} 只, 开始基本面叠加")

        # Step 2: 获取基本面数据
        fund_df = self.fund_fetcher.get_batch_fundamental(list(tech_codes))

        # Step 3: 基本面评分
        fund_scores = {}
        if not fund_df.empty and self.fund_screener:
            for _, row in fund_df.iterrows():
                code = str(row["code"])
                score = 0.0
                signals = []
                for cond in self.fund_screener.conditions:
                    try:
                        if cond.check_func(row):
                            score += cond.weight
                            signals.append(cond.description)
                    except Exception:
                        pass
                fund_scores[code] = {"score": score, "signals": signals}

        # Step 4: 综合评分
        combined = []
        for tr in tech_results:
            fund_info = fund_scores.get(tr.code, {"score": 0, "signals": []})
            total_score = (
                tr.score * self.tech_weight
                + fund_info["score"] * self.fund_weight
            )
            all_signals = tr.signals + fund_info["signals"]

            combined.append(ScreeningResult(
                code=tr.code,
                name=tr.name,
                score=round(total_score, 2),
                signals=all_signals,
                price=tr.price,
                pct_change=tr.pct_change,
            ))

        combined.sort(key=lambda x: x.score, reverse=True)
        logger.info(
            f"综合筛选完成: {len(combined)} 只候选, 返回 top {top_n}"
        )
        return combined[:top_n]


# ---------------------------------------------------------------------------
# 便捷函数: 一步完成综合筛选
# ---------------------------------------------------------------------------

def quick_screen(
    df_dict: dict,
    name_map: dict = None,
    tech_strategy: str = "bull_trend",
    fund_strategy: str = "value",
    top_n: int = 30,
) -> list[ScreeningResult]:
    """一步完成技术面 + 基本面综合筛选

    Args:
        df_dict: {code: kline_dataframe} 行情数据
        name_map: {code: stock_name} 名称映射
        tech_strategy: 技术策略名 (TECH_PRESETS 中的 key)
        fund_strategy: 基本面策略名 (FUND_PRESETS 中的 key)
        top_n: 返回前 N 名

    Returns:
        按综合得分降序排列的 ScreeningResult 列表
    """
    cs = CombinedScreener(
        tech_strategy=tech_strategy,
        fund_strategy=fund_strategy,
        tech_weight=1.0,
        fund_weight=0.8,
    )
    return cs.screen(df_dict, name_map, top_n=top_n)
