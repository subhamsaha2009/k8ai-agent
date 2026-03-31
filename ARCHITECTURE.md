# K8s AI Agent — Architecture & Technical Documentation

**Project:** Kubernetes AI Operations Agent  
**Platform:** Azure (AKS + Azure AI Foundry)  
**Author:** Subham Saha  
**Date:** March 2026

---

## 1. What This Project Does

This is a conversational AI agent that connects to a live Azure Kubernetes Service (AKS) cluster. You interact with it in plain English — it understands your intent, executes Kubernetes operations, and reports results. It can:

- **Diagnose** failed pods and explain the root cause
- **Deploy** web applications with a single sentence
- **Expose** pods publicly via a LoadBalancer and return a live URL
- **Update** web content on the fly using Kubernetes ConfigMaps
- **Fix** issues — but always asks for your permission before making changes

---

## 2. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Developer Machine                     │
│                                                             │
│   ┌──────────────┐      ┌──────────────────────────────┐   │
│   │  agent.py    │─────▶│  Azure AI Foundry            │   │
│   │  (CLI Chat)  │◀─────│  GPT-4o (gpt-4o 2024-11-20) │   │
│   └──────┬───────┘      └──────────────────────────────┘   │
│          │ Function Calling (Tools)                         │
│          ▼                                                  │
│   ┌──────────────┐                                         │
│   │ k8s_tools.py │  ── Python Kubernetes Client            │
│   └──────┬───────┘                                         │
└──────────┼──────────────────────────────────────────────────┘
           │ HTTPS (kubeconfig / AKS API)
           ▼
┌─────────────────────────────────────────────────────────────┐
│                    Azure Kubernetes Service                   │
│                    k8ai-cluster  (eastus)                    │
│                                                             │
│   ┌─────────────┐   ┌──────────────┐   ┌───────────────┐  │
│   │  Pods        │   │  ConfigMaps  │   │   Services    │  │
│   │  (nginx etc.)│   │  (HTML/CSS)  │   │  (LoadBalancer│  │
│   └─────────────┘   └──────────────┘   │   → Public IP)│  │
│                                         └───────────────┘  │
└─────────────────────────────────────────────────────────────┘
           │
           ▼
     Public Internet
     http://<LoadBalancer-IP>  ──▶  User's Browser
```

---

## 3. Azure Resources Created

| Resource | Name | Location | Purpose |
|---|---|---|---|
| Resource Group | `k8ai-rg` | East US | Container for all resources |
| AKS Cluster | `k8ai-cluster` | East US | Managed Kubernetes, 2 nodes, K8s v1.34.4 |
| Azure OpenAI | `k8ai-openai` | East US | Hosts the GPT-4o model |
| GPT-4o Deployment | `gpt-4o` | East US | `gpt-4o-2024-11-20`, 10K TPM |

**AKS Node Specs:** Standard_D4d_v5 (4 vCPU, 16GB RAM), Ubuntu 22.04, Ephemeral OS disk 150GB  
**OpenAI Endpoint:** `https://k8ai-openai.openai.azure.com/`

---

## 4. Project File Structure

```
k8AI/
├── agent.py          ← Main entry point — agent loop & conversation
├── k8s_tools.py      ← All Kubernetes operations (Python functions)
├── tools_schema.py   ← Tool definitions sent to GPT-4o
├── .env              ← Azure OpenAI credentials
└── requirements.txt  ← Python dependencies
```

---

## 5. File-by-File Deep Dive

---

### 5.1 `agent.py` — The Brain

**Role:** Runs the main conversation loop. Connects the user to GPT-4o and orchestrates tool execution.

**Key Components:**

| Component | Description |
|---|---|
| `AzureOpenAI` client | Connects to Azure AI Foundry using endpoint + API key from `.env` |
| `SYSTEM_PROMPT` | Instructs GPT-4o on its role, what tools to use, and when |
| `DESTRUCTIVE_TOOLS` | Set of tool names that require user approval before execution |
| `ask_permission()` | Shows a permission panel and waits for yes/no before running risky actions |
| `execute_tool()` | Dynamically calls the matching function from `k8s_tools.py` |
| `agent_loop()` | Main while loop: takes user input → calls GPT-4o → executes tools → repeats |

**How the Agent Loop Works (Step by Step):**

```
1. User types a message (e.g., "check for failed pods")
2. Message is appended to the conversation history
3. GPT-4o is called with the full history + available tools
4. GPT-4o responds with either:
   a. A tool_call → agent executes the tool, appends result, calls GPT-4o again
   b. A plain message → displayed to the user, loop ends for this turn
5. For destructive tools: permission is requested before execution
6. Repeat from step 1
```

**Permission System:**

Certain tools require explicit user approval before running. These are:
- `deploy_pod` — creates a pod
- `deploy_web_pod` — creates a web-facing pod
- `create_service` — exposes a pod to the internet
- `delete_pod` — removes a pod
- `delete_service` — removes a service
- `update_configmap` — modifies live web content

---

### 5.2 `k8s_tools.py` — The Hands

**Role:** All actual Kubernetes API calls. Each function is a discrete operation the agent can perform. Uses the official `kubernetes` Python client.

**Authentication:** Reads `~/.kube/config` (populated by `az aks get-credentials`). No hardcoded credentials.

**Functions Reference:**

| Function | Category | What It Does |
|---|---|---|
| `list_pods(namespace)` | Diagnostics | Lists all pods with status, container states, restart counts |
| `describe_pod(pod_name)` | Diagnostics | Gets K8s events for a pod — reveals ImagePullBackOff, OOMKilled etc. |
| `get_pod_logs(pod_name, previous)` | Diagnostics | Fetches stdout/stderr logs. `previous=True` gets logs from crashed container |
| `get_node_status()` | Diagnostics | Lists nodes with CPU, memory, and Ready status |
| `list_namespaces()` | Diagnostics | Lists all K8s namespaces |
| `deploy_pod(name, image)` | Deployment | Creates a generic pod (no web exposure) |
| `deploy_web_pod(name, configmap_name)` | Deployment | Creates nginx pod, optionally mounts ConfigMap as HTML content |
| `create_configmap(name, html_content)` | Content | Stores HTML/CSS/JS as a K8s ConfigMap key `index.html` |
| `update_configmap(name, html_content)` | Content | Replaces ConfigMap data — nginx serves updated content immediately |
| `create_service(name, pod_name, service_type)` | Networking | Creates K8s Service. `LoadBalancer` type gets a public Azure IP |
| `get_service(name)` | Networking | Returns service details including public IP and browser URL |
| `delete_pod(pod_name)` | Cleanup | Deletes a pod (forces restart if managed by a controller) |
| `delete_service(name)` | Cleanup | Deletes a Service and releases the LoadBalancer IP |
| `exec_in_pod(pod_name, command)` | Inspection | Runs a shell command inside a running pod (like `kubectl exec`) |
| `_sanitize_name(name)` | Utility | Converts any string to a valid K8s name (RFC 1123: lowercase, hyphens only, max 63 chars) |

---

### 5.3 `tools_schema.py` — The Contract

**Role:** Defines the JSON schema for each tool. This is sent to GPT-4o with every request so the model knows exactly what tools are available, what parameters they accept, and when to use them.

**Why This Matters:** This is the bridge between natural language and code. When you say *"deploy a color picker"*, GPT-4o reads the tool descriptions and decides to call `create_configmap` → `deploy_web_pod` → `create_service` → `get_service` in sequence.

**Tools Defined:** 13 tools total — each with name, description, and parameter schema.

---

### 5.4 `.env` — Credentials

```
AZURE_OPENAI_ENDPOINT=https://k8ai-openai.openai.azure.com/
AZURE_OPENAI_API_KEY=<key>
AZURE_OPENAI_DEPLOYMENT=gpt-4o
AZURE_OPENAI_API_VERSION=2024-10-21
```

> **Security note:** Never commit `.env` to version control. Add it to `.gitignore`.

---

### 5.5 `requirements.txt` — Dependencies

| Package | Version | Purpose |
|---|---|---|
| `openai` | 2.x | Azure OpenAI SDK — function calling, chat completions |
| `kubernetes` | 35.x | Official K8s Python client — all cluster API calls |
| `python-dotenv` | 1.x | Load `.env` file into environment variables |
| `rich` | 14.x | Beautiful terminal output — panels, tables, colors |

---

## 6. Key Workflows

### 6.1 Diagnosing a Failed Pod

```
User: "why is my pod failing?"
         │
         ▼
  GPT-4o decides to call:
  1. list_pods() ──────────────────▶ finds pod in "Error" or "CrashLoopBackOff"
  2. describe_pod("pod-name") ─────▶ reads K8s events (e.g., "ImagePullBackOff")
  3. get_pod_logs("pod-name",       
       previous=True) ─────────────▶ reads application error logs
         │
         ▼
  GPT-4o synthesizes diagnosis:
  "Pod is in CrashLoopBackOff. Logs show KeyError: DATABASE_URL.
   The container is missing a required environment variable."
         │
         ▼
  Agent proposes fix → asks permission → applies if approved
```

### 6.2 Deploying a Website End-to-End

```
User: "deploy a color picker app"
         │
         ▼
  GPT-4o generates full HTML/CSS/JS for the app
         │
         ▼
  Step 1: create_configmap("colorpicker", "<html>...")
          ─── stores HTML in K8s ConfigMap
         │
         ▼
  Step 2: [Permission] deploy_web_pod("colorpicker-pod", configmap_name="colorpicker")
          ─── nginx pod created, ConfigMap mounted at /usr/share/nginx/html
         │
         ▼
  Step 3: [Permission] create_service("colorpicker-svc", "colorpicker-pod", type="LoadBalancer")
          ─── AKS provisions Azure Load Balancer, assigns public IP
         │
         ▼
  Step 4: get_service("colorpicker-svc")
          ─── retrieves public IP
         │
         ▼
  Agent: "Your app is live at http://20.x.x.x"
         │
         ▼
  User opens browser → sees the color picker app
```

### 6.3 Updating Web Content Live

```
User: "change the app to show a calculator instead"
         │
         ▼
  GPT-4o generates new HTML for a calculator
         │
         ▼
  Step 1: [Permission] update_configmap("colorpicker", "<new html>")
          ─── K8s updates the ConfigMap data
          ─── nginx automatically picks up the new index.html
         │
         ▼
  Agent: "Done. Refresh your browser at http://20.x.x.x"
```

---

## 7. How GPT-4o Function Calling Works

This is the core mechanism of the agent. Here's what happens at the API level:

```
Request to GPT-4o:
{
  "model": "gpt-4o",
  "messages": [ system_prompt + conversation_history ],
  "tools": [ ...13 tool definitions from tools_schema.py... ],
  "tool_choice": "auto"
}

GPT-4o Response (when it wants to use a tool):
{
  "tool_calls": [{
    "function": {
      "name": "list_pods",
      "arguments": "{\"namespace\": \"default\"}"
    }
  }]
}

Agent executes list_pods(namespace="default")
Appends result back to messages:
{
  "role": "tool",
  "content": "[{\"name\": \"my-pod\", \"status\": \"Failed\", ...}]"
}

Calls GPT-4o again → model analyzes result → may call more tools or give final answer
```

This loop continues until GPT-4o stops calling tools and returns a plain text response.

---

## 8. Security Design

| Concern | How It's Handled |
|---|---|
| Destructive K8s actions | Permission gate — user must type "yes" before execution |
| API credentials | Stored in `.env`, never hardcoded |
| Cluster authentication | Uses kubeconfig with AKS managed identity (no passwords) |
| Conversation context | Kept in memory only, not persisted to disk |

---

## 9. How to Run

**Prerequisites:**
- Azure CLI (`az`) installed and logged in
- `kubectl` installed and connected to `k8ai-cluster`
- Python 3.12+ with conda (base environment)

```powershell
# Connect to cluster (run once per session)
az aks get-credentials --resource-group k8ai-rg --name k8ai-cluster

# Run the agent
cd C:\Users\subhamsaha\k8AI
C:\Users\subhamsaha\AppData\Local\anaconda3\python.exe agent.py
```

**Sample Prompts:**
```
check my cluster for failed pods
deploy a todo app with a nice UI
expose the pod externally with a LoadBalancer
update the web content to show a dark themed calculator
why is pod nginx-web-ui failing?
show me node status
```

---

## 10. Tech Stack Summary

| Layer | Technology |
|---|---|
| AI Model | GPT-4o on Azure AI Foundry |
| Kubernetes Cluster | Azure Kubernetes Service (AKS) |
| Agent Framework | Custom Python loop with OpenAI function calling |
| K8s Client | Official `kubernetes` Python SDK |
| Terminal UI | `rich` library |
| Authentication | Azure CLI kubeconfig + OpenAI API key |
| Language | Python 3.12 |
| OS | Windows 11 (dev machine) |
