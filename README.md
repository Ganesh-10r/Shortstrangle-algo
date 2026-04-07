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

### 1. Daily Initialization
*   **API Connection:** Connects to Zerodha Kite Connect and generates your daily session token.
*   **Position Recovery:** It immediately checks `open_positions.json`. If you have trades running from previous days, it loads them and resumes monitoring them instantly.

### 2. High-Frequency Schedule
*   **Polling Every 5 Seconds:** The algorithm now checks the market every **5 seconds** after **9:45 AM**.
*   **Correct Trading Days:**
    *   **NIFTY:** Triggers on **Mondays** (1 day before Tuesday weekly expiry).
    *   **SENSEX:** Triggers on **Wednesdays** (1 day before Thursday weekly expiry).

### 3. Smart Market Filters
*   **India VIX Filter:** Before entering any new trade, it checks the **India VIX**. If VIX is **above 20**, it stays out of the market to avoid excessive risk.
*   **API Optimization:** To handle the 5-second speed, it downloads the list of thousands of options once and **caches** them in memory. This prevents Zerodha from blocking your account for making too many heavy requests.

### 4. Independent Leg Entry (PE and CE)
*   The algorithm treats the **PE (Put)** and **CE (Call)** sides as two separate trades.
*   It will enter whichever side meets its conditions first. For example, if the PE condition is met at 9:50 AM, it will take that trade and continue checking for the CE side every 5 seconds until that too is met.

### 5. Advanced OI-Based Strike Selection
For each leg, it follows this logic to find the best strike:
*   **Premium Range Filter:**
    *   **Nifty:** Looks for strikes priced between **₹30–₹40**.
    *   **Sensex:** Looks for strikes priced between **₹120–₹150**.
*   **Sort by Open Interest (OI):** It finds all strikes in that price range and sorts them from **highest to lowest OI**.
*   **The Conditional Bias:**
    *   **For PE (Put):** It picks the highest OI strike where **PE OI is greater than CE OI**.
    *   **For CE (Call):** It picks the highest OI strike where **CE OI is greater than PE OI**.
*   **Fallback:** If the top OI strike doesn't meet the condition, it immediately checks the 2nd highest, then the 3rd. If none qualify, it waits 5 seconds and tries again.

### 6. Safe Order Execution (Hedge First)
Once a strike is selected, it places the orders in this specific order to maximize your margin benefit and reduce risk:
1.  **BUY the Hedge:** First, it buys the OTM hedge (₹10-15 for Nifty PE, etc.).
2.  **SELL the Main Leg:** Immediately after the hedge is confirmed, it sells the main strike.
3.  **Product Type:** All orders are placed as **NRML** (Positional) so you can hold them overnight.

### 7. Real-Time Monitoring & Exits
A background process monitors every open leg individually every **5 seconds**:
*   **Stop Loss (SL):** If the price of your sold option doubles (**100% loss**), it exits that leg instantly.
*   **Profit Target (Day 1):** If the premium decays by **60%** on the day you entered, it takes the profit.
*   **Profit Target (Day 2+):** If held overnight, the target increases to **80%** decay.
*   **Expiry Auto-Exit:** On the day of expiry at **2:30 PM (14:30)**, it automatically closes all remaining open positions for that index.

### 8. Technical Reliability
*   **Thread Safety:** The code uses a "Locking" mechanism to ensure that the monitoring thread and the entry thread never conflict or crash while sharing trade data.
*   **Persistence:** Every entry and exit is saved to your disk. If your computer or the script restarts, it won't "lose" your trades.

## Setup
1. Install dependencies: `pip install kiteconnect pandas schedule`
2. Update `API_KEY` and `API_SECRET` in `nifty_sensex_algo.py`.
3. Run: `python nifty_sensex_algo.py`
