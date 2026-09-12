from fastapi import APIRouter, Query

from core.data.fetcher import DataFetcher

router = APIRouter()
fetcher = DataFetcher()


@router.get("/stock/{code}")
async def get_stock_info(code: str):
    """获取股票基本信息"""
    return await fetcher.get_stock_info(code)


@router.get("/kline/{code}")
async def get_kline(
    code: str,
    period: str = Query(default="daily", description="周期: daily/weekly/monthly"),
    start_date: str = Query(default="", description="开始日期 YYYYMMDD"),
    end_date: str = Query(default="", description="结束日期 YYYYMMDD"),
):
    """获取K线数据"""
    return await fetcher.get_kline(code, period, start_date, end_date)


@router.get("/search")
async def search_stock(keyword: str = Query(description="股票代码或名称关键字")):
    """搜索股票"""
    return await fetcher.search_stock(keyword)
