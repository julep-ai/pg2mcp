# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## pg2mcp: Postgres to MCP Bridge

pg2mcp is a utility that automatically converts PostgreSQL database objects into a modern MCP (Model Context Protocol) server with full support for tools, resources, prompts, streaming, and OAuth 2.1 authentication. This enables LLMs to interact with PostgreSQL databases through a standardized protocol.

### Key Features

- **Auto-Generated Resources**: Tables and views become MCP resources with automatic pagination, filtering, and schema introspection
- **Auto-Generated Tools**: PostgreSQL functions become MCP tools with automatic parameter mapping and type conversion
- **Real-time Streaming**: LISTEN/NOTIFY channels exposed as streaming endpoints
- **Security**: Built-in support for OAuth 2.1, JWT validation, row-level security, and connection pooling
- **Type Safety**: Automatic PostgreSQL to JSON Schema type conversion with custom mapping support
- **Configuration-Driven**: Simple YAML configuration to expose database objects selectively

### Architecture Overview

```
PostgreSQL DB ← asyncpg → pg2mcp → FastMCP Server → MCP Clients
                            ↑
                      Config File (YAML)
```

### Quick Start

1. Create a configuration file (pg2mcp.yaml):
```yaml
database:
  url: "postgresql://user:pass@localhost:5432/mydb"
  
server:
  name: "PostgreSQL MCP Bridge"
  port: 8000
  
expose:
  resources:
    - pattern: "public.*"  # Expose all tables in public schema
  tools:
    - pattern: "api.*"     # Expose all functions in api schema
```

2. Run the server:
```bash
python main.py -c pg2mcp.yaml
```

<!-- AIDEV-NOTE: Main implementation details are in docs/DESIGN.md and docs/IMPLEMENTORS_GUIDE.md -->

## IMPORTANT: Use Anchor comments

<!-- AIDEV-NOTE: This is an Anchor Comment -->

Add specially formatted comments throughout the codebase, where appropriate, for yourself as inline knowledge that can be easily `grep`ped for.

- Use `AIDEV-NOTE:`, `AIDEV-TODO:`, `AIDEV-QUESTION:`, or `AIDEV-SECTION:` as prefix as appropriate.

- *Important:* Before scanning files, always first try to grep for existing `AIDEV-…`.

- Update relevant anchors, after finishing any task.

- Make sure to add relevant anchor comments, whenever a file or piece of code is:

  * too complex, or
  * very important, or
  * could have a bug

## AI Assistant Workflow: Step-by-Step Methodology

When responding to user instructions, the AI assistant (Claude, Cursor, GPT, etc.) should follow this process to ensure clarity, correctness, and maintainability:

1. **Consult Relevant Guidance**: When the user gives an instruction, consult the relevant instructions from `CLAUDE.md` files (both root and directory-specific) for the request.
2. **Clarify Ambiguities**: Based on what you could gather, see if there's any need for clarifications. If so, ask the user targeted questions before proceeding.
3. **Break Down & Plan**: Break down the task at hand and chalk out a rough plan for carrying it out, referencing project conventions and best practices.
4. **Trivial Tasks**: If the plan/request is trivial, go ahead and get started immediately.
5. **Non-Trivial Tasks**: Otherwise, present the plan to the user for review and iterate based on their feedback.
6. **Track Progress**: Use a to-do list (internally, or optionally in a `TODOS.md` file) to keep track of your progress on multi-step or complex tasks.
7. **If Stuck, Re-plan**: If you get stuck or blocked, return to step 3 to re-evaluate and adjust your plan.
8. **Update Documentation**: Once the user's request is fulfilled, update relevant anchor comments (`AIDEV-NOTE`, etc.) and `CLAUDE.md` files in the files and directories you touched.
9. **User Review**: After completing the task, ask the user to review what you've done, and repeat the process as needed.
10. **Session Boundaries**: If the user's request isn't directly related to the current context and can be safely started in a fresh session, suggest starting from scratch to avoid context confusion.

## Development Commands

### Testing

**Using UV (recommended):**
```bash
# Run all tests with UV
uv run python -m pytest

# Run tests with coverage
uv run python -m pytest --cov=pg2mcp --cov-report=xml

# Run specific test files
uv run python -m pytest tests/test_introspector.py
uv run python -m pytest tests/test_resources.py
uv run python -m pytest tests/test_tools.py
```

### Installation

**Preferred method using UV (recommended):**
```bash
# Install in development mode with UV
uv pip install -e .

# Or if project uses pyproject.toml with UV
uv sync --all-extras --dev

# Build package with UV
uv build
```

**Alternative method using pip:**
```bash
# Install in development mode with pip (legacy)
python -m pip install -e .
```

### Running the Server

```bash
# Run with default config
uv run python main.py

# Run with custom config
uv run python main.py -c /path/to/pg2mcp.yaml

# Run with environment variable overrides
PG_PASSWORD=secret uv run python main.py
```

AIDEV-NOTE: Always prefer UV for new development - it's faster and handles virtual environments automatically

## UV Package Manager

UV is a modern, blazing-fast Python package and project manager written in Rust. It serves as a drop-in replacement for pip, virtualenv, poetry, and other Python tooling, offering 10-100x speed improvements.

AIDEV-NOTE: UV is now the preferred package manager for SteadyText development. It automatically handles virtual environments, avoids activation/deactivation issues, and provides superior dependency resolution.

### Key Benefits

- **Speed**: 10-100x faster than pip for package installation and dependency resolution
- **Automatic Virtual Environments**: Creates and manages `.venv` automatically when needed
- **No Activation Required**: Commands work without manual virtual environment activation
- **Superior Dependency Resolution**: Modern resolver prevents version conflicts
- **Unified Tooling**: Replaces multiple tools (pip, virtualenv, poetry, pyenv) with one
- **Drop-in Compatibility**: Works with existing requirements.txt and pyproject.toml files

### Installation

Install UV system-wide using the official installer:

```bash
# Linux/macOS
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows PowerShell (run as administrator)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# Alternative: using pip (not recommended)
pip install uv
```

### Basic Usage

**Project Initialization:**
```bash
# Initialize new project with pyproject.toml
uv init steadytext-project
cd steadytext-project

# Initialize in existing directory
uv init .
```

**Virtual Environment Management:**
```bash
# Create virtual environment (done automatically with uv add)
uv venv

# Create with specific Python version
uv venv --python 3.11

# UV automatically finds and uses .venv when present - no activation needed!
```

**Package Management:**
```bash
# Add dependencies (creates .venv automatically if needed)
uv add requests numpy pandas

# Add development dependencies
uv add --dev pytest black ruff

# Add optional dependencies
uv add --optional test pytest coverage

# Remove dependencies
uv remove requests

# Install from requirements.txt
uv pip install -r requirements.txt

# Install project in development mode
uv pip install -e .

# Sync dependencies from lock file
uv sync
```

**Running Code:**
```bash
# Run Python scripts (automatically uses project's .venv)
uv run python script.py
uv run pytest
uv run python -m pytest

# Run tools without installing in project
uv tool run black .
uv tool run ruff check .

# Short alias for tool run
uvx black .
uvx ruff check .
```

### Python Version Management

```bash
# Install Python versions
uv python install 3.10 3.11 3.12

# List available Python versions
uv python list

# Use specific Python version for project
uv python pin 3.11

# Create venv with specific Python version
uv venv --python 3.11
```

### Advanced Features

**Lock Files and Reproducibility:**
```bash
# Generate lock file (done automatically with uv add)
uv lock

# Export to requirements.txt format
uv export -o requirements.txt

# Install from lock file
uv sync
```

**Development Workflow:**
```bash
# Install project with all development dependencies
uv sync --all-extras --dev

# Update dependencies
uv lock --upgrade

# Check for dependency conflicts
uv tree
```

### Migration from pip/virtualenv

Replace common commands:
```bash
# Old way                          # New way
python -m venv .venv              # uv venv (automatic)
source .venv/bin/activate         # (not needed)
pip install requests              # uv add requests
pip install -r requirements.txt  # uv pip install -r requirements.txt
pip freeze > requirements.txt    # uv export -o requirements.txt
deactivate                        # (not needed)
```

### Common Patterns for pg2mcp Development

**Setting up development environment:**
```bash
# Clone and setup
git clone <repo>
cd pg2mcp
uv sync --all-extras --dev

# Run tests
uv run python -m pytest

# Run linting
uvx ruff check .
uvx black .

# Install in development mode
uv pip install -e .
```

**Working with dependencies:**
```bash
# Add core dependencies
uv add fastmcp asyncpg pydantic pyyaml uvicorn httpx

# Add development tools
uv add --dev pytest pytest-asyncio pytest-cov ruff black mypy

# Check installed packages
uv pip list

# Show dependency tree
uv tree
```

### Troubleshooting

**Common Issues:**
- If UV can't find Python version, install it: `uv python install 3.11`
- For permission errors on Linux/Mac: `sudo chown -R $USER ~/.local/share/uv`
- To force recreation of virtual environment: `rm -rf .venv && uv sync`

**Cache Management:**
```bash
# Show cache info
uv cache info

# Clean cache
uv cache clean
```

AIDEV-TODO: Consider adding UV-specific CI/CD configurations for faster builds
AIDEV-NOTE: UV's automatic virtual environment management eliminates common "forgot to activate venv" issues

## Development Workflow

### Additional Process Guidance

- At the end of code changes, please make sure to run linting and formatting:
  ```bash
  uvx ruff check .
  uvx black .
  ```

## Project Structure

<!-- AIDEV-NOTE: This section describes the expected project layout -->

```
pg2mcp/
├── main.py              # Entry point and CLI
├── pg2mcp/
│   ├── __init__.py
│   ├── config.py        # Configuration models and loader
│   ├── introspector.py  # Database schema introspection
│   ├── resources.py     # Resource (table/view) generation
│   ├── tools.py         # Tool (function) generation
│   ├── streaming.py     # LISTEN/NOTIFY handling
│   ├── security.py      # Authentication and authorization
│   ├── types.py         # Type conversion utilities
│   └── server.py        # Main server class
├── tests/
│   ├── test_config.py
│   ├── test_introspector.py
│   ├── test_resources.py
│   ├── test_tools.py
│   └── fixtures/        # Test database schemas
├── examples/
│   ├── basic.yaml       # Basic configuration example
│   ├── advanced.yaml    # Advanced features example
│   └── docker-compose.yml
├── docs/
│   ├── DESIGN.md        # Architecture and implementation
│   └── IMPLEMENTORS_GUIDE.md  # Detailed implementation guide
└── pyproject.toml       # Project metadata and dependencies
```

## Key Implementation Notes

<!-- AIDEV-NOTE: Important implementation details to remember -->

1. **Async Everything**: Use async/await throughout - asyncpg requires it and it improves performance
2. **Type Safety**: Use Pydantic models for all configuration and data structures
3. **Connection Pooling**: Always use asyncpg connection pools, never create individual connections
4. **Error Handling**: Wrap database operations in try/except blocks and return meaningful error messages
5. **Security First**: Always use parameterized queries, validate inputs, and respect row-level security

## Testing PostgreSQL Locally

For local development, you can use Docker to run PostgreSQL:

```bash
# Start PostgreSQL
docker run -d \
  --name pg2mcp-postgres \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=testdb \
  -p 5432:5432 \
  postgres:16

# Create test schema
docker exec -i pg2mcp-postgres psql -U postgres testdb << 'EOF'
CREATE SCHEMA IF NOT EXISTS api;
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE OR REPLACE FUNCTION api.get_user(user_id INTEGER)
RETURNS TABLE(id INTEGER, name TEXT, email TEXT) AS $$
BEGIN
    RETURN QUERY SELECT u.id, u.name, u.email FROM users u WHERE u.id = user_id;
END;
$$ LANGUAGE plpgsql;
EOF
```
