from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MARKETFORGE_ROOT = Path(r"H:\MarketForge")
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "data" / "hv"
DEFAULT_WINDOWS = [10, 20, 30, 60, 90, 252]
EXCLUDED_MASTER_FILES = {"equity_mto_master"}


def load_spot_file(path: Path, segment: str) -> pd.DataFrame:
    df = pd.read_csv(path, low_memory=False)
    df.columns = df.columns.astype(str).str.strip().str.upper()

    date_col = "TRADE_DATE" if segment == "INDICES" else "DATE"
    required = {date_col, "SYMBOL", "CLOSE"}
    missing = required - set(df.columns)
    if missing:
        raise RuntimeError(f"Missing columns in {path}: {sorted(missing)}")

    if date_col == "TRADE_DATE":
        trade_date = pd.to_datetime(
            pd.to_numeric(df[date_col], errors="coerce").astype("Int64").astype(str),
            format="%Y%m%d",
            errors="coerce",
        )
    else:
        trade_date = pd.to_datetime(df[date_col], errors="coerce")

    out = pd.DataFrame(
        {
            "TRADE_DATE": trade_date,
            "SYMBOL": df["SYMBOL"].astype(str).str.strip(),
            "CLOSE": pd.to_numeric(df["CLOSE"], errors="coerce"),
        }
    )
    return out.dropna(subset=["TRADE_DATE", "CLOSE"]).sort_values("TRADE_DATE")


def calculate_hv(df: pd.DataFrame, windows: list[int]) -> pd.DataFrame:
    out = df.copy()
    out["LOG_RETURN"] = np.log(out["CLOSE"] / out["CLOSE"].shift(1))

    for window in windows:
        col = f"HV_{window}"
        out[col] = out["LOG_RETURN"].rolling(window=window, min_periods=window).std() * np.sqrt(252)

    out["TRADE_DATE"] = out["TRADE_DATE"].dt.strftime("%Y%m%d").astype("Int64")
    return out


def source_dir(marketforge_root: Path, segment: str) -> Path:
    if segment == "INDICES":
        return marketforge_root / "data" / "master" / "Indices_master"
    return marketforge_root / "data" / "master" / "Equity_stock_master"


def discover_symbols(marketforge_root: Path, segment: str) -> list[str]:
    src = source_dir(marketforge_root, segment)
    if not src.exists():
        raise FileNotFoundError(f"Source directory not found: {src}")
    return sorted(path.stem for path in src.glob("*.csv") if path.stem not in EXCLUDED_MASTER_FILES)


def build_symbol(
    marketforge_root: Path,
    output_root: Path,
    segment: str,
    symbol: str,
    windows: list[int],
) -> Path:
    src_file = source_dir(marketforge_root, segment) / f"{symbol}.csv"
    if not src_file.exists():
        raise FileNotFoundError(f"Spot file not found: {src_file}")

    spot = load_spot_file(src_file, segment)
    hv = calculate_hv(spot, windows)

    out_dir = output_root / segment
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{symbol}.csv"
    hv.to_csv(out_file, index=False)
    return out_file


def build_symbol_worker(args: tuple[Path, Path, str, str, list[int]]) -> tuple[str, Path]:
    marketforge_root, output_root, segment, symbol, windows = args
    return symbol, build_symbol(marketforge_root, output_root, segment, symbol, windows)


def parse_windows(value: str) -> list[int]:
    windows = [int(x.strip()) for x in value.split(",") if x.strip()]
    if not windows or any(x <= 1 for x in windows):
        raise argparse.ArgumentTypeError("Windows must be comma-separated integers greater than 1.")
    return windows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build historical volatility from MarketForge spot masters.")
    parser.add_argument("--marketforge-root", type=Path, default=DEFAULT_MARKETFORGE_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--segment", choices=["STOCKS", "INDICES"], required=True)
    parser.add_argument("--symbol", help="Optional symbol. If omitted, all symbols in the segment are processed.")
    parser.add_argument("--windows", type=parse_windows, default=DEFAULT_WINDOWS, help="Comma-separated windows. Default: 10,20,30,60,90,252")
    parser.add_argument("--jobs", type=int, default=1, help="Parallel symbol workers. Default: 1")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    symbols = [args.symbol.upper()] if args.symbol else discover_symbols(args.marketforge_root, args.segment)

    print("OptionGreeks HV build started")
    print(f"MarketForge root : {args.marketforge_root}")
    print(f"Output root      : {args.output_root}")
    print(f"Segment          : {args.segment}")
    print(f"Windows          : {args.windows}")
    print(f"Symbols          : {len(symbols)}")
    print(f"Jobs             : {args.jobs}")

    built = 0
    failed = 0
    jobs = max(1, args.jobs)
    tasks = [(args.marketforge_root, args.output_root, args.segment, symbol, args.windows) for symbol in symbols]

    if jobs == 1 or len(tasks) <= 1:
        for task in tasks:
            symbol = task[3]
            try:
                _, out_file = build_symbol_worker(task)
                built += 1
                print(f"[OK] {symbol} -> {out_file}")
            except Exception as exc:
                failed += 1
                print(f"[FAILED] {symbol}: {exc}")
    else:
        with ProcessPoolExecutor(max_workers=jobs) as executor:
            futures = {executor.submit(build_symbol_worker, task): task[3] for task in tasks}
            for future in as_completed(futures):
                symbol = futures[future]
                try:
                    _, out_file = future.result()
                    built += 1
                    print(f"[OK] {symbol} -> {out_file}")
                except Exception as exc:
                    failed += 1
                    print(f"[FAILED] {symbol}: {exc}")

    print("")
    print(f"Completed. Built: {built}, Failed: {failed}")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
