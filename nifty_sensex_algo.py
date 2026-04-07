"""
=============================================================
NIFTY & SENSEX SHORT STRANGLE ALGO — ZERODHA KITE CONNECT
=============================================================

STRATEGY SUMMARY:
- Trigger: 1 day before weekly expiry (Monday for Nifty/Tuesday expiry, Wednesday for Sensex/Thursday expiry)
- Time: After 9:45 AM
- VIX Filter: Do not enter if India VIX > 20
- Action (Hedges BOUGHT before selling for margin benefit):
    NIFTY:
      SELL PE with premium in range 30–40
      BUY  PE hedge with premium in range 10–15
      SELL CE with premium in range 30–40
      BUY  CE hedge with premium in range 5–10

    SENSEX:
      SELL PE with premium in range 120–150
      BUY  PE hedge with premium in range 30–50
      SELL CE with premium in range 120–150
      BUY  CE hedge with premium in range 30–50

- Exit: Based on Stop Loss % or Target % defined below
- Alerts: Printed to console (you can add email/SMS later)

=============================================================
"""

# ─────────────────────────────────────────────
# IMPORTS
# ─────────────────────────────────────────────
import time
import datetime
import webbrowser
import threading
from threading import Lock
import json
import os

import schedule
import pandas as pd
from kiteconnect import KiteConnect, KiteTicker


# ─────────────────────────────────────────────
# ✏️  USER SETTINGS — Edit these before running
# ─────────────────────────────────────────────

API_KEY     = "your_api_key_here"       # From kite.trade dashboard
API_SECRET  = "your_api_secret_here"    # From kite.trade dashboard

# Number of lots to trade (1 lot = 50 qty for Nifty, 10 qty for Sensex)
NIFTY_LOTS   = 1      # Change this to however many lots you want
SENSEX_LOTS  = 1      # Change this to however many lots you want

NIFTY_LOT_SIZE   = 50    # Nifty lot size
SENSEX_LOT_SIZE  = 10    # Sensex lot size

# Entry time — algo will only run after this time (24hr format)
ENTRY_HOUR   = 9
ENTRY_MINUTE = 45

# Premium ranges for option selection (in ₹)
NIFTY_PE_SELL_MIN,  NIFTY_PE_SELL_MAX  = 30, 40    # Sell PE in this range
NIFTY_PE_BUY_MIN,   NIFTY_PE_BUY_MAX   = 10, 15    # Buy hedge PE in this range
NIFTY_CE_SELL_MIN,  NIFTY_CE_SELL_MAX  = 30, 40    # Sell CE in this range
NIFTY_CE_BUY_MIN,   NIFTY_CE_BUY_MAX   = 5,  10    # Buy hedge CE in this range

SENSEX_PE_SELL_MIN, SENSEX_PE_SELL_MAX = 120, 150
SENSEX_PE_BUY_MIN,  SENSEX_PE_BUY_MAX  = 30, 50
SENSEX_CE_SELL_MIN, SENSEX_CE_SELL_MAX = 120, 150
SENSEX_CE_BUY_MIN,  SENSEX_CE_BUY_MAX  = 30, 50

# Exit rules
STOP_LOSS_PERCENT = 100    # Exit if sold premium doubles (100% loss on premium)
TARGET_DAY1       = 60     # 60% decay target on entry day
TARGET_DAY2       = 80     # 80% decay target on subsequent days

# VIX threshold
VIX_THRESHOLD = 20

# Persistence file
POSITIONS_FILE = "open_positions.json"

# Thread safety
positions_lock = Lock()

# Global cache for instruments
cached_instruments = {
    "NIFTY": {"df": None, "expiry": None},
    "SENSEX": {"df": None, "expiry": None}
}


# ─────────────────────────────────────────────
# STEP 1 — LOGIN & CONNECT TO ZERODHA
# ─────────────────────────────────────────────

def login_and_get_kite():
    """
    Opens the Zerodha login page in your browser.
    After you log in, Zerodha redirects to your redirect URL with a 'request_token'.
    You paste that token here and the script generates your access token.
    This needs to be done once every trading day.
    """

    kite = KiteConnect(api_key=API_KEY)

    # Open login URL in browser automatically
    login_url = kite.login_url()
    print("\n📌 Opening Zerodha login in your browser...")
    print(f"   If it doesn't open, go to: {login_url}\n")
    webbrowser.open(login_url)

    # After logging in, the browser will show a URL like:
    # http://127.0.0.1:5000/?request_token=XXXXXXXX&action=login&status=success
    # Copy the 'request_token' value from that URL and paste below
    request_token = input("✏️  Paste the 'request_token' from the redirect URL: ").strip()

    # Generate session (access token)
    data = kite.generate_session(request_token, api_secret=API_SECRET)
    kite.set_access_token(data["access_token"])

    print("✅ Login successful! Access token generated.\n")
    return kite


# ─────────────────────────────────────────────
# STEP 2 — HELPER: GET CURRENT EXPIRY DATES
# ─────────────────────────────────────────────

def get_expiry_info():
    """
    Returns the current week's expiry dates for Nifty and Sensex.

    Nifty  expires every TUESDAY  → take position on MONDAY  (1 day before)
    Sensex expires every THURSDAY → take position on WEDNESDAY (1 day before)

    Python weekday numbers:
        Monday=0, Tuesday=1, Wednesday=2, Thursday=3, Friday=4
    """

    today = datetime.date.today()

    # ── NIFTY ──
    # Find this week's Tuesday (Nifty expiry) — weekday 1 = Tuesday
    days_to_tuesday = (1 - today.weekday()) % 7
    # If today IS Tuesday, look at next Tuesday (expiry day itself, not trigger day)
    if days_to_tuesday == 0:
        days_to_tuesday = 7
    nifty_expiry = today + datetime.timedelta(days=days_to_tuesday)

    # Trigger day = Monday (1 day before Tuesday expiry)
    nifty_trigger_day = nifty_expiry - datetime.timedelta(days=1)
    nifty_trigger     = (today == nifty_trigger_day)   # True only on Monday

    # ── SENSEX ──
    # Find this week's Thursday (Sensex expiry) — weekday 3 = Thursday
    days_to_thursday = (3 - today.weekday()) % 7
    # If today IS Thursday, look at next Thursday
    if today.weekday() == 3:
        days_to_thursday = 7
    sensex_expiry = today + datetime.timedelta(days=days_to_thursday)

    # Trigger day = Wednesday (1 day before Thursday expiry)
    sensex_trigger_day = sensex_expiry - datetime.timedelta(days=1)
    sensex_trigger     = (today == sensex_trigger_day)  # True only on Wednesday

    print(f"📅 Today: {today} ({today.strftime('%A')})")
    print(f"   Nifty  expiry: {nifty_expiry} (Tuesday)  | Entry on: {nifty_trigger_day} (Monday)  | Trigger today: {nifty_trigger}")
    print(f"   Sensex expiry: {sensex_expiry} (Thursday) | Entry on: {sensex_trigger_day} (Wednesday) | Trigger today: {sensex_trigger}\n")

    return {
        "nifty_expiry":   nifty_expiry,
        "sensex_expiry":  sensex_expiry,
        "nifty_trigger":  nifty_trigger,
        "sensex_trigger": sensex_trigger,
    }


# ─────────────────────────────────────────────
# STEP 3 — FETCH OPTION CHAIN & PICK STRIKES
# ─────────────────────────────────────────────

def get_option_instruments(kite, index_name, expiry_date):
    """
    Downloads the full list of instruments from Zerodha for the given index.
    Filters to only options expiring on the given date.
    Uses caching to avoid repeated full downloads.

    index_name: "NIFTY" or "SENSEX"
    expiry_date: datetime.date object
    """
    global cached_instruments

    # Check if we already have the correct instruments cached for today/this expiry
    if (cached_instruments[index_name]["df"] is not None and
        cached_instruments[index_name]["expiry"] == expiry_date):
        return cached_instruments[index_name]["df"]

    print(f"📡 Fetching instruments for {index_name} expiry {expiry_date}...")

    # Get all NSE instruments (Nifty options are on NFO exchange)
    exchange = "NFO" if index_name == "NIFTY" else "BFO"
    instruments = kite.instruments(exchange)

    # Convert to DataFrame for easy filtering
    df = pd.DataFrame(instruments)

    # Filter: only options for this index and expiry
    mask = (
        (df["name"]        == index_name) &
        (df["instrument_type"].isin(["CE", "PE"])) &
        (df["expiry"]      == expiry_date)
    )
    options_df = df[mask].copy()
    options_df = options_df.sort_values("strike").reset_index(drop=True)

    # Update cache
    cached_instruments[index_name]["df"] = options_df
    cached_instruments[index_name]["expiry"] = expiry_date

    print(f"   Found {len(options_df)} option strikes for {index_name}\n")
    return options_df


def get_ltp(kite, instrument_tokens):
    """
    Fetches Last Traded Price (LTP) for a list of instrument tokens.
    Returns a dict: { instrument_token: ltp_price }
    """
    quotes = kite.quote(instrument_tokens)
    ltp_map = {}
    for token_str, data in quotes.items():
        token = int(token_str.split(":")[1]) if ":" in token_str else int(token_str)
        ltp_map[token] = data["last_price"]
    return ltp_map


def find_strike_in_range(kite, options_df, option_type, min_premium, max_premium):
    """
    Scans all strikes of a given option type (CE or PE) and
    returns the one whose current LTP falls within the premium range.

    option_type: "CE" or "PE"
    min_premium, max_premium: the premium range in ₹
    """

    # Filter by CE or PE
    filtered = options_df[options_df["instrument_type"] == option_type].copy()

    if filtered.empty:
        print(f"   ⚠️  No {option_type} options found in instrument list.")
        return None

    # Get all instrument tokens to fetch LTP in bulk
    # Use the 'exchange' from the row (NFO for Nifty, BFO for Sensex)
    tokens = [f"{row['exchange']}:{row['tradingsymbol']}" for _, row in filtered.iterrows()]

    # Zerodha allows max 500 tokens per quote request — chunk if needed
    ltp_map = {}
    chunk_size = 200
    for i in range(0, len(tokens), chunk_size):
        chunk = tokens[i:i+chunk_size]
        ltp_map.update(kite.quote(chunk))

    # Match strike whose LTP is within desired range
    for _, row in filtered.iterrows():
        symbol = f"{row['exchange']}:{row['tradingsymbol']}"
        if symbol in ltp_map:
            ltp = ltp_map[symbol]["last_price"]
            if min_premium <= ltp <= max_premium:
                print(f"   ✅ Found {option_type} strike {row['strike']} | LTP: ₹{ltp} | Symbol: {row['tradingsymbol']}")
                return {
                    "tradingsymbol": row["tradingsymbol"],
                    "token":         row["instrument_token"],
                    "strike":        row["strike"],
                    "ltp":           ltp,
                    "exchange":      row["exchange"],
                }

    print(f"   ❌ No {option_type} strike found in premium range ₹{min_premium}–₹{max_premium}")
    return None


def find_best_strike_by_oi(kite, options_df, option_type, min_premium, max_premium):
    """
    1. Finds all strikes within the premium range.
    2. Fetches OI for both CE and PE for those strikes.
    3. Sorts by the specified option_type's OI (highest first).
    4. Returns the first strike that meets the condition:
       - For PE: PE_OI > CE_OI
       - For CE: CE_OI > PE_OI
    """

    # Filter strikes by option_type
    filtered = options_df[options_df["instrument_type"] == option_type].copy()
    if filtered.empty:
        return None

    # Get LTP first to find strikes in range
    tokens = [f"{row['exchange']}:{row['tradingsymbol']}" for _, row in filtered.iterrows()]
    ltp_map = {}
    chunk_size = 200
    for i in range(0, len(tokens), chunk_size):
        chunk = tokens[i:i+chunk_size]
        ltp_map.update(kite.quote(chunk))

    strikes_in_range = []
    for _, row in filtered.iterrows():
        symbol = f"{row['exchange']}:{row['tradingsymbol']}"
        if symbol in ltp_map:
            ltp = ltp_map[symbol]["last_price"]
            if min_premium <= ltp <= max_premium:
                strikes_in_range.append({
                    "strike": row["strike"],
                    "ltp": ltp,
                    "exchange": row["exchange"]
                })

    if not strikes_in_range:
        print(f"   ❌ No {option_type} strike found in premium range ₹{min_premium}–₹{max_premium}")
        return None

    # Now for these strikes, fetch BOTH CE and PE OI
    # We need to find the corresponding other option (CE for PE, PE for CE) for the same strike
    full_info_list = []
    for s_info in strikes_in_range:
        strike = s_info["strike"]
        # Find both PE and CE symbols for this strike
        mask = (options_df["strike"] == strike)
        strike_options = options_df[mask]

        symbols_to_quote = [f"{row['exchange']}:{row['tradingsymbol']}" for _, row in strike_options.iterrows()]
        quotes = kite.quote(symbols_to_quote)

        pe_oi, ce_oi = 0, 0
        pe_data, ce_data = None, None

        for sym, q in quotes.items():
            if sym.endswith("PE"):
                pe_oi = q["oi"]
                pe_data = q
                pe_data["tradingsymbol"] = sym.split(":")[1]
                pe_data["exchange"] = sym.split(":")[0]
            elif sym.endswith("CE"):
                ce_oi = q["oi"]
                ce_data = q
                ce_data["tradingsymbol"] = sym.split(":")[1]
                ce_data["exchange"] = sym.split(":")[0]

        full_info_list.append({
            "strike": strike,
            "pe_oi": pe_oi,
            "ce_oi": ce_oi,
            "pe_data": pe_data,
            "ce_data": ce_data
        })

    # Sort by the primary option_type's OI (descending)
    if option_type == "PE":
        full_info_list.sort(key=lambda x: x["pe_oi"], reverse=True)
    else:
        full_info_list.sort(key=lambda x: x["ce_oi"], reverse=True)

    # Find the first one that meets the condition
    for item in full_info_list:
        if option_type == "PE" and item["pe_oi"] > item["ce_oi"]:
            print(f"   ✅ Found PE strike {item['strike']} | PE OI: {item['pe_oi']} | CE OI: {item['ce_oi']} | LTP: ₹{item['pe_data']['last_price']}")
            return {
                "tradingsymbol": item["pe_data"]["tradingsymbol"],
                "token":         item["pe_data"]["instrument_token"],
                "strike":        item["strike"],
                "ltp":           item["pe_data"]["last_price"],
                "exchange":      item["pe_data"]["exchange"],
            }
        elif option_type == "CE" and item["ce_oi"] > item["pe_oi"]:
            print(f"   ✅ Found CE strike {item['strike']} | CE OI: {item['ce_oi']} | PE OI: {item['pe_oi']} | LTP: ₹{item['ce_data']['last_price']}")
            return {
                "tradingsymbol": item["ce_data"]["tradingsymbol"],
                "token":         item["ce_data"]["instrument_token"],
                "strike":        item["strike"],
                "ltp":           item["ce_data"]["last_price"],
                "exchange":      item["ce_data"]["exchange"],
            }

    print(f"   ❌ No {option_type} strike in range meets OI condition (PE_OI > CE_OI for PE, CE_OI > PE_OI for CE)")
    return None


# ─────────────────────────────────────────────
# STEP 4 — PLACE ORDER
# ─────────────────────────────────────────────

def place_order(kite, tradingsymbol, exchange, transaction_type, quantity, order_label=""):
    """
    Places a MARKET order on Zerodha.

    transaction_type: kite.TRANSACTION_TYPE_BUY or kite.TRANSACTION_TYPE_SELL
    quantity: number of shares (lots * lot_size)
    order_label: just a description for your logs
    """

    print(f"\n📤 Placing order: {order_label}")
    print(f"   Symbol: {tradingsymbol} | Action: {transaction_type} | Qty: {quantity}")

    try:
        order_id = kite.place_order(
            variety     = kite.VARIETY_REGULAR,
            exchange    = exchange,
            tradingsymbol = tradingsymbol,
            transaction_type = transaction_type,
            quantity    = quantity,
            order_type  = kite.ORDER_TYPE_MARKET,   # Market order for fast execution
            product     = kite.PRODUCT_NRML,        # NRML = positional / overnight product
        )
        print(f"   ✅ Order placed! Order ID: {order_id}")
        alert(f"ORDER PLACED: {order_label} | {tradingsymbol} | Qty {quantity} | ID {order_id}")
        return order_id

    except Exception as e:
        print(f"   ❌ Order FAILED: {e}")
        alert(f"ORDER FAILED: {order_label} | {tradingsymbol} | Error: {e}")
        return None


# ─────────────────────────────────────────────
# STEP 5 — ALERTS & PERSISTENCE
# ─────────────────────────────────────────────

def get_india_vix(kite):
    """
    Fetches the current value of India VIX.
    """
    try:
        quote = kite.quote("NSE:INDIA VIX")
        vix = quote["NSE:INDIA VIX"]["last_price"]
        print(f"📊 Current India VIX: {vix}")
        return vix
    except Exception as e:
        print(f"⚠️ Error fetching VIX: {e}")
        return None


def save_positions(positions_to_watch):
    """
    Saves current open positions to a JSON file for persistence.
    """
    with positions_lock:
        try:
            with open(POSITIONS_FILE, "w") as f:
                active_only = [p for p in positions_to_watch if not p.get("exited")]
                serializable = []
                for p in active_only:
                    p_copy = p.copy()
                    serializable.append(p_copy)
                json.dump(serializable, f, indent=4)
            print(f"📁 Positions saved to {POSITIONS_FILE}")
        except Exception as e:
            print(f"⚠️ Error saving positions: {e}")


def load_positions():
    """
    Loads open positions from the JSON file.
    """
    if not os.path.exists(POSITIONS_FILE):
        return []
    try:
        with open(POSITIONS_FILE, "r") as f:
            data = json.load(f)
            print(f"📁 Loaded {len(data)} existing positions from {POSITIONS_FILE}")
            return data
    except Exception as e:
        print(f"⚠️ Error loading positions: {e}")
        return []


def alert(message):
    """
    Prints an alert message with timestamp.
    """
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n🔔 ALERT [{timestamp}]: {message}\n")


# ─────────────────────────────────────────────
# STEP 6 — MONITOR POSITIONS & AUTO EXIT
# ─────────────────────────────────────────────

def monitor_and_exit(kite, positions_to_watch):
    """
    Monitors all open positions. Supports multi-day monitoring.
    Exits if:
    - Loss on sold premium > STOP_LOSS_PERCENT
    - Profit hits dynamic targets:
        - Entry day: TARGET_DAY1 (60% decay)
        - Subsequent days: TARGET_DAY2 (80% decay)
    - Auto square-off at 2:30 PM on the DAY OF EXPIRY.
    """

    print("\n👁️  Starting position monitor... (checks every 5 seconds)")
    alert("Monitoring started for all positions.")

    while True:
        time.sleep(5)

        with positions_lock:
            active_positions = [p for p in positions_to_watch if not p.get("exited")]

        if not active_positions:
            # We don't break here because we might enter new legs later today
            continue

        today = datetime.date.today()
        now_time = datetime.datetime.now().time()

        # Iterate over a copy to avoid issues if positions_to_watch is modified
        with positions_lock:
            monitored_list = list(positions_to_watch)

        for pos in monitored_list:
            if pos.get("exited"):
                continue

            # ── Check Expiry Square-off ──────────────────
            expiry_date_obj = datetime.datetime.strptime(pos["expiry_date"], "%Y-%m-%d").date()
            if today >= expiry_date_obj and now_time >= datetime.time(14, 30):
                alert(f"⏰ Expiry day reached for {pos['leg_name']} — Auto square-off at 2:30 PM")
                exit_position(kite, pos, reason="Expiry Day Auto Square Off")
                save_positions(positions_to_watch)
                continue

            # ── Fetch P&L ──────────────────────────────
            try:
                sell_quote  = kite.quote([f"{pos['sell_exchange']}:{pos['sell_symbol']}"])
                current_ltp = sell_quote[f"{pos['sell_exchange']}:{pos['sell_symbol']}"]["last_price"]
            except Exception as e:
                print(f"⚠️ Error fetching quote for {pos['sell_symbol']}: {e}")
                continue

            entry_price = pos["sell_entry_price"]
            pnl_pct     = ((current_ltp - entry_price) / entry_price) * 100

            # ── Determine Target ───────────────────────
            entry_date_obj = datetime.datetime.strptime(pos["entry_date"], "%Y-%m-%d").date()
            target = TARGET_DAY1 if today == entry_date_obj else TARGET_DAY2

            print(f"   {pos['leg_name']} | Entry: ₹{entry_price} | Now: ₹{current_ltp} | P&L: {pnl_pct:.1f}% | Target: -{target}%")

            # ── Check SL/Target ────────────────────────
            if pnl_pct >= STOP_LOSS_PERCENT:
                alert(f"🚨 STOP LOSS HIT on {pos['leg_name']}! Entry ₹{entry_price} → Now ₹{current_ltp}")
                exit_position(kite, pos, reason="Stop Loss")
                save_positions(positions_to_watch)
            elif pnl_pct <= -target:
                alert(f"🎯 TARGET HIT ({target}%) on {pos['leg_name']}! Entry ₹{entry_price} → Now ₹{current_ltp}")
                # exit_position modifies pos['exited'] which is fine since we have the object reference
                exit_position(kite, pos, reason=f"Target {target}%")
                save_positions(positions_to_watch)


def exit_position(kite, pos, reason="Manual"):
    """
    Exits a single leg by:
    1. Buying back the sold option (to close short)
    2. Selling the hedge option (to close long hedge)
    """
    print(f"\n🔄 Exiting position: {pos['leg_name']} | Reason: {reason}")

    # Buy back the SELL leg
    place_order(
        kite, pos["sell_symbol"], pos["sell_exchange"],
        KiteConnect.TRANSACTION_TYPE_BUY,
        pos["sell_qty"],
        order_label=f"EXIT SELL leg — {pos['leg_name']} ({reason})"
    )

    # Sell the BUY hedge leg
    place_order(
        kite, pos["buy_symbol"], pos["buy_exchange"],
        KiteConnect.TRANSACTION_TYPE_SELL,
        pos["buy_qty"],
        order_label=f"EXIT BUY hedge — {pos['leg_name']} ({reason})"
    )

    pos["exited"] = True


# ─────────────────────────────────────────────
# STEP 7 — MAIN ENTRY LOGIC PER INDEX
# ─────────────────────────────────────────────

def check_and_enter_leg(kite, index_name, expiry_date, leg_type, qty,
                         sell_range, buy_range, options_df, positions_to_watch):
    """
    Checks if a specific leg (PE or CE) is already entered for the day.
    If not, attempts to find a strike based on OI and enter.
    Hedge is bought before selling.
    """
    leg_name = f"{index_name} {leg_type}"
    today_str = datetime.date.today().strftime("%Y-%m-%d")

    # Check if already entered today
    with positions_lock:
        for pos in positions_to_watch:
            if pos["leg_name"] == leg_name and pos["entry_date"] == today_str:
                return False # Already entered

    print(f"🔎 Checking entry for {leg_name}...")

    # 1. Find SELL strike based on OI
    sell_strike = find_best_strike_by_oi(kite, options_df, leg_type, *sell_range)
    if not sell_strike:
        return False

    # 2. Find BUY hedge strike based on premium
    buy_strike = find_strike_in_range(kite, options_df, leg_type, *buy_range)
    if not buy_strike:
        print(f"   ⚠️ Found SELL strike for {leg_name} but no BUY hedge in range {buy_range}. Skipping.")
        return False

    # 3. Place Orders (BUY hedge FIRST)
    exchange = "NFO" if index_name == "NIFTY" else "BFO"

    place_order(kite, buy_strike["tradingsymbol"], exchange, KiteConnect.TRANSACTION_TYPE_BUY, qty, order_label=f"{leg_name} BUY hedge")
    place_order(kite, sell_strike["tradingsymbol"], exchange, KiteConnect.TRANSACTION_TYPE_SELL, qty, order_label=f"{leg_name} SELL")

    # 4. Add to positions
    expiry_str = expiry_date.strftime("%Y-%m-%d")
    with positions_lock:
        positions_to_watch.append({
            "leg_name": leg_name,
            "entry_date": today_str,
            "expiry_date": expiry_str,
            "sell_symbol": sell_strike["tradingsymbol"],
            "sell_exchange": exchange,
            "sell_qty": qty,
            "sell_entry_price": sell_strike["ltp"],
            "buy_symbol": buy_strike["tradingsymbol"],
            "buy_exchange": buy_strike["exchange"],
            "buy_qty": qty,
            "exited": False,
        })

    save_positions(positions_to_watch)
    alert(f"✅ {leg_name} entry completed!")
    return True


def run_strategy_for_index(kite, index_name, expiry_date, lots, lot_size,
                            pe_sell_range, pe_buy_range,
                            ce_sell_range, ce_buy_range,
                            positions_to_watch):
    """
    Core logic — finds strikes and attempts to place orders for PE and CE legs independently.
    """

    qty = lots * lot_size

    print(f"\n{'='*50}")
    print(f"🚀 Running strategy for {index_name} | Expiry: {expiry_date} | Qty: {qty}")
    print(f"{'='*50}")

    options_df = get_option_instruments(kite, index_name, expiry_date)

    # Attempt PE entry
    check_and_enter_leg(kite, index_name, expiry_date, "PE", qty,
                        pe_sell_range, pe_buy_range, options_df, positions_to_watch)

    # Attempt CE entry
    check_and_enter_leg(kite, index_name, expiry_date, "CE", qty,
                        ce_sell_range, ce_buy_range, options_df, positions_to_watch)


# ─────────────────────────────────────────────
# STEP 8 — DAILY JOB
# ─────────────────────────────────────────────

# Global to track if monitor thread is already running
_MONITOR_STARTED = False

def daily_job(kite, positions_to_watch):
    global _MONITOR_STARTED
    now  = datetime.datetime.now()
    info = get_expiry_info()

    if now.time() < datetime.time(ENTRY_HOUR, ENTRY_MINUTE):
        print(f"⏳ Waiting... Current time {now.strftime('%H:%M')} is before entry time 09:45")
        return

    vix = get_india_vix(kite)
    if vix and vix > VIX_THRESHOLD:
        print(f"🚫 India VIX ({vix}) is above {VIX_THRESHOLD}. Staying out of market today.")
    else:
        # ── NIFTY ──
        if info["nifty_trigger"]:
            run_strategy_for_index(kite, "NIFTY", info["nifty_expiry"], NIFTY_LOTS, NIFTY_LOT_SIZE,
                                   (NIFTY_PE_SELL_MIN, NIFTY_PE_SELL_MAX), (NIFTY_PE_BUY_MIN, NIFTY_PE_BUY_MAX),
                                   (NIFTY_CE_SELL_MIN, NIFTY_CE_SELL_MAX), (NIFTY_CE_BUY_MIN, NIFTY_CE_BUY_MAX),
                                   positions_to_watch)

        # ── SENSEX ──
        if info["sensex_trigger"]:
            run_strategy_for_index(kite, "SENSEX", info["sensex_expiry"], SENSEX_LOTS, SENSEX_LOT_SIZE,
                                   (SENSEX_PE_SELL_MIN, SENSEX_PE_SELL_MAX), (SENSEX_PE_BUY_MIN, SENSEX_PE_BUY_MAX),
                                   (SENSEX_CE_SELL_MIN, SENSEX_CE_SELL_MAX), (SENSEX_CE_BUY_MIN, SENSEX_CE_BUY_MAX),
                                   positions_to_watch)

    if positions_to_watch and not _MONITOR_STARTED:
        _MONITOR_STARTED = True
        monitor_thread = threading.Thread(target=monitor_and_exit, args=(kite, positions_to_watch), daemon=True)
        monitor_thread.start()


# ─────────────────────────────────────────────
# STEP 9 — ENTRY POINT
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("  NIFTY & SENSEX POSITIONAL SHORT STRANGLE")
    print("=" * 60)

    kite = login_and_get_kite()
    positions_to_watch = load_positions()

    if positions_to_watch:
        print(f"🔄 Resuming monitoring for {len(positions_to_watch)} active positions...")
        _MONITOR_STARTED = True
        threading.Thread(target=monitor_and_exit, args=(kite, positions_to_watch), daemon=True).start()

    # Run every 5 seconds to check conditions
    schedule.every(5).seconds.do(daily_job, kite=kite, positions_to_watch=positions_to_watch)

    print("\n⏰ Scheduler started. Running every 5 seconds...")
    daily_job(kite, positions_to_watch)

    while True:
        schedule.run_pending()
        time.sleep(1)
