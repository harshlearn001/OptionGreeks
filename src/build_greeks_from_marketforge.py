from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

from black_scholes import calculate_greeks


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MARKETFORGE_ROOT = Path(r"H:\MarketForge")
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "data" / "greeks"

INDEX_SPOT_SYMBOL_ALIASES = {
    "NIFTYNXT50": "NIFTYNEXT50",
}

STOCK_SPOT_SYMBOL_ALIASES = {
    "AMARAJABAT": "ARE&M",
    "CADILAHC": "ZYDUSLIFE",
    "GMRINFRA": "GMRAIRPORT",
    "IBULHSGFIN": "SAMMAANCAP",
    "L&TFH": "LTF",
    "LTI": "LTIM",
    "MCDOWELL-N": "UNITDSPR",
    "MINDTREE": "LTIM",
    "MOTHERSUMI": "MOTHERSON",
    "PVR": "PVRINOX",
    "SRTRANSFIN": "SHRIRAMFIN",
    "TATAMOTORS": "TMPV",
    "ZOMATO": "ETERNAL",
}


def yyyymmdd_to_datetime(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series.astype("Int64").astype(str), format="%Y%m%d", errors="coerce")


def load_spot_series(marketforge_root: Path, segment: str, symbol: str) -> pd.DataFrame:
    if segment == "INDICES":
        spot_symbol = INDEX_SPOT_SYMBOL_ALIASES.get(symbol, symbol)
        spot_file = marketforge_root / "data" / "master" / "Indices_master" / f"{spot_symbol}.csv"
        date_col = "TRADE_DATE"
    else:
        spot_symbol = STOCK_SPOT_SYMBOL_ALIASES.get(symbol, symbol)
        spot_file = marketforge_root / "data" / "master" / "Equity_stock_master" / f"{spot_symbol}.csv"
        date_col = "DATE"

    if not spot_file.exists():
        raise FileNotFoundError(f"Spot file not found: {spot_file}")

    spot = pd.read_csv(spot_file, low_memory=False)
    spot.columns = spot.columns.astype(str).str.strip().str.upper()

    if date_col not in spot.columns or "CLOSE" not in spot.columns:
        raise RuntimeError(f"Spot file must contain {date_col} and CLOSE: {spot_file}")

    if date_col == "TRADE_DATE":
        spot_date = yyyymmdd_to_datetime(pd.to_numeric(spot[date_col], errors="coerce"))
    else:
        spot_date = pd.to_datetime(spot[date_col], errors="coerce")

    out = pd.DataFrame(
        {
            "TRADE_DT": spot_date,
            "SPOT_CLOSE": pd.to_numeric(spot["CLOSE"], errors="coerce"),
        }
    )
    return out.dropna(subset=["TRADE_DT", "SPOT_CLOSE"]).drop_duplicates("TRADE_DT", keep="last")


def load_options(marketforge_root: Path, segment: str, symbol: str) -> pd.DataFrame:
    option_file = marketforge_root / "data" / "master" / "option_master" / segment / f"{symbol}.csv"
    if not option_file.exists():
        raise FileNotFoundError(f"Option master not found: {option_file}")

    opt = pd.read_csv(option_file, low_memory=False)
    opt.columns = opt.columns.astype(str).str.strip().str.upper()

    required = {"TRADE_DATE", "EXP_DATE", "STRIKE_PRICE", "OPT_TYPE", "CLOSE_PRICE"}
    missing = required - set(opt.columns)
    if missing:
        raise RuntimeError(f"Missing option columns in {option_file}: {sorted(missing)}")

    opt["TRADE_DT"] = yyyymmdd_to_datetime(pd.to_numeric(opt["TRADE_DATE"], errors="coerce"))
    opt["EXP_DT"] = yyyymmdd_to_datetime(pd.to_numeric(opt["EXP_DATE"], errors="coerce"))
    opt["STRIKE_PRICE"] = pd.to_numeric(opt["STRIKE_PRICE"], errors="coerce")
    opt["CLOSE_PRICE"] = pd.to_numeric(opt["CLOSE_PRICE"], errors="coerce")
    opt["OPT_TYPE"] = opt["OPT_TYPE"].astype(str).str.strip().str.upper()

    return opt.dropna(subset=["TRADE_DT", "EXP_DT", "STRIKE_PRICE", "CLOSE_PRICE"])


def enrich_with_greeks(options: pd.DataFrame, spot: pd.DataFrame, rate: float, dividend: float) -> pd.DataFrame:
    df = options.merge(spot, on="TRADE_DT", how="left")
    df["DAYS_TO_EXPIRY"] = (df["EXP_DT"] - df["TRADE_DT"]).dt.days
    df["TIME_TO_EXPIRY"] = df["DAYS_TO_EXPIRY"] / 365.0
    df["RISK_FREE_RATE"] = rate
    df["DIVIDEND_YIELD"] = dividend

    greek_rows: list[tuple[float | None, ...]] = []

    for row in df.itertuples(index=False):
        if (
            pd.isna(row.SPOT_CLOSE)
            or pd.isna(row.STRIKE_PRICE)
            or pd.isna(row.CLOSE_PRICE)
            or pd.isna(row.TIME_TO_EXPIRY)
            or row.TIME_TO_EXPIRY <= 0
            or row.OPT_TYPE not in {"CE", "PE"}
        ):
            greek_rows.append((None, None, None, None, None, None, None, None, None, None, None, None, None))
            continue

        greeks = calculate_greeks(
            market_price=float(row.CLOSE_PRICE),
            spot=float(row.SPOT_CLOSE),
            strike=float(row.STRIKE_PRICE),
            time_years=float(row.TIME_TO_EXPIRY),
            rate=rate,
            dividend=dividend,
            option_type=str(row.OPT_TYPE),
        )
        greek_rows.append(
            (
                greeks.implied_vol,
                greeks.delta,
                greeks.gamma,
                greeks.theta,
                greeks.vega,
                greeks.rho,
                greeks.vanna,
                greeks.charm,
                greeks.vomma,
                greeks.speed,
                greeks.color,
                greeks.zomma,
                greeks.ultima,
            )
        )

    greek_cols = [
        "IMPLIED_VOL",
        "DELTA",
        "GAMMA",
        "THETA",
        "VEGA",
        "RHO",
        "VANNA",
        "CHARM",
        "VOMMA",
        "SPEED",
        "COLOR",
        "ZOMMA",
        "ULTIMA",
    ]
    df[greek_cols] = pd.DataFrame(greek_rows, index=df.index)

    df = df.replace({np.nan: None})
    return df.drop(columns=["TRADE_DT", "EXP_DT"])


def discover_symbols(marketforge_root: Path, segment: str) -> list[str]:
    option_dir = marketforge_root / "data" / "master" / "option_master" / segment
    if not option_dir.exists():
        raise FileNotFoundError(f"Option segment directory not found: {option_dir}")
    return sorted(path.stem for path in option_dir.glob("*.csv"))


def build_symbol(
    marketforge_root: Path,
    output_root: Path,
    segment: str,
    symbol: str,
    rate: float,
    dividend: float,
) -> Path:
    options = load_options(marketforge_root, segment, symbol)
    spot = load_spot_series(marketforge_root, segment, symbol)
    enriched = enrich_with_greeks(options, spot, rate, dividend)

    out_dir = output_root / segment
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{symbol}.csv"
    enriched.to_csv(out_file, index=False)
    return out_file


def build_symbol_worker(args: tuple[Path, Path, str, str, float, float]) -> tuple[str, Path]:
    marketforge_root, output_root, segment, symbol, rate, dividend = args
    return symbol, build_symbol(marketforge_root, output_root, segment, symbol, rate, dividend)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build option Greeks from MarketForge option masters.")
    parser.add_argument("--marketforge-root", type=Path, default=DEFAULT_MARKETFORGE_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--segment", choices=["STOCKS", "INDICES"], required=True)
    parser.add_argument("--symbol", help="Optional symbol. If omitted, all symbols in the segment are processed.")
    parser.add_argument("--risk-free-rate", type=float, default=0.06)
    parser.add_argument("--dividend-yield", type=float, default=0.0)
    parser.add_argument("--allow-failures", action="store_true", help="Exit successfully even if some symbols fail.")
    parser.add_argument("--jobs", type=int, default=1, help="Parallel symbol workers. Default: 1")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    symbols = [args.symbol.upper()] if args.symbol else discover_symbols(args.marketforge_root, args.segment)

    print("OptionGreeks build started")
    print(f"MarketForge root : {args.marketforge_root}")
    print(f"Output root      : {args.output_root}")
    print(f"Segment          : {args.segment}")
    print(f"Symbols          : {len(symbols)}")
    print(f"Jobs             : {args.jobs}")

    built = 0
    failed = 0
    jobs = max(1, args.jobs)
    tasks = [
        (args.marketforge_root, args.output_root, args.segment, symbol, args.risk_free_rate, args.dividend_yield)
        for symbol in symbols
    ]

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
    if failed and not args.allow_failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
