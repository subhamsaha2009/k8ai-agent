# K8AI — Architecture

## Overview

K8AI is a Kubernetes management agent that translates plain English into cluster operations. It can run as an **interactive terminal agent** or as an **MCP server** for VS Code / Claude Desktop.

```
                              ┌──────────────────────┐
                              │   AI Provider        │
                              │  (Azure / OpenAI /   │
                              │   Claude)            │
                              └──────────┬───────────┘
                                         │ API calls
                                         │
┌────────────────────────────────────────┼────────────────────────────┐
│                          K8AI Agent                                 │
│                                                                    │
│   ┌──────────┐       ┌──────────┐       ┌────────────────────┐    │
│   │  cli.py  │──────▶│ agent.py │──────▶│  k8s_tools.py      │    │
│   │          │       │          │       │  (24 tools)         │    │
│   └──────────┘       └──────────┘       └─────────┬──────────┘    │
│                                                    │               │
│   ┌──────────────┐   ┌──────────┐                 │               │
│   │ mcp_server.py│──▶│k8s_tools │                 │               │
│   │ (VS Code)    │   │  (same)  │                 │               │
│   └──────────────┘   └──────────┘                 │               │
│                                                    │               │
│   ┌──────────────┐                                │               │
│   │  config.py   │  ~/.k8ai/config.yaml           │               │
│   │  + keychain  │  + OS keychain                 │               │
│   └──────────────┘                                │               │
│                                                    │               │
│   ┌──────────────┐                                │               │
│   │  providers/  │  Azure / OpenAI / Claude       │               │
│   └──────────────┘                                │               │
└────────────────────────────────────────────────────┼───────────────┘
                                                     │
                          ┌──────────────────────────┼──────┐
                          │                          │      │
                          ▼                          ▼      ▼
                    ┌──────────┐             ┌────────┐  ┌──────────┐
                    │ kubectl  │             │ az aks │  │ MS Learn │
                    │ (any K8s)│             │ (AKS)  │  │ (docs)   │
                    └────┬─────┘             └───┬────┘  └──────────┘
                         │                       │
                         ▼                       ▼
                  ┌─────────────────────────────────┐
                  │     Kubernetes Cluster           │
                  │  (AKS / EKS / GKE / any)        │
                  └─────────────────────────────────┘
```

---

## File Responsibilities

### `cli.py` — Entry Point
- Handles `k8ai`, `k8ai init`, `k8ai config show`, `k8ai --version`, `k8ai --help`
- `k8ai init` runs the interactive setup wizard (provider, API key, cluster detection)
- Loads config from `~/.k8ai/` and sets env vars before starting the agent

### `config.py` — Configuration
- Saves/loads config to `~/.k8ai/config.yaml`
- Stores API key in OS keychain (Windows Credential Manager / macOS Keychain) — never in plaintext
- `apply_config_to_env()` sets `AI_PROVIDER`, `AI_API_KEY`, `AI_MODEL`, etc. so providers work unchanged

### `agent.py` — Interactive Agent
- Main chat loop: user input -> AI model -> tool calls -> results -> AI explains
- Permission system: destructive actions require user approval
- Impact analysis: deep dependency check before destructive kubectl/AKS commands
- AKS auto-detection at startup via kubeconfig API server URL (`.azmk8s.io`)
- Uses `rich` for terminal UI (panels, tables, spinners)

### `mcp_server.py` — MCP Server
- Wraps all k8s_tools as MCP tools via FastMCP
- Two-step safety for destructive commands: returns impact analysis + `action_id`, requires `confirm_destructive_action(action_id)` to execute
- AKS tools conditionally registered only on AKS clusters
- Loads config from `~/.k8ai/` at startup

### `k8s_tools.py` — All Operations (24 tools)
- **Kubernetes:** list_pods, describe_pod, get_pod_logs, deploy_pod, delete_pod, deploy_web_pod, create/update_configmap, create/get/delete_service, exec_in_pod, list_namespaces, get_node_status, get_node_names, get_kubelet_logs, get_pod_resource_usage, get_pod_resource_limits, check_metrics_server
- **kubectl:** run_kubectl (generic executor), analyze_impact (deep dependency analysis)
- **AKS:** detect_aks_cluster, run_az_aks, analyze_aks_impact, get_az_aks_help
- **Docs:** search_azure_docs, fetch_azure_doc

### `tools_schema.py` — Tool Definitions
- JSON schema for each tool sent to the AI model
- Tells the model what tools exist, what parameters they accept, and when to use them

### `providers/` — AI Provider Adapters
- `base.py` — BaseProvider interface: `chat()`, `get_tool_calls()`, `build_tool_result()`
- `azure.py` — Azure OpenAI adapter
- `openai.py` — OpenAI direct adapter
- `claude.py` — Anthropic Claude adapter (handles format differences: tool_result as role=user, separate system prompt, etc.)
- `__init__.py` — `load_provider()` reads `AI_PROVIDER` env var and returns the right adapter

---

## Safety Design

### Agent Mode (terminal)
1. Read-only commands (get, describe, logs) execute immediately
2. Destructive kubectl commands trigger `analyze_impact()` — checks pods, services, ingress, HPA, PDB
3. Destructive AKS commands trigger `analyze_aks_impact()` — checks autoscaler, nodepools, addons
4. Impact report shown with risk level (LOW/MEDIUM/HIGH/CRITICAL) and safer alternatives
5. User must type "yes" to proceed

### MCP Mode (VS Code)
1. Safe tools execute immediately (no VS Code prompt via `alwaysAllow`)
2. Destructive tools return `{"status": "AWAITING_CONFIRMATION", "action_id": "..."}` with impact analysis
3. AI client must call `confirm_destructive_action(action_id)` to execute
4. Pending actions stored in memory — expire when server restarts

### kubectl Safety Classification
- **Safe verbs:** get, describe, logs, top, explain, api-resources, api-versions, version, cluster-info, auth, config, diff
- **Everything else** is treated as destructive

### AKS Safety Classification
- **Safe verbs:** show, list, get-upgrades, get-credentials, get-versions, nodepool list, nodepool show
- **Everything else** is treated as destructive

---

## Config Storage

```
~/.k8ai/
├── config.yaml          # provider, model, endpoint, api_version
└── my_tools/            # reserved for future self-extending agent (P3)
```

API key is stored in the OS keychain under service `k8ai`, key `ai_api_key`.

`config.yaml` example:
```yaml
provider: azure
model: gpt-4o
endpoint: https://my-resource.openai.azure.com/
api_version: "2024-10-21"
```

---

## Two Ways to Use

| Mode | Command | How It Works |
|---|---|---|
| **Agent** | `k8ai` | Interactive terminal chat. You type, agent responds, calls tools, asks permission. |
| **MCP Server** | `k8ai-mcp` | JSON-RPC server over stdio. VS Code / Claude Desktop calls tools programmatically. |

Both modes use the same `k8s_tools.py`, same providers, same config. The only difference is the interface — human chat vs machine protocol.
