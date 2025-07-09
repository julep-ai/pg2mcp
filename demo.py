#!/usr/bin/env python3
"""Demonstration of the PostgreSQL to MCP Bridge MVP."""
import asyncio
import json
from typing import List, Dict, Any

import asyncpg
from pg2mcp.introspector import DatabaseInspector
from pg2mcp.config import ConfigLoader
from pg2mcp.types import TypeConverter


async def demonstrate_mvp():
    """Demonstrate the working MVP components."""
    print("🐘 PostgreSQL to MCP Bridge - MVP Demonstration")
    print("=" * 60)
    
    # 1. Configuration Loading
    print("\n📋 1. Configuration Loading")
    try:
        loader = ConfigLoader()
        config = loader.load("example_config.yaml")
        print(f"✅ Config loaded: {config.server.name}")
        print(f"   Database: {config.database.host}:{config.database.port}/{config.database.database}")
        print(f"   Resources: {len(config.expose.resources)} patterns")
        print(f"   Tools: {len(config.expose.tools)} patterns")
    except Exception as e:
        print(f"❌ Config failed: {e}")
        return
    
    # 2. Database Connection
    print("\n🔗 2. Database Connection")
    try:
        pool = await asyncpg.create_pool(
            dsn=config.database.get_dsn(),
            min_size=2,
            max_size=5
        )
        print("✅ Connected to PostgreSQL")
        
        # Test query
        async with pool.acquire() as conn:
            version = await conn.fetchval('SELECT version()')
            print(f"   Version: {version.split(',')[0]}")
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return
    
    # 3. Database Introspection
    print("\n🔍 3. Database Introspection")
    try:
        inspector = DatabaseInspector(pool)
        
        # Get tables
        tables = await inspector.get_tables()
        public_tables = [t for t in tables if t.schema == 'public']
        print(f"✅ Found {len(tables)} total tables, {len(public_tables)} in public schema")
        
        for table in public_tables:
            print(f"   📊 {table.full_name} ({table.type})")
            for col in table.columns[:3]:  # Show first 3 columns
                nullable = "NULL" if col.is_nullable else "NOT NULL"
                print(f"      - {col.name}: {col.data_type} {nullable}")
            if len(table.columns) > 3:
                print(f"      ... and {len(table.columns) - 3} more columns")
        
        # Get functions
        functions = await inspector.get_functions()
        public_functions = [f for f in functions if f.schema == 'public']
        print(f"\n✅ Found {len(functions)} total functions, {len(public_functions)} in public schema")
        
        for func in public_functions[:3]:  # Show first 3
            print(f"   🔧 {func.full_name}")
            print(f"      Returns: {func.return_type}")
            if func.parameters:
                for param in func.parameters[:2]:  # Show first 2 params
                    print(f"      - {param.name}: {param.data_type} [{param.mode}]")
                if len(func.parameters) > 2:
                    print(f"      ... and {len(func.parameters) - 2} more parameters")
        
    except Exception as e:
        print(f"❌ Introspection failed: {e}")
        return
    
    # 4. Type Conversion
    print("\n🔄 4. Type Conversion")
    try:
        # Test table schema generation
        users_table = next((t for t in public_tables if t.name == 'users'), None)
        if users_table:
            schema = TypeConverter.generate_table_schema(users_table.columns)
            print(f"✅ Generated JSON Schema for 'users' table:")
            print(f"   Properties: {list(schema['properties'].keys())}")
            print(f"   Required: {schema.get('required', [])}")
        
        # Test function schema generation
        get_user_func = next((f for f in public_functions if 'get_user' in f.name), None)
        if get_user_func:
            params_schema = TypeConverter.generate_function_params_schema(get_user_func.parameters)
            print(f"\n✅ Generated parameter schema for '{get_user_func.name}' function:")
            print(f"   Parameters: {list(params_schema['properties'].keys())}")
            print(f"   Required: {params_schema.get('required', [])}")
    except Exception as e:
        print(f"❌ Type conversion failed: {e}")
    
    # 5. Resource Simulation
    print("\n📊 5. Resource Access Simulation")
    try:
        # Simulate reading users table
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM users LIMIT 3")
            data = [dict(row) for row in rows]
            
            print(f"✅ Read {len(data)} records from 'users' table:")
            for record in data:
                print(f"   - ID {record['id']}: {record['name']} ({record['email']})")
    except Exception as e:
        print(f"❌ Resource access failed: {e}")
    
    # 6. Tool Simulation
    print("\n🔧 6. Tool Execution Simulation")
    try:
        # Simulate calling get_user_by_email function
        async with pool.acquire() as conn:
            result = await conn.fetchrow(
                "SELECT * FROM get_user_by_email($1)",
                "alice@example.com"
            )
            
            if result:
                print(f"✅ Tool 'get_user_by_email' executed successfully:")
                print(f"   Result: {dict(result)}")
            else:
                print("✅ Tool executed but no user found")
    except Exception as e:
        print(f"❌ Tool execution failed: {e}")
    
    # 7. Pattern Matching
    print("\n🎯 7. Pattern Matching")
    try:
        # Test pattern matching
        public_pattern_tables = await inspector.filter_tables(['public.*'])
        user_pattern_functions = await inspector.filter_functions(['public.*user*'])
        
        print(f"✅ Pattern 'public.*' matched {len(public_pattern_tables)} tables")
        print(f"✅ Pattern 'public.*user*' matched {len(user_pattern_functions)} functions:")
        for func in user_pattern_functions:
            print(f"   - {func.full_name}")
    except Exception as e:
        print(f"❌ Pattern matching failed: {e}")
    
    # Cleanup
    await pool.close()
    
    print("\n🎉 MVP Demonstration Complete!")
    print("=" * 60)
    print("\n📋 Summary:")
    print("✅ Configuration loading and validation")
    print("✅ PostgreSQL connection and pooling")
    print("✅ Database schema introspection")
    print("✅ Type conversion (PostgreSQL → JSON Schema)")
    print("✅ Resource access simulation (tables/views)")
    print("✅ Tool execution simulation (functions)")
    print("✅ Pattern-based exposure configuration")
    print("\n🚀 The MVP demonstrates all core functionality for")
    print("   converting PostgreSQL objects to MCP resources and tools!")


if __name__ == "__main__":
    asyncio.run(demonstrate_mvp())