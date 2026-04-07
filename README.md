# Nifty & Sensex Positional Short Strangle Trading Algo

This Python-based trading algorithm automates a Short Strangle strategy with hedges for NIFTY and SENSEX using the Zerodha Kite Connect API. It is designed to be **positional**, meaning it can hold trades overnight to capture maximum premium decay.

## Core Features
- **Indices Supported:** NIFTY and SENSEX.
- **Entry Logic:**
    - **Nifty:** Enters on Monday (1 day before Tuesday weekly expiry).
    - **Sensex:** Enters on Wednesday (1 day before Thursday weekly expiry).
    - **OI Condition:** Within the premium range, the strike with the highest Open Interest (OI) is selected, provided that for PE, `PE OI > CE OI` and for CE, `CE OI > PE OI`.
- **Execution Order:** Always buys OTM hedges *before* selling short options to ensure maximum margin benefit.
- **VIX Filter:** Automatically skips entry if India VIX is greater than 20 at 9:45 AM. If already in a trade, the trade continues normally.
- **Positional Logic:**
    - Trades use the **NRML** product type.
    - Positions are held overnight if targets are not met on the first day.
    - **Dynamic Targets:**
        - Day of Entry (Day 1): 60% premium decay.
        - Subsequent Days (Day 2+): 80% premium decay.
    - **Stop Loss:** 100% loss on sold premium (exit if premium doubles).
    - **Individual Exit:** Each leg (CE/PE) is managed and exited independently.
    - **Persistence:** Active trades are saved to `open_positions.json`. The algo automatically resumes monitoring them if the script restarts.
- **Expiry Exit:** Automatically squares off open positions at **2:30 PM (14:30)** ONLY on the day of expiry for that index.

## Premium Ranges
| Index | Leg | Action | Range (₹) |
|---|---|---|---|
| **NIFTY** | PE | SELL | 30–40 |
| **NIFTY** | PE | BUY (Hedge) | 10–15 |
| **NIFTY** | CE | SELL | 30–40 |
| **NIFTY** | CE | BUY (Hedge) | 5–10 |
| **SENSEX** | PE | SELL | 120–150 |
| **SENSEX** | PE | BUY (Hedge) | 30–50 |
| **SENSEX** | CE | SELL | 120–150 |
| **SENSEX** | CE | BUY (Hedge) | 30–50 |

## Setup
1. Install dependencies: `pip install kiteconnect pandas schedule`
2. Update `API_KEY` and `API_SECRET` in `nifty_sensex_algo.py`.
3. Run: `python nifty_sensex_algo.py`
