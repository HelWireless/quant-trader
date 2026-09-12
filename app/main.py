from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import market, strategy

app = FastAPI(
    title="Quant Trader API",
    description="股票量化交易工具 API",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(market.router, prefix="/api/market", tags=["行情数据"])
app.include_router(strategy.router, prefix="/api/strategy", tags=["交易策略"])


@app.get("/")
async def root():
    return {"message": "Quant Trader API is running", "version": "0.1.0"}


@app.get("/health")
async def health():
    return {"status": "ok"}
