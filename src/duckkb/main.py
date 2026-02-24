import typer
from duckkb.mcp.server import mcp
from duckkb.config import settings
from duckkb.logger import setup_logging

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
