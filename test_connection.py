#!/usr/bin/env python3
"""Test database connection."""
import asyncio
import asyncpg


async def test_connection():
    """Test connection to PostgreSQL."""
    try:
        conn = await asyncpg.connect(
            host='localhost',
            port=5432,
            database='postgres',
            user='db_admin',
            password='password'
        )
        
        print("✅ Connected to PostgreSQL successfully!")
        
        # Test query
        version = await conn.fetchval('SELECT version()')
        print(f"PostgreSQL version: {version}")
        
        # Check for tables
        tables = await conn.fetch("""
            SELECT table_schema, table_name 
            FROM information_schema.tables 
            WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
            ORDER BY table_schema, table_name
        """)
        
        print(f"\nFound {len(tables)} tables:")
        for table in tables:
            print(f"  - {table['table_schema']}.{table['table_name']}")
        
        # Check for functions
        functions = await conn.fetch("""
            SELECT n.nspname as schema_name, p.proname as function_name
            FROM pg_proc p
            JOIN pg_namespace n ON p.pronamespace = n.oid
            WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
            ORDER BY n.nspname, p.proname
        """)
        
        print(f"\nFound {len(functions)} functions:")
        for func in functions:
            print(f"  - {func['schema_name']}.{func['function_name']}")
        
        await conn.close()
        
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return False
    
    return True


if __name__ == '__main__':
    asyncio.run(test_connection())