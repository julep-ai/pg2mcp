#!/usr/bin/env python3
"""Test database introspection."""
import asyncio
import asyncpg
from pg2mcp.introspector import DatabaseInspector


async def test_introspection():
    """Test the database introspector."""
    # Create connection pool
    pool = await asyncpg.create_pool(
        dsn="postgresql://db_admin:password@localhost:5432/postgres",
        min_size=2,
        max_size=5
    )
    
    try:
        inspector = DatabaseInspector(pool)
        
        # Test table introspection
        print("📊 Tables and Views:")
        tables = await inspector.get_tables()
        for table in tables:
            if table.schema == 'public':
                print(f"\n{table.type.upper()}: {table.full_name}")
                print(f"  Description: {table.description or 'No description'}")
                print("  Columns:")
                for col in table.columns:
                    nullable = "NULL" if col.is_nullable else "NOT NULL"
                    print(f"    - {col.name}: {col.data_type} {nullable}")
        
        # Test function introspection
        print("\n🔧 Functions:")
        functions = await inspector.get_functions()
        for func in functions:
            if func.schema == 'public':
                print(f"\nFUNCTION: {func.full_name}")
                print(f"  Returns: {func.return_type}")
                print(f"  Is aggregate: {func.is_aggregate}")
                if func.parameters:
                    print("  Parameters:")
                    for param in func.parameters:
                        default = " (has default)" if param.has_default else ""
                        print(f"    - {param.name}: {param.data_type} [{param.mode}]{default}")
        
        # Test pattern matching
        print("\n🔍 Pattern Matching Test:")
        filtered_tables = await inspector.filter_tables(['public.*'])
        print(f"Tables matching 'public.*': {len(filtered_tables)}")
        
        filtered_functions = await inspector.filter_functions(['public.get_user*', 'public.create_*'])
        print(f"Functions matching patterns: {len(filtered_functions)}")
        for func in filtered_functions:
            print(f"  - {func.full_name}")
        
    finally:
        await pool.close()


if __name__ == '__main__':
    asyncio.run(test_introspection())