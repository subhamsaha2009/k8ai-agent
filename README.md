# K8AI

AI-powered Kubernetes cluster management agent. Talk to your cluster in plain English — diagnose failures, deploy apps, manage AKS, and more.

Works with **Azure OpenAI**, **OpenAI**, and **Anthropic Claude**. Supports any Kubernetes cluster, with extra features for **Azure Kubernetes Service (AKS)**.

---

## Install

```bash
pip install git+https://github.com/subhamsaha2009/k8ai-agent.git
```

## Setup

```bash
k8ai init
```

The wizard asks three things:
1. **AI Provider** — Azure OpenAI, OpenAI, or Claude
2. **API Key + Model** — stored securely in your OS keychain
3. **Kubernetes Cluster** — auto-detected from your kubeconfig

## Use

**As a chat agent (terminal):**
```bash
k8ai
```

**As an MCP server (VS Code / Claude Desktop):**
```bash
k8ai-mcp
```

---

## What It Can Do

### Cluster Diagnostics
```
You: check my cluster for failed pods
You: why is pod my-app failing?
You: show me kubelet logs for node 1
You: show CPU and memory usage of all pods
```

### Deploy & Manage
```
You: deploy a todo app with a nice UI
You: scale deployment nginx to 5 replicas
You: show me all deployments in all namespaces
You: get all events sorted by time
```

### Destructive Command Safety
Every destructive command (delete, scale, drain, etc.) goes through a **deep impact analysis** before execution:
- Checks dependent resources (pods, services, ingress, HPA)
- Shows risk level (LOW / MEDIUM / HIGH / CRITICAL)
- Suggests safer alternatives
- Asks for your permission before proceeding

```
You: delete deployment nginx

  IMPACT ANALYSIS
  Command:     kubectl delete deployment nginx
  Risk Level:  HIGH
  Direct Impact:
    - Deployment nginx (3 replicas) will be terminated
  Dependent Resources:
    - Service nginx-svc (LoadBalancer) will lose all endpoints
    - HPA nginx-hpa will have no target
  Safer Alternatives:
    - Scale to 0 replicas instead of deleting

  Proceed? (yes/no)
```

### AKS Management (Azure clusters only)
Auto-detected from your kubeconfig. No extra setup needed.
```
You: show me available kubernetes upgrades
You: list my node pools
You: enable monitoring addon
You: scale nodepool1 to 5 nodes
You: disable cluster autoscaler
```

AKS commands also get impact analysis. The agent checks `az aks --help` before running any command to ensure correct flags.

### Azure Docs Lookup
```
You: what addons can I enable on AKS?
You: how do I set up KEDA on my cluster?
```
Searches official Microsoft Learn documentation and returns accurate, up-to-date answers.

### MCP Server (VS Code / Claude Desktop)
All tools are exposed via the Model Context Protocol. Safe commands run immediately. Destructive commands require a two-step confirmation (impact analysis + `confirm_destructive_action`).

Add to your VS Code `settings.json`:
```json
{
    "github.copilot.chat.mcpServers": {
        "k8ai": {
            "command": "k8ai-mcp"
        }
    }
}
```

---

## All Tools

| Tool | Type | Description |
|---|---|---|
| `list_pods` | Read | List pods with status, container states, restart counts |
| `describe_pod` | Read | Pod events — ImagePullBackOff, OOMKilled, CrashLoopBackOff |
| `get_pod_logs` | Read | Container logs (supports previous crashed container) |
| `get_node_status` | Read | Node CPU, memory, ready status |
| `get_node_names` | Read | List all node names |
| `get_kubelet_logs` | Read | Kubelet system logs from a node |
| `get_pod_resource_usage` | Read | Live CPU/memory usage via metrics-server |
| `get_pod_resource_limits` | Read | Configured requests/limits for a pod |
| `check_metrics_server` | Read | Check if metrics-server is installed |
| `list_namespaces` | Read | List all namespaces |
| `get_service` | Read | Service details, external IP, URL |
| `exec_in_pod` | Read | Run shell command inside a pod |
| `run_kubectl` | Read/Write | Execute any kubectl command |
| `deploy_pod` | Write | Deploy a generic pod with resource limits |
| `deploy_web_pod` | Write | Deploy nginx with optional custom HTML |
| `create_configmap` | Write | Store HTML/CSS/JS as ConfigMap |
| `update_configmap` | Write | Update live web content |
| `create_service` | Write | Expose pod via LoadBalancer/NodePort/ClusterIP |
| `delete_pod` | Write | Delete a pod |
| `delete_service` | Write | Delete a service |
| `run_az_aks` | AKS | Execute any az aks command (AKS only) |
| `get_az_aks_help` | AKS | Check az aks --help before running commands |
| `search_azure_docs` | Docs | Search Microsoft Learn documentation |
| `fetch_azure_doc` | Docs | Fetch full content of a docs page |

---

## CLI Commands

| Command | Description |
|---|---|
| `k8ai` | Start the interactive AI agent |
| `k8ai init` | Setup wizard (provider, API key, cluster) |
| `k8ai config show` | Show current configuration |
| `k8ai --version` | Show version |
| `k8ai-mcp` | Start MCP server for VS Code |

---

## Project Structure

```
k8ai-agent/
├── pyproject.toml              # Package config, dependencies, CLI entry points
├── k8ai/
│   ├── __init__.py             # Package version
│   ├── cli.py                  # CLI entry point (k8ai, k8ai init, k8ai config)
│   ├── config.py               # Config loader (~/.k8ai/config.yaml + OS keychain)
│   ├── agent.py                # Interactive chat agent loop
│   ├── mcp_server.py           # MCP server for VS Code / Claude Desktop
│   ├── k8s_tools.py            # All Kubernetes + AKS + Azure docs operations
│   ├── tools_schema.py         # Tool definitions for AI function calling
│   └── providers/
│       ├── __init__.py          # Provider loader (reads AI_PROVIDER env var)
│       ├── base.py              # BaseProvider interface
│       ├── azure.py             # Azure OpenAI adapter
│       ├── openai.py            # OpenAI adapter
│       └── claude.py            # Anthropic Claude adapter
├── .env.example                # Example environment variables
└── .gitignore
```

---

## How It Works

```
You type a message
      |
      v
cli.py loads config from ~/.k8ai/ and starts agent.py
      |
      v
agent.py sends your message + tool schemas to the AI model
      |
      v
AI model picks the right tool(s) to call
      |
      v
Is it destructive? ── YES ──> Impact analysis + ask permission
      |                              |
      NO                          Approved?
      |                           /      \
      v                         YES       NO
Execute tool                  Execute    Skip
      |                          |
      v                          v
Result sent back to AI model
      |
      v
AI explains the result to you
```

---

## Supported AI Providers

| Provider | Models | Env Vars |
|---|---|---|
| Azure OpenAI | gpt-4o, gpt-4o-mini | AI_PROVIDER, AI_API_KEY, AI_ENDPOINT, AI_MODEL, AI_API_VERSION |
| OpenAI | gpt-4o, gpt-4o-mini, gpt-4-turbo | AI_PROVIDER, AI_API_KEY, AI_MODEL |
| Anthropic Claude | claude-opus-4-6, claude-sonnet-4-6 | AI_PROVIDER, AI_API_KEY, AI_MODEL |

After running `k8ai init`, you don't need to set env vars manually — the config is stored in `~/.k8ai/config.yaml` and the API key is in your OS keychain.

---

## Prerequisites

- Python 3.10+
- `kubectl` installed and connected to a cluster
- An API key for one of the supported AI providers
- (Optional) Azure CLI if using AKS management features

---

## License

MIT
