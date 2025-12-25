import os
import pandas as pd
import ast
import re
from typer.testing import CliRunner
from backtester.cli import app

runner = CliRunner()

def test_run_command():
    result = runner.invoke(app, ["run"]) # expected failure - missing required args
    assert result.exit_code == 2

def test_e2e_backtest():
    """End-to-end test: run backtest with CSV data and verify output CSV."""
    # Get absolute paths since CliRunner uses temp directory
    test_data_dir = os.path.abspath("tests/test_data")
    config_path = os.path.abspath("tests/test_data/test_config.yaml")
    output_path = os.path.join(test_data_dir, "test_equity_curve.csv")

    # Run the backtest
    result = runner.invoke(app, [
        "run",
        "--data-dir", test_data_dir,
        "--data-source", "csv",
        "--config-path", config_path,
        "--output-path", output_path
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
    time_diffs = df.index[1:] - df.index[:-1]
    assert all(diff in [pd.Timedelta('1d')] for diff in time_diffs), f"Timestamps not spaced by 1 day: {time_diffs}"

    # Check that we have the expected number of days
    assert len(df) == 26, f"Expected 26 days, got {len(df)}"

    # Check that equity_curve and returns columns always have values (no NaN)
    assert df["equity_curve"].notna().all(), "equity_curve column has NaN values"
    assert df["returns"].notna().all(), "returns column has NaN values"

    # Check that equity_curve is not flat (all values 1.0)
    assert not (df["equity_curve"] == 1.0).all(), "Equity curve is flat (all values are 1.0)"

    # Check that there is exactly 1 row with a value in the "order" column
    order_rows = df["order"].notna() & (df["order"] != "")
    assert order_rows.sum() == 1, f"Expected 1 row with order, got {order_rows.sum()}"

    # Check that the row with order also has slippage
    if order_rows.any():
        order_idx = order_rows.idxmax()  # get the index of the True value
        assert pd.notna(df.loc[order_idx, "slippage"]) and df.loc[order_idx, "slippage"] != "", "Row with order missing slippage value"

        # Parse slippage value and ensure it's not zero
        slippage_str = df.loc[order_idx, "slippage"]
        # Extract numeric value from slippage string (e.g., "0.0012 | " or similar)
        slippage_match = re.search(r'(\d+\.?\d*)', slippage_str)
        assert slippage_match, f"Could not parse slippage value from: {slippage_str}"
        slippage_value = float(slippage_match.group(1))
        assert slippage_value > 0.0, f"Slippage value should be > 0.0, got {slippage_value}"

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
    # os.remove(output_path)
