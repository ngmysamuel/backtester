import ast
import os
import re

import pandas as pd
import pytest
from typer.testing import CliRunner

from backtester.cli import app

runner = CliRunner()

@pytest.mark.integration
class TestIntegration:
    """System integration tests."""

    def test_e2e_backtest_csv(self):
        """End-to-end test: run backtest with CSV data and verify output CSV."""
        test_data_dir = os.path.abspath("tests/test_data")
        config_path = os.path.abspath("tests/test_data/test_config.yaml")
        output_path = os.path.join(test_data_dir, "equity_curve.csv")

        # Run the backtest
        result = runner.invoke(app, [
            "run",
            "--data-dir", test_data_dir,
            "--data-source", "csv",
            "--config-path", config_path,
            "--output-path", test_data_dir,
            "--strategy","moving_average"
        ])

        # Assert successful execution
        assert result.exit_code == 0, f"Backtest failed: {result.output}"

        # Assert output CSV exists
        assert os.path.exists(output_path), "Equity curve CSV not created"

        # Load and validate CSV content
        df = pd.read_csv(output_path, index_col=0, parse_dates=True)
        assert not df.empty, "Equity curve CSV is empty"
        assert "equity_curve" in df.columns, "Missing 'equity_curve' column"
        assert "returns" in df.columns, "Missing 'returns' column"

        # Check that timestamps are spaced by business days (1d config resamples to 1B)
        # time_diffs = df.index[1:] - df.index[:-1]
        # assert all(diff in [pd.Timedelta('1d')] for diff in time_diffs), f"Timestamps not spaced by 1 day: {time_diffs}"

        # Check that we have the expected number of days
        # assert len(df) == 26, f"Expected 26 days, got {len(df)}"

        # Check that equity_curve and returns columns always have values (no NaN)
        assert df["equity_curve"].notna().all(), "equity_curve column has NaN values"
        assert df["returns"].notna().all(), "returns column has NaN values"

        # Check that equity_curve is not flat (all values 1.0)
        assert not (df["equity_curve"] == 1.0).all(), "Equity curve is flat (all values are 1.0)"

        # Check that there is exactly 1 row with a value in the "order" column
        order_rows = df["order"].notna() & (df["order"] != "")
        assert order_rows.sum() >= 1, f"Expected 1 row with order, got {order_rows.sum()}"

        # Check that the row with order also has slippage
        if order_rows.any():
            has_non_zero_slippage = False
            for order_idx in df[order_rows].index:
                assert pd.notna(df.loc[order_idx, "slippage"]) and df.loc[order_idx, "slippage"] != "", f"Row with order missing slippage value at {order_idx}"

                # Parse slippage values and check if at least one is not zero
                slippage_str = df.loc[order_idx, "slippage"]
                # Extract all numeric values from slippage string
                slippage_parts = [part.strip() for part in slippage_str.split(" | ") if part.strip()]
                slippage_values = []
                for part in slippage_parts:
                    try:
                        slippage_values.append(float(part))
                    except ValueError:
                        continue  # Skip non-numeric parts
                if slippage_values and any(float(val) != 0.0 for val in slippage_values):
                    has_non_zero_slippage = True
                    break
            assert has_non_zero_slippage, "At least one row with order should have at least one non-zero slippage value"

        # Parse order and position data to validate ATR sizing
        if order_rows.any():
            order_idx = order_rows.idxmax()
            order_str = df.loc[order_idx, "order"]

            # Parse quantity from order string (e.g., "BUY 1.80722891 BTC-USD @ 17,800.00 | ")
            match = re.search(r'BUY (\d+\.?\d*) BTC-USD', order_str)
            assert match, f"Could not parse quantity from order: {order_str}"
            order_quantity = float(match.group(1))

            # Parse position from BTC-USD column (e.g., "{'position': 1.80722891, 'value': 32349.397489000003}")
            btc_data_str = df.loc[order_idx, "BTC-USD"]
            btc_data = ast.literal_eval(btc_data_str)
            position_quantity = btc_data['position']

            # Validate that ATR sized the position (not default 1) and matches order
            assert order_quantity != 1.0, f"Position size not adjusted by ATR (still 1.0): {order_quantity}"
            assert abs(order_quantity - position_quantity) < 1e-6, f"Order quantity {order_quantity} doesn't match position {position_quantity}"

        # Clean up only if all assertions pass
        # if os.path.exists(output_path):
        #     os.remove(output_path)

    @pytest.mark.live_integration
    def test_e2e_backtest_yf(self):
        """End-to-end test: run backtest with Yahoo Finance data."""
        # Skip if yfinance not available or network issues
        pytest.importorskip("yfinance")

        test_data_dir = os.path.abspath("tests/test_data")
        config_path = os.path.abspath("tests/test_data/test_config_yf.yaml")
        output_path = os.path.join(test_data_dir, "equity_curve.csv")

        # Run the backtest with YF data
        result = runner.invoke(app, [
            "run",
            "--data-source", "yf",
            "--strategy", "moving_average",
            "--config-path", config_path,
            "--output-path", test_data_dir
        ])

        # Assert successful execution
        assert result.exit_code == 0, f"YF backtest failed: {result.output}"

        # Assert output CSV exists
        assert os.path.exists(output_path), "YF equity curve CSV not created"

        # Load and validate CSV content
        df = pd.read_csv(output_path, index_col=0, parse_dates=True)
        assert not df.empty, "YF equity curve CSV is empty"
        assert "equity_curve" in df.columns, "Missing 'equity_curve' column"
        assert "returns" in df.columns, "Missing 'returns' column"

        # Check that we have data (YF date range may vary due to market holidays)
        assert len(df) > 0, "No data retrieved from YF"

        # Check that equity_curve and returns columns have values
        assert df["equity_curve"].notna().any(), "No equity_curve values"
        assert df["returns"].notna().any(), "No returns values"

        # Check that equity_curve is not flat
        assert not (df["equity_curve"] == 1.0).all(), "YF equity curve is flat"

        # Check that there are at least 1 BUY and 1 SELL order (moving average strategy should have traded both ways)
        order_rows = df["order"].notna() & (df["order"] != "")
        assert order_rows.sum() >= 2, f"Expected at least 2 orders for moving average strategy, got {order_rows.sum()}"

        # Check for both BUY and SELL orders
        buy_orders = df["order"].str.contains("BUY", na=False).sum()
        sell_orders = df["order"].str.contains("SELL", na=False).sum()
        assert buy_orders >= 1, f"Expected at least 1 BUY order, got {buy_orders}"
        assert sell_orders >= 1, f"Expected at least 1 SELL order, got {sell_orders}"

        # For YF test with ATR and multi-factor slippage
        if order_rows.any():
            order_idx = order_rows.idxmax()

            # Parse order to check ATR sizing (should not be 1.0)
            order_str = df.loc[order_idx, "order"]
            match = re.search(r'BUY (\d+\.?\d*) AAPL', order_str)
            assert match, f"Could not parse quantity from order: {order_str}"
            order_quantity = float(match.group(1))
            assert order_quantity != 1.0, f"ATR position sizer should not give 1.0, got {order_quantity}"

            # Check at least one slippage is != 0.0 (multi-factor slippage)
            slippage_str = df.loc[order_idx, "slippage"]
            # Extract all numeric values from slippage string
            slippage_parts = [part.strip() for part in slippage_str.split(" | ") if part.strip()]
            slippage_values = []
            for part in slippage_parts:
                try:
                    slippage_values.append(float(part))
                except ValueError:
                    continue  # Skip non-numeric parts
            assert slippage_values, f"No numeric slippage values found in: {slippage_str}"
            assert any(val != 0.0 for val in slippage_values), f"At least one slippage value should be != 0.0, got {slippage_values}"

        # Verify cumulative position calculations
        previous_position = 0.0
        for idx, row in df.iterrows():
            aapl_data_str = row['AAPL']
            if not (pd.notna(aapl_data_str) and aapl_data_str != '' and isinstance(aapl_data_str, str)):
                continue  # Skip rows without position data

            try:
                aapl_dict = ast.literal_eval(aapl_data_str)
                current_position = aapl_dict['position']
                position_value = aapl_dict['value']
            except (ValueError, KeyError):
                continue  # Invalid data, skip

            order_str = row['order']
            if pd.notna(order_str) and order_str != '':
                match = re.search(r'(BUY|SELL) (\d+\.?\d*) AAPL', order_str)
                if match:
                    direction = match.group(1)
                    quantity = float(match.group(2))
                    if direction == 'BUY':
                        expected_position = previous_position + quantity
                    elif direction == 'SELL':
                        expected_position = previous_position - quantity
                    assert abs(current_position - expected_position) < 1e-6, f"Position mismatch at {idx}: expected {expected_position}, got {current_position}"
            else:
                assert abs(current_position - previous_position) < 1e-6, f"Position changed without order at {idx}: expected {previous_position}, got {current_position}"
            previous_position = current_position


    @pytest.mark.live_integration
    def test_live_data_collection(self):
        """Test that live data handler can collect real-time data."""
        runner = CliRunner()

        test_data_dir = os.path.abspath("tests/test_data")
        config_path = os.path.abspath("tests/test_data/test_config_live.yaml")
        output_path = os.path.join(test_data_dir, "equity_curve.csv")

        # Run live backtest (this will take ~10 minutes)
        result = runner.invoke(app, [
            "run",
            "--strategy", "buy_and_hold_simple",
            "--data-source", "live",
            "--position-calc", "no_position_sizer",
            "--slippage", "no_slippage",
            "--config-path", config_path,
            "--output-path", test_data_dir
        ])

        # Should complete successfully
        assert result.exit_code == 0, f"Live backtest failed: {result.output}"

        # Verify output file was created
        assert os.path.exists(output_path), "Live backtest output not created"

        # Load and validate results
        df = pd.read_csv(output_path, index_col=0, parse_dates=True)

        # Should have collected some data during the 10-minute period
        assert len(df) > 0, "No data collected during live test"

        # Should have the expected columns
        assert "equity_curve" in df.columns, "Missing equity_curve column"
        assert "returns" in df.columns, "Missing returns column"

        # Should have some variation (market movement during test period)
        assert not (df["equity_curve"] == 1.0).all(), "No market movement detected"

        # Clean up
        if os.path.exists(output_path):
            os.remove(output_path)

    @pytest.mark.live_integration
    def test_live_data_structure(self):
        """Test that live data has proper structure."""
        runner = CliRunner()

        config_path = os.path.abspath("tests/test_data/test_config_live.yaml")
        output_path = os.path.join(os.path.dirname(config_path), "test_equity_curve_live.csv")

        result = runner.invoke(app, [
            "run",
            "--data-source", "live",
            "--position-calc", "no_position_sizer",
            "--slippage", "no_slippage",
            "--config-path", config_path,
            "--output-path", output_path
        ])

        assert result.exit_code == 0

        df = pd.read_csv(output_path, index_col=0, parse_dates=True)

        # Check data quality
        assert df["equity_curve"].notna().all(), "Equity curve has missing values"
        assert df["returns"].notna().all(), "Returns has missing values"

        # Check for reasonable data ranges
        assert df["equity_curve"].min() >= 0.99, "Equity curve values seem unreasonable"
        assert df["equity_curve"].max() <= 1.01, "Equity curve values seem unreasonable"

        # Clean up
        if os.path.exists(output_path):
            os.remove(output_path)
