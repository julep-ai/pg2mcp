#!/usr/bin/env python3
"""Test FastMCP resource registration."""
from fastmcp import FastMCP

# Create server
mcp = FastMCP("test-server")

# Try static resource
@mcp.resource("static://test")
async def static_resource():
    return {"test": "data"}

# Try parameterized resource
@mcp.resource("table://{table_name}")
async def table_resource(table_name: str):
    return {"table": table_name, "data": [1, 2, 3]}

# List resources
print("Resources registered:")
# Check if there's a way to list resources
print(dir(mcp))