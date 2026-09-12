"""导入通达信日线数据包 (hsjday.zip 解压后)

通达信 .day 格式 (32 bytes/record):
  [date u32][open u32][high u32][low u32][close u32][amount f32][volume u32][reserved u32]
  - 价格单位: 分 (需除以 100)
  - 日期: YYYYMMDD
  - amount: 成交额 (元)
  - volume: 成交量 (股)

数据覆盖:
  - SH: 5874 只 (上海)
  - SZ: 5785 只 (深圳)
  - BJ: 585 只 (北交所)
  - 日期范围: 各股上市日 ~ 2026-06-26

使用方式:
    py -3 scripts/import_tdx_day.py
    py -3 scripts/import_tdx_day.py --data-dir C:/path/to/tdx
    py -3 scripts/import_tdx_day.py --dry-run  # 仅统计不写入
"""

import argparse
import os
import struct
import sys
import time
from pathlib import Path

from loguru import logger
from sqlalchemy import create_engine, text

PROJECT_ROOT = Path(__file__).parent.parent
DEFAULT_DATA_DIR = PROJECT_ROOT / "data" / "raw" / "tdx"
DEFAULT_DB_URL = "postgresql://postgres@localhost:5432/quant_minute"

RECORD_SIZE = 32
RECORD_STRUCT = struct.Struct("<IIIIIfII")


def parse_day_file(filepath: str) -> list[tuple]:
    """解析通达信 .day 文件

    Returns:
        [(date_str, open, high, low, close, volume, amount), ...]
    """
    with open(filepath, "rb") as f:
        data = f.read()

    n = len(data) // RECORD_SIZE
    records = []

    for i in range(n):
        offset = i * RECORD_SIZE
        date_int, open_fen, high_fen, low_fen, close_fen, amount, vol, _ = \
            RECORD_STRUCT.unpack_from(data, offset)

        # 跳过无效记录
        if date_int < 19900101 or date_int > 20991231:
            continue
        if open_fen == 0 and close_fen == 0:
            continue

        date_str = str(date_int)
        if len(date_str) != 8:
            continue
        date_fmt = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"

        records.append((
            date_fmt,
            open_fen / 100.0,
            high_fen / 100.0,
            low_fen / 100.0,
            close_fen / 100.0,
            float(vol),
            float(amount),
        ))

    return records


def scan_files(data_dir: str) -> dict[str, str]:
    """扫描所有 .day 文件，返回 {code: filepath}"""
    files = {}
    for market in ["sh", "sz", "bj"]:
        lday_dir = os.path.join(data_dir, market, "lday")
        if not os.path.isdir(lday_dir):
            logger.warning(f"目录不存在: {lday_dir}")
            continue
        for fname in os.listdir(lday_dir):
            if fname.endswith(".day"):
                # e.g. sh600367.day -> 600367
                code = fname[2:-4]  # 去掉市场前缀和扩展名
                filepath = os.path.join(lday_dir, fname)
                files[code] = filepath

    return files


def import_to_pg(files: dict[str, str], db_url: str, dry_run: bool = False):
    """批量导入到 PostgreSQL"""
    engine = create_engine(db_url)

    # 检查现有数据最大日期
    with engine.connect() as conn:
        r = conn.execute(text("SELECT MAX(date) FROM daily_kline")).fetchone()
        existing_max = r[0] or "0000-00-00"
        logger.info(f"现有数据最大日期: {existing_max}")

        # 统计现有记录数
        r = conn.execute(text("SELECT COUNT(*) FROM daily_kline")).fetchone()
        before_count = r[0]
        logger.info(f"导入前记录数: {before_count:,}")

    if dry_run:
        logger.info("=== DRY RUN 模式, 不写入数据库 ===")

    total_files = len(files)
    total_records = 0
    total_new = 0
    total_updated = 0
    errors = 0
    t0 = time.time()

    for i, (code, filepath) in enumerate(sorted(files.items())):
        try:
            records = parse_day_file(filepath)
        except Exception as e:
            errors += 1
            logger.debug(f"解析失败 {code}: {e}")
            continue

        if not records:
            continue

        total_records += len(records)

        if not dry_run:
            # 使用 INSERT ... ON CONFLICT DO UPDATE (新数据覆盖旧数据)
            rows = [
                {"code": code, "date": r[0], "open": r[1], "high": r[2],
                 "low": r[3], "close": r[4], "volume": r[5], "amount": r[6]}
                for r in records
            ]
            try:
                with engine.begin() as conn:
                    conn.execute(
                        text("""INSERT INTO daily_kline
                                (code, date, open, high, low, close, volume, amount)
                                VALUES (:code, :date, :open, :high, :low, :close, :volume, :amount)
                                ON CONFLICT (code, date) DO UPDATE SET
                                    open = EXCLUDED.open,
                                    high = EXCLUDED.high,
                                    low = EXCLUDED.low,
                                    close = EXCLUDED.close,
                                    volume = EXCLUDED.volume,
                                    amount = EXCLUDED.amount"""),
                        rows,
                    )
            except Exception as e:
                logger.error(f"导入失败 {code}: {e}")
                errors += 1

        if (i + 1) % 500 == 0:
            elapsed = time.time() - t0
            speed = (i + 1) / elapsed
            eta = (total_files - i - 1) / speed if speed > 0 else 0
            logger.info(
                f"进度: {i+1}/{total_files} ({(i+1)/total_files*100:.0f}%), "
                f"records={total_records:,}, elapsed={elapsed:.0f}s, eta={eta:.0f}s"
            )

    if not dry_run:
        # 统计导入后
        with engine.connect() as conn:
            r = conn.execute(text("SELECT COUNT(*) FROM daily_kline")).fetchone()
            after_count = r[0]
            r = conn.execute(text("SELECT MAX(date) FROM daily_kline")).fetchone()
            new_max = r[0]
            r = conn.execute(text("SELECT COUNT(DISTINCT code) FROM daily_kline")).fetchone()
            code_count = r[0]

        logger.info(f"导入完成!")
        logger.info(f"  文件数: {total_files}")
        logger.info(f"  总记录: {total_records:,}")
        logger.info(f"  写入前: {before_count:,} → 写入后: {after_count:,}")
        logger.info(f"  新增: {after_count - before_count:,}")
        logger.info(f"  股票数: {code_count}")
        logger.info(f"  日期范围: → {new_max}")
        logger.info(f"  错误: {errors}")
        logger.info(f"  耗时: {time.time()-t0:.1f}s")
    else:
        logger.info(f"DRY RUN 统计: {total_files} 文件, {total_records:,} 记录, {errors} 错误")

    engine.dispose()


def update_stock_info(files: dict[str, str], db_url: str):
    """更新 stock_info 表 (新增通达信有但我们库里没有的股票)"""
    engine = create_engine(db_url)

    # 获取现有代码
    with engine.connect() as conn:
        r = conn.execute(text("SELECT code FROM stock_info")).fetchall()
        existing = {row[0] for row in r}

    new_codes = [code for code in files if code not in existing]
    logger.info(f"通达信文件: {len(files)}, 现有stock_info: {len(existing)}, 新增: {len(new_codes)}")

    if new_codes:
        with engine.begin() as conn:
            for code in new_codes:
                market = "SH" if code.startswith("6") else "SZ" if code.startswith(("0", "3")) else "BJ"
                conn.execute(
                    text("INSERT INTO stock_info (code, name, market) VALUES (:code, '', :market)"),
                    {"code": code, "market": market},
                )

    engine.dispose()
    logger.info(f"新增 {len(new_codes)} 只股票到 stock_info")


def main():
    parser = argparse.ArgumentParser(description="导入通达信日线数据")
    parser.add_argument("--data-dir", type=str, default=str(DEFAULT_DATA_DIR))
    parser.add_argument("--db", type=str, default=DEFAULT_DB_URL)
    parser.add_argument("--dry-run", action="store_true", help="仅统计不写入")
    args = parser.parse_args()

    logger.info(f"数据目录: {args.data_dir}")
    logger.info(f"数据库: {args.db}")

    files = scan_files(args.data_dir)
    logger.info(f"扫描到 {len(files)} 个 .day 文件")

    if not files:
        logger.error("未找到 .day 文件, 请检查数据目录")
        return

    # 先更新 stock_info
    if not args.dry_run:
        update_stock_info(files, args.db)

    # 导入K线数据
    import_to_pg(files, args.db, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
