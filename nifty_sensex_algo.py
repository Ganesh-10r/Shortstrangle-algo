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
      SELL CE with premium in range 20–30
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
NIFTY_CE_SELL_MIN,  NIFTY_CE_SELL_MAX  = 20, 30    # Sell CE in this range
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
    if days_to_thursday == 0:
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

    index_name: "NIFTY" or "SENSEX"
    expiry_date: datetime.date object
    """

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
# STEP 5 — ALERTS
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
    try:
        with open(POSITIONS_FILE, "w") as f:
            # We filter out already exited legs before saving to keep it clean
            active_only = [p for p in positions_to_watch if not p.get("exited")]
            # Convert date objects to strings for JSON
            serializable = []
            for p in active_only:
                p_copy = p.copy()
                if isinstance(p_copy.get("entry_date"), (datetime.date, datetime.datetime)):
                    p_copy["entry_date"] = p_copy["entry_date"].strftime("%Y-%m-%d")
                if isinstance(p_copy.get("expiry_date"), (datetime.date, datetime.datetime)):
                    p_copy["expiry_date"] = p_copy["expiry_date"].strftime("%Y-%m-%d")
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
    You can extend this later to send:
    - SMS via Twilio
    - Email via smtplib
    - Telegram message via python-telegram-bot
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
    - Auto square-off at 3:20 PM on the DAY OF EXPIRY.
    """

    print("\n👁️  Starting position monitor... (checks every 60 seconds)")
    alert("Monitoring started for all positions.")

    while True:
        # Check if there are any active positions left to monitor
        active_positions = [p for p in positions_to_watch if not p.get("exited")]
        if not active_positions:
            print("✅ All positions have been closed. Stopping monitor.")
            break

        time.sleep(60)

        today = datetime.date.today()
        now_time = datetime.datetime.now().time()

        for pos in positions_to_watch:
            if pos.get("exited"):
                continue

            # ── Check Expiry Square-off ──────────────────
            # Only auto-exit after 2:30 PM (14:30) if today is the expiry date
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
            # Stop Loss
            if pnl_pct >= STOP_LOSS_PERCENT:
                alert(f"🚨 STOP LOSS HIT on {pos['leg_name']}! Entry ₹{entry_price} → Now ₹{current_ltp}")
                exit_position(kite, pos, reason="Stop Loss")
                save_positions(positions_to_watch)

            # Target (60% or 80% decay)
            elif pnl_pct <= -target:
                alert(f"🎯 TARGET HIT ({target}%) on {pos['leg_name']}! Entry ₹{entry_price} → Now ₹{current_ltp}")
                exit_position(kite, pos, reason=f"Target {target}%")
                save_positions(positions_to_watch)


def exit_position(kite, pos, reason="Manual"):
    """
    Exits a single leg by:
    1. Buying back the sold option (to close short)
    2. Selling the hedge option (to close long hedge)
    """
    print(f"\n🔄 Exiting position: {pos['leg_name']} | Reason: {reason}")

    # Buy back the SELL leg (closing short position)
    place_order(
        kite, pos["sell_symbol"], pos["sell_exchange"],
        KiteConnect.TRANSACTION_TYPE_BUY,
        pos["sell_qty"],
        order_label=f"EXIT SELL leg — {pos['leg_name']} ({reason})"
    )

    # Sell the BUY hedge leg (closing long hedge)
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

def run_strategy_for_index(kite, index_name, expiry_date, lots, lot_size,
                            pe_sell_range, pe_buy_range,
                            ce_sell_range, ce_buy_range,
                            positions_to_watch):
    """
    Core logic — finds strikes and places all 4 orders for one index.
    Then adds the positions to the monitoring list.

    index_name:    "NIFTY" or "SENSEX"
    expiry_date:   datetime.date
    lots:          number of lots
    lot_size:      shares per lot
    pe_sell_range: (min, max) premium range for PE sell
    pe_buy_range:  (min, max) premium range for PE hedge buy
    ce_sell_range: (min, max) premium range for CE sell
    ce_buy_range:  (min, max) premium range for CE hedge buy
    positions_to_watch: list to append open positions into (for monitoring)
    """

    exchange = "NFO" if index_name == "NIFTY" else "BFO"
    qty = lots * lot_size  # Total quantity to trade

    print(f"\n{'='*50}")
    print(f"🚀 Running strategy for {index_name} | Expiry: {expiry_date} | Qty: {qty}")
    print(f"{'='*50}")

    # Get the option chain for this index and expiry
    options_df = get_option_instruments(kite, index_name, expiry_date)

    # ── Find the 4 strikes ──────────────────────

    # 1. PE to SELL (short put — collect premium)
    print(f"\n🔍 Looking for PE SELL strike (₹{pe_sell_range[0]}–₹{pe_sell_range[1]})...")
    pe_sell = find_strike_in_range(kite, options_df, "PE", *pe_sell_range)

    # 2. PE to BUY as hedge (long put — limit downside)
    print(f"🔍 Looking for PE BUY hedge strike (₹{pe_buy_range[0]}–₹{pe_buy_range[1]})...")
    pe_buy  = find_strike_in_range(kite, options_df, "PE", *pe_buy_range)

    # 3. CE to SELL (short call — collect premium)
    print(f"🔍 Looking for CE SELL strike (₹{ce_sell_range[0]}–₹{ce_sell_range[1]})...")
    ce_sell = find_strike_in_range(kite, options_df, "CE", *ce_sell_range)

    # 4. CE to BUY as hedge (long call — limit upside risk)
    print(f"🔍 Looking for CE BUY hedge strike (₹{ce_buy_range[0]}–₹{ce_buy_range[1]})...")
    ce_buy  = find_strike_in_range(kite, options_df, "CE", *ce_buy_range)

    # ── Validate all 4 strikes found ─────────────
    if not all([pe_sell, pe_buy, ce_sell, ce_buy]):
        alert(f"⚠️ {index_name}: Could not find all required strikes. Skipping.")
        return

    # ── Place 4 orders (BUY first for margin benefit) ────────────────────

    # ORDER 1: Buy PE hedge
    place_order(kite, pe_buy["tradingsymbol"], exchange,
                KiteConnect.TRANSACTION_TYPE_BUY, qty,
                order_label=f"{index_name} BUY PE hedge {pe_buy['strike']}")

    # ORDER 2: Sell PE
    place_order(kite, pe_sell["tradingsymbol"], exchange,
                KiteConnect.TRANSACTION_TYPE_SELL, qty,
                order_label=f"{index_name} SELL PE {pe_sell['strike']}")

    # ORDER 3: Buy CE hedge
    place_order(kite, ce_buy["tradingsymbol"], exchange,
                KiteConnect.TRANSACTION_TYPE_BUY, qty,
                order_label=f"{index_name} BUY CE hedge {ce_buy['strike']}")

    # ORDER 4: Sell CE
    place_order(kite, ce_sell["tradingsymbol"], exchange,
                KiteConnect.TRANSACTION_TYPE_SELL, qty,
                order_label=f"{index_name} SELL CE {ce_sell['strike']}")

    # ── Add positions to monitoring list ─────────

    # PE leg monitoring entry
    positions_to_watch.append({
        "leg_name":         f"{index_name} PE",
        "entry_date":       datetime.date.today().strftime("%Y-%m-%d"),
        "expiry_date":      expiry_date.strftime("%Y-%m-%d"),
        "sell_symbol":      pe_sell["tradingsymbol"],
        "sell_exchange":    exchange,
        "sell_qty":         qty,
        "sell_entry_price": pe_sell["ltp"],
        "buy_symbol":       pe_buy["tradingsymbol"],
        "buy_exchange":     pe_buy["exchange"],
        "buy_qty":          qty,
        "exited":           False,
    })

    # CE leg monitoring entry
    positions_to_watch.append({
        "leg_name":         f"{index_name} CE",
        "entry_date":       datetime.date.today().strftime("%Y-%m-%d"),
        "expiry_date":      expiry_date.strftime("%Y-%m-%d"),
        "sell_symbol":      ce_sell["tradingsymbol"],
        "sell_exchange":    exchange,
        "sell_qty":         qty,
        "sell_entry_price": ce_sell["ltp"],
        "buy_symbol":       ce_buy["tradingsymbol"],
        "buy_exchange":     ce_buy["exchange"],
        "buy_qty":          qty,
        "exited":           False,
    })

    save_positions(positions_to_watch)
    alert(f"✅ All 4 orders placed for {index_name}!")


# ─────────────────────────────────────────────
# STEP 8 — DAILY JOB (runs after 9:45 AM)
# ─────────────────────────────────────────────

def daily_job(kite):
    """
    This is the main function that runs every trading day.
    It checks:
    1. Is today a trigger day (2 days before expiry)?
    2. Is the time past 9:45 AM?
    If both yes → place orders and start monitoring.
    """

    now  = datetime.datetime.now()
    info = get_expiry_info()

    # Check time gate — must be after 9:45 AM
    if now.time() < datetime.time(ENTRY_HOUR, ENTRY_MINUTE):
        print(f"⏳ Waiting... Current time {now.strftime('%H:%M')} is before entry time 09:45")
        return

    # Check India VIX — skip if VIX > VIX_THRESHOLD (20)
    vix = get_india_vix(kite)
    if vix and vix > VIX_THRESHOLD:
        print(f"🚫 India VIX ({vix}) is above {VIX_THRESHOLD}. Staying out of market today.")
        return

    positions_to_watch = []  # Will hold all open legs for monitoring

    # ── NIFTY ──
    if info["nifty_trigger"]:
        run_strategy_for_index(
            kite         = kite,
            index_name   = "NIFTY",
            expiry_date  = info["nifty_expiry"],
            lots         = NIFTY_LOTS,
            lot_size     = NIFTY_LOT_SIZE,
            pe_sell_range = (NIFTY_PE_SELL_MIN,  NIFTY_PE_SELL_MAX),
            pe_buy_range  = (NIFTY_PE_BUY_MIN,   NIFTY_PE_BUY_MAX),
            ce_sell_range = (NIFTY_CE_SELL_MIN,  NIFTY_CE_SELL_MAX),
            ce_buy_range  = (NIFTY_CE_BUY_MIN,   NIFTY_CE_BUY_MAX),
            positions_to_watch = positions_to_watch,
        )
    else:
        print("ℹ️  Today is NOT a Nifty trigger day. Skipping Nifty.")

    # ── SENSEX ──
    if info["sensex_trigger"]:
        run_strategy_for_index(
            kite         = kite,
            index_name   = "SENSEX",
            expiry_date  = info["sensex_expiry"],
            lots         = SENSEX_LOTS,
            lot_size     = SENSEX_LOT_SIZE,
            pe_sell_range = (SENSEX_PE_SELL_MIN,  SENSEX_PE_SELL_MAX),
            pe_buy_range  = (SENSEX_PE_BUY_MIN,   SENSEX_PE_BUY_MAX),
            ce_sell_range = (SENSEX_CE_SELL_MIN,  SENSEX_CE_SELL_MAX),
            ce_buy_range  = (SENSEX_CE_BUY_MIN,   SENSEX_CE_BUY_MAX),
            positions_to_watch = positions_to_watch,
        )
    else:
        print("ℹ️  Today is NOT a Sensex trigger day. Skipping Sensex.")

    # ── Start monitoring if any orders were placed ──
    if positions_to_watch:
        # Run monitor in a separate thread so it doesn't block the scheduler
        monitor_thread = threading.Thread(
            target = monitor_and_exit,
            args   = (kite, positions_to_watch),
            daemon = True
        )
        monitor_thread.start()
    else:
        print("\n✅ No orders placed today. Nothing to monitor.")


# ─────────────────────────────────────────────
# STEP 9 — PROGRAM ENTRY POINT
# ─────────────────────────────────────────────

if __name__ == "__main__":

    print("=" * 60)
    print("  NIFTY & SENSEX SHORT STRANGLE ALGO")
    print("=" * 60)

    # Login once at the start of the day
    kite = login_and_get_kite()

    # 1. Check for existing positions from previous days
    positions_to_watch = load_positions()
    if positions_to_watch:
        print(f"🔄 Resuming monitoring for {len(positions_to_watch)} active positions...")
        monitor_thread = threading.Thread(
            target = monitor_and_exit,
            args   = (kite, positions_to_watch),
            daemon = True
        )
        monitor_thread.start()

    # 2. Schedule the job to run at 9:45 AM every day for NEW entries
    schedule.every().day.at("09:45").do(daily_job, kite=kite)

    print("\n⏰ Scheduler started. Waiting for 9:45 AM...")
    print("   (Press Ctrl+C to stop)\n")

    # Run daily_job once immediately on start (useful for testing or if starting after 9:45 AM)
    daily_job(kite)

    # Keep the script running and check schedule every 30 seconds
    while True:
        schedule.run_pending()
        time.sleep(30)
