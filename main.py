#!/usr/bin/env python3
"""Main entry point for pg2mcp."""
import asyncio
import sys
from pathlib import Path

import click
import structlog

from pg2mcp.bridge import PostgresMCPBridge


logger = structlog.get_logger()


@click.command()
@click.option(
    '-c', '--config',
    type=click.Path(exists=True, path_type=Path),
    default='pg2mcp.yaml',
    help='Path to configuration file'
)
@click.option(
    '-v', '--verbose',
    is_flag=True,
    help='Enable verbose logging'
)
def main(config: Path, verbose: bool):
    """PostgreSQL to MCP Bridge - Expose PostgreSQL objects via MCP protocol."""
    # Configure logging level
    if verbose:
        logging_level = "DEBUG"
    else:
        logging_level = "INFO"
    
    structlog.configure(
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    
    # Print startup banner
    click.echo("🐘 PostgreSQL to MCP Bridge")
    click.echo(f"📋 Configuration: {config}")
    click.echo("")
    
    # Create and run the bridge
    bridge = PostgresMCPBridge(str(config))
    
    try:
        # Run the async main function
        asyncio.run(run_bridge(bridge))
    except KeyboardInterrupt:
        click.echo("\n⏹️  Shutting down...")
        sys.exit(0)
    except Exception as e:
        logger.error("Bridge failed", error=str(e), exc_info=True)
        click.echo(f"\n❌ Error: {e}", err=True)
        sys.exit(1)


async def run_bridge(bridge: PostgresMCPBridge):
    """Run the bridge with proper cleanup."""
    try:
        await bridge.initialize()
        await bridge.run()
    finally:
        await bridge.cleanup()


if __name__ == '__main__':
    main()