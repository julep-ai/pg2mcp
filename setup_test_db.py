#!/usr/bin/env python3
"""Setup test database objects."""
import asyncio
import asyncpg


async def setup_test_db():
    """Create test tables and functions."""
    conn = await asyncpg.connect(
        host='localhost',
        port=5432,
        database='postgres',
        user='db_admin',
        password='password'
    )
    
    try:
        # Create a test table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                active BOOLEAN DEFAULT true,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print("✅ Created users table")
        
        # Insert some test data
        await conn.execute("""
            INSERT INTO users (name, email) VALUES
            ('Alice Smith', 'alice@example.com'),
            ('Bob Johnson', 'bob@example.com'),
            ('Charlie Brown', 'charlie@example.com')
            ON CONFLICT (email) DO NOTHING
        """)
        print("✅ Inserted test data")
        
        # Create a test function
        await conn.execute("""
            CREATE OR REPLACE FUNCTION get_user_by_email(user_email TEXT)
            RETURNS TABLE(id INTEGER, name TEXT, email TEXT, active BOOLEAN)
            AS $$
            BEGIN
                RETURN QUERY
                SELECT u.id, u.name, u.email, u.active
                FROM users u
                WHERE u.email = user_email;
            END;
            $$ LANGUAGE plpgsql;
        """)
        print("✅ Created get_user_by_email function")
        
        # Create another function with multiple parameters
        await conn.execute("""
            CREATE OR REPLACE FUNCTION create_user(
                user_name TEXT,
                user_email TEXT,
                is_active BOOLEAN DEFAULT true
            )
            RETURNS INTEGER
            AS $$
            DECLARE
                new_id INTEGER;
            BEGIN
                INSERT INTO users (name, email, active)
                VALUES (user_name, user_email, is_active)
                RETURNING id INTO new_id;
                
                RETURN new_id;
            END;
            $$ LANGUAGE plpgsql;
        """)
        print("✅ Created create_user function")
        
        # Create a view
        await conn.execute("""
            CREATE OR REPLACE VIEW active_users AS
            SELECT id, name, email, created_at
            FROM users
            WHERE active = true
        """)
        print("✅ Created active_users view")
        
        print("\n✅ Test database setup complete!")
        
    finally:
        await conn.close()


if __name__ == '__main__':
    asyncio.run(setup_test_db())