# K8s AI Agent 🤖

A conversational AI agent that manages your **Azure Kubernetes Service (AKS)** cluster using plain English. Powered by **Azure AI Foundry (GPT-4o)**.

> Talk to your cluster. Deploy apps. Diagnose failures. Fix issues. All from a chat prompt.

---

## Demo

```
You: check my cluster for failed pods

  → list_pods()
  → describe_pod("my-app-xyz")
  → get_pod_logs("my-app-xyz", previous=True)

Agent: Pod 'my-app-xyz' is in CrashLoopBackOff.
       Root cause: Missing environment variable DATABASE_URL.
       Logs show: KeyError: 'DATABASE_URL'
       Fix: Delete and redeploy with correct env vars. Proceed? (yes/no)
```

```
You: deploy a color picker website

  → create_configmap("colorpicker", "<html>...")
  → deploy_web_pod("colorpicker-pod", configmap="colorpicker")
  → create_service("colorpicker-svc", type="LoadBalancer")
  → get_service("colorpicker-svc")

Agent: Your app is live at http://20.x.x.x 🎉
```

---

## What It Can Do

| Capability | Example Prompt |
|---|---|
| Check cluster health | `check my cluster for failed pods` |
| Diagnose pod failures | `why is pod my-app failing?` |
| Deploy a website | `deploy a todo app with a nice UI` |
| Expose publicly | `expose the pod with a LoadBalancer` |
| Update web content | `change the website to show a calculator` |
| Node status | `show me node status` |
| Fix issues | `fix the failing pod` (asks permission first) |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Your Machine (CLI)                       │
│                                                             │
│   ┌──────────────┐      ┌──────────────────────────────┐   │
│   │  agent.py    │─────▶│  Azure AI Foundry            │   │
│   │  (Chat Loop) │◀─────│  GPT-4o (gpt-4o-2024-11-20) │   │
│   └──────┬───────┘      └──────────────────────────────┘   │
│          │ Function Calling                                  │
│          ▼                                                  │
│   ┌──────────────┐                                         │
│   │ k8s_tools.py │── Python Kubernetes Client              │
│   └──────┬───────┘                                         │
└──────────┼──────────────────────────────────────────────────┘
           │ HTTPS via kubeconfig
           ▼
┌─────────────────────────────────────────────────────────────┐
│              Azure Kubernetes Service (AKS)                  │
│                                                             │
│   Pods  │  ConfigMaps  │  Services (LoadBalancer → Public IP)│
└─────────────────────────────────────────────────────────────┘
```

---

## How It Works — The 3 Files

This project has 3 core files, each with one job:

### 1. `agent.py` — The Brain
- Runs the chat loop
- Sends your messages to GPT-4o
- Receives tool call instructions from GPT-4o
- **Asks your permission** before any destructive action (deploy, delete, expose)
- Calls the right function from `k8s_tools.py`
- Shows you the final result

### 2. `k8s_tools.py` — The Hands
- Contains all Kubernetes operations as Python functions
- Talks directly to AKS using the Kubernetes Python SDK
- Does NOT know about the conversation — just executes and returns data
- Functions: `list_pods`, `deploy_web_pod`, `create_service`, `get_pod_logs`, etc.

### 3. `tools_schema.py` — The Menu
- JSON descriptions of every tool sent to GPT-4o
- Tells GPT-4o: "here are the tools you can use and when to use them"
- Without this, GPT-4o would only chat — it would never take action
- Every function in `k8s_tools.py` has a matching entry here

```
You say something
      ↓
agent.py sends message + tools_schema.py to GPT-4o
      ↓
GPT-4o picks the right tool
      ↓
agent.py asks permission (if risky)
      ↓
agent.py calls k8s_tools.py function
      ↓
k8s_tools.py talks to AKS cluster
      ↓
Result flows back → GPT-4o explains it → You see the answer
```

---

## Permission System

Before any action that modifies the cluster, the agent pauses and asks:

```
╔ Permission Required ════════════════╗
  Tool: deploy_web_pod
  Args: {
    "name": "colorpicker-pod",
    "image": "nginx:latest"
  }
  Allow? (yes/no)
╚═════════════════════════════════════╝
```

Actions that require permission:
- `deploy_pod` / `deploy_web_pod`
- `create_service`
- `delete_pod` / `delete_service`
- `update_configmap`

Read-only actions (list, describe, logs) run automatically.

---

## Website Deployment Flow

When you ask for a website, the agent runs this full pipeline automatically:

```
Step 1: create_configmap     → writes your HTML/CSS/JS into Kubernetes
Step 2: deploy_web_pod       → starts nginx pod, mounts the HTML
Step 3: create_service       → creates LoadBalancer, Azure assigns public IP
Step 4: get_service          → fetches the IP
Step 5: gives you the URL    → open in browser
```

To update content later:
```
You: change the website to show a dark theme calculator
  → update_configmap (updates HTML in place)
  → nginx auto-serves new content
  → "Done. Refresh your browser."
```

---

## Azure Resources Required

| Resource | Name | Purpose |
|---|---|---|
| Resource Group | `k8ai-rg` | Container for all resources |
| AKS Cluster | `k8ai-cluster` | Kubernetes cluster (2 nodes) |
| Azure OpenAI | `k8ai-openai` | Hosts GPT-4o model |

---

## Setup & Installation

### Prerequisites
- [Azure CLI](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli)
- [kubectl](https://kubernetes.io/docs/tasks/tools/)
- Python 3.12+ (Anaconda recommended)
- Azure subscription

### Step 1 — Clone the repo
```bash
git clone https://github.com/<your-username>/k8AI.git
cd k8AI
```

### Step 2 — Install dependencies
```bash
pip install -r requirements.txt
```

### Step 3 — Set up Azure resources
```bash
# Login
az login

# Create resource group
az group create --name k8ai-rg --location eastus

# Create AKS cluster
az aks create --resource-group k8ai-rg --name k8ai-cluster \
  --node-count 2 --enable-managed-identity --generate-ssh-keys

# Create Azure OpenAI
az cognitiveservices account create \
  --name k8ai-openai --resource-group k8ai-rg \
  --kind OpenAI --sku S0 --location eastus

# Add custom domain (required for SDK)
az cognitiveservices account update \
  --name k8ai-openai --resource-group k8ai-rg \
  --custom-domain k8ai-openai

# Deploy GPT-4o model
az cognitiveservices account deployment create \
  --name k8ai-openai --resource-group k8ai-rg \
  --deployment-name gpt-4o --model-name gpt-4o \
  --model-version "2024-11-20" --model-format OpenAI \
  --sku-capacity 10 --sku-name Standard
```

### Step 4 — Configure credentials
```bash
# Copy the example env file
cp .env.example .env
```

Edit `.env` with your values:
```
AZURE_OPENAI_ENDPOINT=https://k8ai-openai.openai.azure.com/
AZURE_OPENAI_API_KEY=<get from: az cognitiveservices account keys list --name k8ai-openai --resource-group k8ai-rg>
AZURE_OPENAI_DEPLOYMENT=gpt-4o
AZURE_OPENAI_API_VERSION=2024-10-21
```

### Step 5 — Connect kubectl to AKS
```bash
az aks get-credentials --resource-group k8ai-rg --name k8ai-cluster
kubectl get nodes  # verify connection
```

### Step 6 — Run the agent
```bash
python agent.py
```

---

## Project Structure

```
k8AI/
├── agent.py          # Main agent loop — conversation, GPT-4o, permissions
├── k8s_tools.py      # All Kubernetes operations (Python functions)
├── tools_schema.py   # Tool definitions sent to GPT-4o (function calling)
├── .env.example      # Template for credentials (copy to .env)
├── requirements.txt  # Python dependencies
└── ARCHITECTURE.md   # Detailed architecture documentation
```

---

## Tools Available

| Tool | Type | Description |
|---|---|---|
| `list_pods` | Read | List all pods and their status |
| `describe_pod` | Read | Get K8s events — reveals ImagePullBackOff, OOMKilled etc. |
| `get_pod_logs` | Read | Fetch container logs (supports previous crashed container) |
| `get_node_status` | Read | Node CPU, memory, ready status |
| `list_namespaces` | Read | List all namespaces |
| `deploy_pod` | Write | Deploy a generic pod |
| `deploy_web_pod` | Write | Deploy nginx with optional custom HTML content |
| `create_configmap` | Write | Store HTML/CSS/JS as Kubernetes ConfigMap |
| `update_configmap` | Write | Update live web content |
| `create_service` | Write | Expose pod via LoadBalancer (public IP) |
| `get_service` | Read | Get service external IP and URL |
| `delete_pod` | Write | Delete a pod |
| `delete_service` | Write | Delete a service |
| `exec_in_pod` | Read | Run shell command inside a pod |

---

## Tech Stack

| Layer | Technology |
|---|---|
| AI Model | GPT-4o — Azure AI Foundry |
| Kubernetes | Azure Kubernetes Service (AKS) |
| Agent Pattern | OpenAI Function Calling |
| K8s Client | `kubernetes` Python SDK |
| Terminal UI | `rich` |
| Language | Python 3.12 |

---

## Security Notes

- `.env` is in `.gitignore` — API keys are never committed
- Cluster auth uses kubeconfig (AKS managed identity — no passwords)
- All write operations require explicit user approval

---

## License

MIT
