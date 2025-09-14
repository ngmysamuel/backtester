from typer.testing import CliRunner
from backtester.cli import app

runner = CliRunner()

def test_run_command():
    result = runner.invoke(app, ["run", "--strategy", "my_strategy.py"])
    assert result.exit_code == 0
    assert "Running backtest for strategy: my_strategy.py" in result.output