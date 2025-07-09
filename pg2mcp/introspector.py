"""Database introspection for discovering PostgreSQL objects."""
import re
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass

import asyncpg


@dataclass
class ColumnInfo:
    """Information about a table/view column."""
    name: str
    data_type: str
    is_nullable: bool
    ordinal_position: int
    default_value: Optional[str] = None


@dataclass
class TableInfo:
    """Information about a table or view."""
    schema: str
    name: str
    type: str  # 'table' or 'view'
    columns: List[ColumnInfo]
    description: Optional[str] = None
    
    @property
    def full_name(self) -> str:
        return f"{self.schema}.{self.name}"


@dataclass
class ParameterInfo:
    """Information about a function parameter."""
    name: str
    data_type: str
    mode: str  # 'IN', 'OUT', 'INOUT'
    position: int
    has_default: bool = False


@dataclass
class FunctionInfo:
    """Information about a PostgreSQL function."""
    schema: str
    name: str
    parameters: List[ParameterInfo]
    return_type: str
    is_aggregate: bool
    description: Optional[str] = None
    
    @property
    def full_name(self) -> str:
        return f"{self.schema}.{self.name}"


class DatabaseInspector:
    """Introspect PostgreSQL database schema."""
    
    # Query to get tables and views with columns
    TABLES_QUERY = """
    SELECT 
        t.table_schema,
        t.table_name,
        t.table_type,
        obj_description(pgc.oid, 'pg_class') as table_description,
        json_agg(
            json_build_object(
                'name', c.column_name,
                'data_type', c.data_type,
                'is_nullable', c.is_nullable = 'YES',
                'ordinal_position', c.ordinal_position,
                'default_value', c.column_default
            ) ORDER BY c.ordinal_position
        ) as columns
    FROM information_schema.tables t
    JOIN information_schema.columns c 
        ON t.table_schema = c.table_schema 
        AND t.table_name = c.table_name
    LEFT JOIN pg_catalog.pg_class pgc 
        ON pgc.relname = t.table_name
        AND pgc.relnamespace = (
            SELECT oid FROM pg_namespace WHERE nspname = t.table_schema
        )
    WHERE t.table_schema NOT IN ('pg_catalog', 'information_schema')
        AND t.table_type IN ('BASE TABLE', 'VIEW')
        AND ($1::text IS NULL OR t.table_schema ~ $1)
    GROUP BY t.table_schema, t.table_name, t.table_type, pgc.oid
    ORDER BY t.table_schema, t.table_name
    """
    
    # Query to get functions
    FUNCTIONS_QUERY = """
    WITH function_args AS (
        SELECT 
            n.nspname as schema_name,
            p.proname as function_name,
            p.pronargs as num_args,
            p.proargtypes,
            p.proargnames,
            p.proargmodes,
            p.prorettype,
            p.prokind = 'a' as is_aggregate,
            obj_description(p.oid, 'pg_proc') as function_description,
            pg_get_function_arguments(p.oid) as args_signature,
            pg_get_function_result(p.oid) as return_signature
        FROM pg_proc p
        JOIN pg_namespace n ON p.pronamespace = n.oid
        WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
            AND p.prokind IN ('f', 'a')  -- functions and aggregates only
            AND ($1::text IS NULL OR n.nspname ~ $1)
    )
    SELECT 
        schema_name,
        function_name,
        num_args,
        args_signature,
        return_signature,
        proargtypes::oid[] as arg_types,
        proargnames::text[] as arg_names,
        proargmodes::text[] as arg_modes,
        is_aggregate,
        function_description
    FROM function_args
    ORDER BY schema_name, function_name
    """
    
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool
        self._cache = {}
    
    async def get_tables(self, pattern: Optional[str] = None) -> List[TableInfo]:
        """Get all tables and views matching the pattern."""
        cache_key = f"tables_{pattern}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(self.TABLES_QUERY, pattern)
            
        tables = []
        for row in rows:
            # Parse JSON column data
            import json
            columns_data = json.loads(row['columns']) if isinstance(row['columns'], str) else row['columns']
            
            columns = [
                ColumnInfo(
                    name=col['name'],
                    data_type=col['data_type'],
                    is_nullable=col['is_nullable'],
                    ordinal_position=col['ordinal_position'],
                    default_value=col['default_value']
                )
                for col in columns_data
            ]
            
            table = TableInfo(
                schema=row['table_schema'],
                name=row['table_name'],
                type='table' if row['table_type'] == 'BASE TABLE' else 'view',
                columns=columns,
                description=row['table_description']
            )
            tables.append(table)
        
        self._cache[cache_key] = tables
        return tables
    
    async def get_functions(self, pattern: Optional[str] = None) -> List[FunctionInfo]:
        """Get all functions matching the pattern."""
        cache_key = f"functions_{pattern}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(self.FUNCTIONS_QUERY, pattern)
        
        functions = []
        for row in rows:
            # Parse parameters from the signature
            parameters = self._parse_function_params(
                row['args_signature'],
                row['arg_names'],
                row['arg_modes']
            )
            
            function = FunctionInfo(
                schema=row['schema_name'],
                name=row['function_name'],
                parameters=parameters,
                return_type=row['return_signature'],
                is_aggregate=row['is_aggregate'],
                description=row['function_description']
            )
            functions.append(function)
        
        self._cache[cache_key] = functions
        return functions
    
    def _parse_function_params(
        self, 
        signature: str, 
        names: Optional[List[str]], 
        modes: Optional[List[str]]
    ) -> List[ParameterInfo]:
        """Parse function parameters from PostgreSQL signature."""
        if not signature:
            return []
        
        # Simple regex-based parser for common cases
        # Format: "param_name type, param_name type DEFAULT value"
        params = []
        param_parts = signature.split(', ')
        
        for i, part in enumerate(param_parts):
            # Check for parameter mode (IN, OUT, INOUT)
            mode = 'IN'
            if modes and i < len(modes):
                mode = modes[i] or 'IN'
            
            # Parse parameter
            has_default = ' DEFAULT ' in part
            if has_default:
                part = part.split(' DEFAULT ')[0]
            
            # Split name and type
            parts = part.strip().split(' ', 1)
            if len(parts) == 2:
                name, data_type = parts
            else:
                # Sometimes parameters don't have names
                name = f"param_{i+1}"
                data_type = parts[0]
            
            params.append(ParameterInfo(
                name=name.strip(),
                data_type=data_type.strip(),
                mode=mode.upper(),
                position=i + 1,
                has_default=has_default
            ))
        
        return params
    
    def match_pattern(self, full_name: str, pattern: str) -> bool:
        """Check if a table/function name matches a pattern."""
        if '*' in pattern:
            # Convert simple glob pattern to regex
            regex_pattern = pattern.replace('.', r'\.').replace('*', '.*')
            return bool(re.match(f"^{regex_pattern}$", full_name))
        else:
            return full_name == pattern
    
    async def filter_tables(self, patterns: List[str]) -> List[TableInfo]:
        """Get tables matching any of the patterns."""
        all_tables = await self.get_tables()
        filtered = []
        
        for table in all_tables:
            for pattern in patterns:
                if self.match_pattern(table.full_name, pattern):
                    filtered.append(table)
                    break
        
        return filtered
    
    async def filter_functions(self, patterns: List[str]) -> List[FunctionInfo]:
        """Get functions matching any of the patterns."""
        all_functions = await self.get_functions()
        filtered = []
        
        for function in all_functions:
            for pattern in patterns:
                if self.match_pattern(function.full_name, pattern):
                    filtered.append(function)
                    break
        
        return filtered