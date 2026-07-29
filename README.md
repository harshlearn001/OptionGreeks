# OptionGreeks

OptionGreeks is a separate project for calculating historical option Greeks from MarketForge option master data.

It does not modify `H:\MarketForge`.

## Inputs

Default input project:

```text
H:\MarketForge
```

Expected MarketForge inputs:

- `data/master/option_master/STOCKS/*.csv`
- `data/master/option_master/INDICES/*.csv`
- `data/master/Equity_stock_master/*.csv`
- `data/master/Indices_master/*.csv`

## Outputs

Greeks are written here:

```text
H:\OptionGreeks\data\greeks
```

Historical volatility is written here:

```text
H:\OptionGreeks\data\hv
```

IV-HV, IVP, IVR, and FRV indicators are written here:

```text
H:\OptionGreeks\data\indicators
```

Output layout:

```text
data/greeks/
├── STOCKS/
└── INDICES/
```

Each output CSV keeps the original option row and adds:

- `SPOT_CLOSE`
- `DAYS_TO_EXPIRY`
- `TIME_TO_EXPIRY`
- `RISK_FREE_RATE`
- `DIVIDEND_YIELD`
- `IMPLIED_VOL`
- `DELTA`
- `GAMMA`
- `THETA`
- `VEGA`
- `RHO`
- `VANNA`
- `CHARM`
- `VOMMA`
- `SPEED`
- `COLOR`
- `ZOMMA`
- `ULTIMA`

## Run Examples

Calculate Greeks for NIFTY index options:

```powershell
.\scripts\build_greeks.ps1 -Segment INDICES -Symbol NIFTY
```

Calculate Greeks for RELIANCE stock options:

```powershell
.\scripts\build_greeks.ps1 -Segment STOCKS -Symbol RELIANCE
```

Calculate all symbols in one segment:

```powershell
.\scripts\build_greeks.ps1 -Segment INDICES
```

Direct Python usage:

```powershell
python .\src\build_greeks_from_marketforge.py --segment INDICES --symbol NIFTY
```

Build historical volatility for one symbol:

```powershell
.\scripts\build_hv.ps1 -Segment INDICES -Symbol NIFTY
```

Build historical volatility for all stock masters:

```powershell
.\scripts\build_hv.ps1 -Segment STOCKS
```

Build indicators for one symbol:

```powershell
.\scripts\build_indicators.ps1 -Segment INDICES -Symbol NIFTY
```

Build indicators for all symbols in a segment:

```powershell
.\scripts\build_indicators.ps1 -Segment STOCKS
```

Update all Greeks and HV after MarketForge has finished its daily update:

```powershell
.\scripts\daily_update_optiongreeks.ps1
```

The daily updater allows known missing symbols in Greeks builds, then continues to HV and indicators.

## Notes

Greeks are calculated with the Black-Scholes model. Implied volatility is solved from the option `CLOSE_PRICE`.

Default assumptions:

- Risk-free rate: `0.06`
- Dividend yield: `0.00`
- Calendar-day time to expiry: `days / 365`

You can override these from the command line.

Greek scaling:

- `VEGA`, `RHO`, and `VANNA` are scaled for a 1 percentage-point move.
- `VOMMA` is scaled for two 1 percentage-point volatility moves.
- `ULTIMA` is scaled for three 1 percentage-point volatility moves.
- `THETA`, `CHARM`, and `COLOR` are calendar-day values.

HV is annualized from daily log returns using `sqrt(252)`. Default windows are:

- `HV_10`
- `HV_20`
- `HV_30`
- `HV_60`
- `HV_90`
- `HV_252`

Indicators include:

- `IV_MINUS_HV_20`
- `IV_MINUS_HV_30`
- `IV_HV_RATIO_20`
- `IV_HV_RATIO_30`
- `IVP_252`
- `IVR_252`
- `FRV_SCORE`
- `FRV_ZONE`

`FRV_SCORE` is a 0-100 relative-volatility score. Higher values mean IV is richer versus realized volatility and its own recent history.
