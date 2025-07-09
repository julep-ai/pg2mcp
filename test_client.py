#!/usr/bin/env python3
"""Test client for the MCP server."""
import httpx
import asyncio
import json


async def test_mcp_server():
    """Test the MCP server endpoints."""
    base_url = "http://localhost:8000"
    
    async with httpx.AsyncClient() as client:
        # Test listing tools
        print("📋 Testing tool listing...")
        response = await client.post(
            f"{base_url}/mcp/v1/list_tools",
            json={}
        )
        if response.status_code == 200:
            tools = response.json()
            print(f"✅ Found {len(tools.get('tools', []))} tools:")
            for tool in tools.get('tools', []):
                print(f"   - {tool['name']}: {tool.get('description', 'No description')}")
        else:
            print(f"❌ Failed to list tools: {response.status_code}")
        
        # Test listing resources
        print("\n📋 Testing resource listing...")
        response = await client.post(
            f"{base_url}/mcp/v1/list_resources",
            json={}
        )
        if response.status_code == 200:
            resources = response.json()
            print(f"✅ Found {len(resources.get('resources', []))} resource templates")
        else:
            print(f"❌ Failed to list resources: {response.status_code}")
        
        # Test calling a tool
        print("\n🔧 Testing tool execution (list_tables)...")
        response = await client.post(
            f"{base_url}/mcp/v1/call_tool",
            json={
                "name": "list_tables",
                "arguments": {}
            }
        )
        if response.status_code == 200:
            result = response.json()
            tables = result.get('content', [])
            print(f"✅ Found {len(tables)} tables")
            for table in tables[:3]:
                print(f"   - {table['schema']}.{table['name']}")
        else:
            print(f"❌ Failed to call tool: {response.status_code}")
        
        # Test reading a resource
        print("\n📊 Testing resource reading (users table)...")
        response = await client.post(
            f"{base_url}/mcp/v1/read_resource",
            json={
                "uri": "table://public/users",
                "arguments": {"limit": 5}
            }
        )
        if response.status_code == 200:
            result = response.json()
            data = result.get('contents', [{}])[0].get('text', '{}')
            parsed = json.loads(data) if isinstance(data, str) else data
            print(f"✅ Read {parsed.get('count', 0)} records")
            for record in parsed.get('data', [])[:3]:
                print(f"   - {record}")
        else:
            print(f"❌ Failed to read resource: {response.status_code} - {response.text}")


if __name__ == "__main__":
    print("🧪 Testing PostgreSQL MCP Server...")
    print("=" * 50)
    asyncio.run(test_mcp_server())