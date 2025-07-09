"""Type conversion utilities between PostgreSQL and JSON Schema."""
from typing import Dict, Any, List, Optional


class TypeConverter:
    """Convert PostgreSQL types to JSON Schema types."""
    
    # Mapping of PostgreSQL types to JSON Schema types
    PG_TO_JSON_SCHEMA = {
        # Numeric types
        'smallint': {'type': 'integer', 'minimum': -32768, 'maximum': 32767},
        'integer': {'type': 'integer'},
        'bigint': {'type': 'integer'},
        'decimal': {'type': 'number'},
        'numeric': {'type': 'number'},
        'real': {'type': 'number'},
        'double precision': {'type': 'number'},
        'smallserial': {'type': 'integer', 'minimum': 1, 'maximum': 32767},
        'serial': {'type': 'integer', 'minimum': 1},
        'bigserial': {'type': 'integer', 'minimum': 1},
        
        # Monetary
        'money': {'type': 'string', 'pattern': r'^\$?\d+(\.\d{2})?$'},
        
        # Character types
        'character varying': {'type': 'string'},
        'varchar': {'type': 'string'},
        'character': {'type': 'string'},
        'char': {'type': 'string'},
        'text': {'type': 'string'},
        
        # Binary
        'bytea': {'type': 'string', 'contentEncoding': 'base64'},
        
        # Date/Time types
        'timestamp': {'type': 'string', 'format': 'date-time'},
        'timestamp without time zone': {'type': 'string', 'format': 'date-time'},
        'timestamp with time zone': {'type': 'string', 'format': 'date-time'},
        'date': {'type': 'string', 'format': 'date'},
        'time': {'type': 'string', 'format': 'time'},
        'time without time zone': {'type': 'string', 'format': 'time'},
        'time with time zone': {'type': 'string', 'format': 'time'},
        'interval': {'type': 'string'},
        
        # Boolean
        'boolean': {'type': 'boolean'},
        
        # Geometric types (simplified)
        'point': {'type': 'object', 'properties': {'x': {'type': 'number'}, 'y': {'type': 'number'}}},
        'line': {'type': 'string'},
        'lseg': {'type': 'string'},
        'box': {'type': 'string'},
        'path': {'type': 'string'},
        'polygon': {'type': 'string'},
        'circle': {'type': 'string'},
        
        # Network types
        'cidr': {'type': 'string', 'format': 'ipv4'},
        'inet': {'type': 'string', 'format': 'ipv4'},
        'macaddr': {'type': 'string', 'pattern': r'^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$'},
        'macaddr8': {'type': 'string', 'pattern': r'^([0-9A-Fa-f]{2}[:-]){7}([0-9A-Fa-f]{2})$'},
        
        # UUID
        'uuid': {'type': 'string', 'format': 'uuid'},
        
        # JSON types
        'json': {'type': 'object'},
        'jsonb': {'type': 'object'},
        
        # Arrays handled separately
        'ARRAY': {'type': 'array'},
        
        # Others
        'xml': {'type': 'string'},
        'pg_lsn': {'type': 'string'},
        'tsquery': {'type': 'string'},
        'tsvector': {'type': 'string'},
    }
    
    @classmethod
    def pg_type_to_json_schema(cls, pg_type: str) -> Dict[str, Any]:
        """Convert a PostgreSQL type to JSON Schema type definition."""
        # Normalize the type
        pg_type = pg_type.lower().strip()
        
        # Handle arrays
        if pg_type.endswith('[]'):
            base_type = pg_type[:-2]
            base_schema = cls.pg_type_to_json_schema(base_type)
            return {
                'type': 'array',
                'items': base_schema
            }
        
        # Handle character varying with length
        if pg_type.startswith('character varying(') or pg_type.startswith('varchar('):
            length = int(pg_type.split('(')[1].rstrip(')'))
            return {'type': 'string', 'maxLength': length}
        
        # Handle character with length
        if pg_type.startswith('character(') or pg_type.startswith('char('):
            length = int(pg_type.split('(')[1].rstrip(')'))
            return {'type': 'string', 'minLength': length, 'maxLength': length}
        
        # Handle numeric with precision
        if pg_type.startswith('numeric(') or pg_type.startswith('decimal('):
            # For now, just return number type
            # Could parse precision/scale if needed
            return {'type': 'number'}
        
        # Look up in mapping
        if pg_type in cls.PG_TO_JSON_SCHEMA:
            return cls.PG_TO_JSON_SCHEMA[pg_type].copy()
        
        # Default to string for unknown types
        return {'type': 'string'}
    
    @classmethod
    def generate_table_schema(cls, columns: List[Any]) -> Dict[str, Any]:
        """Generate JSON Schema for a table based on its columns."""
        properties = {}
        required = []
        
        for column in columns:
            schema = cls.pg_type_to_json_schema(column.data_type)
            
            if column.is_nullable:
                # Nullable fields can be null
                schema = {
                    'oneOf': [
                        schema,
                        {'type': 'null'}
                    ]
                }
            else:
                required.append(column.name)
            
            properties[column.name] = schema
        
        return {
            'type': 'object',
            'properties': properties,
            'required': required
        }
    
    @classmethod
    def generate_function_params_schema(cls, parameters: List[Any]) -> Dict[str, Any]:
        """Generate JSON Schema for function parameters."""
        properties = {}
        required = []
        
        for param in parameters:
            # Only include IN and INOUT parameters
            if param.mode in ('IN', 'INOUT'):
                schema = cls.pg_type_to_json_schema(param.data_type)
                properties[param.name] = schema
                
                if not param.has_default:
                    required.append(param.name)
        
        return {
            'type': 'object',
            'properties': properties,
            'required': required
        }
    
    @classmethod
    def generate_function_result_schema(cls, return_type: str, out_params: List[Any]) -> Dict[str, Any]:
        """Generate JSON Schema for function results."""
        # If there are OUT parameters, return object with those
        if out_params:
            properties = {}
            for param in out_params:
                if param.mode in ('OUT', 'INOUT'):
                    properties[param.name] = cls.pg_type_to_json_schema(param.data_type)
            
            return {
                'type': 'object',
                'properties': properties
            }
        
        # Otherwise use the return type
        if return_type.lower() == 'void':
            return {'type': 'null'}
        
        if return_type.startswith('SETOF '):
            # Returns a set of rows
            base_type = return_type[6:]
            base_schema = cls.pg_type_to_json_schema(base_type)
            return {
                'type': 'array',
                'items': base_schema
            }
        
        if return_type.startswith('TABLE'):
            # TABLE return type - would need more parsing
            return {'type': 'array', 'items': {'type': 'object'}}
        
        return cls.pg_type_to_json_schema(return_type)