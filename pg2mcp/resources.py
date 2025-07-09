"""Resource generation for PostgreSQL tables and views."""
import json
from typing import List, Dict, Any, Optional
from urllib.parse import quote, unquote

import asyncpg
from fastmcp import FastMCP

from .config import ResourcePattern
from .introspector import DatabaseInspector, TableInfo
from .types import TypeConverter


class ResourceGenerator:
    """Generate MCP resources from PostgreSQL tables and views."""
    
    def __init__(self, mcp: FastMCP, inspector: DatabaseInspector, pool: asyncpg.Pool):
        self.mcp = mcp
        self.inspector = inspector
        self.pool = pool
        self._registered_resources = set()
        self._table_cache = {}  # Cache table info by name
    
    async def register_patterns(self, patterns: List[ResourcePattern]) -> None:
        """Register resource patterns with the MCP server."""
        # First, collect all tables we need to register
        tables_to_register = []
        
        for pattern in patterns:
            if pattern.pattern:
                # Pattern-based registration
                tables = await self.inspector.filter_tables([pattern.pattern])
                for table in tables:
                    tables_to_register.append((table, pattern))
            elif pattern.table or pattern.view:
                # Specific table/view registration
                all_tables = await self.inspector.get_tables()
                for table in all_tables:
                    if ((pattern.table and table.name == pattern.table and table.type == 'table') or
                        (pattern.view and table.name == pattern.view and table.type == 'view')):
                        tables_to_register.append((table, pattern))
        
        # Store tables in cache for later lookup
        for table, pattern in tables_to_register:
            cache_key = f"{table.schema}.{table.name}"
            self._table_cache[cache_key] = (table, pattern)
            self._registered_resources.add(f"table://{table.full_name}")
        
        # Register a single parameterized resource handler for all tables
        @self.mcp.resource("table://{schema}/{table}")
        async def handle_table_resource(schema: str, table: str, **kwargs) -> Dict[str, Any]:
            """Handle resource requests for tables."""
            cache_key = f"{schema}.{table}"
            
            if cache_key not in self._table_cache:
                raise ValueError(f"Table {cache_key} not found")
            
            table_info, pattern = self._table_cache[cache_key]
            
            # Generate schema for the table
            schema_def = TypeConverter.generate_table_schema(table_info.columns)
            
            # Parse query parameters
            limit = int(kwargs.get('limit', pattern.limit or 1000))
            offset = int(kwargs.get('offset', 0))
            where = kwargs.get('where', pattern.where)
            order_by = kwargs.get('order_by')
            
            # Build column list
            if pattern.columns:
                columns = [col for col in pattern.columns if col in [c.name for c in table_info.columns]]
            else:
                columns = [col.name for col in table_info.columns]
            
            # Build query
            query_parts = [
                f"SELECT {', '.join(columns)}",
                f"FROM {table_info.full_name}"
            ]
            
            # Add WHERE clause
            params = []
            if where:
                query_parts.append(f"WHERE {where}")
            
            # Add ORDER BY
            if order_by:
                query_parts.append(f"ORDER BY {order_by}")
            
            # Add pagination
            query_parts.append(f"LIMIT {limit} OFFSET {offset}")
            
            query = ' '.join(query_parts)
            
            # Execute query
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query, *params)
            
            # Convert rows to JSON-serializable format
            data = []
            for row in rows:
                data.append(dict(row))
            
            # Return the data directly - FastMCP will handle formatting
            return {
                "data": data,
                "metadata": {
                    "schema": schema_def,
                    "total_rows": len(data),
                    "limit": limit,
                    "offset": offset
                }
            }
    
    def get_resource_list(self) -> List[Dict[str, str]]:
        """Get list of registered resources for MCP resource listing."""
        resources = []
        for uri in self._registered_resources:
            # Extract table name from URI
            table_name = unquote(uri.replace("table://", ""))
            resources.append({
                "uri": uri,
                "name": table_name,
                "description": f"PostgreSQL table {table_name}",
                "mimeType": "application/json"
            })
        return resources