
import unittest
from unittest.mock import MagicMock, patch
import datetime
import nifty_sensex_algo
import json
import os

class TestPositionalLogic(unittest.TestCase):

    def setUp(self):
        self.test_file = "test_positions.json"
        nifty_sensex_algo.POSITIONS_FILE = self.test_file

    def tearDown(self):
        if os.path.exists(self.test_file):
            os.remove(self.test_file)

    def test_save_load_positions(self):
        positions = [
            {
                "leg_name": "NIFTY PE",
                "entry_date": datetime.date(2023, 10, 23),
                "expiry_date": datetime.date(2023, 10, 24),
                "exited": False
            }
        ]
        nifty_sensex_algo.save_positions(positions)

        loaded = nifty_sensex_algo.load_positions()
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0]["leg_name"], "NIFTY PE")
        self.assertEqual(loaded[0]["entry_date"], "2023-10-23")

    @patch('nifty_sensex_algo.exit_position')
    def test_monitor_target_day1(self, mock_exit):
        today = datetime.date.today().strftime("%Y-%m-%d")
        positions = [{
            "leg_name": "NIFTY PE",
            "entry_date": today,
            "expiry_date": "2099-12-31",
            "sell_symbol": "PE",
            "sell_exchange": "NFO",
            "sell_entry_price": 100,
            "exited": False
        }]

        mock_kite = MagicMock()
        # LTP 39 (61% decay) should hit Day 1 target (60%)
        mock_kite.quote.return_value = {"NFO:PE": {"last_price": 39}}

        # We need to break the loop in monitor_and_exit
        # Since it's a while True, we'll mock time.sleep to return None (one loop) then raise an exception
        with patch('time.sleep', side_effect=[None, InterruptedError]):
            try:
                nifty_sensex_algo.monitor_and_exit(mock_kite, positions)
            except InterruptedError:
                pass

        mock_exit.assert_called_with(mock_kite, positions[0], reason="Target 60%")

    @patch('nifty_sensex_algo.exit_position')
    def test_monitor_target_day2(self, mock_exit):
        yesterday = (datetime.date.today() - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
        positions = [{
            "leg_name": "NIFTY PE",
            "entry_date": yesterday,
            "expiry_date": "2099-12-31",
            "sell_symbol": "PE",
            "sell_exchange": "NFO",
            "sell_entry_price": 100,
            "exited": False
        }]

        mock_kite = MagicMock()
        # LTP 30 (70% decay) should NOT hit Day 2 target (80%)
        mock_kite.quote.return_value = {"NFO:PE": {"last_price": 30}}

        with patch('time.sleep', side_effect=[None, InterruptedError]):
            try:
                nifty_sensex_algo.monitor_and_exit(mock_kite, positions)
            except InterruptedError:
                pass

        mock_exit.assert_not_called()

        # LTP 19 (81% decay) SHOULD hit Day 2 target (80%)
        mock_kite.quote.return_value = {"NFO:PE": {"last_price": 19}}
        with patch('time.sleep', side_effect=[None, InterruptedError]):
            try:
                nifty_sensex_algo.monitor_and_exit(mock_kite, positions)
            except InterruptedError:
                pass

        mock_exit.assert_called_with(mock_kite, positions[0], reason="Target 80%")

    @patch('nifty_sensex_algo.exit_position')
    @patch('nifty_sensex_algo.datetime')
    def test_expiry_exit_at_1430(self, mock_dt, mock_exit):
        mock_kite = MagicMock()
        expiry_today = datetime.date.today().strftime("%Y-%m-%d")
        positions = [{
            "leg_name": "NIFTY PE",
            "entry_date": "2023-10-23",
            "expiry_date": expiry_today,
            "sell_symbol": "PE",
            "sell_exchange": "NFO",
            "sell_entry_price": 100,
            "exited": False
        }]

        # Mock time as 2:31 PM (14:31) and today's date
        mock_dt.datetime.now.return_value.time.return_value = datetime.time(14, 31)
        mock_dt.date.today.return_value = datetime.date.today()
        mock_dt.datetime.strptime = datetime.datetime.strptime # keep real strptime
        mock_dt.time = datetime.time

        with patch('time.sleep', side_effect=[None, InterruptedError]):
            try:
                nifty_sensex_algo.monitor_and_exit(mock_kite, positions)
            except InterruptedError:
                pass

        mock_exit.assert_called_with(mock_kite, positions[0], reason="Expiry Day Auto Square Off")

if __name__ == '__main__':
    unittest.main()
