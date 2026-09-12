"""导入 waizaowang.com 历史分钟K线数据到 PostgreSQL。

数据源: E:\\BaiduNetdiskDownload\\财经数据\\ 下的 zip 文件。
覆盖: 2021-08 ~ 2023-02，5个频率（1/5/15/30/60分钟）。

CSV 格式:
  5/15/30/60分钟: code,name,ktype,fq,tdate,open,close,high,low,cjl,cje,hsl
  1分钟:          code,tdate,open,close,high,low,cjl,cje,cjjj

使用方式:
    # 全量导入（所有频率，不复权）
    py -3 scripts/import_waizaowang.py

    # 只导入5分钟数据
    py -3 scripts/import_waizaowang.py --freq 5

    # 前复权
    py -3 scripts/import_waizaowang.py --fq 2

    # 只统计不导入
    py -3 scripts/import_waizaowang.py --dry-run

    # 指定数据目录
    py -3 scripts/import_waizaowang.py --source-dir "D:\\data\\财经数据"
"""

import argparse
import io
import logging
import os
import sys
import time
import zipfile
from pathlib import Path

import pandas as pd

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.data.pg_storage import MinuteKlineDB

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# waizaowang 频率目录 → 系统频率映射
FREQ_DIR_MAP = {
    "1":  "一分钟K线数据",
    "5":  "五分钟K线数据",
    "15": "十五分钟K线数据",
    "30": "三十分钟K线数据",
    "60": "六十分钟K线数据",
}

# 默认数据目录
DEFAULT_SOURCE_DIR = r"E:\BaiduNetdiskDownload\财经数据"


def decode_zip_filename(raw: bytes) -> str:
    """尝试 GBK → UTF-8 解码 zip 内文件名。"""
    for enc in ("gbk", "utf-8", "cp437"):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, AttributeError):
            continue
    return raw.decode("utf-8", errors="replace")


def parse_csv_5min(raw_bytes: bytes, fq_filter: float) -> pd.DataFrame:
    """解析 5/15/30/60 分钟 CSV。

    两种格式:
    - 12列(202108~202202): code,name,ktype,fq,tdate,open,close,high,low,cjl,cje,hsl
    - 11列(202203~202302): code,name,ktype,tdate,open,close,high,low,cjl,cje,hsl
    """
    text = raw_bytes.decode("gbk", errors="replace")
    lines = text.strip().splitlines()
    if len(lines) < 2:
        return pd.DataFrame()

    header = lines[0]
    has_fq = "fq" in header

    # 跳过可能的中文 header 行（以引号开头的行）
    data_lines = []
    for line in lines[1:]:
        if line.startswith('"'):
            continue
        data_lines.append(line)

    if not data_lines:
        return pd.DataFrame()

    records = []
    for line in data_lines:
        parts = line.split(",")
        try:
            if has_fq:
                # 12列: code,name,ktype,fq,tdate,...
                if len(parts) < 12:
                    continue
                fq = float(parts[3]) if parts[3] else 0
                if fq != fq_filter:
                    continue
                tdate = parts[4]
                o, c, h, l = float(parts[5]), float(parts[6]), float(parts[7]), float(parts[8])
                vol = int(float(parts[9]))
                amt = float(parts[10])
            else:
                # 11列: code,name,ktype,tdate,...
                if len(parts) < 11:
                    continue
                tdate = parts[3]
                o, c, h, l = float(parts[4]), float(parts[5]), float(parts[6]), float(parts[7])
                vol = int(float(parts[8]))
                amt = float(parts[9])

            code = parts[0]
            records.append({
                "code": code,
                "datetime": tdate,
                "open": o,
                "close": c,
                "high": h,
                "low": l,
                "volume": vol,
                "amount": amt,
            })
        except (ValueError, IndexError):
            continue

    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)
    df["date"] = pd.to_datetime(df["datetime"]).dt.date
    return df


def parse_csv_1min(raw_bytes: bytes) -> pd.DataFrame:
    """解析 1 分钟 CSV（无 name/ktype/fq 列）。

    列: code,tdate,open,close,high,low,cjl,cje,cjjj
    """
    text = raw_bytes.decode("gbk", errors="replace")
    lines = text.strip().splitlines()
    if len(lines) < 2:
        return pd.DataFrame()

    # 跳过中文 header 行
    data_lines = []
    for line in lines[1:]:
        if line.startswith('"'):
            continue
        data_lines.append(line)

    if not data_lines:
        return pd.DataFrame()

    records = []
    for line in data_lines:
        parts = line.split(",")
        if len(parts) < 9:
            continue
        code = parts[0]
        tdate = parts[1]
        try:
            records.append({
                "code": code,
                "datetime": tdate,
                "open": float(parts[2]),
                "close": float(parts[3]),
                "high": float(parts[4]),
                "low": float(parts[5]),
                "volume": int(float(parts[6])),
                "amount": float(parts[7]),
            })
        except (ValueError, IndexError):
            continue

    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)
    df["date"] = pd.to_datetime(df["datetime"]).dt.date
    return df


def is_stock_file(filename: str) -> bool:
    """判断是否为个股文件（_1_ 后缀），排除指数（_10_）等。"""
    # 文件名格式: 600000_浦发银行_1_外网(www.waizaowang.com).csv
    # 或: 000001_上证指数_10_外网(www.waizaowang).csv
    parts = filename.rsplit("_", 2)
    if len(parts) >= 3:
        suffix = parts[-2]
        return suffix == "1"
    return False


def extract_code_from_filename(filename: str) -> str:
    """从文件名提取股票代码。"""
    base = os.path.basename(filename)
    return base.split("_")[0]


def import_one_zip(db, zip_path: str, freq: str,
                   fq_filter: float, source_tag: str,
                   dry_run: bool = False) -> dict:
    """导入单个 zip 文件。

    Returns:
        {files, rows, codes} 统计
    """
    zip_name = os.path.basename(zip_path)
    parse_errors = 0
    total_rows = 0
    total_codes = 0
    file_count = 0

    # 批量写入缓冲
    batch_dfs = []
    batch_size_rows = 500_000  # 每批最多 50 万行

    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            # Python zipfile 把 GBK 文件名按 cp437 解码了，需要反转
            try:
                decoded = info.filename.encode("cp437").decode("gbk")
            except (UnicodeEncodeError, UnicodeDecodeError):
                decoded = info.filename

            if not decoded.endswith(".csv"):
                continue
            if not is_stock_file(decoded):
                continue

            file_count += 1
            try:
                raw = zf.read(info.filename)
                if freq == "1":
                    df = parse_csv_1min(raw)
                else:
                    df = parse_csv_5min(raw, fq_filter)

                if not df.empty:
                    df["source"] = source_tag
                    batch_dfs.append(df)
                    total_rows += len(df)
                    total_codes += 1

                # 达到批量阈值时写入
                if not dry_run and batch_dfs:
                    buf_rows = sum(len(d) for d in batch_dfs)
                    if buf_rows >= batch_size_rows:
                        merged = pd.concat(batch_dfs, ignore_index=True)
                        db.bulk_insert_fast(freq, merged, source=source_tag)
                        batch_dfs = []

            except Exception as e:
                parse_errors += 1
                if parse_errors <= 5:
                    logger.warning(f"  解析失败 {decoded}: {e}")

    logger.info(f"  {zip_name}: {file_count} 个个股文件")

    if dry_run:
        return {"files": file_count, "rows": total_rows, "codes": total_codes}

    # 写入剩余数据
    if batch_dfs:
        merged = pd.concat(batch_dfs, ignore_index=True)
        db.bulk_insert_fast(freq, merged, source=source_tag)

    if parse_errors > 5:
        logger.warning(f"  共 {parse_errors} 个文件解析失败")

    return {"files": file_count, "rows": total_rows, "codes": total_codes}


def main():
    parser = argparse.ArgumentParser(
        description="导入 waizaowang.com 历史分钟K线到 PostgreSQL"
    )
    parser.add_argument(
        "--source-dir", default=DEFAULT_SOURCE_DIR,
        help=f"数据根目录（默认: {DEFAULT_SOURCE_DIR}）"
    )
    parser.add_argument(
        "--freq", default="",
        help="频率过滤，逗号分隔（如 '5,15'），默认全部"
    )
    parser.add_argument(
        "--fq", type=float, default=0,
        help="复权方式: 0=不复权, 2=前复权（默认: 0）"
    )
    parser.add_argument(
        "--skip-completed", action="store_true",
        help="跳过已导入的代码"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="只统计不导入"
    )
    parser.add_argument(
        "--db-url", default="postgresql://postgres@localhost:5432/quant_minute",
        help="PostgreSQL 连接 URL"
    )
    args = parser.parse_args()

    source_dir = Path(args.source_dir)
    if not source_dir.exists():
        logger.error(f"数据目录不存在: {source_dir}")
        sys.exit(1)

    # 确定要导入的频率
    freqs = []
    if args.freq:
        freqs = [f.strip() for f in args.freq.split(",")]
    else:
        freqs = list(FREQ_DIR_MAP.keys())

    source_tag = "waizaowang"

    logger.info(f"数据目录: {source_dir}")
    logger.info(f"导入频率: {freqs}")
    logger.info(f"复权方式: {'不复权' if args.fq == 0 else '前复权'}")
    logger.info(f"Dry run: {args.dry_run}")

    if not args.dry_run:
        db = MinuteKlineDB(args.db_url)
        # waizaowang 数据范围: 2021-08 ~ 2023-02
        db.ensure_partitions("5", "2021-08-01", "2023-02-28")
        db.ensure_partitions("15", "2021-08-01", "2023-02-28")
        db.ensure_partitions("30", "2021-08-01", "2023-02-28")
        db.ensure_partitions("60", "2021-08-01", "2023-02-28")
    else:
        db = None

    grand_total = 0
    start_time = time.time()

    for freq in freqs:
        if freq == "1":
            logger.info("跳过1分钟数据（当前无对应分区表）")
            continue

        dir_name = FREQ_DIR_MAP.get(freq)
        if not dir_name:
            logger.warning(f"未知频率: {freq}")
            continue

        freq_dir = source_dir / dir_name
        if not freq_dir.exists():
            logger.warning(f"目录不存在: {freq_dir}")
            continue

        zip_files = sorted([
            f for f in os.listdir(freq_dir) if f.endswith(".zip")
        ])
        logger.info(f"\n{'='*60}")
        logger.info(f"频率 {freq}分钟: {len(zip_files)} 个zip文件")
        logger.info(f"{'='*60}")

        for zip_name in zip_files:
            zip_path = str(freq_dir / zip_name)
            zip_start = time.time()

            stats = import_one_zip(
                db, zip_path, freq, args.fq, source_tag,
                dry_run=args.dry_run,
            )

            elapsed = time.time() - zip_start
            total = stats.get("rows", 0)
            codes = stats.get("codes", 0)
            grand_total += total
            logger.info(
                f"  {zip_name}: {codes} 只股票, "
                f"{total} 行, {elapsed:.1f}s"
            )

    total_time = time.time() - start_time
    logger.info(f"\n{'='*60}")
    logger.info(
        f"导入完成: {grand_total} 行, "
        f"总耗时 {total_time:.1f}s ({total_time/60:.1f}分钟)"
    )


if __name__ == "__main__":
    main()
