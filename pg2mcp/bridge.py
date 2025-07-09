"""Main PostgreSQL to MCP Bridge class."""
import asyncio
import logging
from typing import Optional

import asyncpg
from fastmcp import FastMCP
import uvicorn
import structlog

from .config import Config, ConfigLoader
from .introspector import DatabaseInspector
from .resources import ResourceGenerator
from .tools import ToolGenerator


# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.dev.ConsoleRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


class PostgresMCPBridge:
    """Main bridge class that orchestrates the PostgreSQL to MCP conversion."""
    
    def __init__(self, config_path: str):
        self.config_path = config_path
        self.config: Optional[Config] = None
        self.pool: Optional[asyncpg.Pool] = None
        self.mcp: Optional[FastMCP] = None
        self.inspector: Optional[DatabaseInspector] = None
        self.resource_generator: Optional[ResourceGenerator] = None
        self.tool_generator: Optional[ToolGenerator] = None
        self._initialized = False
    
    async def initialize(self) -> None:
        """Initialize the bridge components."""
        if self._initialized:
            return
        
        logger.info("Initializing PostgreSQL to MCP Bridge", config_path=self.config_path)
        
        # Load configuration
        loader = ConfigLoader()
        self.config = loader.load(self.config_path)
        logger.info("Configuration loaded", server_name=self.config.server.name)
        
        # Create connection pool
        await self._create_pool()
        
        # Initialize MCP server
        self.mcp = FastMCP(
            name=self.config.server.name,
            instructions=self.config.server.description,
            version=self.config.server.version
        )
        
        # Initialize components
        self.inspector = DatabaseInspector(self.pool)
        self.resource_generator = ResourceGenerator(self.mcp, self.inspector, self.pool)
        self.tool_generator = ToolGenerator(self.mcp, self.inspector, self.pool)
        
        # Generate resources and tools
        await self._generate_components()
        
        self._initialized = True
        logger.info("Bridge initialized successfully")
    
    async def _create_pool(self) -> None:
        """Create the asyncpg connection pool."""
        logger.info("Creating database connection pool")
        
        try:
            self.pool = await asyncpg.create_pool(
                dsn=self.config.database.get_dsn(),
                min_size=self.config.database.pool_min_size,
                max_size=self.config.database.pool_max_size,
                timeout=self.config.database.pool_timeout,
                init=self._init_connection
            )
            logger.info(
                "Connection pool created",
                min_size=self.config.database.pool_min_size,
                max_size=self.config.database.pool_max_size
            )
        except Exception as e:
            logger.error("Failed to create connection pool", error=str(e))
            raise
    
    async def _init_connection(self, conn: asyncpg.Connection) -> None:
        """Initialize each connection in the pool."""
        # Set any connection-specific settings here
        await conn.execute("SET search_path TO public")
    
    async def _generate_components(self) -> None:
        """Generate MCP resources and tools from database objects."""
        logger.info("Generating MCP components from database objects")
        
        # Register resources
        if self.config.expose.resources:
            logger.info("Registering resources", count=len(self.config.expose.resources))
            await self.resource_generator.register_patterns(self.config.expose.resources)
            resource_count = len(self.resource_generator._registered_resources)
            logger.info(f"Registered {resource_count} resources")
        
        # Register tools
        if self.config.expose.tools:
            logger.info("Registering tools", count=len(self.config.expose.tools))
            await self.tool_generator.register_patterns(self.config.expose.tools)
            tool_count = len(self.tool_generator._registered_tools)
            logger.info(f"Registered {tool_count} tools")
    
    async def run(self) -> None:
        """Run the MCP server."""
        if not self._initialized:
            await self.initialize()
        
        logger.info(
            "Starting MCP server",
            host=self.config.server.host,
            port=self.config.server.port
        )
        
        # Create the ASGI app from FastMCP
        app = self.mcp.create_asgi_app()
        
        # Configure uvicorn
        config = uvicorn.Config(
            app,
            host=self.config.server.host,
            port=self.config.server.port,
            log_level="info"
        )
        
        # Run the server
        server = uvicorn.Server(config)
        await server.serve()
    
    async def cleanup(self) -> None:
        """Clean up resources."""
        logger.info("Cleaning up bridge resources")
        
        if self.pool:
            await self.pool.close()
            logger.info("Connection pool closed")
        
        self._initialized = False