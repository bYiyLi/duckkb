import typer

from duckkb.logger import setup_logging
from duckkb.mcp.server import mcp

app = typer.Typer()


@app.callback()
def main(verbose: bool = False):
    """DuckKB CLI and MCP Server."""
    setup_logging()


@app.command()
def serve():
    """Start the MCP server."""
    mcp.run()


@app.command()
def version():
    """Show version."""
    print("DuckKB v0.1.0")


if __name__ == "__main__":
    app()
