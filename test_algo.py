
import unittest
from unittest.mock import MagicMock, patch
import datetime
import nifty_sensex_algo

class TestAlgoModifications(unittest.TestCase):

    def test_vix_threshold_constant(self):
        self.assertEqual(nifty_sensex_algo.VIX_THRESHOLD, 20)

    @patch('nifty_sensex_algo.KiteConnect')
    def test_get_india_vix_success(self, MockKite):
        mock_kite = MockKite.return_value
        mock_kite.quote.return_value = {"NSE:INDIA VIX": {"last_price": 18.5}}

        vix = nifty_sensex_algo.get_india_vix(mock_kite)
        self.assertEqual(vix, 18.5)
        mock_kite.quote.assert_called_with("NSE:INDIA VIX")

    @patch('nifty_sensex_algo.KiteConnect')
    def test_get_india_vix_failure(self, MockKite):
        mock_kite = MockKite.return_value
        mock_kite.quote.side_effect = Exception("API Error")

        vix = nifty_sensex_algo.get_india_vix(mock_kite)
        self.assertIsNone(vix)

    @patch('nifty_sensex_algo.get_india_vix')
    @patch('nifty_sensex_algo.get_expiry_info')
    def test_daily_job_skips_on_high_vix(self, mock_expiry, mock_vix):
        mock_vix.return_value = 21
        mock_expiry.return_value = {"nifty_trigger": True, "sensex_trigger": True}

        mock_kite = MagicMock()

        # Patching datetime.datetime can be tricky. Let's patch where it's used in the function.
        with patch('nifty_sensex_algo.datetime') as mock_dt:
            # mock_dt.datetime.now().time() should be > 9:45
            mock_now = MagicMock()
            mock_now.time.return_value = datetime.time(10, 0)
            mock_dt.datetime.now.return_value = mock_now
            mock_dt.time = datetime.time # keep the real time class

            with patch('nifty_sensex_algo.run_strategy_for_index') as mock_run:
                nifty_sensex_algo.daily_job(mock_kite)
                mock_run.assert_not_called()

    @patch('nifty_sensex_algo.place_order')
    @patch('nifty_sensex_algo.get_option_instruments')
    @patch('nifty_sensex_algo.find_strike_in_range')
    def test_order_execution_order(self, mock_find, mock_inst, mock_place):
        mock_kite = MagicMock()
        mock_inst.return_value = MagicMock()

        # Mock finding 4 strikes
        mock_find.side_effect = [
            {"tradingsymbol": "PE_SELL", "strike": 19000, "ltp": 35, "exchange": "NFO"},
            {"tradingsymbol": "PE_BUY", "strike": 18800, "ltp": 12, "exchange": "NFO"},
            {"tradingsymbol": "CE_SELL", "strike": 20000, "ltp": 25, "exchange": "NFO"},
            {"tradingsymbol": "CE_BUY", "strike": 20200, "ltp": 7, "exchange": "NFO"},
        ]

        positions_to_watch = []
        nifty_sensex_algo.run_strategy_for_index(
            mock_kite, "NIFTY", datetime.date(2023, 10, 31), 1, 50,
            (30, 40), (10, 15), (20, 30), (5, 10), positions_to_watch
        )

        # Check that BUY PE hedge was placed before SELL PE
        # and BUY CE hedge was placed before SELL CE

        calls = mock_place.call_args_list
        self.assertEqual(len(calls), 4)

        # Call 0: BUY PE
        self.assertEqual(calls[0][0][3], "BUY")
        self.assertEqual(calls[0][0][1], "PE_BUY")

        # Call 1: SELL PE
        self.assertEqual(calls[1][0][3], "SELL")
        self.assertEqual(calls[1][0][1], "PE_SELL")

        # Call 2: BUY CE
        self.assertEqual(calls[2][0][3], "BUY")
        self.assertEqual(calls[2][0][1], "CE_BUY")

        # Call 3: SELL CE
        self.assertEqual(calls[3][0][3], "SELL")
        self.assertEqual(calls[3][0][1], "CE_SELL")

    @patch('nifty_sensex_algo.place_order')
    def test_exit_position(self, mock_place):
        mock_kite = MagicMock()
        pos = {
            "leg_name": "NIFTY PE",
            "sell_symbol": "PE_SELL",
            "sell_exchange": "NFO",
            "sell_qty": 50,
            "buy_symbol": "PE_BUY",
            "buy_exchange": "NFO",
            "buy_qty": 50,
            "exited": False
        }

        nifty_sensex_algo.exit_position(mock_kite, pos, reason="Test")

        self.assertTrue(pos["exited"])
        self.assertEqual(mock_place.call_count, 2)

        # First call: Buy back the sold option
        self.assertEqual(mock_place.call_args_list[0][0][3], "BUY")
        self.assertEqual(mock_place.call_args_list[0][0][1], "PE_SELL")

        # Second call: Sell the hedge option
        self.assertEqual(mock_place.call_args_list[1][0][3], "SELL")
        self.assertEqual(mock_place.call_args_list[1][0][1], "PE_BUY")

if __name__ == '__main__':
    unittest.main()
