"""
Extract CSV files from Baidu Netdisk RAR archive into data/raw/baidu/
"""
import os
import sys
import time

try:
    import unrar.cffi as unrar_cffi
    from unrar.cffi import rarfile
    USE_CFFI = True
except ImportError:
    USE_CFFI = False

try:
    import rarfile
    USE_RARFILE = True
except ImportError:
    USE_RARFILE = False


RAR_PATH = r"E:\BaiduNetdiskDownload\股票历史日线数据.rar"
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw", "baidu")


def extract_with_cffi():
    """Extract using unrar-cffi (bundles its own unrar library)."""
    from unrar.cffi import rarfile as rf

    print(f"Opening RAR: {RAR_PATH}")
    archive = rf.RarFile(RAR_PATH)
    entries = archive.infolist()
    print(f"Total entries: {len(entries)}")

    os.makedirs(OUT_DIR, exist_ok=True)

    csv_entries = [e for e in entries if e.filename.lower().endswith(".csv")]
    print(f"CSV files to extract: {len(csv_entries)}")

    extracted = 0
    errors = []
    t0 = time.time()

    for i, entry in enumerate(csv_entries):
        fname = os.path.basename(entry.filename)
        if not fname:
            continue
        out_path = os.path.join(OUT_DIR, fname)
        try:
            data = archive.read(entry)
            with open(out_path, "wb") as f:
                f.write(data)
            extracted += 1
        except Exception as e:
            errors.append((fname, str(e)))

        if (i + 1) % 500 == 0:
            elapsed = time.time() - t0
            print(f"  [{i+1}/{len(csv_entries)}] extracted in {elapsed:.1f}s")

    elapsed = time.time() - t0
    print(f"\nDone: {extracted} files extracted in {elapsed:.1f}s")
    if errors:
        print(f"Errors ({len(errors)}):")
        for fname, err in errors[:10]:
            print(f"  {fname}: {err}")
    return extracted, errors


def extract_with_rarfile():
    """Extract using rarfile library (needs external unrar binary)."""
    print(f"Opening RAR: {RAR_PATH}")
    archive = rarfile.RarFile(RAR_PATH)
    entries = archive.namelist()
    print(f"Total entries: {len(entries)}")

    os.makedirs(OUT_DIR, exist_ok=True)

    csv_entries = [e for e in entries if e.lower().endswith(".csv")]
    print(f"CSV files to extract: {len(csv_entries)}")

    extracted = 0
    errors = []
    t0 = time.time()

    for i, entry in enumerate(csv_entries):
        fname = os.path.basename(entry)
        if not fname:
            continue
        out_path = os.path.join(OUT_DIR, fname)
        try:
            data = archive.read(entry)
            with open(out_path, "wb") as f:
                f.write(data)
            extracted += 1
        except Exception as e:
            errors.append((fname, str(e)))

        if (i + 1) % 500 == 0:
            elapsed = time.time() - t0
            print(f"  [{i+1}/{len(csv_entries)}] extracted in {elapsed:.1f}s")

    elapsed = time.time() - t0
    print(f"\nDone: {extracted} files extracted in {elapsed:.1f}s")
    if errors:
        print(f"Errors ({len(errors)}):")
        for fname, err in errors[:10]:
            print(f"  {fname}: {err}")
    return extracted, errors


if __name__ == "__main__":
    if USE_CFFI:
        print("Using unrar-cffi backend")
        extract_with_cffi()
    elif USE_RARFILE:
        print("Using rarfile backend")
        extract_with_rarfile()
    else:
        print("ERROR: No RAR library available. Install unrar-cffi or rarfile.")
        sys.exit(1)
