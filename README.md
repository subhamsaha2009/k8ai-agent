# K8AI

Talk to your Kubernetes cluster in plain English.

K8AI is an AI agent that connects to your live cluster and helps you diagnose issues, deploy apps, search docs, and manage infrastructure — all through natural conversation.

```
You: why is my payment pod failing?

Agent: Pod payment-svc is in CrashLoopBackOff.
       Root cause: OOMKilled — container exceeded its 256Mi memory limit.
       Recommendation: Increase memory limit to 512Mi.
       Want me to fix it?
```

## Quick Start

```bash
# Install
pip install git+https://github.com/subhamsaha2009/k8ai-agent.git

# Setup (one-time wizard — picks your AI provider and verifies cluster)
k8ai init

# Start chatting with your cluster
k8ai
```

## Two Ways to Use

| Mode | Command | Best for |
|------|---------|----------|
| **Terminal Agent** | `k8ai` | Interactive debugging, deployments, cluster management |
| **VS Code / Copilot** | `k8ai mcp install` | Using K8AI tools inside GitHub Copilot Chat |

## What You Can Do

**Diagnose problems** — find failing pods, read logs, check resource usage, inspect events

**Deploy workloads** — create pods, services, websites with full HTML/CSS/JS

**Run any kubectl command** — deployments, scaling, rollouts, draining nodes, everything

**Manage AKS clusters** — upgrades, node pools, addons, autoscaler (auto-detected)

**Search docs offline** — download Azure + Kubernetes docs locally with RAG-powered semantic search

**Build team knowledge** — save past incidents and runbooks, search them in future conversations

## Safety Built In

Every destructive command goes through **impact analysis** before execution:
- Shows what will be affected (pods, services, HPA, ingress)
- Rates risk level (LOW / MEDIUM / HIGH / CRITICAL)
- Suggests safer alternatives
- Asks your permission before proceeding

Read-only commands run instantly, no prompts.

## RAG Search (Optional)

Sync official docs locally and search by **meaning**, not just keywords:

```bash
k8ai docs sync
```

"my pod keeps running out of memory" finds docs about **OOMKilled**, **resource limits**, and **memory quotas** — even though those exact words aren't in your query.

Requires `text-embedding-ada-002` deployed alongside your chat model. See [DOCS.md](DOCS.md#rag-semantic-search) for setup.

## Supported Providers

| Provider | Chat Model | RAG Support |
|---|---|---|
| Azure OpenAI | gpt-4o | Yes (with text-embedding-ada-002) |
| OpenAI | gpt-4o | Yes (built-in) |
| Anthropic Claude | claude-sonnet-4-6 | Keyword search only |

## All CLI Commands

```
k8ai                          Start the AI agent
k8ai init                     Setup wizard
k8ai docs sync                Download docs + generate RAG embeddings
k8ai docs status              Show sync stats
k8ai kb status                Show knowledge base stats
k8ai kb import --file x.json  Import incidents/runbooks from JSON
k8ai kb import --folder ./    Import markdown files as runbooks
k8ai kb setup --azure         Connect Azure AI Search (team sharing)
k8ai mcp install              Auto-configure VS Code MCP server
k8ai config show              Show current config
```

## Learn More

See [DOCS.md](DOCS.md) for:
- Complete tool reference (27 tools)
- Architecture and code walkthrough
- RAG setup step-by-step
- Knowledge base details
- MCP server configuration
- Provider adapter internals

## Prerequisites

- Python 3.10+
- `kubectl` connected to a cluster
- API key for Azure OpenAI, OpenAI, or Claude
- (Optional) Azure CLI for AKS management
- (Optional) `text-embedding-ada-002` for RAG semantic search

## License

MIT
