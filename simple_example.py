#!/usr/bin/env python3
"""Simple example of pg2mcp - MVP demonstration."""
import asyncio
import json
from typing import Dict, Any, List

import asyncpg
from fastmcp import FastMCP
import uvicorn

# Create the MCP server
mcp = FastMCP(
    name="PostgreSQL MCP Bridge Demo",
    instructions="Access PostgreSQL tables and functions via MCP"
)

# Global connection pool
pool = None


async def init_pool():
    """Initialize connection pool."""
    global pool
    pool = await asyncpg.create_pool(
        dsn="postgresql://db_admin:password@localhost:5432/postgres",
        min_size=2,
        max_size=10
    )


# Resource: Access tables
@mcp.resource("table://{schema}/{table}")
async def read_table(schema: str, table: str, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
    """Read data from a PostgreSQL table."""
    # Validate table exists
    async with pool.acquire() as conn:
        # Check if table exists
        exists = await conn.fetchval("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables 
                WHERE table_schema = $1 AND table_name = $2
            )
        """, schema, table)
        
        if not exists:
            raise ValueError(f"Table {schema}.{table} does not exist")
        
        # Get table data
        query = f"SELECT * FROM {schema}.{table} LIMIT {limit} OFFSET {offset}"
        rows = await conn.fetch(query)
        
        # Convert to list of dicts
        data = [dict(row) for row in rows]
        
        return {
            "table": f"{schema}.{table}",
            "count": len(data),
            "limit": limit,
            "offset": offset,
            "data": data
        }


# Tool: Get user by email (specific function)
@mcp.tool(name="get_user_by_email", description="Get user information by email address")
async def get_user_by_email(email: str) -> Dict[str, Any]:
    """Get user by email address."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM get_user_by_email($1)",
            email
        )
        
        if row:
            return dict(row)
        else:
            return {"error": f"No user found with email: {email}"}


# Tool: Create user
@mcp.tool(name="create_user", description="Create a new user")
async def create_user(name: str, email: str, active: bool = True) -> Dict[str, Any]:
    """Create a new user."""
    async with pool.acquire() as conn:
        try:
            user_id = await conn.fetchval(
                "SELECT create_user($1, $2, $3)",
                name, email, active
            )
            
            return {
                "success": True,
                "user_id": user_id,
                "message": f"User created with ID: {user_id}"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }


# Helper function to list tables
async def _list_tables() -> List[Dict[str, str]]:
    """List all available tables."""
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT table_schema, table_name, table_type
            FROM information_schema.tables
            WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
            ORDER BY table_schema, table_name
        """)
        
        return [
            {
                "schema": row["table_schema"],
                "name": row["table_name"],
                "type": row["table_type"],
                "resource_uri": f"table://{row['table_schema']}/{row['table_name']}"
            }
            for row in rows
        ]


# Tool: List tables
@mcp.tool(name="list_tables", description="List all tables in the database")
async def list_tables() -> List[Dict[str, str]]:
    """List all available tables."""
    return await _list_tables()


async def main():
    """Run the example server."""
    print("🐘 PostgreSQL to MCP Bridge - Simple Example")
    print("=" * 50)
    
    # Initialize connection pool
    print("Connecting to database...")
    await init_pool()
    print("✅ Connected!")
    
    # List available resources
    print("\n📊 Available Resources:")
    tables = await _list_tables()
    for table in tables[:5]:  # Show first 5
        print(f"  - {table['resource_uri']}")
    if len(tables) > 5:
        print(f"  ... and {len(tables) - 5} more")
    
    print("\n🔧 Available Tools:")
    print("  - list_tables: List all tables")
    print("  - get_user_by_email: Get user by email")
    print("  - create_user: Create new user")
    
    print("\n🚀 Starting MCP server on http://localhost:8000")
    print("=" * 50)
    
    # Run the server
    try:
        # Use FastMCP's built-in HTTP server
        await mcp.run_http_async(host="0.0.0.0", port=8000)
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())