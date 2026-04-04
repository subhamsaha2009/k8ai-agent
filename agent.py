import json
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box
import k8s_tools
from tools_schema import TOOLS
from providers import load_provider

load_dotenv()

console = Console()
provider = load_provider()

# Auto-detect AKS cluster at startup
aks_info = None
with console.status("[dim]Detecting cluster type...[/dim]", spinner="dots"):
    aks_info = k8s_tools.detect_aks_cluster()

DESTRUCTIVE_TOOLS = {"deploy_pod", "delete_pod", "deploy_web_pod", "create_service", "delete_service", "update_configmap"}

# kubectl commands that are read-only (safe to run without permission)
SAFE_KUBECTL_VERBS = {"get", "describe", "logs", "top", "explain", "api-resources",
                      "api-versions", "version", "cluster-info", "auth", "config", "diff"}

# az aks sub-commands that are read-only
SAFE_AKS_VERBS = {"show", "list", "get-upgrades", "get-credentials", "get-versions",
                  "nodepool list", "nodepool show"}

def is_destructive_kubectl(command: str) -> bool:
    """Check if a kubectl command is destructive (needs permission + impact analysis)."""
    parts = command.strip().split()
    if not parts:
        return True  # empty command, be safe
    verb = parts[0].lower()
    return verb not in SAFE_KUBECTL_VERBS

def is_destructive_aks(command: str) -> bool:
    """Check if an az aks command is destructive."""
    parts = command.strip().split()
    if not parts:
        return True
    # Check two-word commands first (e.g., "nodepool list")
    if len(parts) >= 2:
        two_word = f"{parts[0].lower()} {parts[1].lower()}"
        if two_word in SAFE_AKS_VERBS:
            return False
    verb = parts[0].lower()
    return verb not in SAFE_AKS_VERBS

SYSTEM_PROMPT = """
You are an expert Kubernetes operations AI agent connected to a live AKS cluster.
You have FULL capability to perform all K8s operations using your tools. NEVER tell the user you cannot do something if a tool exists for it.

═══ STRICT RULES ═══
1. NEVER say "I cannot create a service" — use create_service tool.
2. NEVER say "I cannot modify web content" — use create_configmap or update_configmap tool.
3. NEVER say "you need to run kubectl manually" — use your tools instead.
4. ALWAYS use deploy_web_pod (not deploy_pod) when the user wants a web-accessible pod.
5. ALWAYS follow deploy_web_pod immediately with create_service(service_type="LoadBalancer").
6. ALWAYS follow create_service with get_service to retrieve the public IP for the user.
7. For destructive actions, ask permission — but do it via the tool, not by refusing.

═══ TOOL REFERENCE ═══
• list_pods / describe_pod / get_pod_logs — cluster diagnostics
• deploy_pod — generic pod (no web exposure)
• deploy_web_pod — nginx pod with optional custom HTML (use this for all web requests)
• create_configmap(name, html_content) — store HTML to mount into nginx
• update_configmap(name, html_content) — update existing HTML content live
• create_service(name, pod_name, service_type="LoadBalancer") — expose pod externally
• get_service(name) — get public IP and URL
• delete_pod / delete_service — cleanup
• list_namespaces / get_node_status — cluster info
• run_kubectl(command) — execute ANY kubectl command for operations not covered above

═══ KUBECTL TOOL USAGE ═══
Use run_kubectl for ALL operations that don't have a specific tool:
  • Deployments: run_kubectl("get deployments"), run_kubectl("scale deploy nginx --replicas=3")
  • StatefulSets: run_kubectl("get statefulsets")
  • DaemonSets: run_kubectl("get daemonsets")
  • Ingress: run_kubectl("get ingress"), run_kubectl("describe ingress my-ingress")
  • Events: run_kubectl("get events --sort-by=.lastTimestamp")
  • Rollouts: run_kubectl("rollout restart deploy nginx"), run_kubectl("rollout status deploy nginx")
  • Nodes: run_kubectl("drain node-1"), run_kubectl("cordon node-1")
  • PVCs: run_kubectl("get pvc"), run_kubectl("describe pvc my-volume")
  • Jobs/CronJobs: run_kubectl("get jobs"), run_kubectl("get cronjobs")
  • All resources: run_kubectl("get all"), run_kubectl("get all -A")
  • Labels: run_kubectl("get pods -l app=nginx")
  • YAML output: run_kubectl("get deploy nginx", output_format="yaml")

RULE: Prefer specific tools (list_pods, describe_pod, etc.) for common operations.
      Use run_kubectl for EVERYTHING ELSE — never tell the user you cannot do something.

═══ WEB POD WORKFLOW (follow exactly) ═══
User asks for a web pod or website:
  Step 1 → create_configmap with full HTML/CSS/JS content
  Step 2 → deploy_web_pod with configmap_name set
  Step 3 → create_service with service_type="LoadBalancer"
  Step 4 → get_service → give user the URL: http://<external_ip>

User asks to change/update web content:
  Step 1 → update_configmap with new HTML
  Step 2 → tell user to refresh browser (nginx auto-serves new content)

═══ WEBSITE CREATION CAPABILITY ═══
When a user describes a website or app (e.g., "color picker", "todo app", "calculator"):
  - Write complete, beautiful HTML with inline CSS and JavaScript
  - No backend needed — pure HTML/CSS/JS served by nginx
  - Use modern styling (gradients, shadows, responsive design)
  - Create the configmap, deploy the pod, expose it, return the URL

═══ DIAGNOSTICS WORKFLOW ═══
For failed pods:
  Step 1 → list_pods to find failing pods
  Step 2 → describe_pod to get K8s events
  Step 3 → get_pod_logs (previous=true for CrashLoopBackOff)
  Step 4 → summarize root cause, propose fix, ask permission

Common errors: CrashLoopBackOff=app crash, ImagePullBackOff=bad image name,
OOMKilled=out of memory, Pending=no resources/scheduling issue

═══ OOMKill REPRODUCTION ═══
When user wants to simulate/reproduce an OOMKill:
  Use deploy_pod in ONE call with ALL of these set:
  - image: "busybox"
  - memory_limit: "10Mi"
  - memory_request: "10Mi"
  - command: "dd if=/dev/zero bs=1M count=100"   ← allocates 100MB, kills pod at 10Mi limit
  Do NOT deploy first and configure later. Set limits and command in the SAME deploy_pod call.

═══ KUBELET LOGS WORKFLOW ═══
When user asks about kubelet logs, node logs, or node-level issues:
  Step 1 → get_node_names() to list available nodes
  Step 2 → ask user which node (or pick the relevant one if obvious)
  Step 3 → get_kubelet_logs(node_name, lines=100)
  Step 4 → analyze logs for errors: OOMKill, ImagePull failures, CNI issues, certificate errors
  Step 5 → summarize findings and suggest fixes

═══ RESOURCE UTILIZATION WORKFLOW ═══
When user asks about CPU/memory usage or resource utilization:
  Step 1 → get_pod_resource_usage(pod_name) for live metrics
  Step 2 → if error "metrics-server not available": call check_metrics_server
  Step 3 → if metrics-server not installed: tell user the install command and offer to run it
  Step 4 → get_pod_resource_limits(pod_name) to compare usage vs configured limits
  Step 5 → summarize: is the pod near its limit? Is it OOMKill risk?

═══ DESTRUCTIVE COMMAND SAFETY ═══
For ANY destructive kubectl command (delete, drain, scale, cordon, rollout restart, apply, patch, etc.):
  - The system will automatically run a deep impact analysis BEFORE asking for permission
  - The impact analysis checks: dependent pods, services, ingress, HPA, PDB
  - The user will see the full impact report with risk level and safer alternatives
  - Read-only commands (get, describe, logs, top) run immediately without permission
  - NEVER bypass this safety gate — it protects the user from accidental damage

═══ AKS CLUSTER MANAGEMENT (only if AKS detected) ═══
If this is an AKS cluster, you have run_az_aks tool for Azure-level operations:
  • Cluster info: run_az_aks("show"), run_az_aks("get-upgrades")
  • Upgrades: run_az_aks("upgrade --kubernetes-version 1.29.0")
  • Start/Stop: run_az_aks("stop"), run_az_aks("start")
  • Node pools: run_az_aks("nodepool list"), run_az_aks("nodepool add --name gpu --node-count 1 --node-vm-size Standard_NC6")
  • Scale pools: run_az_aks("nodepool scale --name nodepool1 --node-count 5")
  • Addons: run_az_aks("enable-addons --addons monitoring"), run_az_aks("disable-addons --addons monitoring")
  • Autoscaler: run_az_aks("update --enable-cluster-autoscaler --min-count 1 --max-count 5")

CRITICAL RULES for az aks commands:
  1. ALWAYS call get_az_aks_help("subcommand") BEFORE run_az_aks to verify the exact flags.
  2. Read the help output carefully — use ONLY the flags listed there. NEVER invent flags.
  3. If a single user request needs multiple operations (e.g., "disable autoscaler AND set node count"),
     break it into SEPARATE commands. Example:
       - az aks nodepool update --disable-cluster-autoscaler  (first command)
       - az aks nodepool scale --node-count 2                 (second command)
  4. NEVER retry a failed command with guessed flags. If a command fails, re-check get_az_aks_help.
  5. NEVER pass "false" or "true" as values to boolean flags. Boolean flags are standalone:
     ✅ --disable-cluster-autoscaler     (correct)
     ❌ --enable-cluster-autoscaler false (wrong)

Resource group and cluster name are auto-injected — no need to pass them manually.
Same safety rules apply: destructive AKS operations show impact analysis before executing.

═══ AZURE DOCS LOOKUP ═══
You have two tools to look up official Microsoft documentation:
  • search_azure_docs("query") — search Microsoft Learn for any Azure/AKS topic
  • fetch_azure_doc("url") — fetch full content of a specific docs page

Use these when:
  - User asks about available addons, extensions, or features
  - You need accurate, up-to-date information about AKS capabilities
  - The az aks --help output is incomplete or unclear
  - User asks "what options do I have for X?"

Workflow:
  Step 1 → search_azure_docs("AKS available addons extensions")
  Step 2 → fetch_azure_doc(url) for the most relevant result
  Step 3 → Answer with accurate information from official docs

NEVER rely solely on --help for listing available features. Always check official docs.
"""


def ask_permission(tool_name, args, impact=None):
    """Ask user permission before executing a destructive action.
    If impact analysis is provided, show it in the permission panel."""

    if impact and impact.get("action"):
        # Build rich impact report
        risk = impact.get("risk_level", "UNKNOWN")
        risk_colors = {"CRITICAL": "red bold", "HIGH": "red", "MEDIUM": "yellow", "LOW": "green"}
        risk_style = risk_colors.get(risk, "white")

        lines = [
            f"[yellow bold]⚠  IMPACT ANALYSIS[/yellow bold]\n",
            f"[bold]Command:[/bold] {impact.get('command', '')}",
            f"[bold]What this does:[/bold] {impact.get('what_this_does', '')}",
            f"[bold]Risk Level:[/bold] [{risk_style}]{risk}[/{risk_style}]\n",
        ]

        if impact.get("direct_impact"):
            lines.append("[bold]── Direct Impact ──[/bold]")
            for item in impact["direct_impact"]:
                lines.append(f"  • {item}")
            lines.append("")

        if impact.get("dependent_resources"):
            lines.append("[bold]── Dependent Resources Affected ──[/bold]")
            for item in impact["dependent_resources"]:
                lines.append(f"  • {item}")
            lines.append("")

        if impact.get("safer_alternatives"):
            lines.append("[bold]── Safer Alternatives ──[/bold]")
            for item in impact["safer_alternatives"]:
                lines.append(f"  • {item}")
            lines.append("")

        lines.append("[white]Do you want to proceed? (yes/no)[/white]")

        console.print(Panel(
            "\n".join(lines),
            title=f"[red]⚠  Permission Needed — {risk} RISK[/red]",
            border_style="red" if risk in ("CRITICAL", "HIGH") else "yellow",
        ))
    else:
        console.print(Panel(
            f"[yellow bold]Action Required[/yellow bold]\n\n"
            f"Tool: [bold]{tool_name}[/bold]\n"
            f"Args: {json.dumps(args, indent=2)}\n\n"
            f"[white]Do you want to proceed? (yes/no)[/white]",
            title="[red]Permission Needed[/red]",
            border_style="yellow"
        ))

    response = input("Your decision: ").strip().lower()
    return response in ("yes", "y")


def execute_tool(name, args):
    fn = getattr(k8s_tools, name)
    return fn(**args)


def print_welcome():
    table = Table(box=box.ROUNDED, show_header=False, border_style="cyan")
    table.add_column(style="bold")
    table.add_column()

    if aks_info and aks_info.get("is_aks"):
        cluster_display = f"{aks_info['cluster_name']} (AKS — {aks_info.get('location', '')})"
        table.add_row("Cluster", cluster_display)
        table.add_row("Resource Group", aks_info.get("resource_group", ""))
        table.add_row("K8s Version", aks_info.get("kubernetes_version", ""))
        table.add_row("AKS Management", "[green]Enabled[/green] (az aks commands available)")
    else:
        table.add_row("Cluster", "Kubernetes (non-AKS)")
        table.add_row("AKS Management", "[dim]Disabled[/dim]")

    table.add_row("AI Model", provider.get_model_name())
    table.add_row("Commands", "Type your request or 'exit' to quit")

    console.print(Panel(
        table,
        title="[bold cyan]K8s AI Agent[/bold cyan]",
        border_style="cyan"
    ))
    console.print()
    console.print("[dim]Examples:[/dim]")
    console.print("[dim]  • check my cluster for failed pods[/dim]")
    console.print("[dim]  • deploy a color picker website[/dim]")
    console.print("[dim]  • show me all deployments in all namespaces[/dim]")
    if aks_info and aks_info.get("is_aks"):
        console.print("[dim]  • show me available kubernetes upgrades[/dim]")
        console.print("[dim]  • list my node pools[/dim]")
        console.print("[dim]  • enable monitoring addon[/dim]")
    console.print("[dim]  • why is pod <name> failing?[/dim]")
    console.print()


def agent_loop():
    print_welcome()
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    while True:
        try:
            user_input = input("[bold green]You:[/bold green] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Goodbye.[/dim]")
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit", "q"):
            console.print("[dim]Goodbye.[/dim]")
            break

        messages.append({"role": "user", "content": user_input})

        # Agent loop — continues until the model stops calling tools
        while True:
            with console.status("[dim]Thinking...[/dim]", spinner="dots"):
                response = provider.chat(messages, TOOLS)

            messages.append(provider.build_assistant_message(response))

            tool_calls = provider.get_tool_calls(response)

            # No tool calls — model has a final answer
            if not tool_calls:
                console.print(f"\n[bold cyan]Agent:[/bold cyan] {provider.get_content(response)}\n")
                break

            # Process each tool call
            for tool_call in tool_calls:
                tool_name = tool_call.name
                args = tool_call.arguments

                console.print(f"[dim]  → {tool_name}({json.dumps(args)})[/dim]")

                # Determine if this action needs permission
                needs_permission = False
                impact = None

                if tool_name == "run_az_aks":
                    # Auto-inject resource_group and cluster_name from AKS detection
                    if aks_info and aks_info.get("is_aks"):
                        if "resource_group" not in args:
                            args["resource_group"] = aks_info["resource_group"]
                        if "cluster_name" not in args:
                            args["cluster_name"] = aks_info["cluster_name"]
                    cmd = args.get("command", "")
                    if is_destructive_aks(cmd):
                        needs_permission = True
                        with console.status("[dim]Analyzing AKS impact...[/dim]", spinner="dots"):
                            impact = k8s_tools.analyze_aks_impact(
                                cmd, args.get("resource_group"), args.get("cluster_name"))
                elif tool_name == "run_kubectl":
                    cmd = args.get("command", "")
                    if is_destructive_kubectl(cmd):
                        needs_permission = True
                        # Run deep impact analysis
                        with console.status("[dim]Analyzing impact...[/dim]", spinner="dots"):
                            impact = k8s_tools.analyze_impact(cmd)
                    # else: read-only kubectl, runs freely
                elif tool_name in DESTRUCTIVE_TOOLS:
                    needs_permission = True

                if needs_permission:
                    if not ask_permission(tool_name, args, impact):
                        result = {"status": "denied", "message": "User denied this action."}
                        console.print("[yellow]  Action denied.[/yellow]")
                    else:
                        try:
                            # AKS operations can take minutes — show spinner
                            if tool_name == "run_az_aks":
                                with console.status("[dim]Executing AKS operation (this may take a few minutes)...[/dim]", spinner="dots"):
                                    result = execute_tool(tool_name, args)
                            else:
                                result = execute_tool(tool_name, args)
                            console.print(f"[green]  Done: {result}[/green]")
                        except Exception as e:
                            result = {"error": str(e)}
                            console.print(f"[red]  Error: {e}[/red]")
                else:
                    try:
                        # AKS read-only commands can also be slow
                        if tool_name == "run_az_aks":
                            with console.status("[dim]Querying AKS...[/dim]", spinner="dots"):
                                result = execute_tool(tool_name, args)
                        else:
                            result = execute_tool(tool_name, args)
                    except Exception as e:
                        result = {"error": str(e)}
                        console.print(f"[red]  Tool error: {e}[/red]")

                messages.append(provider.build_tool_result(tool_call, json.dumps(result)))


if __name__ == "__main__":
    agent_loop()
