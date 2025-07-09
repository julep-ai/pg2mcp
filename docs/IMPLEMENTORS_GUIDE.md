# PostgreSQL to MCP Bridge: Implementor's Guide

<!-- AIDEV-NOTE: Compactified version for busy coders - focus on implementation essentials -->

## Quick Navigation
1. [Architecture](#architecture) | 2. [Setup](#setup) | 3. [Core Implementation](#core-implementation) | 4. [Configuration](#configuration) | 5. [Database Introspection](#database-introspection) | 6. [Resources](#resources) | 7. [Tools](#tools) | 8. [Streaming](#streaming) | 9. [Security](#security) | 10. [Testing](#testing) | 11. [Deployment](#deployment) | 12. [Performance](#performance) | 13. [Troubleshooting](#troubleshooting) | 14. [Extensions](#extensions)

## Architecture

```
MCP Clients ──HTTP──▶ pg2mcp ──TCP──▶ PostgreSQL
                        │
                        ▼
                   YAML Config
```

**Core Components:**
- **ConfigLoader**: YAML→Pydantic validation, env var expansion
- **DatabaseInspector**: PostgreSQL system catalog introspection with caching
- **ResourceGenerator**: Tables/views→MCP resources with pagination/filtering
- **ToolGenerator**: Functions→MCP tools with parameter mapping
- **StreamHandler**: LISTEN/NOTIFY→streaming endpoints
- **SecurityManager**: OAuth/JWT + Row-Level Security
- **TypeConverter**: PostgreSQL→JSON Schema mapping

## Setup

**Dependencies:**
```bash
pip install fastmcp>=2.0.0 asyncpg>=0.30.0 pydantic>=2.0 pyyaml>=6.0 uvicorn[standard]>=0.30.0
```

**PostgreSQL:**
```sql
CREATE DATABASE mcp_dev;
CREATE USER mcp_bridge WITH PASSWORD 'secure_password';
GRANT CONNECT ON DATABASE mcp_dev TO mcp_bridge;
GRANT USAGE ON SCHEMA public TO mcp_bridge;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO mcp_bridge;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO mcp_bridge;
```

## Core Implementation

**Project Structure:**
```
pg2mcp/
├── bridge.py                # Main PostgresMCPBridge class
├── config/
│   ├── models.py           # Pydantic configuration models
│   └── loader.py           # Configuration loading logic
├── introspection/
│   ├── inspector.py        # DatabaseInspector with caching
│   └── queries.py          # PostgreSQL system catalog queries
├── generators/
│   ├── resource.py         # ResourceGenerator
│   ├── tool.py             # ToolGenerator
│   └── stream.py           # StreamGenerator
├── converters/
│   ├── types.py            # PostgreSQL→JSON Schema conversion
│   └── values.py           # Value conversion utilities
├── security/
│   ├── auth.py             # JWT/OAuth authentication
│   ├── policies.py         # Authorization policies
│   └── rls.py              # Row-level security
└── utils/
    ├── logging.py          # Structured logging
    └── metrics.py          # Prometheus metrics
```

**Main Bridge Class:**
```python
class PostgresMCPBridge:
    def __init__(self, config_path: str):
        self.config = None
        self.pool = None  # asyncpg.Pool
        self.mcp = None   # FastMCP
        self.inspector = None
        self.security = None
    
    async def initialize(self):
        # Load config → Create pool → Initialize MCP → Generate components
        self.config = await ConfigLoader().load(self.config_path)
        self.pool = await self._create_pool()
        self.mcp = FastMCP(name=self.config.server.name)
        self.security = SecurityManager(self.config.security, self.pool)
        self.inspector = DatabaseInspector(self.pool, self.config.introspection)
        await self._generate_components()
    
    async def _create_pool(self) -> asyncpg.Pool:
        return await asyncpg.create_pool(
            dsn=self.config.database.url,
            min_size=self.config.database.pool.min_size,
            max_size=self.config.database.pool.max_size,
            init=self._init_connection
        )
    
    async def _generate_components(self):
        ResourceGenerator(self.mcp, self.inspector, self.config.expose.resources)
        ToolGenerator(self.mcp, self.inspector, self.config.expose.tools)
        StreamGenerator(self.mcp, self.inspector, self.config.expose.notifications)
```

## Configuration

**Key Pydantic Models:**
```python
class DatabaseConfig(BaseModel):
    url: str
    pool: PoolConfig = PoolConfig()

class PoolConfig(BaseModel):
    min_size: int = 5
    max_size: int = 20
    statement_timeout: Optional[int] = None

class ResourcePattern(BaseModel):
    pattern: str  # e.g., "public.*"
    security_context: Optional[Dict[str, Any]] = None
    cache_ttl: Optional[int] = 300

class ToolPattern(BaseModel):
    pattern: str  # e.g., "api.*"
    dangerous: bool = False
    require_confirmation: bool = False

class SecurityConfig(BaseModel):
    jwt: Optional[JWTConfig] = None
    oauth: Optional[OAuthConfig] = None
    row_level_security: bool = True
    rate_limiting: Optional[RateLimitConfig] = None
```

**Configuration Loading:**
```python
class ConfigLoader:
    async def load(self, path: str) -> Config:
        with open(path) as f:
            raw_config = yaml.safe_load(f)
        
        # Environment variable expansion
        expanded = self._expand_env_vars(raw_config)
        
        # Pydantic validation
        return Config.model_validate(expanded)
```

## Database Introspection

**DatabaseInspector with Caching:**
```python
class DatabaseInspector:
    def __init__(self, pool: asyncpg.Pool, config: IntrospectionConfig):
        self.pool = pool
        self.config = config
        self._cache = {}
        self._cache_ttl = config.cache_ttl
    
    async def get_tables(self, schema: str) -> List[TableInfo]:
        cache_key = f"tables_{schema}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        async with self.pool.acquire() as conn:
            result = await conn.fetch(TABLES_QUERY, schema)
            tables = [TableInfo.from_row(row) for row in result]
            self._cache[cache_key] = tables
            return tables
    
    async def get_functions(self, schema: str) -> List[FunctionInfo]:
        # Similar caching pattern for functions
        pass
```

**Key Introspection Queries:**
```sql
-- Tables with columns
SELECT t.table_name, t.table_type, c.column_name, c.data_type, c.is_nullable
FROM information_schema.tables t
JOIN information_schema.columns c ON t.table_name = c.table_name
WHERE t.table_schema = $1;

-- Functions with parameters
SELECT p.proname, p.pronargs, format_type(p.prorettype, NULL) as return_type,
       unnest(p.proargnames) as arg_name, unnest(p.proargtypes) as arg_type
FROM pg_proc p
JOIN pg_namespace n ON p.pronamespace = n.oid
WHERE n.nspname = $1;
```

## Resources

**ResourceGenerator:**
```python
class ResourceGenerator:
    def __init__(self, mcp: FastMCP, inspector: DatabaseInspector, patterns: List[ResourcePattern]):
        self.mcp = mcp
        self.inspector = inspector
        for pattern in patterns:
            self._register_pattern(pattern)
    
    def _register_pattern(self, pattern: ResourcePattern):
        @self.mcp.resource(pattern.pattern)
        async def resource_handler(uri: str, **kwargs):
            schema, table = self._parse_uri(uri)
            
            # Build query with security context
            query = self._build_query(schema, table, kwargs, pattern.security_context)
            
            # Execute with connection from pool
            async with self.pool.acquire() as conn:
                result = await conn.fetch(query, **kwargs)
                return self._format_response(result)
    
    def _build_query(self, schema: str, table: str, params: dict, security_context: dict) -> str:
        base_query = f"SELECT * FROM {schema}.{table}"
        
        # Add WHERE clauses
        where_clauses = []
        if security_context:
            where_clauses.extend(self._build_security_clauses(security_context))
        if params.get('where'):
            where_clauses.append(params['where'])
        
        if where_clauses:
            base_query += f" WHERE {' AND '.join(where_clauses)}"
        
        # Add pagination
        if params.get('limit'):
            base_query += f" LIMIT {params['limit']}"
        if params.get('offset'):
            base_query += f" OFFSET {params['offset']}"
        
        return base_query
```

## Tools

**ToolGenerator:**
```python
class ToolGenerator:
    def __init__(self, mcp: FastMCP, inspector: DatabaseInspector, patterns: List[ToolPattern]):
        self.mcp = mcp
        self.inspector = inspector
        for pattern in patterns:
            self._register_pattern(pattern)
    
    def _register_pattern(self, pattern: ToolPattern):
        functions = self.inspector.get_functions_by_pattern(pattern.pattern)
        
        for func in functions:
            schema = self._generate_json_schema(func)
            
            @self.mcp.tool(func.name, schema=schema)
            async def tool_handler(**kwargs):
                # Parameter validation
                self._validate_parameters(kwargs, func)
                
                # Security checks
                if pattern.dangerous and not kwargs.get('confirm'):
                    raise ValueError("Dangerous function requires confirmation")
                
                # Execute function
                query = f"SELECT {func.schema}.{func.name}({self._format_args(kwargs)})"
                async with self.pool.acquire() as conn:
                    result = await conn.fetchval(query)
                    return result
    
    def _generate_json_schema(self, func: FunctionInfo) -> dict:
        return {
            "type": "object",
            "properties": {
                param.name: self._pg_type_to_json_schema(param.type)
                for param in func.parameters
            },
            "required": [p.name for p in func.parameters if not p.has_default]
        }
```

## Streaming

**StreamGenerator for LISTEN/NOTIFY:**
```python
class StreamGenerator:
    def __init__(self, mcp: FastMCP, inspector: DatabaseInspector, notifications: List[NotificationConfig]):
        self.mcp = mcp
        self.listeners = {}
        for config in notifications:
            self._setup_listener(config)
    
    def _setup_listener(self, config: NotificationConfig):
        @self.mcp.stream(config.channel)
        async def stream_handler():
            listener = NotificationListener(config.channel, self.pool)
            await listener.start()
            
            try:
                async for notification in listener:
                    # Validate and transform notification
                    if config.schema:
                        payload = self._validate_payload(notification.payload, config.schema)
                    else:
                        payload = notification.payload
                    
                    yield {
                        "channel": notification.channel,
                        "payload": payload,
                        "timestamp": notification.timestamp
                    }
            finally:
                await listener.stop()

class NotificationListener:
    def __init__(self, channel: str, pool: asyncpg.Pool):
        self.channel = channel
        self.pool = pool
        self.connection = None
        self.queue = asyncio.Queue()
    
    async def start(self):
        self.connection = await self.pool.acquire()
        await self.connection.add_listener(self.channel, self._on_notification)
        await self.connection.execute(f"LISTEN {self.channel}")
    
    def _on_notification(self, connection, pid, channel, payload):
        notification = Notification(channel=channel, payload=payload, timestamp=time.time())
        self.queue.put_nowait(notification)
    
    async def __aiter__(self):
        while True:
            yield await self.queue.get()
```

## Security

**SecurityManager:**
```python
class SecurityManager:
    def __init__(self, config: SecurityConfig, pool: asyncpg.Pool):
        self.config = config
        self.pool = pool
        self.jwt_validator = JWTValidator(config.jwt) if config.jwt else None
        self.rate_limiter = RateLimiter(config.rate_limiting) if config.rate_limiting else None
    
    async def authenticate(self, request) -> Optional[UserContext]:
        if not self.jwt_validator:
            return None
        
        token = self._extract_token(request)
        if not token:
            return None
        
        claims = await self.jwt_validator.validate(token)
        return UserContext(
            user_id=claims.get('sub'),
            roles=claims.get('roles', []),
            scopes=claims.get('scopes', [])
        )
    
    async def authorize(self, user_context: UserContext, resource: str, action: str) -> bool:
        # Check role-based access
        required_roles = self._get_required_roles(resource, action)
        if not set(user_context.roles).intersection(required_roles):
            return False
        
        # Check rate limiting
        if self.rate_limiter:
            return await self.rate_limiter.check_rate_limit(user_context.user_id)
        
        return True
    
    def build_rls_context(self, user_context: UserContext) -> Dict[str, Any]:
        return {
            'current_user_id': user_context.user_id,
            'current_user_roles': user_context.roles
        }
```

## Testing

**Key Test Patterns:**
```python
# pytest fixtures
@pytest.fixture
async def db_pool():
    pool = await asyncpg.create_pool("postgresql://test:test@localhost/test_db")
    yield pool
    await pool.close()

@pytest.fixture
async def bridge(db_pool):
    config = Config(database=DatabaseConfig(url="postgresql://test:test@localhost/test_db"))
    bridge = PostgresMCPBridge(config)
    await bridge.initialize()
    yield bridge
    await bridge.cleanup()

# Resource testing
async def test_resource_generation(bridge):
    # Test resource creation
    resources = await bridge.mcp.list_resources()
    assert "public.users" in [r.uri for r in resources]
    
    # Test resource access
    result = await bridge.mcp.read_resource("public.users")
    assert result.content is not None

# Tool testing
async def test_tool_execution(bridge):
    tools = await bridge.mcp.list_tools()
    assert "api.get_user" in [t.name for t in tools]
    
    result = await bridge.mcp.call_tool("api.get_user", {"user_id": 1})
    assert result.content is not None
```

## Deployment

**Docker:**
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["python", "main.py"]
```

**Kubernetes:**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: pg2mcp
spec:
  replicas: 3
  selector:
    matchLabels:
      app: pg2mcp
  template:
    metadata:
      labels:
        app: pg2mcp
    spec:
      containers:
      - name: pg2mcp
        image: pg2mcp:latest
        ports:
        - containerPort: 8000
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: db-secret
              key: url
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "512Mi"
            cpu: "500m"
```

## Performance

**Connection Pool Optimization:**
```python
# Monitor pool usage
pool_usage = Gauge('pg2mcp_pool_usage', 'Connection pool usage')
pool_usage.set(pool.get_size() / pool.get_max_size())

# Optimize based on metrics
async def optimize_pool_size():
    current_usage = await get_pool_usage_metrics()
    if current_usage > 0.8:
        await pool.resize(min_size=pool.get_min_size() + 2)
```

**Query Optimization:**
```python
# Prepared statements
PREPARED_QUERIES = {
    'get_user': 'SELECT * FROM users WHERE id = $1',
    'list_users': 'SELECT * FROM users LIMIT $1 OFFSET $2'
}

# Query hints
query_with_hint = f"/*+ USE_INDEX(users users_email_idx) */ {base_query}"
```

## Troubleshooting

**Common Issues:**
- **Connection Pool Exhaustion**: Monitor `pg2mcp_pool_usage` metric
- **Authentication Failures**: Check JWT token validation, JWKS endpoint
- **RLS Errors**: Verify security context variables are set correctly
- **Slow Queries**: Use `EXPLAIN ANALYZE`, add appropriate indexes

**Debug Utilities:**
```python
# Query profiling
async def profile_query(query: str, params: list):
    start_time = time.time()
    result = await conn.fetch(query, *params)
    duration = time.time() - start_time
    logger.info("Query executed", query=query, duration=duration, row_count=len(result))
    return result

# Connection monitoring
async def monitor_connections():
    active_connections = await conn.fetchval("SELECT count(*) FROM pg_stat_activity WHERE state = 'active'")
    logger.info("Active connections", count=active_connections)
```

## Extensions

**Extension Architecture:**
```python
class ResourceExtension(ABC):
    @abstractmethod
    async def generate_resources(self, inspector: DatabaseInspector) -> List[Resource]:
        pass

class AnalyticsExtension(ResourceExtension):
    async def generate_resources(self, inspector: DatabaseInspector) -> List[Resource]:
        # Generate analytics resources
        return [
            Resource(
                uri="analytics.query_stats",
                name="Query Statistics",
                description="Query performance metrics"
            )
        ]

# Extension loading
extensions = [
    AnalyticsExtension(),
    CustomReportExtension(),
    IntegrationExtension()
]

for ext in extensions:
    resources = await ext.generate_resources(inspector)
    for resource in resources:
        mcp.add_resource(resource)
```

---

**Key Implementation Notes:**
- Use async/await throughout for performance
- Always use connection pooling with asyncpg
- Implement comprehensive error handling and logging
- Use Pydantic for all configuration and data validation
- Implement proper security with JWT/OAuth and RLS
- Cache database metadata for performance
- Use prepared statements for frequently executed queries
- Monitor performance with Prometheus metrics

<!-- AIDEV-NOTE: This compactified guide removes verbose explanations while preserving all essential implementation details -->