"""
K8s AI Agent — MCP Server
Exposes all k8s_tools as MCP tools for use with VS Code GitHub Copilot, Claude Desktop, etc.
Destructive commands use two-step confirmation (Option B safety).
"""

import uuid
import json
import k8s_tools
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("k8ai", instructions=(
    "K8s AI Agent — Kubernetes cluster management tools. "
    "Safe commands (get, describe, logs, list) execute immediately. "
    "Destructive commands (delete, scale, drain, etc.) return an impact analysis "
    "and require you to call confirm_destructive_action(action_id) to proceed."
))

# ─── Pending destructive actions (Option B safety) ────────────────────────
_pending_actions: dict = {}

SAFE_KUBECTL_VERBS = {
    "get", "describe", "logs", "top", "explain", "api-resources",
    "api-versions", "version", "cluster-info", "auth", "config", "diff",
}

SAFE_AKS_VERBS = {
    "show", "list", "get-upgrades", "get-credentials", "get-versions",
    "nodepool list", "nodepool show",
}


def _is_destructive_kubectl(command: str) -> bool:
    verb = command.strip().split()[0].lower() if command.strip() else ""
    return verb not in SAFE_KUBECTL_VERBS


def _is_destructive_aks(command: str) -> bool:
    cmd_lower = command.strip().lower()
    for safe in SAFE_AKS_VERBS:
        if cmd_lower.startswith(safe):
            return False
    return True


# ═══════════════════════════════════════════════════════════════════════════
#  CONFIRMATION TOOL
# ═══════════════════════════════════════════════════════════════════════════

@mcp.tool()
def confirm_destructive_action(action_id: str) -> str:
    """Confirm and execute a pending destructive action.
    Call this ONLY after reviewing the impact analysis returned by a destructive command.
    The action_id is provided in the impact analysis response."""
    if action_id not in _pending_actions:
        return json.dumps({"error": f"No pending action with id '{action_id}'. It may have expired or already been executed."})

    action_fn = _pending_actions.pop(action_id)
    try:
        result = action_fn()
        return json.dumps(result, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


# ═══════════════════════════════════════════════════════════════════════════
#  READ-ONLY / SAFE TOOLS — execute immediately
# ═══════════════════════════════════════════════════════════════════════════

@mcp.tool()
def list_pods(namespace: str = "default") -> str:
    """List all pods in a namespace with status, container states, restart counts, and failure reasons."""
    return json.dumps(k8s_tools.list_pods(namespace), default=str)


@mcp.tool()
def describe_pod(pod_name: str, namespace: str = "default") -> str:
    """Get detailed information and events for a specific pod."""
    return json.dumps(k8s_tools.describe_pod(pod_name, namespace), default=str)


@mcp.tool()
def get_pod_logs(pod_name: str, namespace: str = "default", lines: int = 100, previous: bool = False) -> str:
    """Fetch logs from a pod. Use previous=true for crashed container logs."""
    return json.dumps(k8s_tools.get_pod_logs(pod_name, namespace, lines, previous), default=str)


@mcp.tool()
def list_namespaces() -> str:
    """List all namespaces in the cluster."""
    return json.dumps(k8s_tools.list_namespaces(), default=str)


@mcp.tool()
def get_node_status() -> str:
    """Get status, CPU, and memory of all nodes."""
    return json.dumps(k8s_tools.get_node_status(), default=str)


@mcp.tool()
def get_node_names() -> str:
    """Get all node names in the cluster."""
    return json.dumps(k8s_tools.get_node_names(), default=str)


@mcp.tool()
def get_service(name: str, namespace: str = "default") -> str:
    """Get service details including external IP and URL."""
    return json.dumps(k8s_tools.get_service(name, namespace), default=str)


@mcp.tool()
def get_pod_resource_usage(pod_name: str = None, namespace: str = "default") -> str:
    """Get live CPU and memory usage for pods via metrics-server."""
    return json.dumps(k8s_tools.get_pod_resource_usage(pod_name, namespace), default=str)


@mcp.tool()
def get_pod_resource_limits(pod_name: str, namespace: str = "default") -> str:
    """Get CPU and memory requests/limits configured for a pod."""
    return json.dumps(k8s_tools.get_pod_resource_limits(pod_name, namespace), default=str)


@mcp.tool()
def check_metrics_server(namespace: str = "default") -> str:
    """Check if metrics-server is installed and working."""
    return json.dumps(k8s_tools.check_metrics_server(namespace), default=str)


@mcp.tool()
def exec_in_pod(pod_name: str, command: str, namespace: str = "default") -> str:
    """Run a shell command inside a running pod."""
    return json.dumps(k8s_tools.exec_in_pod(pod_name, command, namespace), default=str)


@mcp.tool()
def get_kubelet_logs(node_name: str, lines: int = 100) -> str:
    """Fetch kubelet system logs from a node. Use get_node_names first to find the node name."""
    return json.dumps(k8s_tools.get_kubelet_logs(node_name, lines), default=str)


# ═══════════════════════════════════════════════════════════════════════════
#  KUBECTL — safe commands run immediately, destructive get impact analysis
# ═══════════════════════════════════════════════════════════════════════════

@mcp.tool()
def run_kubectl(command: str, namespace: str = None, output_format: str = None) -> str:
    """Execute any kubectl command. Safe commands (get, describe, logs, top) run immediately.
    Destructive commands (delete, scale, drain, etc.) return an impact analysis first —
    you must then call confirm_destructive_action(action_id) to execute."""
    if not _is_destructive_kubectl(command):
        return json.dumps(k8s_tools.run_kubectl(command, namespace, output_format), default=str)

    # Destructive — run impact analysis, store action for confirmation
    impact = k8s_tools.analyze_impact(command)
    action_id = str(uuid.uuid4())[:8]
    _pending_actions[action_id] = lambda: k8s_tools.run_kubectl(command, namespace, output_format)

    return json.dumps({
        "status": "AWAITING_CONFIRMATION",
        "action_id": action_id,
        "message": "This is a destructive command. Review the impact analysis below, then call confirm_destructive_action(action_id) to execute.",
        "impact_analysis": impact,
    }, default=str)


# ═══════════════════════════════════════════════════════════════════════════
#  DESTRUCTIVE TOOLS — always require confirmation
# ═══════════════════════════════════════════════════════════════════════════

@mcp.tool()
def deploy_pod(name: str, image: str, namespace: str = "default",
               env_vars: dict = None, command: str = None,
               memory_limit: str = None, cpu_limit: str = None,
               memory_request: str = None, cpu_request: str = None) -> str:
    """Deploy a new pod. Returns impact analysis — call confirm_destructive_action(action_id) to execute."""
    action_id = str(uuid.uuid4())[:8]
    _pending_actions[action_id] = lambda: k8s_tools.deploy_pod(
        name, image, namespace, env_vars, command,
        memory_limit, cpu_limit, memory_request, cpu_request
    )
    return json.dumps({
        "status": "AWAITING_CONFIRMATION",
        "action_id": action_id,
        "message": f"Will deploy pod '{name}' with image '{image}' in namespace '{namespace}'. Call confirm_destructive_action('{action_id}') to proceed.",
        "details": {
            "name": name, "image": image, "namespace": namespace,
            "memory_limit": memory_limit, "cpu_limit": cpu_limit,
        }
    })


@mcp.tool()
def delete_pod(pod_name: str, namespace: str = "default") -> str:
    """Delete a pod. Returns confirmation prompt — call confirm_destructive_action(action_id) to execute."""
    action_id = str(uuid.uuid4())[:8]
    _pending_actions[action_id] = lambda: k8s_tools.delete_pod(pod_name, namespace)
    return json.dumps({
        "status": "AWAITING_CONFIRMATION",
        "action_id": action_id,
        "message": f"Will delete pod '{pod_name}' in namespace '{namespace}'. Call confirm_destructive_action('{action_id}') to proceed.",
    })


@mcp.tool()
def deploy_web_pod(name: str, namespace: str = "default",
                   configmap_name: str = None, image: str = "nginx:latest") -> str:
    """Deploy an nginx web pod. Returns confirmation prompt — call confirm_destructive_action(action_id) to execute."""
    action_id = str(uuid.uuid4())[:8]
    _pending_actions[action_id] = lambda: k8s_tools.deploy_web_pod(name, namespace, configmap_name, image)
    return json.dumps({
        "status": "AWAITING_CONFIRMATION",
        "action_id": action_id,
        "message": f"Will deploy web pod '{name}' in namespace '{namespace}'. Call confirm_destructive_action('{action_id}') to proceed.",
    })


@mcp.tool()
def create_configmap(name: str, html_content: str, namespace: str = "default") -> str:
    """Create a ConfigMap with HTML content."""
    return json.dumps(k8s_tools.create_configmap(name, html_content, namespace), default=str)


@mcp.tool()
def update_configmap(name: str, html_content: str, namespace: str = "default") -> str:
    """Update an existing ConfigMap. Returns confirmation prompt — call confirm_destructive_action(action_id) to execute."""
    action_id = str(uuid.uuid4())[:8]
    _pending_actions[action_id] = lambda: k8s_tools.update_configmap(name, html_content, namespace)
    return json.dumps({
        "status": "AWAITING_CONFIRMATION",
        "action_id": action_id,
        "message": f"Will update ConfigMap '{name}' in namespace '{namespace}'. Call confirm_destructive_action('{action_id}') to proceed.",
    })


@mcp.tool()
def create_service(name: str, pod_name: str, port: int = 80,
                   namespace: str = "default", service_type: str = "LoadBalancer") -> str:
    """Create a Kubernetes Service. Returns confirmation prompt — call confirm_destructive_action(action_id) to execute."""
    action_id = str(uuid.uuid4())[:8]
    _pending_actions[action_id] = lambda: k8s_tools.create_service(name, pod_name, port, namespace, service_type)
    return json.dumps({
        "status": "AWAITING_CONFIRMATION",
        "action_id": action_id,
        "message": f"Will create {service_type} service '{name}' exposing pod '{pod_name}' on port {port}. Call confirm_destructive_action('{action_id}') to proceed.",
    })


@mcp.tool()
def delete_service(name: str, namespace: str = "default") -> str:
    """Delete a Kubernetes Service. Returns confirmation prompt — call confirm_destructive_action(action_id) to execute."""
    action_id = str(uuid.uuid4())[:8]
    _pending_actions[action_id] = lambda: k8s_tools.delete_service(name, namespace)
    return json.dumps({
        "status": "AWAITING_CONFIRMATION",
        "action_id": action_id,
        "message": f"Will delete service '{name}' in namespace '{namespace}'. Call confirm_destructive_action('{action_id}') to proceed.",
    })


# ═══════════════════════════════════════════════════════════════════════════
#  AZURE DOCS TOOLS — always safe
# ═══════════════════════════════════════════════════════════════════════════

@mcp.tool()
def search_azure_docs(query: str) -> str:
    """Search official Microsoft Learn documentation for Azure/AKS topics."""
    return json.dumps(k8s_tools.search_azure_docs(query), default=str)


@mcp.tool()
def fetch_azure_doc(url: str) -> str:
    """Fetch full content of a Microsoft Learn documentation page."""
    return json.dumps(k8s_tools.fetch_azure_doc(url), default=str)


# ═══════════════════════════════════════════════════════════════════════════
#  AKS TOOLS — conditionally registered only on AKS clusters
# ═══════════════════════════════════════════════════════════════════════════

_aks_info = k8s_tools.detect_aks_cluster()

if _aks_info.get("is_aks"):
    _aks_rg = _aks_info.get("resource_group")
    _aks_name = _aks_info.get("cluster_name")

    @mcp.tool()
    def get_az_aks_help(subcommand: str = "") -> str:
        """Get official help text for any az aks command. Call this BEFORE run_az_aks when unsure about flags."""
        return json.dumps(k8s_tools.get_az_aks_help(subcommand), default=str)

    @mcp.tool()
    def run_az_aks(command: str, resource_group: str = None, cluster_name: str = None) -> str:
        """Execute any 'az aks' command. Safe commands run immediately.
        Destructive commands return impact analysis — call confirm_destructive_action(action_id) to execute.
        Resource group and cluster name are auto-injected."""
        rg = resource_group or _aks_rg
        cn = cluster_name or _aks_name

        if not _is_destructive_aks(command):
            return json.dumps(k8s_tools.run_az_aks(command, rg, cn), default=str)

        # Destructive — run impact analysis first
        impact = k8s_tools.analyze_aks_impact(command, rg, cn)
        action_id = str(uuid.uuid4())[:8]
        _pending_actions[action_id] = lambda: k8s_tools.run_az_aks(command, rg, cn)

        return json.dumps({
            "status": "AWAITING_CONFIRMATION",
            "action_id": action_id,
            "message": "This is a destructive AKS command. Review the impact analysis below, then call confirm_destructive_action(action_id) to execute.",
            "impact_analysis": impact,
            "cluster": {"resource_group": rg, "cluster_name": cn},
        }, default=str)


# ═══════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    mcp.run(transport="stdio")
