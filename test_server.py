#!/usr/bin/env python3
"""Test server startup."""
import asyncio
from pg2mcp.bridge import PostgresMCPBridge


async def test_server():
    """Test basic server initialization."""
    bridge = PostgresMCPBridge("example_config.yaml")
    
    try:
        await bridge.initialize()
        print("✅ Bridge initialized successfully!")
        
        # Check registered resources
        resources = bridge.resource_generator.get_resource_list()
        print(f"\n📊 Registered {len(resources)} resources:")
        for res in resources:
            print(f"  - {res['name']}")
        
        # Check registered tools
        tools = bridge.tool_generator.get_tool_list()
        print(f"\n🔧 Registered {len(tools)} tools:")
        for tool in tools[:5]:  # Show first 5
            print(f"  - {tool['name']}")
        if len(tools) > 5:
            print(f"  ... and {len(tools) - 5} more")
        
        print("\n✅ All components working!")
        
    finally:
        await bridge.cleanup()


if __name__ == '__main__':
    asyncio.run(test_server())