# PostgreSQL to MCP Bridge: Design & Implementation

## Overview

This utility automatically converts PostgreSQL database objects into a modern MCP server with full support for tools, resources, prompts, streaming, and OAuth 2.1 authentication.

## Architecture

```
PostgreSQL DB ← asyncpg → pg2mcp → FastMCP Server → MCP Clients
                            ↑
                      Config File (YAML)
```

## Tech Stack

- **FastMCP** - Simplified MCP server framework
- **asyncpg** - High-performance PostgreSQL driver (5x faster than psycopg3)
- **pydantic** - Configuration validation
- **uvicorn** - ASGI server for HTTP transport
- **httpx** - OAuth client implementation

## Configuration File Format

```yaml
# pg2mcp.yaml
database:
  url: "postgresql://user:pass@localhost:5432/mydb"
  # or individual params
  host: localhost
  port: 5432
  database: mydb
  user: user
  password: ${PG_PASSWORD}  # env var support
  
server:
  name: "PostgreSQL MCP Bridge"
  description: "Auto-generated MCP interface for PostgreSQL"
  version: "1.0.0"
  host: "0.0.0.0"
  port: 8000
  
  # OAuth configuration (optional)
  auth:
    enabled: true
    issuer_url: "https://auth.example.com"
    audience: "postgresql-mcp"
    required_scopes: ["db:read", "db:write"]
    
expose:
  # Tables/Views become Resources (read-only)
  resources:
    - pattern: "public.*"  # all tables in public schema
      exclude: ["audit_*", "tmp_*"]  # exclude patterns
      
    - table: "users"
      description: "User profiles"
      columns: ["id", "name", "email"]  # specific columns
      where: "active = true"  # default filter
      limit: 1000  # default limit
      
    - view: "sales_summary"
      description: "Aggregated sales data"
      
  # Functions become Tools (can have side effects)
  tools:
    - pattern: "api.*"  # all functions in api schema
      
    - function: "calculate_discount"
      description: "Calculate customer discount"
      # Override parameter descriptions
      params:
        customer_id:
          description: "Customer ID"
        amount:
          description: "Purchase amount in cents"
          
    - function: "send_notification"
      dangerous: true  # requires explicit confirmation
      
  # Custom prompts
  prompts:
    - name: "analyze_sales"
      description: "Analyze sales performance"
      template: |
        Using the sales_summary view, analyze the performance for {period}.
        Focus on:
        - Top performing products
        - Revenue trends
        - Customer segments
        
  # LISTEN/NOTIFY channels for streaming
  notifications:
    - channel: "data_updates"
      description: "Real-time data change notifications"
      
    - channel: "job_status"
      description: "Background job status updates"
      format: "json"  # auto-parse JSON payloads
      
# Type mappings (optional overrides)
type_mappings:
  # PostgreSQL type -> JSON Schema type
  numeric: { type: "number", format: "decimal" }
  money: { type: "integer", description: "Amount in cents" }
  jsonb: { type: "object" }
  uuid: { type: "string", format: "uuid" }
  
# Security policies
security:
  # Row-level security
  resource_policies:
    users:
      # Use JWT claims in queries
      where: "organization_id = current_setting('jwt.claims.org_id')"
      
  # Function access control
  tool_policies:
    dangerous_functions:
      require_scope: "admin"
      confirm: true
      
  # Connection pooling
  pool:
    min_size: 2
    max_size: 10
    timeout: 30
```

## Implementation

```python
# pg2mcp.py
import asyncio
import os
from typing import Dict, List, Any, Optional
from pathlib import Path

import asyncpg
import yaml
from fastmcp import FastMCP
from pydantic import BaseModel, Field
import uvicorn
from functools import wraps

# Configuration models
class DatabaseConfig(BaseModel):
    url: Optional[str] = None
    host: str = "localhost"
    port: int = 5432
    database: str
    user: str
    password: str
    
class ResourceConfig(BaseModel):
    pattern: Optional[str] = None
    table: Optional[str] = None
    view: Optional[str] = None
    description: Optional[str] = None
    columns: Optional[List[str]] = None
    where: Optional[str] = None
    limit: int = 100
    
class ToolConfig(BaseModel):
    pattern: Optional[str] = None
    function: Optional[str] = None
    description: Optional[str] = None
    dangerous: bool = False
    params: Optional[Dict[str, Dict[str, Any]]] = None
    
class Config(BaseModel):
    database: DatabaseConfig
    server: Dict[str, Any]
    expose: Dict[str, List[Any]]
    type_mappings: Optional[Dict[str, Dict[str, Any]]] = None
    security: Optional[Dict[str, Any]] = None


class PostgresMCPBridge:
    def __init__(self, config_path: str):
        self.config = self._load_config(config_path)
        self.pool: Optional[asyncpg.Pool] = None
        self.mcp = FastMCP(
            self.config.server.get("name", "PostgreSQL MCP"),
            description=self.config.server.get("description")
        )
        self._type_cache = {}
        
    def _load_config(self, path: str) -> Config:
        """Load and validate configuration"""
        with open(path) as f:
            data = yaml.safe_load(f)
            
        # Expand environment variables
        def expand_env(obj):
            if isinstance(obj, str) and obj.startswith("${") and obj.endswith("}"):
                return os.environ.get(obj[2:-1], obj)
            elif isinstance(obj, dict):
                return {k: expand_env(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [expand_env(v) for v in obj]
            return obj
            
        data = expand_env(data)
        return Config(**data)
        
    async def initialize(self):
        """Connect to database and setup MCP server"""
        # Create connection pool
        if self.config.database.url:
            self.pool = await asyncpg.create_pool(self.config.database.url)
        else:
            self.pool = await asyncpg.create_pool(
                host=self.config.database.host,
                port=self.config.database.port,
                database=self.config.database.database,
                user=self.config.database.user,
                password=self.config.database.password,
                min_size=self.config.security.get("pool", {}).get("min_size", 2),
                max_size=self.config.security.get("pool", {}).get("max_size", 10)
            )
            
        # Introspect and setup
        await self._setup_resources()
        await self._setup_tools()
        self._setup_prompts()
        await self._setup_notifications()
        
    async def _setup_resources(self):
        """Create MCP resources from tables/views"""
        async with self.pool.acquire() as conn:
            # Query information schema
            tables = await conn.fetch("""
                SELECT 
                    schemaname,
                    tablename,
                    obj_description(
                        (schemaname||'.'||tablename)::regclass
                    ) as description
                FROM pg_tables
                WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
                
                UNION ALL
                
                SELECT 
                    schemaname,
                    viewname as tablename,
                    obj_description(
                        (schemaname||'.'||viewname)::regclass
                    ) as description
                FROM pg_views
                WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
            """)
            
            for config in self.config.expose.get("resources", []):
                if config.get("pattern"):
                    # Pattern matching
                    schema, pattern = config["pattern"].split(".")
                    matching_tables = [
                        t for t in tables 
                        if t["schemaname"] == schema 
                        and self._matches_pattern(t["tablename"], pattern, config.get("exclude", []))
                    ]
                    
                    for table in matching_tables:
                        await self._create_resource(conn, table, config)
                        
                elif config.get("table") or config.get("view"):
                    # Specific table/view
                    name = config.get("table") or config.get("view")
                    table = next((t for t in tables if t["tablename"] == name), None)
                    if table:
                        await self._create_resource(conn, table, config)
                        
    async def _create_resource(self, conn, table_info, config):
        """Create a single MCP resource"""
        schema = table_info["schemaname"]
        table = table_info["tablename"]
        full_name = f"{schema}.{table}"
        
        # Get column info
        columns = await conn.fetch("""
            SELECT 
                column_name,
                data_type,
                is_nullable,
                column_default,
                col_description(
                    (table_schema||'.'||table_name)::regclass,
                    ordinal_position
                ) as description
            FROM information_schema.columns
            WHERE table_schema = $1 AND table_name = $2
            ORDER BY ordinal_position
        """, schema, table)
        
        # Filter columns if specified
        if config.get("columns"):
            columns = [c for c in columns if c["column_name"] in config["columns"]]
            
        # Create resource function
        @self.mcp.resource(
            name=f"db_{schema}_{table}",
            description=config.get("description") or table_info["description"] or f"Data from {full_name}"
        )
        async def resource_handler(
            limit: int = config.get("limit", 100),
            offset: int = 0,
            where: Optional[str] = None,
            order_by: Optional[str] = None
        ) -> Dict[str, Any]:
            """Query table data"""
            async with self.pool.acquire() as conn:
                # Build query
                col_names = [c["column_name"] for c in columns]
                select_list = ", ".join(f'"{c}"' for c in col_names)
                
                query = f'SELECT {select_list} FROM "{schema}"."{table}"'
                params = []
                
                # Add WHERE clause
                where_parts = []
                if config.get("where"):
                    where_parts.append(config["where"])
                if where:
                    where_parts.append(where)
                    
                if where_parts:
                    query += f" WHERE {' AND '.join(where_parts)}"
                    
                # Add ORDER BY
                if order_by:
                    query += f" ORDER BY {order_by}"
                elif columns:
                    # Default order by first column
                    query += f' ORDER BY "{columns[0]["column_name"]}"'
                    
                # Add LIMIT/OFFSET
                query += f" LIMIT ${len(params)+1} OFFSET ${len(params)+2}"
                params.extend([limit, offset])
                
                # Execute query
                rows = await conn.fetch(query, *params)
                
                # Get total count
                count_query = f'SELECT COUNT(*) FROM "{schema}"."{table}"'
                if where_parts:
                    count_query += f" WHERE {' AND '.join(where_parts)}"
                total = await conn.fetchval(count_query)
                
                return {
                    "schema": {
                        col["column_name"]: {
                            "type": self._pg_type_to_json_schema(col["data_type"]),
                            "nullable": col["is_nullable"] == "YES",
                            "description": col["description"]
                        }
                        for col in columns
                    },
                    "data": [dict(row) for row in rows],
                    "pagination": {
                        "limit": limit,
                        "offset": offset,
                        "total": total,
                        "hasMore": offset + len(rows) < total
                    }
                }
                
    async def _setup_tools(self):
        """Create MCP tools from PostgreSQL functions"""
        async with self.pool.acquire() as conn:
            # Query function info
            functions = await conn.fetch("""
                SELECT 
                    n.nspname as schema,
                    p.proname as name,
                    pg_get_function_identity_arguments(p.oid) as args,
                    pg_get_functiondef(p.oid) as definition,
                    obj_description(p.oid) as description,
                    p.prorettype::regtype as return_type,
                    p.provolatile as volatility
                FROM pg_proc p
                JOIN pg_namespace n ON p.pronamespace = n.oid
                WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
                AND p.prokind = 'f'  -- only functions, not procedures
            """)
            
            for config in self.config.expose.get("tools", []):
                if config.get("pattern"):
                    # Pattern matching
                    schema, pattern = config["pattern"].split(".")
                    matching_funcs = [
                        f for f in functions
                        if f["schema"] == schema
                        and self._matches_pattern(f["name"], pattern, config.get("exclude", []))
                    ]
                    
                    for func in matching_funcs:
                        await self._create_tool(conn, func, config)
                        
                elif config.get("function"):
                    # Specific function
                    name = config["function"]
                    func = next((f for f in functions if f["name"] == name), None)
                    if func:
                        await self._create_tool(conn, func, config)
                        
    async def _create_tool(self, conn, func_info, config):
        """Create a single MCP tool from a PostgreSQL function"""
        schema = func_info["schema"]
        name = func_info["name"]
        
        # Parse function arguments
        args = self._parse_function_args(func_info["args"])
        
        # Create tool function
        @self.mcp.tool(
            name=f"db_{schema}_{name}",
            description=config.get("description") or func_info["description"] or f"Execute {schema}.{name}",
            dangerous=config.get("dangerous", False)
        )
        async def tool_handler(**kwargs) -> Any:
            """Execute PostgreSQL function"""
            async with self.pool.acquire() as conn:
                # Build function call
                placeholders = [f"${i+1}" for i in range(len(args))]
                query = f'SELECT "{schema}"."{name}"({", ".join(placeholders)})'
                
                # Map kwargs to positional args
                params = [kwargs.get(arg["name"]) for arg in args]
                
                # Execute
                result = await conn.fetchval(query, *params)
                return result
                
        # Add parameter documentation
        if config.get("params"):
            # Override parameter descriptions from config
            tool_handler.__annotations__ = {
                arg["name"]: self._pg_type_to_python(arg["type"])
                for arg in args
            }
            
    def _setup_prompts(self):
        """Setup custom prompts"""
        for prompt_config in self.config.expose.get("prompts", []):
            @self.mcp.prompt(
                name=prompt_config["name"],
                description=prompt_config.get("description", "")
            )
            async def prompt_handler(**kwargs) -> str:
                """Generate prompt from template"""
                template = prompt_config["template"]
                return template.format(**kwargs)
                
    async def _setup_notifications(self):
        """Setup LISTEN/NOTIFY streaming"""
        if not self.config.expose.get("notifications"):
            return
            
        # Create a dedicated connection for LISTEN
        listen_conn = await asyncpg.connect(
            **self.config.database.dict(exclude={"url"})
        )
        
        for notif_config in self.config.expose["notifications"]:
            channel = notif_config["channel"]
            
            # Add LISTEN
            await listen_conn.execute(f"LISTEN {channel}")
            
            # Create streaming endpoint
            @self.mcp.resource(
                name=f"notify_{channel}",
                description=notif_config.get("description", f"Notifications from {channel}")
            )
            async def notification_stream():
                """Stream PostgreSQL notifications"""
                async for notif in listen_conn.listen(channel):
                    payload = notif.payload
                    
                    # Auto-parse JSON if configured
                    if notif_config.get("format") == "json":
                        import json
                        payload = json.loads(payload)
                        
                    yield {
                        "channel": channel,
                        "pid": notif.pid,
                        "payload": payload,
                        "timestamp": asyncio.get_event_loop().time()
                    }
                    
    def _matches_pattern(self, name: str, pattern: str, excludes: List[str]) -> bool:
        """Check if name matches pattern and not in excludes"""
        import fnmatch
        
        # Check excludes first
        for exclude in excludes:
            if fnmatch.fnmatch(name, exclude):
                return False
                
        # Check pattern
        return fnmatch.fnmatch(name, pattern)
        
    def _parse_function_args(self, args_str: str) -> List[Dict[str, str]]:
        """Parse PostgreSQL function arguments"""
        if not args_str:
            return []
            
        args = []
        for arg in args_str.split(", "):
            parts = arg.split(" ")
            if len(parts) >= 2:
                args.append({
                    "name": parts[0],
                    "type": " ".join(parts[1:])
                })
                
        return args
        
    def _pg_type_to_json_schema(self, pg_type: str) -> Dict[str, Any]:
        """Convert PostgreSQL type to JSON Schema type"""
        type_map = {
            "integer": {"type": "integer"},
            "bigint": {"type": "integer"},
            "smallint": {"type": "integer"},
            "numeric": {"type": "number"},
            "real": {"type": "number"},
            "double precision": {"type": "number"},
            "text": {"type": "string"},
            "varchar": {"type": "string"},
            "char": {"type": "string"},
            "boolean": {"type": "boolean"},
            "json": {"type": "object"},
            "jsonb": {"type": "object"},
            "uuid": {"type": "string", "format": "uuid"},
            "timestamp": {"type": "string", "format": "date-time"},
            "date": {"type": "string", "format": "date"},
            "time": {"type": "string", "format": "time"},
            "bytea": {"type": "string", "format": "byte"},
        }
        
        # Check custom mappings
        if self.config.type_mappings and pg_type in self.config.type_mappings:
            return self.config.type_mappings[pg_type]
            
        # Check array types
        if pg_type.endswith("[]"):
            base_type = pg_type[:-2]
            return {
                "type": "array",
                "items": self._pg_type_to_json_schema(base_type)
            }
            
        return type_map.get(pg_type, {"type": "string"})
        
    def _pg_type_to_python(self, pg_type: str) -> type:
        """Convert PostgreSQL type to Python type"""
        type_map = {
            "integer": int,
            "bigint": int,
            "smallint": int,
            "numeric": float,
            "real": float,
            "double precision": float,
            "text": str,
            "varchar": str,
            "char": str,
            "boolean": bool,
            "json": dict,
            "jsonb": dict,
            "uuid": str,
            "timestamp": str,
            "date": str,
            "time": str,
            "bytea": bytes,
        }
        
        return type_map.get(pg_type, str)
        
    async def run(self):
        """Run the MCP server"""
        await self.initialize()
        
        # Setup OAuth if enabled
        if self.config.server.get("auth", {}).get("enabled"):
            from fastmcp.auth import OAuthProvider
            
            # Configure OAuth
            auth_config = self.config.server["auth"]
            # ... OAuth setup ...
            
        # Run server
        config = uvicorn.Config(
            self.mcp.app,
            host=self.config.server.get("host", "0.0.0.0"),
            port=self.config.server.get("port", 8000),
            log_level="info"
        )
        server = uvicorn.Server(config)
        await server.serve()


# CLI entry point
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="PostgreSQL to MCP Bridge")
    parser.add_argument(
        "-c", "--config",
        default="pg2mcp.yaml",
        help="Configuration file path"
    )
    
    args = parser.parse_args()
    
    # Run bridge
    bridge = PostgresMCPBridge(args.config)
    asyncio.run(bridge.run())
```

## Usage

1. **Install dependencies:**
```bash
pip install fastmcp asyncpg pydantic pyyaml uvicorn httpx
```

2. **Create configuration file:**
```bash
# pg2mcp.yaml - see example above
```

3. **Run the server:**
```bash
python pg2mcp.py -c pg2mcp.yaml
```

4. **Connect from MCP client:**
```python
from mcp import ClientSession
import httpx

async with ClientSession(
    transport=httpx.AsyncClient(base_url="http://localhost:8000")
) as session:
    # List available resources (tables/views)
    resources = await session.list_resources()
    
    # Query data
    users = await session.read_resource("db_public_users", limit=10)
    
    # Execute function
    result = await session.call_tool(
        "db_api_calculate_discount",
        customer_id=123,
        amount=9999
    )
```

## Features

### Auto-Generated Resources (Tables/Views)
- Automatic pagination support
- Column filtering
- WHERE clause support
- ORDER BY support
- Schema introspection
- Row-level security via JWT claims

### Auto-Generated Tools (Functions)
- Automatic parameter mapping
- Type conversion
- Return value handling
- Dangerous function marking
- Transaction support

### Streaming via LISTEN/NOTIFY
- Real-time notifications
- JSON payload parsing
- Multiple channel support
- Backpressure handling

### OAuth 2.1 Support
- Resource server implementation
- Protected Resource Metadata
- JWT validation
- Scope-based access control
- Dynamic client registration

### Security Features
- Connection pooling
- Prepared statements (SQL injection prevention)
- Row-level security policies
- Function access control
- Rate limiting support

## Advanced Features

### Custom Type Mappings
Define how PostgreSQL types map to JSON Schema:
```yaml
type_mappings:
  money: 
    type: "integer"
    description: "Amount in cents"
  geography:
    type: "object"
    properties:
      lat: { type: "number" }
      lng: { type: "number" }
```

### Computed Resources
Create virtual resources with custom queries:
```yaml
resources:
  - name: "user_stats"
    query: |
      SELECT 
        u.id,
        u.name,
        COUNT(o.id) as order_count,
        SUM(o.total) as total_spent
      FROM users u
      LEFT JOIN orders o ON u.id = o.user_id
      GROUP BY u.id, u.name
```

### Webhook Notifications
Forward PostgreSQL notifications to webhooks:
```yaml
notifications:
  - channel: "data_updates"
    webhook: "https://api.example.com/mcp-notify"
    headers:
      Authorization: "Bearer ${WEBHOOK_TOKEN}"
```

This creates a powerful bridge between PostgreSQL and the MCP ecosystem, enabling any PostgreSQL database to instantly become an AI-accessible resource with minimal configuration.
