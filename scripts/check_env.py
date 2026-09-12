"""Server-side checks: QA user existence + LLM config."""
import asyncio
import sys

sys.path.insert(0, "/home/cody/projects/quant-trader")

from core.auth.db import async_session_maker
from sqlalchemy import text
from core.chat.agent import get_llm_config


async def main():
    async with async_session_maker() as s:
        r = await s.execute(
            text("SELECT id, email FROM auth_user WHERE email='qa_test@quanttrader.io'")
        )
        rows = r.fetchall()
        print("QA_USER_ROWS:", rows)

    cfg = get_llm_config()
    print("LLM_PROVIDER:", cfg.provider)
    print("LLM_MODEL:", cfg.model)
    print("LLM_API_BASE:", cfg.api_base)
    print("LLM_HAS_KEY:", cfg.has_key)


asyncio.run(main())
