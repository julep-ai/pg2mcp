"""Configuration models and loader for pg2mcp."""
import os
from typing import List, Optional, Dict, Any
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator, SecretStr


class DatabaseConfig(BaseModel):
    """Database connection configuration."""
    url: Optional[str] = None
    host: Optional[str] = None
    port: int = 5432
    database: Optional[str] = None
    user: Optional[str] = None
    password: Optional[SecretStr] = None
    
    # Connection pool settings
    pool_min_size: int = Field(default=5, ge=1)
    pool_max_size: int = Field(default=20, ge=1)
    pool_timeout: Optional[float] = Field(default=None, ge=0)
    
    @field_validator('url')
    def validate_url(cls, v, values):
        if v and any([values.data.get('host'), values.data.get('database'), 
                     values.data.get('user'), values.data.get('password')]):
            raise ValueError("Cannot specify both 'url' and individual connection parameters")
        return v
    
    def get_dsn(self) -> str:
        """Get the database connection string."""
        if self.url:
            return self._expand_env(self.url)
        
        if not all([self.host, self.database, self.user]):
            raise ValueError("Must specify either 'url' or all of: host, database, user")
        
        password = self.password.get_secret_value() if self.password else ""
        password = self._expand_env(password)
        
        return f"postgresql://{self.user}:{password}@{self.host}:{self.port}/{self.database}"
    
    @staticmethod
    def _expand_env(value: str) -> str:
        """Expand environment variables in string."""
        return os.path.expandvars(value)


class ServerConfig(BaseModel):
    """MCP server configuration."""
    name: str = "PostgreSQL MCP Bridge"
    description: str = "Auto-generated MCP interface for PostgreSQL"
    version: str = "1.0.0"
    host: str = "0.0.0.0"
    port: int = 8000


class ResourcePattern(BaseModel):
    """Pattern for exposing resources (tables/views)."""
    pattern: Optional[str] = None
    table: Optional[str] = None
    view: Optional[str] = None
    description: Optional[str] = None
    columns: Optional[List[str]] = None
    exclude: Optional[List[str]] = None
    where: Optional[str] = None
    limit: Optional[int] = Field(default=1000, ge=1)
    
    @field_validator('pattern')
    def validate_pattern(cls, v, values):
        if v and (values.data.get('table') or values.data.get('view')):
            raise ValueError("Cannot specify both 'pattern' and specific table/view")
        return v


class ToolPattern(BaseModel):
    """Pattern for exposing tools (functions)."""
    pattern: Optional[str] = None
    function: Optional[str] = None
    description: Optional[str] = None
    dangerous: bool = False
    params: Optional[Dict[str, Dict[str, Any]]] = None
    
    @field_validator('pattern')
    def validate_pattern(cls, v, values):
        if v and values.data.get('function'):
            raise ValueError("Cannot specify both 'pattern' and specific function")
        return v


class ExposeConfig(BaseModel):
    """Configuration for what to expose via MCP."""
    resources: List[ResourcePattern] = Field(default_factory=list)
    tools: List[ToolPattern] = Field(default_factory=list)


class Config(BaseModel):
    """Root configuration model."""
    database: DatabaseConfig
    server: ServerConfig = Field(default_factory=ServerConfig)
    expose: ExposeConfig = Field(default_factory=ExposeConfig)


class ConfigLoader:
    """Load and validate configuration from YAML file."""
    
    def __init__(self):
        self._cache = {}
    
    def load(self, path: str) -> Config:
        """Load configuration from YAML file."""
        path_obj = Path(path)
        
        if not path_obj.exists():
            raise FileNotFoundError(f"Configuration file not found: {path}")
        
        with open(path_obj, 'r') as f:
            raw_config = yaml.safe_load(f)
        
        # Expand environment variables in the config
        expanded = self._expand_env_vars(raw_config)
        
        # Validate with Pydantic
        return Config.model_validate(expanded)
    
    def _expand_env_vars(self, obj: Any) -> Any:
        """Recursively expand environment variables in config."""
        if isinstance(obj, dict):
            return {k: self._expand_env_vars(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._expand_env_vars(item) for item in obj]
        elif isinstance(obj, str):
            return os.path.expandvars(obj)
        else:
            return obj