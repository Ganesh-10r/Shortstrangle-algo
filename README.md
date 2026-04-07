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

## Detailed Algorithm Breakdown

### 1. Initialization & Daily Session
*   **API Login:** Connects to Zerodha Kite Connect and generates a daily access token via manual browser login.
*   **State Persistence:** Loads any active trades from `open_positions.json` to ensure monitoring resumes immediately across script restarts.

### 2. Schedule & Timing
*   **Polling Frequency:** The algorithm now runs **every 1 minute**.
*   **Entry Window:** It starts checking for new trades only after **9:45 AM**.
*   **Index Trigger Days:**
    *   **NIFTY:** Triggers only on **Mondays** (1 day before Tuesday weekly expiry).
    *   **SENSEX:** Triggers only on **Wednesdays** (1 day before Thursday weekly expiry).

### 3. Entry Filters (The "Safety Switch")
*   **India VIX Filter:** Before entering any new trade, it checks the **India VIX**. If VIX is **above 20**, it will not take any new positions for the day to avoid high volatility risk.

### 4. Independent Leg Entry
*   The algorithm treats the **PE (Put)** and **CE (Call)** legs independently.
*   It will enter whichever leg meets its conditions first. If one leg is entered, it continues to check for the other leg every minute until its specific conditions are also met.

### 5. Advanced Strike Selection (OI-Based)
For each leg (PE and CE), it follows this precise selection process:
*   **Identify Premium Range:**
    *   **Nifty:** Looks for strikes priced between **₹30–₹40**.
    *   **Sensex:** Looks for strikes priced between **₹120–₹150**.
*   **Scan & Sort by OI:** It identifies all strikes within that price range and sorts them from **highest to lowest Open Interest (OI)**.
*   **The Conditional Rule:**
    *   **For PE:** It selects the strike with the highest OI where **PE OI > CE OI** (for the same strike price).
    *   **For CE:** It selects the strike with the highest OI where **CE OI > PE OI** (for the same strike price).
*   **Fallback:** If the strike with the highest OI doesn't meet the condition, it checks the 2nd highest, then the 3rd, and so on. If no strike in the range qualifies, it waits and tries again in the next 1-minute cycle.

### 6. Hedge Selection & Margin Execution
*   Once a Sell strike is confirmed, it picks a Hedge (Buy) strike based on premium:
    *   **Nifty PE Hedge:** ₹10–₹15 | **Nifty CE Hedge:** ₹5–₹10.
    *   **Sensex Hedges:** ₹30–₹50.
*   **Order Sequence:** It **always places the BUY order first**, followed immediately by the SELL order. This ensures you get the maximum margin benefit from Zerodha.
*   **Product Type:** All trades are placed as **NRML** (Positional) to allow for overnight holding.

### 7. Position Monitoring & Exit Rules
A background process monitors each open leg individually every 60 seconds:
*   **Stop Loss (SL):** If the premium of a sold option increases by **100%** (it doubles), the leg is exited immediately.
*   **Dynamic Profit Targets:**
    *   **Day 1 (Entry Day):** Exits if the premium decays by **60%**.
    *   **Day 2 onwards:** Exits if the premium decays by **80%**.
*   **Expiry Auto-Squareoff:** On the actual day of expiry, if any leg is still open at **2:30 PM**, it is automatically closed.

### 8. Logging & Persistence
*   Every entry and exit is recorded in `open_positions.json`.
*   Detailed alerts and price updates (Entry price vs. LTP vs. Target) are printed to the console in real-time.

## Setup
1. Install dependencies: `pip install kiteconnect pandas schedule`
2. Update `API_KEY` and `API_SECRET` in `nifty_sensex_algo.py`.
3. Run: `python nifty_sensex_algo.py`
