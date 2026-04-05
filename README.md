# Nifty & Sensex Short Strangle Trading Algo

This Python-based trading algorithm automates a Short Strangle strategy with hedges for NIFTY and SENSEX using the Zerodha Kite Connect API.

## Core Features
- **Indices Supported:** NIFTY and SENSEX.
- **Entry Logic:**
    - **Nifty:** Enters on Monday (1 day before Tuesday weekly expiry).
    - **Sensex:** Enters on Wednesday (1 day before Thursday weekly expiry).
- **Execution Order:** Always buys OTM hedges *before* selling short options to ensure maximum margin benefit.
- **VIX Filter:** Automatically skips entry if India VIX is greater than 20. If already in a trade, the trade continues normally.
- **Auto-Exit & Positional Logic:**
    - **Positional (Overnight):** Trades are taken using `NRML` product type and held across days if targets are not hit.
    - **Dynamic Targets:**
        - Entry Day: 60% premium decay.
        - Subsequent Days: 80% premium decay.
    - **Stop Loss:** 100% loss on sold premium (exit if premium doubles).
    - **Individual Exit:** Each leg (CE/PE) is managed and exited independently when its specific target or SL is hit.
    - **Expiry Exit:** Automatically squares off open positions at 2:30 PM (14:30) ONLY on the day of expiry.
    - **Persistence:** Open positions are saved to `open_positions.json` so the algo can resume monitoring after a restart.

## Premium Ranges
| Index | Leg | Action | Range (₹) |
|---|---|---|---|
| **NIFTY** | PE | SELL | 30–40 |
| **NIFTY** | PE | BUY (Hedge) | 10–15 |
| **NIFTY** | CE | SELL | 20–30 |
| **NIFTY** | CE | BUY (Hedge) | 5–10 |
| **SENSEX** | PE | SELL | 120–150 |
| **SENSEX** | PE | BUY (Hedge) | 30–50 |
| **SENSEX** | CE | SELL | 120–150 |
| **SENSEX** | CE | BUY (Hedge) | 30–50 |

## Setup
1. Install dependencies: `pip install kiteconnect pandas schedule`
2. Update `API_KEY` and `API_SECRET` in `nifty_sensex_algo.py`.
3. Run: `python nifty_sensex_algo.py`
