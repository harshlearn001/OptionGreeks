from __future__ import annotations

from dataclasses import dataclass
from math import erf, exp, log, pi, sqrt


SQRT_2 = sqrt(2.0)
SQRT_2PI = sqrt(2.0 * pi)


@dataclass(frozen=True)
class Greeks:
    implied_vol: float | None
    delta: float | None
    gamma: float | None
    theta: float | None
    vega: float | None
    rho: float | None
    vanna: float | None
    charm: float | None
    vomma: float | None
    speed: float | None
    color: float | None
    zomma: float | None
    ultima: float | None


def norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + erf(x / SQRT_2))


def norm_pdf(x: float) -> float:
    return exp(-0.5 * x * x) / SQRT_2PI


def _d1_d2(spot: float, strike: float, time_years: float, rate: float, dividend: float, vol: float) -> tuple[float, float]:
    vol_sqrt_t = vol * sqrt(time_years)
    d1 = (log(spot / strike) + (rate - dividend + 0.5 * vol * vol) * time_years) / vol_sqrt_t
    d2 = d1 - vol_sqrt_t
    return d1, d2


def black_scholes_price(
    spot: float,
    strike: float,
    time_years: float,
    rate: float,
    dividend: float,
    vol: float,
    option_type: str,
) -> float:
    d1, d2 = _d1_d2(spot, strike, time_years, rate, dividend, vol)
    df_r = exp(-rate * time_years)
    df_q = exp(-dividend * time_years)
    opt = option_type.upper()

    if opt == "CE":
        return spot * df_q * norm_cdf(d1) - strike * df_r * norm_cdf(d2)
    if opt == "PE":
        return strike * df_r * norm_cdf(-d2) - spot * df_q * norm_cdf(-d1)

    raise ValueError(f"Unsupported option type: {option_type}")


def implied_volatility(
    market_price: float,
    spot: float,
    strike: float,
    time_years: float,
    rate: float,
    dividend: float,
    option_type: str,
    *,
    low: float = 0.0001,
    high: float = 5.0,
    tolerance: float = 0.000001,
    max_iter: int = 100,
) -> float | None:
    if market_price <= 0 or spot <= 0 or strike <= 0 or time_years <= 0:
        return None

    opt = option_type.upper()
    df_r = exp(-rate * time_years)
    df_q = exp(-dividend * time_years)
    intrinsic = max(spot * df_q - strike * df_r, 0.0) if opt == "CE" else max(strike * df_r - spot * df_q, 0.0)

    if market_price < intrinsic - 0.01:
        return None

    low_price = black_scholes_price(spot, strike, time_years, rate, dividend, low, opt)
    high_price = black_scholes_price(spot, strike, time_years, rate, dividend, high, opt)

    if market_price < low_price - 0.01 or market_price > high_price + 0.01:
        return None

    lo = low
    hi = high
    for _ in range(max_iter):
        mid = (lo + hi) / 2.0
        price = black_scholes_price(spot, strike, time_years, rate, dividend, mid, opt)

        if abs(price - market_price) <= tolerance:
            return mid

        if price > market_price:
            hi = mid
        else:
            lo = mid

    return (lo + hi) / 2.0


def calculate_greeks(
    market_price: float,
    spot: float,
    strike: float,
    time_years: float,
    rate: float,
    dividend: float,
    option_type: str,
) -> Greeks:
    vol = implied_volatility(market_price, spot, strike, time_years, rate, dividend, option_type)
    if vol is None:
        return Greeks(None, None, None, None, None, None, None, None, None, None, None, None, None)

    d1, d2 = _d1_d2(spot, strike, time_years, rate, dividend, vol)
    df_r = exp(-rate * time_years)
    df_q = exp(-dividend * time_years)
    pdf_d1 = norm_pdf(d1)
    opt = option_type.upper()
    sqrt_t = sqrt(time_years)
    vol_sqrt_t = vol * sqrt_t

    gamma = df_q * pdf_d1 / (spot * vol_sqrt_t)
    raw_vega = spot * df_q * pdf_d1 * sqrt_t
    vega = raw_vega / 100.0
    vanna = -df_q * pdf_d1 * d2 / vol / 100.0
    vomma = raw_vega * d1 * d2 / vol / 10000.0
    speed = -gamma / spot * (d1 / vol_sqrt_t + 1.0)
    color = (
        -df_q
        * pdf_d1
        / (2.0 * spot * time_years * vol_sqrt_t)
        * (
            2.0 * dividend * time_years
            + 1.0
            + (2.0 * (rate - dividend) * time_years - d2 * vol_sqrt_t) * d1 / vol_sqrt_t
        )
    ) / 365.0
    zomma = gamma * (d1 * d2 - 1.0) / vol
    ultima = (
        -raw_vega
        / (vol * vol)
        * (d1 * d2 * (1.0 - d1 * d2) + d1 * d1 + d2 * d2)
    ) / 1000000.0

    if opt == "CE":
        delta = df_q * norm_cdf(d1)
        theta = (
            -spot * df_q * pdf_d1 * vol / (2.0 * sqrt_t)
            - rate * strike * df_r * norm_cdf(d2)
            + dividend * spot * df_q * norm_cdf(d1)
        ) / 365.0
        charm = (
            -dividend * df_q * norm_cdf(d1)
            + df_q * pdf_d1 * (2.0 * (rate - dividend) * time_years - d2 * vol_sqrt_t) / (2.0 * time_years * vol_sqrt_t)
        ) / 365.0
        rho = strike * time_years * df_r * norm_cdf(d2) / 100.0
    elif opt == "PE":
        delta = -df_q * norm_cdf(-d1)
        theta = (
            -spot * df_q * pdf_d1 * vol / (2.0 * sqrt_t)
            + rate * strike * df_r * norm_cdf(-d2)
            - dividend * spot * df_q * norm_cdf(-d1)
        ) / 365.0
        charm = (
            dividend * df_q * norm_cdf(-d1)
            + df_q * pdf_d1 * (2.0 * (rate - dividend) * time_years - d2 * vol_sqrt_t) / (2.0 * time_years * vol_sqrt_t)
        ) / 365.0
        rho = -strike * time_years * df_r * norm_cdf(-d2) / 100.0
    else:
        return Greeks(vol, None, None, None, None, None, None, None, None, None, None, None, None)

    return Greeks(vol, delta, gamma, theta, vega, rho, vanna, charm, vomma, speed, color, zomma, ultima)
