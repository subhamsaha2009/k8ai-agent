# K8AI

AI-powered Kubernetes cluster management agent. Talk to your cluster in plain English — diagnose failures, deploy apps, manage AKS, search docs offline, and learn from past incidents.

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
k8ai mcp install    # auto-configures VS Code
```

Or start the MCP server manually:
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

### Documentation Search (Offline + RAG)
```
You: what addons can I enable on AKS?
You: how do I set up horizontal pod autoscaler?
You: my pod keeps running out of memory
```

Sync official Azure AKS and Kubernetes documentation locally:
```bash
k8ai docs sync
```

This downloads ~10,000 doc chunks from GitHub and stores them in a local SQLite database. When using Azure OpenAI or OpenAI, **RAG embeddings** are generated automatically — enabling semantic search that understands meaning, not just keywords. Claude users get keyword-based search (FTS5 with BM25 ranking).

**Search priority:** Local docs (hybrid RAG + keyword) → Online Microsoft Learn (fallback)

### Knowledge Base
Save and search your team's past incidents, runbooks, and operational rules:

```
You: has this happened before?
Agent: → searches knowledge base for similar incidents

You: save this as an incident
Agent: → stores the resolution for future reference
```

**Import your own data:**
```bash
k8ai kb import --file incidents.json       # from JSON
k8ai kb import --folder ./team-runbooks/   # from markdown files
```

**Optional team sharing** via Azure AI Search:
```bash
k8ai kb setup --azure
```

### MCP Server (VS Code / Claude Desktop)
All tools are exposed via the Model Context Protocol. Safe commands run immediately. Destructive commands require a two-step confirmation (impact analysis + `confirm_destructive_action`).

**Auto-setup for VS Code:**
```bash
k8ai mcp install
```

This adds the MCP server config and sets `alwaysAllow` for safe tools so you don't get permission prompts for read-only commands.

**Manual setup** — add to your VS Code `settings.json`:
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

---

## Setting Up RAG (Semantic Search)

RAG (Retrieval-Augmented Generation) lets K8AI understand the **meaning** of your question, not just match keywords. For example, searching "my pod keeps running out of memory" will find docs about `OOMKilled`, `memory limits`, and `resource quotas` — even though those exact words aren't in your query.

### Step 1: Deploy an Embedding Model

RAG requires an **embedding model** in addition to your chat model (gpt-4o). These are two different models:

| Model | Purpose | Required for |
|---|---|---|
| `gpt-4o` | Chat — understands questions, calls tools, gives answers | K8AI agent (you already have this) |
| `text-embedding-ada-002` | Embeddings — converts text into vectors for semantic search | RAG search (deploy this separately) |

> **Important:** gpt-4o alone is NOT enough for RAG. You must also deploy `text-embedding-ada-002`. It uses the same endpoint and API key — no extra configuration needed.

**If you're using Azure OpenAI:**

1. Go to [Azure AI Foundry](https://ai.azure.com/)
2. Open the **same Azure OpenAI resource** where your gpt-4o is deployed
3. Go to **Deployments** → **Deploy model** → **Deploy base model**
4. Search for **text-embedding-ada-002**
5. Set deployment name to `text-embedding-ada-002`
6. Click **Deploy**

No new endpoint or API key needed — K8AI will use the same credentials for both models.

**If you're using OpenAI (direct):** The embedding model is already available on your API key — no extra setup needed.

> **Note:** Anthropic Claude does not have an embedding model. Claude users get keyword search (FTS5 BM25), which still works well for specific technical terms.

### Step 2: Sync Docs with Embeddings

```bash
k8ai docs sync
```

This does three things:
1. **Downloads** official AKS docs from GitHub (~6,000 chunks)
2. **Downloads** official Kubernetes docs from GitHub (~3,500 chunks)
3. **Generates embeddings** for all ~10,000 chunks using your embedding model

The output will show:

```
╭──────── Done ────────╮
│ Docs synced!         │
│                      │
│ AKS docs:  6392      │
│ K8s docs:  3517      │
│ Total:     9909      │
│ Embeddings: 9909     │
│ (RAG enabled)        │
╰──────────────────────╯
```

If you see `Embeddings: 0` and `RAG: disabled`, it means:
- Your provider is Claude (no embedding model), OR
- The embedding model deployment name doesn't match `text-embedding-ada-002`

### Step 3: Verify RAG is Working

```bash
k8ai kb status
```

Expected output:
```
Docs chunks:  9909
Incidents:    0
Runbooks:     0
Total:        9909
Embeddings:   9909
RAG:          enabled
DB size:      45.2 MB
DB path:      C:\Users\you\.k8ai\kb.db
Azure Search: not configured
```

### How RAG Search Works

When you ask a question, K8AI runs a **hybrid search** combining both methods:

```
Your question: "my pod keeps crashing with memory errors"
                         │
          ┌──────────────┴──────────────┐
          ▼                             ▼
   Semantic Search                Keyword Search
   (RAG embeddings)               (FTS5 BM25)
          │                             │
  Converts your question         Matches exact words:
  to a vector and finds          "crashing", "memory",
  docs with similar meaning:     "errors"
  "OOMKilled", "resource         │
  limits", "memory quotas"       │
          │                             │
          └──────────────┬──────────────┘
                         ▼
                 Merge + Deduplicate
                         │
                         ▼
                 Top 5 results returned
                 (with match_type: "semantic" or "keyword")
```

**Semantic search** catches what keyword search misses:
| You search for | Keyword finds | Semantic also finds |
|---|---|---|
| "memory problem" | docs with word "memory" | OOMKilled, resource limits, container QoS |
| "pod won't start" | docs with word "start" | ImagePullBackOff, CrashLoopBackOff, scheduling failures |
| "slow response" | docs with word "slow" | CPU throttling, resource quotas, HPA configuration |

### RAG Cost

Embedding generation is a one-time cost during `k8ai docs sync`:
- **~10,000 API calls** (batched in groups of 100 = ~100 API calls)
- **Model**: `text-embedding-ada-002` — one of the cheapest models
- **Cost**: ~$0.01 for the full sync
- Each search query generates 1 embedding call (~$0.000001)

Embeddings are stored locally in `~/.k8ai/kb.db` — no cloud dependency after sync.

---

## All Tools (27)

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
| `search_local_docs` | Docs | Search local docs with RAG + keyword hybrid search |
| `search_azure_docs` | Docs | Search Microsoft Learn online (fallback) |
| `fetch_azure_doc` | Docs | Fetch full content of a docs page |
| `search_knowledge_base` | KB | Search past incidents, runbooks, team rules |
| `add_to_knowledge_base` | KB | Save a resolved incident or team rule |

---

## CLI Commands

| Command | Description |
|---|---|
| `k8ai` | Start the interactive AI agent |
| `k8ai init` | Setup wizard (provider, API key, cluster) |
| `k8ai docs sync` | Download Azure + K8s docs locally (with RAG embeddings) |
| `k8ai docs status` | Show docs sync stats and RAG status |
| `k8ai kb status` | Show knowledge base stats |
| `k8ai kb import --file` | Import knowledge from JSON file |
| `k8ai kb import --folder` | Import knowledge from markdown folder |
| `k8ai kb setup --azure` | Connect Azure AI Search for team sharing |
| `k8ai mcp install` | Auto-configure MCP server in VS Code |
| `k8ai config show` | Show current configuration |
| `k8ai --version` | Show version |
| `k8ai-mcp` | Start MCP server for VS Code / Claude Desktop |

---

## Project Structure

```
k8ai-agent/
├── pyproject.toml              # Package config, dependencies, CLI entry points
├── DOCS.md                     # Comprehensive documentation
├── k8ai/
│   ├── __init__.py             # Package version
│   ├── cli.py                  # CLI entry point (all k8ai commands)
│   ├── config.py               # Config loader (~/.k8ai/config.yaml + OS keychain)
│   ├── agent.py                # Interactive chat agent loop
│   ├── mcp_server.py           # MCP server for VS Code / Claude Desktop
│   ├── k8s_tools.py            # All Kubernetes + AKS + docs + KB operations
│   ├── tools_schema.py         # Tool definitions for AI function calling
│   ├── embeddings.py           # RAG embedding generation (Azure OpenAI / OpenAI)
│   ├── kb.py                   # Knowledge base — SQLite FTS5 + vector search
│   ├── docs_sync.py            # Download + chunk + embed Azure/K8s docs
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
      │
      ▼
cli.py loads config from ~/.k8ai/ and starts agent.py
      │
      ▼
agent.py sends your message + tool schemas to the AI model
      │
      ▼
AI model picks the right tool(s) to call
      │
      ▼
Is it destructive? ── YES ──► Impact analysis + ask permission
      │                              │
      NO                          Approved?
      │                           /      \
      ▼                         YES       NO
Execute tool                  Execute    Skip
      │                          │
      ▼                          ▼
Result sent back to AI model
      │
      ▼
AI explains the result to you
```

### Search Flow (RAG)

```
User asks about docs
      │
      ▼
Generate query embedding (Azure OpenAI / OpenAI)
      │
      ▼
┌─────────────────────────┐
│     Hybrid Search       │
│                         │
│  Semantic: cosine       │ → finds docs by meaning
│  similarity vs stored   │   ("memory problem" → "OOMKilled")
│  embeddings             │
│                         │
│  Keyword: FTS5 BM25     │ → finds docs by exact words
│  word matching           │   ("OOMKilled" → "OOMKilled")
│                         │
│  Merge + deduplicate    │
└─────────────────────────┘
      │
      ▼
Top 5 results returned to AI
```

---

## Data Storage

All data is stored locally in `~/.k8ai/`:

```
~/.k8ai/
├── config.yaml         # Provider, model, endpoint settings
├── kb.db               # SQLite database (docs + embeddings + incidents + runbooks)
├── docs_sync.json      # Last sync timestamp and stats
├── azure_search.yaml   # Azure AI Search config (optional)
└── my_tools/           # Reserved for custom tools
```

API key is stored in your **OS keychain** (Windows Credential Manager / macOS Keychain / Linux Secret Service) — never in a plain text file.

---

## Supported AI Providers

| Provider | Models | Embedding Support |
|---|---|---|
| Azure OpenAI | gpt-4o, gpt-4o-mini | Yes (text-embedding-ada-002) — RAG enabled |
| OpenAI | gpt-4o, gpt-4o-mini, gpt-4-turbo | Yes (text-embedding-ada-002) — RAG enabled |
| Anthropic Claude | claude-opus-4-6, claude-sonnet-4-6 | No — keyword search only |

After running `k8ai init`, you don't need to set env vars manually — the config is stored in `~/.k8ai/config.yaml` and the API key is in your OS keychain.

---

## Prerequisites

- Python 3.10+
- `kubectl` installed and connected to a cluster
- An API key for one of the supported AI providers
- (Optional) Azure CLI if using AKS management features
- (Optional for RAG) `text-embedding-ada-002` model deployed alongside your chat model. This is a **separate deployment** from gpt-4o — same endpoint, same API key, but a different model. Without it, K8AI falls back to keyword search which still works but won't understand meaning-based queries

---

## License

MIT
