# K8AI Developer Instructions

**AI-powered Kubernetes cluster management agent with AKS support**

## Quick Reference

- **Language**: Python 3.10+
- **Setup**: `pip install -e .` (from workspace root after venv activation)
- **Run**: `k8ai` (CLI agent) or `k8ai-mcp` (MCP server)
- **Config**: `~/.k8ai/config.yaml` + OS keychain for API keys
- **Entry Points**: `cli.py` (terminal) and `mcp_server.py` (VS Code/Claude Desktop)

## Project Structure

See [ARCHITECTURE.md](../ARCHITECTURE.md) for system diagrams and detailed code responsibilities. Key modules:

- **`cli.py`** — Entry point: handles `k8ai`, `k8ai init`, `k8ai config show`, etc.
- **`config.py`** — Config I/O with OS keychain integration for API keys
- **`agent.py`** — Main chat loop with safety/permission system for destructive commands
- **`k8s_tools.py`** — 24 Kubernetes/AKS/docs tools
- **`mcp_server.py`** — FastMCP wrapper for VS Code integration
- **`tools_schema.py`** — JSON schemas sent to AI models
- **`providers/`** — Adapters for Azure OpenAI, OpenAI, Claude (handle format differences)

### Subsidiary Modules

- **`kb.py`** — Knowledge base: stores incidents/runbooks as searchable embeddings
- **`docs_sync.py`** — RAG sync: downloads Azure + Kubernetes docs locally
- **`embeddings.py`** — Embedding generation for semantic search

## Development Commands

```bash
# Activate virtual environment
source .venv/bin/activate  # Linux/macOS
.\.venv\Scripts\Activate.ps1  # Windows PowerShell

# Install in development mode with all dependencies
pip install -e .

# Run CLI agent
k8ai

# Run specific subcommands
k8ai init                   # Setup wizard
k8ai docs sync              # Download + embed docs
k8ai kb import --folder ./  # Add runbooks
k8ai config show            # Show current config

# Run MCP server (for VS Code / Claude Desktop)
k8ai-mcp

# Check syntax / find errors
python -m py_compile k8ai/*.py
```

## Key Conventions

### Configuration & Credentials
- **Storage**: Config at `~/.k8ai/config.yaml`, API keys in OS keychain (never plaintext)
- **Env Vars**: `config.py::apply_config_to_env()` sets `AI_PROVIDER`, `AI_API_KEY`, `AI_MODEL`, etc.
- **Multi-Provider**: Any provider adapter works unchanged after config; see `providers/base.py` for interface

### Multi-Provider Architecture
Each AI provider (Azure/OpenAI/Claude) has an adapter in `providers/`:
- **Common Interface**: `chat()`, `get_tool_calls()`, `build_tool_result()`
- **Format Differences Handled**: Claude uses `role=user` for tool results (not standard), separate system prompt
- **Load via Env**: `providers/__init__.py::load_provider()` reads `AI_PROVIDER` env var

### Safety System
All destructive commands (delete, scale, upgrade) require:
1. **Impact Analysis** — Show affected resources, risk rating (LOW/MEDIUM/HIGH/CRITICAL), suggest alternatives
2. **User Approval** — Explicit confirmation before execution
3. **Two-Step MCP** — Impact returned with `action_id`; requires `confirm_destructive_action(action_id)` to execute

See [ARCHITECTURE.md#safety-design](../ARCHITECTURE.md) for full details.

### Tool Definitions
- **Location**: `tools_schema.py` — JSON schemas for all 24 tools
- **Purpose**: Describes to AI model what tools exist, parameters, when to use them
- **Pattern**: One function per tool in `k8s_tools.py`, one schema per tool in `tools_schema.py`

### AKS Auto-Detection
- **Trigger**: On startup, `agent.py` checks if kubeconfig API server contains `.azmk8s.io`
- **Effect**: If AKS detected, conditionally register AKS-specific tools (`detect_aks_cluster`, `run_az_aks`, `analyze_aks_impact`, `get_az_aks_help`)
- **Requirement**: Azure CLI (`az`) must be installed and configured for AKS operations

### Testing & Error Handling
- **Pre-Execution Checks**: `analyze_impact()` deep dependency analysis before any destructive operation
- **Soft Failures**: CLI continues, MCP returns error detail for retry
- **Logging**: Use `print()` for user-facing feedback, Python logging for diagnostics

## Documentation

**Always link, never embed.** Project docs cover:
- [ARCHITECTURE.md](../ARCHITECTURE.md) — System design, file responsibilities, safety design
- [DOCS.md](../DOCS.md) — Complete feature reference, setup step-by-step, CLI commands, provider support
- [README.md](../README.md) — Quick start, two usage modes, what you can do

## When Adding Features

1. **New Tool**: Add function to `k8s_tools.py`, add schema to `tools_schema.py`
2. **New Provider**: Implement `BaseProvider` interface in `providers/your_provider.py`, register in `providers/__init__.py`
3. **New CLI Command**: Add command handler in `cli.py`, update `README.md` and `DOCS.md` command reference
4. **Config Addition**: Update `config.py` (load/save), `cli.py` (init wizard), `DOCS.md` (reference)

## Common Development Patterns

### Using Keyring for Credentials
```python
import keyring

# Save securely
keyring.set_password("k8ai", "openai_key", api_key_value)

# Retrieve
api_key = keyring.get_password("k8ai", "openai_key")
```

### Adding a Tool
1. Implement in `k8s_tools.py` with docstring (description goes to schema)
2. Add schema in `tools_schema.py::build_tools_schema()`
3. Register in agent loop and MCP server automatically (already connected via `tools_schema.py`)

### Handling Destructive Operations
```python
# In k8s_tools.py
def delete_pod(namespace: str, pod_name: str):
    """Delete a specific pod (requires confirmation)."""
    analysis = analyze_impact(
        resource_type="pod",
        action="delete",
        target=pod_name
    )
    # Return analysis; agent displays + asks user
    # If approved, caller executes kubectl delete
    return analysis
```

### Provider-Specific Formatting
See `providers/claude.py` for example: Claude requires tool results as `role=user` message, system prompt separate from messages.

## Anti-Patterns to Avoid

❌ **Store API keys in `.env` or config files** — Use OS keychain via `keyring` module  
❌ **Duplicate docs in code comments** — Link to ARCHITECTURE.md / DOCS.md instead  
❌ **Add destructive tools without impact analysis** — Always call `analyze_impact()` first  
❌ **Hard-code provider adapters** — Use `load_provider()` to support all three at once  
❌ **Skip AKS detection** — Check `.azmk8s.io` on startup, conditionally enable Azure tools  

## Example Prompts to Test Instructions

Try these to validate the workspace is set up correctly:

1. **"Add a new tool to list all Kubernetes events in a namespace"**
   - Should understand: tool pattern in `k8s_tools.py` + schema in `tools_schema.py`, safety system placement
   - Will link to ARCHITECTURE.md and tool reference docs

2. **"How do I add support for a new AI provider?"**
   - Should explain: create adapter in `providers/`, implement `BaseProvider`, register in `__init__.py`
   - Will link to existing providers as examples (e.g., `providers/claude.py` for format differences)

3. **"Set up a local dev environment and run k8ai init"**
   - Should: activate venv, pip install -e, run k8ai init
   - Will follow development commands and setup sections

## Next Steps

Consider creating:
- **`/create-agent deploy-assistant`** — Specialized agent for safe deployment workflows
- **`/create-prompt testing-guide`** — Guide for testing K8s operations safely in dev
- **`/create-hook pre-commit-safety`** — Hook to validate new tools have impact analysis

---

*Updated: 2026-04-07*  
*For latest docs: [README.md](../README.md), [ARCHITECTURE.md](../ARCHITECTURE.md), [DOCS.md](../DOCS.md)*
