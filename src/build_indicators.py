from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GREEKS_ROOT = PROJECT_ROOT / "data" / "greeks"
DEFAULT_HV_ROOT = PROJECT_ROOT / "data" / "hv"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "data" / "indicators"
DEFAULT_WINDOWS = [252]

INDEX_HV_SYMBOL_ALIASES = {
    "NIFTYNXT50": "NIFTYNEXT50",
}

STOCK_HV_SYMBOL_ALIASES = {
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


def parse_windows(value: str) -> list[int]:
    windows = [int(x.strip()) for x in value.split(",") if x.strip()]
    if not windows or any(x <= 1 for x in windows):
        raise argparse.ArgumentTypeError("Windows must be comma-separated integers greater than 1.")
    return windows


def hv_symbol_for(segment: str, symbol: str) -> str:
    if segment == "INDICES":
        return INDEX_HV_SYMBOL_ALIASES.get(symbol, symbol)
    return STOCK_HV_SYMBOL_ALIASES.get(symbol, symbol)


def discover_symbols(greeks_root: Path, segment: str) -> list[str]:
    src = greeks_root / segment
    if not src.exists():
        raise FileNotFoundError(f"Greeks directory not found: {src}")
    return sorted(path.stem for path in src.glob("*.csv"))


def rolling_percentile(series: pd.Series, window: int) -> pd.Series:
    def percentile(values: np.ndarray) -> float:
        current = values[-1]
        history = values[:-1]
        history = history[~np.isnan(history)]
        if np.isnan(current) or len(history) == 0:
            return np.nan
        return float((history <= current).sum() / len(history) * 100.0)

    return series.rolling(window=window + 1, min_periods=2).apply(percentile, raw=True)


def rolling_rank(series: pd.Series, window: int) -> pd.Series:
    roll_min = series.shift(1).rolling(window=window, min_periods=2).min()
    roll_max = series.shift(1).rolling(window=window, min_periods=2).max()
    denom = roll_max - roll_min
    return ((series - roll_min) / denom.replace(0, np.nan) * 100.0).clip(0, 100)


def load_greeks(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, low_memory=False)
    df.columns = df.columns.astype(str).str.strip().str.upper()

    required = {"TRADE_DATE", "SYMBOL", "EXP_DATE", "STRIKE_PRICE", "OPT_TYPE", "SPOT_CLOSE", "IMPLIED_VOL"}
    missing = required - set(df.columns)
    if missing:
        raise RuntimeError(f"Missing Greeks columns in {path}: {sorted(missing)}")

    optional_numeric_cols = [
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
    for col in optional_numeric_cols:
        if col not in df.columns:
            df[col] = np.nan

    numeric_cols = [
        "TRADE_DATE",
        "EXP_DATE",
        "STRIKE_PRICE",
        "CLOSE_PRICE",
        "SPOT_CLOSE",
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
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df["SYMBOL"] = df["SYMBOL"].astype(str).str.strip()
    df["OPT_TYPE"] = df["OPT_TYPE"].astype(str).str.strip().str.upper()
    return df


def load_hv(hv_root: Path, segment: str, symbol: str) -> pd.DataFrame:
    hv_symbol = hv_symbol_for(segment, symbol)
    hv_file = hv_root / segment / f"{hv_symbol}.csv"

    if not hv_file.exists():
        raise FileNotFoundError(f"HV file not found: {hv_file}")

    hv = pd.read_csv(hv_file, low_memory=False)
    hv.columns = hv.columns.astype(str).str.strip().str.upper()

    # Keep only required columns
    keep_cols = [
        "TRADE_DATE",
        "CLOSE",
        "HV_10",
        "HV_20",
        "HV_30",
        "HV_60",
        "HV_90",
        "HV_252",
    ]
    keep_cols = [c for c in keep_cols if c in hv.columns]

    hv = hv[keep_cols].copy()

    # Rename CLOSE to UNDERLYING_CLOSE
    hv.rename(columns={"CLOSE": "UNDERLYING_CLOSE"}, inplace=True)

    # Convert numeric columns
    numeric_cols = [
        "UNDERLYING_CLOSE",
        "HV_10",
        "HV_20",
        "HV_30",
        "HV_60",
        "HV_90",
        "HV_252",
    ]

    for col in numeric_cols:
        if col in hv.columns:
            hv[col] = pd.to_numeric(hv[col], errors="coerce")

    # Remove duplicate trade dates
    hv = hv.drop_duplicates(subset="TRADE_DATE", keep="last")

    return hv


def add_row_indicators(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()

    # Prevent divide-by-zero
    out["MONEYNESS"] = out["STRIKE_PRICE"] / out["SPOT_CLOSE"].replace(0, np.nan)

    out["MONEYNESS_PCT"] = (out["MONEYNESS"] - 1.0) * 100.0
    out["ABS_MONEYNESS_PCT"] = out["MONEYNESS_PCT"].abs()

    hv_columns = [
        "HV_10",
        "HV_20",
        "HV_30",
        "HV_60",
        "HV_90",
        "HV_252",
    ]

    for hv_col in hv_columns:
        if hv_col not in out.columns:
            continue

        suffix = hv_col.replace("HV_", "")

        # IV - HV
        out[f"IV_MINUS_HV_{suffix}"] = out["IMPLIED_VOL"] - out[hv_col]

        # IV / HV
        out[f"IV_HV_RATIO_{suffix}"] = (
            out["IMPLIED_VOL"] /
            out[hv_col].replace(0, np.nan)
        )

    return out


def build_daily_summary(option_rows: pd.DataFrame, windows: list[int]) -> pd.DataFrame:
    valid = option_rows.dropna(subset=["IMPLIED_VOL", "TRADE_DATE"]).copy()

    if valid.empty:
        return pd.DataFrame()

    # Prefer ATM options (±3% moneyness)
    atm = valid[valid["ABS_MONEYNESS_PCT"] <= 3.0].copy()
    source = atm if not atm.empty else valid

    daily = (
        source.groupby(["TRADE_DATE", "SYMBOL"], as_index=False)
        .agg(
            ATM_IV=("IMPLIED_VOL", "median"),
            ATM_IV_CE=(
                "IMPLIED_VOL",
                lambda s: s[source.loc[s.index, "OPT_TYPE"].eq("CE")].median(),
            ),
            ATM_IV_PE=(
                "IMPLIED_VOL",
                lambda s: s[source.loc[s.index, "OPT_TYPE"].eq("PE")].median(),
            ),
            MEDIAN_DELTA=("DELTA", "median"),
            MEDIAN_THETA=("THETA", "median"),
            MEDIAN_VEGA=("VEGA", "median"),
            MEDIAN_VANNA=("VANNA", "median"),
            MEDIAN_CHARM=("CHARM", "median"),
            MEDIAN_VOMMA=("VOMMA", "median"),
            MEDIAN_SPEED=("SPEED", "median"),
            MEDIAN_COLOR=("COLOR", "median"),
            MEDIAN_ZOMMA=("ZOMMA", "median"),
            MEDIAN_ULTIMA=("ULTIMA", "median"),
            OPTION_ROWS=("IMPLIED_VOL", "size"),
        )
        .sort_values("TRADE_DATE")
    )

    # --------------------------------------------------
    # Merge Historical Volatility
    # --------------------------------------------------

    hv_cols = [
        "UNDERLYING_CLOSE",
        "HV_10",
        "HV_20",
        "HV_30",
        "HV_60",
        "HV_90",
        "HV_252",
    ]

    available_cols = [
        "TRADE_DATE",
        "SYMBOL",
        *[c for c in hv_cols if c in option_rows.columns],
    ]

    hv_daily = (
        option_rows[available_cols]
        .drop_duplicates(["TRADE_DATE", "SYMBOL"])
    )

    daily = daily.merge(
        hv_daily,
        on=["TRADE_DATE", "SYMBOL"],
        how="left",
    )

    # --------------------------------------------------
    # IV - HV
    # --------------------------------------------------

    daily["IV_MINUS_HV_20"] = daily["ATM_IV"] - daily["HV_20"]

    daily["IV_MINUS_HV_30"] = daily["ATM_IV"] - daily["HV_30"]

    daily["IV_HV_RATIO_20"] = (
        daily["ATM_IV"] /
        daily["HV_20"].replace(0, np.nan)
    )

    daily["IV_HV_RATIO_30"] = (
        daily["ATM_IV"] /
        daily["HV_30"].replace(0, np.nan)
    )

    # --------------------------------------------------
    # IV Percentile / IV Rank
    # --------------------------------------------------

    for window in windows:
        daily[f"IVP_{window}"] = rolling_percentile(
            daily["ATM_IV"],
            window,
        )

        daily[f"IVR_{window}"] = rolling_rank(
            daily["ATM_IV"],
            window,
        )

    # --------------------------------------------------
    # FRV Score
    # --------------------------------------------------

    ratio_window = windows[0]

    daily[f"IVHV_RATIO_PCTL_{ratio_window}"] = rolling_percentile(
        daily["IV_HV_RATIO_20"],
        ratio_window,
    )

    ratio_score = daily[f"IVHV_RATIO_PCTL_{ratio_window}"]
    ivp_score = daily[f"IVP_{ratio_window}"]
    ivr_score = daily[f"IVR_{ratio_window}"]

    daily["FRV_SCORE"] = (
        0.45 * ratio_score
        + 0.35 * ivp_score
        + 0.20 * ivr_score
    ).clip(0, 100)

    daily["FRV_ZONE"] = pd.cut(
        daily["FRV_SCORE"],
        bins=[-np.inf, 25, 45, 60, 75, np.inf],
        labels=[
            "CHEAP",
            "FAIR_LOW",
            "FAIR",
            "RICH",
            "VERY_RICH",
        ],
    )

    return daily


def build_symbol(
    greeks_root: Path,
    hv_root: Path,
    output_root: Path,
    segment: str,
    symbol: str,
    windows: list[int],
) -> tuple[Path, Path]:
    greek_file = greeks_root / segment / f"{symbol}.csv"
    if not greek_file.exists():
        raise FileNotFoundError(f"Greeks file not found: {greek_file}")

    greeks = load_greeks(greek_file)
    hv = load_hv(hv_root, segment, symbol)
    enriched = add_row_indicators(greeks.merge(hv, on="TRADE_DATE", how="left"))
    summary = build_daily_summary(enriched, windows)

    details_dir = output_root / segment / "details"
    summary_dir = output_root / segment / "daily_summary"
    details_dir.mkdir(parents=True, exist_ok=True)
    summary_dir.mkdir(parents=True, exist_ok=True)

    details_file = details_dir / f"{symbol}.csv"
    summary_file = summary_dir / f"{symbol}.csv"

    enriched.to_csv(details_file, index=False)
    summary.to_csv(summary_file, index=False)
    return details_file, summary_file


def build_symbol_worker(args: tuple[Path, Path, Path, str, str, list[int]]) -> tuple[str, Path, Path]:
    greeks_root, hv_root, output_root, segment, symbol, windows = args
    details_file, summary_file = build_symbol(greeks_root, hv_root, output_root, segment, symbol, windows)
    return symbol, details_file, summary_file


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build IV-HV, IVP, IVR, and FRV indicators from OptionGreeks data.")
    parser.add_argument("--greeks-root", type=Path, default=DEFAULT_GREEKS_ROOT)
    parser.add_argument("--hv-root", type=Path, default=DEFAULT_HV_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--segment", choices=["STOCKS", "INDICES"], required=True)
    parser.add_argument("--symbol", help="Optional symbol. If omitted, all Greeks symbols in the segment are processed.")
    parser.add_argument("--windows", type=parse_windows, default=DEFAULT_WINDOWS, help="Comma-separated IVP/IVR windows. Default: 252")
    parser.add_argument("--jobs", type=int, default=1, help="Parallel symbol workers. Default: 1")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # Get symbols to process
    if args.symbol:
        symbols = [args.symbol.strip().upper()]
    else:
        symbols = discover_symbols(
            args.greeks_root,
            args.segment,
        )

    print("OptionGreeks indicator build started")
    print(f"Greeks root : {args.greeks_root}")
    print(f"HV root     : {args.hv_root}")
    print(f"Output root : {args.output_root}")
    print(f"Segment     : {args.segment}")
    print(f"Windows     : {args.windows}")
    print(f"Symbols     : {len(symbols)}")
    print(f"Jobs        : {args.jobs}")

    built = 0
    failed = 0
    jobs = max(1, args.jobs)

    tasks = [
        (
            args.greeks_root,
            args.hv_root,
            args.output_root,
            args.segment,
            symbol,
            args.windows,
        )
        for symbol in symbols
    ]

    if jobs == 1 or len(tasks) <= 1:
        for task in tasks:
            symbol = task[4]
            try:
                _, details_file, summary_file = build_symbol_worker(task)
                built += 1
                print(f"[OK] {symbol} -> {details_file} | {summary_file}")
            except Exception as exc:
                failed += 1
                print(f"[FAILED] {symbol}: {exc}")
    else:
        with ProcessPoolExecutor(max_workers=jobs) as executor:
            futures = {
                executor.submit(build_symbol_worker, task): task[4]
                for task in tasks
            }

            for future in as_completed(futures):
                symbol = futures[future]
                try:
                    _, details_file, summary_file = future.result()
                    built += 1
                    print(f"[OK] {symbol} -> {details_file} | {summary_file}")
                except Exception as exc:
                    failed += 1
                    print(f"[FAILED] {symbol}: {exc}")

    print()
    print(f"Completed. Built: {built}, Failed: {failed}")

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()