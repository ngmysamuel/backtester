from typer.testing import CliRunner

from backtester.cli import app

runner = CliRunner()

def test_run_command(self):
    """Test basic CLI functionality."""
    result = runner.invoke(app, ["run"])  # expected failure - missing required args
    assert result.exit_code == 2
