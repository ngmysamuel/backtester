"""
System Integration Tests for Live Data Handler

These tests require:
- Internet connection
- Yahoo Finance websocket access
- Extended execution time (minutes)
- Run with: pytest tests/test_live_integration.py -m live_integration --tb=short

Usage:
    # Run only when network is available
    LIVE_INTEGRATION=1 pytest tests/test_live_integration.py

    # Skip live tests by default
    pytest tests/ --ignore=tests/test_live_integration.py
"""

import os
import pytest
import pandas as pd
from typer.testing import CliRunner
from backtester.cli import app


# @pytest.mark.skipif(
#     not os.getenv("LIVE_INTEGRATION"),
#     reason="Live integration tests require LIVE_INTEGRATION=1 and internet access"
# )
# @pytest.mark.live_integration
class TestLiveDataHandlerIntegration:
    """System integration tests for live data handler.

    These tests verify the live data handler works with real Yahoo Finance websockets.
    They are separate from unit/e2e tests due to network dependencies and execution time.
    """

    def test_live_data_collection(self):
        """Test that live data handler can collect real-time data."""
        runner = CliRunner()

        config_path = os.path.abspath("tests/test_data/test_config_live.yaml")
        output_path = os.path.join(os.path.dirname(config_path), "test_equity_curve_live.csv")

        # Run live backtest (this will take ~10 minutes)
        result = runner.invoke(app, [
            "run",
            "--data-source", "live",
            "--position-calc", "no_position_sizer",
            "--slippage", "no_slippage",
            "--config-path", config_path,
            "--output-path", output_path
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
        # if os.path.exists(output_path):
        #     os.remove(output_path)

    def test_live_data_structure(self):
        """Test that live data has proper structure."""
        runner = CliRunner()

        config_path = os.path.abspath("tests/test_data/test_config_live.yaml")
        output_path = os.path.join(os.path.dirname(config_path), "test_equity_curve_live.csv")

        result = runner.invoke(app, [
            "run",
            "--data-source", "live",
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


# Manual testing documentation
LIVE_TESTING_README = """
# Live Data Handler Testing

## Prerequisites
- Active internet connection
- Yahoo Finance websocket access
- Python environment with yfinance installed

## Running Tests
```bash
# Run live integration tests
LIVE_INTEGRATION=1 pytest tests/test_live_integration.py -v

# Run with shorter timeout for CI
LIVE_INTEGRATION=1 pytest tests/test_live_integration.py --timeout=900
```

## Manual Verification
1. Check websocket connection logs
2. Verify data collection rate (messages per interval)
3. Confirm bar aggregation accuracy
4. Validate threading behavior

## Troubleshooting
- Tests may fail during market closures
- Network interruptions can cause failures
- Rate limiting may occur with frequent testing
"""
