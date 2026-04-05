# K8AI Documentation

**AI-Powered Kubernetes Cluster Management Agent**

K8AI is a command-line AI agent and MCP server that connects to your live Kubernetes cluster. It can diagnose problems, deploy workloads, manage AKS clusters, search documentation, and learn from your team's past incidents — all through natural language.

---

## Table of Contents

1. [Installation](#installation)
2. [Setup](#setup)
3. [Usage Modes](#usage-modes)
   - [Interactive Agent (CLI)](#mode-1-interactive-agent-cli)
   - [MCP Server (VS Code / Claude Desktop)](#mode-2-mcp-server-vs-code--claude-desktop)
4. [All Capabilities](#all-capabilities)
   - [Cluster Diagnostics](#cluster-diagnostics)
   - [Pod Management](#pod-management)
   - [Service & Networking](#service--networking)
   - [General kubectl](#general-kubectl)
   - [AKS Cluster Management](#aks-cluster-management)
   - [Documentation Search](#documentation-search)
   - [Knowledge Base](#knowledge-base)
5. [Safety System](#safety-system)
6. [Architecture](#architecture)
7. [Configuration Reference](#configuration-reference)
8. [CLI Commands Reference](#cli-commands-reference)
9. [Provider Support](#provider-support)
10. [Knowledge Base & Docs Sync](#knowledge-base--docs-sync)

---

## Installation

### Prerequisites

- Python 3.10+
- `kubectl` configured and connected to a cluster
- An AI provider API key (Azure OpenAI, OpenAI, or Anthropic Claude)
- (Optional) Azure CLI if using AKS management features

### Install from GitHub

```bash
pip install git+https://github.com/subhamsaha2009/k8ai-agent.git
```

### Install from local source (for development)

```bash
git clone https://github.com/subhamsaha2009/k8ai-agent.git
cd k8ai-agent
pip install -e .
```

This installs two commands:
- `k8ai` — the interactive AI agent and CLI
- `k8ai-mcp` — the MCP server (used by VS Code / Claude Desktop)

---

## Setup

After installation, run the setup wizard:

```bash
k8ai init
```

The wizard walks through three steps:

### Step 1: Choose AI Provider

```
  [1] Azure OpenAI
  [2] OpenAI (direct)
  [3] Anthropic Claude
```

### Step 2: Enter Credentials

- **Azure OpenAI**: API key, endpoint URL (e.g. `https://my-resource.openai.azure.com/`), API version, model/deployment name
- **OpenAI**: API key, model name (default: `gpt-4o`)
- **Claude**: API key, model name (default: `claude-sonnet-4-6`)

Your API key is stored in your OS keychain (Windows Credential Manager / macOS Keychain / Linux Secret Service) — never in a plain text file.

### Step 3: Cluster Verification

The wizard runs `kubectl cluster-info` to verify your cluster is reachable. If the cluster API server contains `.azmk8s.io`, AKS-specific tools are automatically enabled.

After setup, configuration is saved to `~/.k8ai/config.yaml`.

---

## Usage Modes

K8AI can be used in two ways. Both share the same tools and safety system.

### Mode 1: Interactive Agent (CLI)

Start the agent in your terminal:

```bash
k8ai
```

This opens an interactive chat session. You type requests in natural language and the agent executes Kubernetes operations using its tools.

```
╭───────── K8AI ─────────╮
│ Cluster    my-cluster   │
│ AI Model   gpt-4o       │
│ Commands   Type request  │
╰─────────────────────────╯

You: check my cluster for failed pods
  → list_pods({"namespace": "default"})
  → describe_pod({"pod_name": "payment-svc-abc123"})
  → get_pod_logs({"pod_name": "payment-svc-abc123", "previous": true})

Agent: Pod payment-svc-abc123 is in CrashLoopBackOff.
Root cause: OOMKilled — the container exceeded its 256Mi memory limit.
Fix: Increase memory limit to 512Mi or investigate the memory leak.
```

**How the agent loop works:**
1. You type a request
2. The AI model decides which tools to call
3. Tools execute against your live cluster via `kubectl` / Kubernetes Python client
4. If a command is destructive, the agent shows an impact analysis and asks for permission
5. Results are fed back to the AI for analysis
6. The AI provides a human-readable summary

**Key features in agent mode:**
- Multi-turn conversation (the agent remembers context)
- Automatic AKS detection and `az aks` command injection
- Rich terminal UI with spinners, panels, and color coding
- Permission prompts with full impact analysis for destructive commands

### Mode 2: MCP Server (VS Code / Claude Desktop)

The MCP (Model Context Protocol) server exposes all K8AI tools to any MCP-compatible host like VS Code GitHub Copilot or Claude Desktop.

#### Automatic VS Code Setup

```bash
k8ai mcp install
```

This automatically:
1. Finds your VS Code `settings.json`
2. Adds the K8AI MCP server configuration
3. Sets `alwaysAllow` for safe (read-only) tools so you don't get permission prompts for every `list_pods`

After running this, reload VS Code and open Copilot Chat. K8AI tools will be available.

#### Manual VS Code Setup

Add this to your VS Code `settings.json` (Ctrl+Shift+P > "Open User Settings (JSON)"):

```json
{
    "github.copilot.chat.mcpServers": {
        "k8ai": {
            "command": "k8ai-mcp",
            "alwaysAllow": [
                "list_pods", "describe_pod", "get_pod_logs",
                "list_namespaces", "get_node_status", "get_node_names",
                "get_service", "get_pod_resource_usage", "get_pod_resource_limits",
                "check_metrics_server", "exec_in_pod", "get_kubelet_logs",
                "run_kubectl", "create_configmap", "search_azure_docs",
                "fetch_azure_doc", "get_az_aks_help", "run_az_aks"
            ]
        }
    }
}
```

#### Claude Desktop Setup

Add to your Claude Desktop config (`claude_desktop_config.json`):

```json
{
    "mcpServers": {
        "k8ai": {
            "command": "k8ai-mcp"
        }
    }
}
```

#### How MCP safety works

In MCP mode, destructive commands use a **two-step confirmation** pattern:

1. You ask Copilot to "delete pod nginx"
2. K8AI returns an impact analysis and an `action_id`
3. Copilot shows you the impact and asks if you want to proceed
4. If yes, Copilot calls `confirm_destructive_action(action_id)` to execute

Safe commands (get, describe, logs, list) execute immediately with no confirmation needed.

---

## All Capabilities

K8AI provides 27 tools organized into categories.

### Cluster Diagnostics

| Tool | Description |
|------|-------------|
| `list_pods` | List all pods in a namespace with status, container states, restart counts, and failure reasons |
| `describe_pod` | Get detailed pod info and events — reveals ImagePullBackOff, OOMKilled, CrashLoopBackOff, scheduling failures |
| `get_pod_logs` | Fetch pod logs. Use `previous=true` to get logs from a crashed container |
| `list_namespaces` | List all namespaces in the cluster |
| `get_node_status` | Get status, CPU, and memory of all nodes |
| `get_node_names` | Get all node names (use before `get_kubelet_logs`) |
| `get_kubelet_logs` | Fetch kubelet system logs from a node. Automatically creates and cleans up a debug pod |
| `check_metrics_server` | Check if metrics-server is installed and working |
| `get_pod_resource_usage` | Get live CPU and memory usage for pods via metrics-server |
| `get_pod_resource_limits` | Get CPU/memory requests and limits configured on a pod |
| `exec_in_pod` | Run a shell command inside a running pod |

### Pod Management

| Tool | Description |
|------|-------------|
| `deploy_pod` | Deploy a new pod with optional resource limits, env vars, and startup command |
| `delete_pod` | Delete a pod (force restart a failing pod) |
| `deploy_web_pod` | Deploy an nginx pod with optional ConfigMap HTML content |
| `create_configmap` | Create a ConfigMap with HTML content to serve via nginx |
| `update_configmap` | Update an existing ConfigMap with new HTML content |

### Service & Networking

| Tool | Description |
|------|-------------|
| `create_service` | Expose a pod via a Kubernetes Service (LoadBalancer, NodePort, ClusterIP) |
| `get_service` | Get service details including external IP and URL |
| `delete_service` | Delete a Kubernetes Service |

### General kubectl

| Tool | Description |
|------|-------------|
| `run_kubectl` | Execute any kubectl command. Covers deployments, statefulsets, daemonsets, ingress, events, rollouts, PVCs, jobs, cronjobs, and more. Safe commands run immediately; destructive commands get impact analysis first |

**Example kubectl commands:**
```
get deployments
scale deploy nginx --replicas=3
get events --sort-by=.lastTimestamp
rollout restart deploy nginx
get all -A
get pods -l app=nginx
drain node-1
```

### AKS Cluster Management

These tools are **only available when an AKS cluster is detected** (API server URL contains `.azmk8s.io`).

| Tool | Description |
|------|-------------|
| `get_az_aks_help` | Get official help text for any `az aks` subcommand. Always call this before `run_az_aks` when unsure about flags |
| `run_az_aks` | Execute any `az aks` command. Resource group and cluster name are auto-injected |

**Example AKS commands:**
```
show                                           # cluster info
get-upgrades                                   # available K8s versions
upgrade --kubernetes-version 1.29.0            # upgrade cluster
stop / start                                   # stop/start cluster
nodepool list                                  # list node pools
nodepool add --name gpu --node-count 1 --node-vm-size Standard_NC6
nodepool scale --name nodepool1 --node-count 5
enable-addons --addons monitoring
update --enable-cluster-autoscaler --min-count 1 --max-count 5
```

### Documentation Search

| Tool | Description |
|------|-------------|
| `search_local_docs` | Search locally synced Azure AKS + Kubernetes docs. Fast, offline, preferred |
| `search_azure_docs` | Search Microsoft Learn online (fallback if local returns nothing) |
| `fetch_azure_doc` | Fetch full content of a Microsoft Learn doc page |

### Knowledge Base

| Tool | Description |
|------|-------------|
| `search_knowledge_base` | Search team knowledge — past incidents, runbooks, postmortems |
| `add_to_knowledge_base` | Save a resolved incident or team rule for future reference |
| `confirm_destructive_action` | Confirm and execute a pending destructive action (MCP mode only) |

---

## Safety System

K8AI has a built-in safety system that prevents accidental damage to your cluster. Every command is classified as **safe** or **destructive**.

### Safe Commands (run immediately, no confirmation)

kubectl verbs: `get`, `describe`, `logs`, `top`, `explain`, `api-resources`, `api-versions`, `version`, `cluster-info`, `auth`, `config`, `diff`

AKS verbs: `show`, `list`, `get-upgrades`, `get-credentials`, `get-versions`, `nodepool list`, `nodepool show`

### Destructive Commands (impact analysis + confirmation required)

Everything else: `delete`, `scale`, `drain`, `cordon`, `rollout restart`, `apply`, `patch`, `upgrade`, `stop`, `start`, `nodepool add`, `nodepool delete`, `enable-addons`, `disable-addons`, etc.

### Impact Analysis

Before executing a destructive command, K8AI performs a deep impact analysis that checks:

- **Direct impact**: What resources will be affected
- **Dependent resources**: Services, ingress, HPA, PDB that reference the target
- **Risk level**: LOW, MEDIUM, HIGH, or CRITICAL
- **Safer alternatives**: Suggestions for less risky approaches

**Agent mode example:**
```
╭──── Permission Needed — HIGH RISK ────╮
│                                        │
│  ⚠  IMPACT ANALYSIS                   │
│                                        │
│  Command: delete deploy payment-svc    │
│  What this does: Deletes deployment    │
│  Risk Level: HIGH                      │
│                                        │
│  ── Direct Impact ──                   │
│    • 3 pods will be terminated         │
│                                        │
│  ── Dependent Resources Affected ──    │
│    • Service: payment-svc-lb           │
│    • HPA: payment-svc-hpa             │
│                                        │
│  ── Safer Alternatives ──             │
│    • Scale to 0 instead of delete     │
│                                        │
│  Do you want to proceed? (yes/no)      │
╰────────────────────────────────────────╯
```

**MCP mode**: The same analysis is returned as JSON with an `action_id`. The MCP host (Copilot/Claude Desktop) shows it to the user and calls `confirm_destructive_action(action_id)` if approved.

---

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                     User Interface                        │
│                                                          │
│   ┌────────────────┐         ┌────────────────────────┐  │
│   │  k8ai (CLI)    │         │  k8ai-mcp (MCP Server) │  │
│   │  agent.py      │         │  mcp_server.py         │  │
│   │  Interactive    │         │  JSON-RPC over stdio   │  │
│   └───────┬────────┘         └───────────┬────────────┘  │
│           │                              │               │
│           └──────────┬───────────────────┘               │
│                      ▼                                   │
│           ┌──────────────────┐                           │
│           │   k8s_tools.py   │  ← All 27 tool functions │
│           │   (Execution)    │                           │
│           └────────┬─────────┘                           │
│                    │                                     │
│     ┌──────────────┼──────────────┐                      │
│     ▼              ▼              ▼                      │
│  ┌────────┐  ┌──────────┐  ┌───────────┐               │
│  │kubectl │  │ az aks   │  │ K8s Python │               │
│  │ (CLI)  │  │ (CLI)    │  │  Client    │               │
│  └────┬───┘  └────┬─────┘  └─────┬─────┘               │
│       └───────────┼───────────────┘                      │
│                   ▼                                      │
│          ┌────────────────┐                              │
│          │  K8s Cluster   │                              │
│          │  (AKS / any)   │                              │
│          └────────────────┘                              │
│                                                          │
│  ┌──────────────────────────────────────────────┐       │
│  │  Supporting Systems                           │       │
│  │                                               │       │
│  │  providers/     AI provider adapters          │       │
│  │    ├── base.py      BaseProvider interface    │       │
│  │    ├── azure.py     Azure OpenAI adapter      │       │
│  │    ├── openai.py    OpenAI adapter            │       │
│  │    └── claude.py    Anthropic Claude adapter   │       │
│  │                                               │       │
│  │  config.py      ~/.k8ai/config.yaml + keyring │       │
│  │  tools_schema.py   OpenAI function schemas     │       │
│  │  kb.py          SQLite FTS5 knowledge base     │       │
│  │  docs_sync.py   GitHub docs downloader         │       │
│  └──────────────────────────────────────────────┘       │
└──────────────────────────────────────────────────────────┘
```

### File Responsibilities

| File | Purpose |
|------|---------|
| `cli.py` | Entry point for all `k8ai` commands. Routes to init wizard, docs sync, KB import, MCP install, config show, or agent loop |
| `agent.py` | The AI agent loop. Sends messages to the AI provider, processes tool calls, handles permission prompts, displays results |
| `mcp_server.py` | FastMCP server exposing all tools over stdio JSON-RPC. Implements two-step destructive confirmation for MCP hosts |
| `k8s_tools.py` | All 27 tool functions. Executes kubectl commands, calls Kubernetes Python client, runs az aks commands. Pure functions with no UI |
| `tools_schema.py` | OpenAI function-calling schemas for all tools. Used by `agent.py` to tell the AI model what tools exist |
| `config.py` | Loads/saves config from `~/.k8ai/config.yaml`. Stores API key in OS keychain via `keyring`. Sets environment variables |
| `kb.py` | SQLite FTS5 knowledge base. Stores docs, incidents, runbooks. BM25 ranking for search. Optional Azure AI Search backend |
| `docs_sync.py` | Downloads AKS and K8s docs from GitHub as ZIP files, chunks by headings (~400 words), stores in `kb.py` |
| `providers/base.py` | Abstract base class (`BaseProvider`) defining the interface: `chat()`, `get_tool_calls()`, `build_tool_result()` |
| `providers/azure.py` | Azure OpenAI adapter using the `openai` SDK with `AzureOpenAI` client |
| `providers/openai.py` | OpenAI adapter using the `openai` SDK |
| `providers/claude.py` | Anthropic Claude adapter using the `anthropic` SDK. Translates between OpenAI tool format and Claude tool format |

### Provider Adapter Pattern

The agent doesn't know which AI model it's talking to. All providers implement the same `BaseProvider` interface:

```python
class BaseProvider(ABC):
    def chat(messages, tools) -> response        # Send to AI model
    def get_tool_calls(response) -> [ToolCall]   # Extract tool calls
    def get_content(response) -> str             # Extract text response
    def build_assistant_message(response) -> dict # For conversation history
    def build_tool_result(tool_call, result) -> dict  # For conversation history
```

A `ToolCall` is a unified dataclass:
```python
@dataclass
class ToolCall:
    id: str           # unique ID
    name: str         # function name
    arguments: dict   # parsed arguments
```

The provider is selected at runtime based on the `AI_PROVIDER` environment variable, which is set by `config.py` from `~/.k8ai/config.yaml`.

---

## Configuration Reference

### Config location

```
~/.k8ai/
├── config.yaml         # Provider, model, endpoint, API version
├── kb.db               # SQLite knowledge base (docs + incidents + runbooks)
├── docs_sync.json      # Last docs sync timestamp and stats
├── azure_search.yaml   # Azure AI Search config (optional)
└── my_tools/           # Reserved for future custom tools
```

### config.yaml format

```yaml
provider: azure           # azure | openai | claude
model: gpt-4o             # model or deployment name
endpoint: https://my-resource.openai.azure.com/  # Azure only
api_version: "2024-10-21" # Azure only
```

API key is stored in your OS keychain under service `k8ai`, key `ai_api_key`.

### Environment variables

If you prefer environment variables over `k8ai init`, set these before running:

| Variable | Description |
|----------|-------------|
| `AI_PROVIDER` | `azure`, `openai`, or `claude` |
| `AI_API_KEY` | Your API key |
| `AI_MODEL` | Model/deployment name |
| `AI_ENDPOINT` | Endpoint URL (Azure only) |
| `AI_API_VERSION` | API version (Azure only) |

---

## CLI Commands Reference

| Command | Description |
|---------|-------------|
| `k8ai` | Start the interactive AI agent |
| `k8ai init` | Run the setup wizard (provider, API key, cluster verification) |
| `k8ai docs sync` | Download Azure AKS + Kubernetes docs for offline search |
| `k8ai docs status` | Show docs sync stats (chunk counts, DB size) |
| `k8ai kb status` | Show knowledge base stats (docs, incidents, runbooks) |
| `k8ai kb import --file data.json` | Import incidents/runbooks from a JSON file |
| `k8ai kb import --folder ./docs/` | Import all markdown files from a folder as runbooks |
| `k8ai kb setup --azure` | Connect Azure AI Search as a shared team backend |
| `k8ai mcp install` | Auto-configure K8AI MCP server in VS Code settings.json |
| `k8ai config show` | Show current configuration (provider, model, endpoint) |
| `k8ai --version` | Show version |
| `k8ai --help` | Show all available commands |

---

## Provider Support

| Provider | SDK | Model Examples | Notes |
|----------|-----|----------------|-------|
| Azure OpenAI | `openai` (AzureOpenAI client) | gpt-4o, gpt-4-turbo | Requires endpoint + API version |
| OpenAI | `openai` | gpt-4o, gpt-4-turbo | Direct API access |
| Anthropic Claude | `anthropic` | claude-sonnet-4-6 | Tool format translated automatically |

All providers support function calling (tool use). The Claude adapter translates between OpenAI's tool schema format and Claude's native tool format transparently.

---

## Knowledge Base & Docs Sync

### Local Docs Sync

Download official Azure AKS and Kubernetes documentation for instant offline search:

```bash
k8ai docs sync
```

**What it downloads:**
- **AKS docs**: From `github.com/MicrosoftDocs/azure-aks-docs` — all files under `articles/aks/`
- **K8s docs**: From `github.com/kubernetes/website` — `content/en/docs/concepts/` and `content/en/docs/tasks/`

**How it works:**
1. Downloads each repo as a single ZIP file (fast, single HTTP request)
2. Extracts all `.md` files from the relevant folders
3. Strips YAML frontmatter
4. Chunks each file by headings, max ~400 words per chunk
5. Stores all chunks in SQLite FTS5 for BM25-ranked full-text search

Typical result: ~10,000 chunks in a ~20 MB database. Search is instant and fully offline.

### Team Knowledge Base

The knowledge base stores three types of data:

| Category | Source | Description |
|----------|--------|-------------|
| `docs` | `k8ai docs sync` | Official Azure + K8s documentation |
| `incident` | Agent (with user approval) | Past incidents the agent helped resolve |
| `runbook` | `k8ai kb import` | Team runbooks, postmortems, and rules |

**Importing your own data:**

JSON file format:
```json
[
  {
    "title": "Payment service OOMKilled — March 2026",
    "description": "Pod crashed due to memory leak in connection pool v2.3.1",
    "resolution": "Upgraded to v2.3.2, set memory limit to 512Mi",
    "category": "incident",
    "tags": "oomkill payment memory"
  }
]
```

```bash
k8ai kb import --file incidents.json
k8ai kb import --folder ./team-runbooks/
```

### Azure AI Search (Optional)

For teams that want to share knowledge across multiple users, connect Azure AI Search:

```bash
k8ai kb setup --azure
```

This prompts for your Azure AI Search endpoint, API key, and index name. Once configured, all `search_knowledge_base` queries check both the local SQLite database and the remote Azure AI Search index.

---

## Common Workflows

### Diagnose a failing pod
```
You: why is pod payment-svc failing?
Agent: → list_pods → describe_pod → get_pod_logs(previous=true)
       Root cause: OOMKilled. Container exceeded 256Mi limit.
```

### Deploy a website
```
You: deploy a color picker website
Agent: → create_configmap (with full HTML/CSS/JS)
       → deploy_web_pod (with configmap)
       → create_service (LoadBalancer)
       → get_service (get public IP)
       Your site is live at http://20.1.2.3
```

### Check resource utilization
```
You: show me CPU and memory usage for all pods
Agent: → get_pod_resource_usage
       → get_pod_resource_limits
       Pod nginx is using 95% of its memory limit — OOMKill risk.
```

### Upgrade AKS cluster
```
You: what Kubernetes versions can I upgrade to?
Agent: → run_az_aks("get-upgrades")
       Available: 1.28.5, 1.29.0, 1.29.2
You: upgrade to 1.29.2
Agent: → get_az_aks_help("upgrade")  (verify flags)
       → run_az_aks("upgrade --kubernetes-version 1.29.2")
       [Shows impact analysis, asks permission]
```

### Search documentation
```
You: how do I set up horizontal pod autoscaler?
Agent: → search_local_docs("horizontal pod autoscaler")
       Here's how to configure HPA...
```

### Save an incident
```
Agent: Issue resolved. Want me to save this for future reference?
You: yes
Agent: → add_to_knowledge_base(title="...", description="...", resolution="...")
       Saved to knowledge base.
```
