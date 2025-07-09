"""Tool generation for PostgreSQL functions."""
import json
from typing import List, Dict, Any, Optional

import asyncpg
from fastmcp import FastMCP

from .config import ToolPattern
from .introspector import DatabaseInspector, FunctionInfo
from .types import TypeConverter


class ToolGenerator:
    """Generate MCP tools from PostgreSQL functions."""
    
    def __init__(self, mcp: FastMCP, inspector: DatabaseInspector, pool: asyncpg.Pool):
        self.mcp = mcp
        self.inspector = inspector
        self.pool = pool
        self._registered_tools = set()
    
    async def register_patterns(self, patterns: List[ToolPattern]) -> None:
        """Register tool patterns with the MCP server."""
        # Collect all functions to register
        functions_to_register = []
        
        for pattern in patterns:
            if pattern.pattern:
                # Pattern-based registration
                functions = await self.inspector.filter_functions([pattern.pattern])
                for function in functions:
                    functions_to_register.append((function, pattern))
            elif pattern.function:
                # Specific function registration
                all_functions = await self.inspector.get_functions()
                for function in all_functions:
                    if function.name == pattern.function or function.full_name == pattern.function:
                        functions_to_register.append((function, pattern))
        
        # Register each function as a tool
        for function, pattern in functions_to_register:
            await self._register_function_tool(function, pattern)
    
    async def _register_function_tool(self, function: FunctionInfo, pattern: ToolPattern) -> None:
        """Register a single function as a tool."""
        tool_name = function.full_name.replace('.', '_')
        
        # Avoid duplicate registration
        if tool_name in self._registered_tools:
            return
        
        self._registered_tools.add(tool_name)
        
        # Generate parameter schema
        params_schema = TypeConverter.generate_function_params_schema(function.parameters)
        
        # Override parameter descriptions if provided
        if pattern.params:
            for param_name, param_info in pattern.params.items():
                if param_name in params_schema['properties']:
                    if 'description' in param_info:
                        params_schema['properties'][param_name]['description'] = param_info['description']
        
        # Generate result schema
        out_params = [p for p in function.parameters if p.mode in ('OUT', 'INOUT')]
        result_schema = TypeConverter.generate_function_result_schema(function.return_type, out_params)
        
        # Tool description
        description = pattern.description or function.description or f"Execute PostgreSQL function {function.full_name}"
        
        # Add danger warning if applicable
        if pattern.dangerous:
            description = f"⚠️ DANGEROUS: {description}"
        
        # Create the tool handler - FastMCP infers parameters from function signature
        # So we need to dynamically create a function with the right signature
        @self.mcp.tool(name=tool_name, description=description)
        async def handle_tool(**kwargs) -> Any:
            """Handle tool execution for this function."""
            # Build function call
            param_values = []
            param_names = []
            
            # Map parameters in order
            for param in function.parameters:
                if param.mode in ('IN', 'INOUT'):
                    if param.name in kwargs:
                        param_values.append(kwargs[param.name])
                        param_names.append(param.name)
                    elif param.has_default:
                        # Skip parameters with defaults if not provided
                        continue
                    else:
                        raise ValueError(f"Missing required parameter: {param.name}")
            
            # Build query
            if param_values:
                placeholders = ', '.join(f'${i+1}' for i in range(len(param_values)))
                query = f"SELECT * FROM {function.full_name}({placeholders})"
            else:
                query = f"SELECT * FROM {function.full_name}()"
            
            try:
                async with self.pool.acquire() as conn:
                    # Execute function
                    if function.return_type.startswith('SETOF') or function.return_type.startswith('TABLE'):
                        # Multiple rows expected
                        rows = await conn.fetch(query, *param_values)
                        result = [dict(row) for row in rows]
                    else:
                        # Single value expected
                        result = await conn.fetchval(query, *param_values)
                        
                        # If there are OUT parameters, fetch as row
                        if out_params:
                            row = await conn.fetchrow(query, *param_values)
                            result = dict(row) if row else None
                
                # Format result
                return {
                    "success": True,
                    "result": result,
                    "function": function.full_name,
                    "parameters": dict(zip(param_names, param_values))
                }
                
            except Exception as e:
                return {
                    "success": False,
                    "error": str(e),
                    "function": function.full_name,
                    "parameters": dict(zip(param_names, param_values))
                }
    
    def get_tool_list(self) -> List[Dict[str, Any]]:
        """Get list of registered tools for MCP tool listing."""
        tools = []
        for tool_name in self._registered_tools:
            # Convert back to function name
            function_name = tool_name.replace('_', '.')
            tools.append({
                "name": tool_name,
                "description": f"PostgreSQL function {function_name}",
                "inputSchema": {
                    "type": "object",
                    "properties": {}
                }
            })
        return tools