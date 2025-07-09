#!/usr/bin/env python3
"""Test MCP client for the PostgreSQL bridge."""
import asyncio
import json
import httpx
from typing import Dict, Any


class MCPClient:
    """Simple MCP client for testing."""
    
    def __init__(self, base_url: str = "http://localhost:8000/mcp"):
        self.base_url = base_url
        self.headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream"
        }
    
    async def make_request(self, method: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """Make an MCP request."""
        request_data = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params or {}
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/message",
                json=request_data,
                headers=self.headers,
                timeout=30.0
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                print(f"❌ Request failed: {response.status_code}")
                print(f"Response: {response.text}")
                return {"error": f"HTTP {response.status_code}"}
    
    async def list_tools(self) -> Dict[str, Any]:
        """List available tools."""
        return await self.make_request("tools/list")
    
    async def list_resources(self) -> Dict[str, Any]:
        """List available resources."""
        return await self.make_request("resources/list")
    
    async def call_tool(self, name: str, arguments: Dict[str, Any] = None) -> Dict[str, Any]:
        """Call a tool."""
        return await self.make_request("tools/call", {
            "name": name,
            "arguments": arguments or {}
        })
    
    async def read_resource(self, uri: str) -> Dict[str, Any]:
        """Read a resource."""
        return await self.make_request("resources/read", {
            "uri": uri
        })


async def test_pg2mcp():
    """Test the PostgreSQL MCP bridge."""
    print("🧪 Testing PostgreSQL MCP Bridge")
    print("=" * 50)
    
    client = MCPClient()
    
    # Test 1: List tools
    print("\n📋 Listing available tools...")
    tools_response = await client.list_tools()
    
    if "result" in tools_response:
        tools = tools_response["result"].get("tools", [])
        print(f"✅ Found {len(tools)} tools:")
        for tool in tools:
            print(f"   - {tool['name']}: {tool.get('description', 'No description')}")
    else:
        print(f"❌ Failed to list tools: {tools_response}")
        return
    
    # Test 2: List resources
    print("\n📊 Listing available resource templates...")
    resources_response = await client.list_resources()
    
    if "result" in resources_response:
        resources = resources_response["result"].get("resourceTemplates", [])
        print(f"✅ Found {len(resources)} resource templates:")
        for resource in resources:
            print(f"   - {resource['uriTemplate']}: {resource.get('name', 'No name')}")
    else:
        print(f"❌ Failed to list resources: {resources_response}")
    
    # Test 3: Call list_tables tool
    print("\n🔧 Calling 'list_tables' tool...")
    tables_response = await client.call_tool("list_tables")
    
    if "result" in tables_response:
        content = tables_response["result"].get("content", [])
        if content and isinstance(content[0].get("text"), str):
            tables = json.loads(content[0]["text"])
        else:
            tables = content
        
        print(f"✅ Found {len(tables)} tables:")
        for table in tables[:5]:  # Show first 5
            print(f"   - {table['schema']}.{table['name']} ({table['type']})")
        if len(tables) > 5:
            print(f"   ... and {len(tables) - 5} more")
    else:
        print(f"❌ Failed to call list_tables: {tables_response}")
    
    # Test 4: Read users table resource
    print("\n📊 Reading 'public.users' table resource...")
    users_response = await client.read_resource("table://public/users")
    
    if "result" in users_response:
        contents = users_response["result"].get("contents", [])
        if contents:
            data_text = contents[0].get("text", "{}")
            try:
                if isinstance(data_text, str):
                    data = json.loads(data_text)
                else:
                    data = data_text
                
                records = data.get("data", [])
                print(f"✅ Read {len(records)} records from users table:")
                for record in records:
                    print(f"   - {record}")
            except json.JSONDecodeError:
                print(f"❌ Failed to parse response: {data_text}")
        else:
            print(f"❌ No content in response: {users_response}")
    else:
        print(f"❌ Failed to read users table: {users_response}")
    
    # Test 5: Call get_user_by_email tool
    print("\n🔧 Testing 'get_user_by_email' tool...")
    user_response = await client.call_tool("get_user_by_email", {"email": "alice@example.com"})
    
    if "result" in user_response:
        content = user_response["result"].get("content", [])
        if content:
            result_text = content[0].get("text", "{}")
            try:
                if isinstance(result_text, str):
                    result = json.loads(result_text)
                else:
                    result = result_text
                print(f"✅ User lookup result: {result}")
            except json.JSONDecodeError:
                print(f"❌ Failed to parse result: {result_text}")
        else:
            print(f"❌ No content in response: {user_response}")
    else:
        print(f"❌ Failed to get user: {user_response}")
    
    print("\n✅ Testing complete!")


if __name__ == "__main__":
    asyncio.run(test_pg2mcp())