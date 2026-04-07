import json
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box
from k8ai import k8s_tools
from k8ai.tools_schema import TOOLS
from k8ai.providers import load_provider
from k8ai.logging_config import logger

console = Console()
provider = load_provider()

# Ensure we're using the current kubectl context
with console.status("[dim]Loading current kubectl context...[/dim]", spinner="dots"):
    k8s_tools._ensure_correct_context()

# Auto-detect AKS cluster at startup
aks_info = None
with console.status("[dim]Detecting cluster type...[/dim]", spinner="dots"):
    aks_info = k8s_tools.detect_aks_cluster()

DESTRUCTIVE_TOOLS = {"deploy_pod", "delete_pod", "deploy_web_pod", "create_service", "delete_service", "update_configmap", "debug_pod", "debug_node"}

# kubectl commands that are read-only (safe to run without permission)
SAFE_KUBECTL_VERBS = {"get", "describe", "logs", "top", "explain", "api-resources",
                      "api-versions", "version", "cluster-info", "auth", "config", "diff"}

# az aks sub-commands that are read-only
SAFE_AKS_VERBS = {"show", "list", "get-upgrades", "get-credentials", "get-versions",
                  "nodepool list", "nodepool show"}

# generic az sub-commands that are read-only
SAFE_AZ_VERBS = {"show", "list", "get"}

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

def is_destructive_az(command: str) -> bool:
    """Check if a generic az command is destructive."""
    parts = command.strip().lower().split()
    verb = None
    for token in parts:
        if token.startswith("-"):
            break
        verb = token
    return verb not in SAFE_AZ_VERBS if verb else True


def analyze_error(error_message: str, command: str = None) -> dict:
    """Analyze an error message and suggest fixes.
    Returns dict with 'pattern', 'explanation', 'recovery_suggestion', 'should_retry'."""
    err_lower = error_message.lower()
    
    # Pattern: Missing vm-set-type for nodepool add
    if "vm-set-type" in err_lower and ("vm-sizes" in err_lower or "vm-size" in err_lower):
        return {
            "pattern": "missing_vm_set_type",
            "explanation": "The nodepool add command requires --vm-set-type flag",
            "recovery_suggestion": "Add '--vm-set-type VirtualMachineScaleSets' to the command and retry",
            "should_retry": True,
        }
    
    # Pattern: Resource not found
    if "not found" in err_lower or "enoent" in err_lower or "404" in err_lower:
        return {
            "pattern": "resource_not_found",
            "explanation": f"The requested resource does not exist",
            "recovery_suggestion": "Check if the resource name is correct, or create it first",
            "should_retry": False,
        }
    
    # Pattern: Permission denied
    if "permission denied" in err_lower or "unauthorized" in err_lower or "403" in err_lower:
        return {
            "pattern": "permission_denied",
            "explanation": "You don't have permission to perform this action",
            "recovery_suggestion": "Check credentials, RBAC settings, or ask for proper permissions",
            "should_retry": False,
        }
    
    # Pattern: Timeout
    if "timeout" in err_lower or "context deadline" in err_lower or "timed out" in err_lower:
        return {
            "pattern": "timeout",
            "explanation": "The operation took longer than expected or exceeded the timeout",
            "recovery_suggestion": "Retry the command (AKS operations can take several minutes)",
            "should_retry": True,
        }
    
    # Pattern: Invalid command syntax
    if "invalid" in err_lower or "no resource found" in err_lower or "unrecognized arguments" in err_lower:
        return {
            "pattern": "invalid_syntax",
            "explanation": f"The command syntax appears to be invalid",
            "recovery_suggestion": "Call get_az_aks_help or get_az_help to check correct syntax, then retry",
            "should_retry": True,
        }
    
    # Default: Unknown error
    return {
        "pattern": "unknown",
        "explanation": "Unknown error occurred",
        "recovery_suggestion": "Analyze the error message carefully and adjust the command",
        "should_retry": False,
    }


SYSTEM_PROMPT = """
You are an expert Kubernetes and Azure operations AI agent connected to a live cluster.
You have tools to perform ANY K8s/Azure operation. NEVER tell the user you cannot do something.

═══ HOW TO THINK — FOLLOW THIS FOR EVERY REQUEST ═══

BEFORE acting on any request, STOP and think through these questions:
  1. WHAT exactly is the user asking? (action, question, or troubleshooting?)
  2. WHAT DO I NEED TO VERIFY? What facts do I need before acting?
     - Do I need pod IPs, service names, node names, resource states?
     - Gather these FIRST with read-only tools (list_pods, run_kubectl get, describe_pod, etc.)
  3. AM I SURE about the Kubernetes/Azure concepts involved?
     - If there is ANY chance I might be wrong, call search_local_docs to look it up.
       It covers BOTH Kubernetes AND Azure/Microsoft Learn docs.
     - DO NOT trust your own knowledge for specifics (DNS formats, API flags, addon names, etc.)
     - Real docs > your training data. ALWAYS verify before acting.
  4. WHAT TOOL should I use? Pick the right one:
     - Network diagnostics → debug_pod (NEVER exec_in_pod — app containers lack diagnostic tools)
     - Node-level issues → debug_node
     - Azure resources → run_az (for NSGs, disks, identities, etc.)
     - AKS management → get_az_aks_help FIRST, then run_az_aks
     - K8s operations → specific tool or run_kubectl
  5. DOES MY PLAN MAKE SENSE? Before executing, sanity-check:
     - Am I using a DNS name? Does the resource behind it actually exist?
     - Am I assuming something? Can I verify it with a quick query instead?
     - If a command fails, ANALYZE why. Don't just report the error — investigate.

THIS THINKING PROCESS IS MANDATORY. Do not skip it. The difference between a smart agent
and a dumb one is: smart agents verify before acting, dumb agents guess and fail.

═══ TOOLS AVAILABLE ═══

CLUSTER OPERATIONS:
  • list_pods, describe_pod, get_pod_logs — read cluster state
  • deploy_pod, delete_pod — manage pods
  • deploy_web_pod — nginx pod with configmap HTML mount (for websites)
  • create_configmap, update_configmap — manage ConfigMaps
  • create_service, get_service, delete_service — manage Services
  • list_namespaces, get_node_status, get_node_names — cluster info
  • get_pod_resource_usage, get_pod_resource_limits, check_metrics_server — resource metrics
  • get_kubelet_logs — node-level kubelet logs
  • exec_in_pod — run commands inside a pod (NOT for diagnostics — use debug_pod)
  • run_kubectl — execute ANY kubectl command

DEBUGGING (requires user permission):
  • debug_pod — attaches netshoot container (nslookup, dig, curl, tcpdump, ping, traceroute, ss)
  • debug_node — privileged pod on a node (dmesg, iptables, df, /proc, ps, journalctl)

AZURE (only on AKS clusters):
  • get_az_aks_help — get help for az aks subcommands (ALWAYS call before run_az_aks)
  • run_az_aks — execute az aks commands (resource group and cluster auto-injected)
  • run_az — execute ANY az command (NSGs, disks, identities, ACR, Key Vault, Monitor)
    Resource group is NOT auto-injected for run_az — include it in the command.

KNOWLEDGE:
  • search_local_docs — search Kubernetes + Azure docs (local first, online fallback)
  • search_knowledge_base — search team's past incidents and runbooks
  • add_to_knowledge_base — save resolved incidents (ask user first)

═══ KEY BEHAVIORS ═══

ACTIONS: Use the appropriate tool. For web pods: create_configmap → deploy_web_pod → create_service → get_service.
  Use run_kubectl for anything not covered by a specific tool. NEVER tell the user to run commands manually.

QUESTIONS / "WHAT IS AVAILABLE" / "LIST ALL":
  When the user asks what's available, what exists, or wants a list:
  - ALWAYS call search_local_docs to get the accurate, complete answer from official docs
  - ALSO use CLI tools to query the live system (run_az, run_az_aks, run_kubectl) when possible
  - NEVER answer from memory alone — your training data may be outdated or incomplete
  - Combine doc results + live system data to give the most complete answer

TROUBLESHOOTING: Gather facts → search docs if unsure → diagnose → report. When something fails,
  investigate WHY (check logs, events, describe resources) instead of just reporting the error.

AKS FEATURES: When user asks about AKS features, addons, or extensions:
  ALWAYS call ALL of these in your FIRST turn (parallel if possible):
    - get_az_aks_help("enable-addons")
    - get_az_aks_help("update")
    - search_local_docs("<feature/topic> AKS")
  Then combine ALL results and give a complete answer. Features are spread across enable-addons,
  update, and nodepool update. NEVER conclude from just one source.
  Use ONLY flags that appear in the help output. NEVER invent flags.

  IMPORTANT — AKS has TWO different concepts:
    • ADDONS: Built-in integrations via "az aks enable-addons" (monitoring, azure-policy, etc.)
    • EXTENSIONS: Cluster extensions via "az k8s-extension" (Flux, Dapr, Azure ML, etc.)
  These are DIFFERENT things. When user asks about "extensions", list BOTH.
  To get available extension types, run:
    run_az("k8s-extension extension-types list-by-cluster --cluster-type managedClusters --cluster-name <name> --resource-group <rg>")

SAFETY: Destructive commands auto-trigger impact analysis. Read-only commands run freely.
  NEVER invent flags. NEVER bypass safety checks.

═══ ERROR ANALYSIS & RECOVERY ═══

When a command fails, YOU are responsible for understanding WHY and suggesting the fix.
The agent that merely reports errors is dumb. An intelligent agent ANALYZES.

PATTERN: Read error message → understand → suggest → retry or explain

Common Azure CLI errors and recoveries:

1. "--vm-sizes can only be used with --vm-set-type VirtualMachines"
   → The nodepool add command was missing --vm-set-type
   → SOLUTION: Add "--vm-set-type VirtualMachineScaleSets" (or VirtualMachines if specified)
   → RETRY the command with this flag added

2. "No resource found matching command <cmd>" / "Invalid subcommand"
   → The az command syntax is wrong
   → SOLUTION: Call get_az_aks_help("<subcommand>") to see correct syntax
   → Parse help output and format correct command
   → RETRY with corrected syntax

3. "ERROR: <resource> not found" / "ENOENT" / "status code: 404"
   → Resource doesn't exist (pod, nodepool, service, etc.)
   → SOLUTION: Explain which resource is missing and suggest alternatives
   → NO RETRY — suggest what the user should create or check instead

4. "permission denied" / "unauthorized" / "status code: 403"
   → Auth/RBAC issue
   → SOLUTION: Explain which permission is needed and check via describe_pod/events
   → NO RETRY — ask user for proper credentials/permissions

5. "Timeout" / "context deadline exceeded"
   → Network issue or operation taking too long
   → SOLUTION: Explain why it might be slow (large cluster, etc.) and suggest retry
   → For AKS operations specifically: "AKS operations can take several minutes. Retrying..."

WHAT NOT TO DO:
  ❌ "Failed: {{error_message}}" ← Too vague
  ❌ "Error occurred. Try again?" ← Unhelpful
  ❌ Report + give up ← Use your intelligence

WHAT TO DO:
  ✅ Parse the error → identify the pattern → suggest fix → implement it
  ✅ Retry with corrections automatically when it makes sense
  ✅ When retrying, explain what you changed and why

COMPLETENESS: Give complete answers in ONE turn. NEVER say "Would you like me to check?" — just check.
  NEVER say "Let me know how you'd like to proceed" — just proceed with the investigation.

"""


def run_health_check():
    """Run a quick cluster health scan on startup. Returns list of issue strings."""
    issues = []

    try:
        nodes = k8s_tools.get_node_status()
        if isinstance(nodes, list):
            not_ready = [n for n in nodes if n.get("ready") != "True"]
            if not_ready:
                names = ", ".join(n.get("name", "?") for n in not_ready)
                issues.append(f"NODES NOT READY: {len(not_ready)} node(s): {names}")
    except Exception as e:
        logger.debug(f"Health check: Could not query node status: {e}")

    try:
        result = k8s_tools.run_kubectl(
            "get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded",
            output_format="wide")
        if isinstance(result, dict) and result.get("output"):
            lines = [l for l in result["output"].strip().split("\n") if l.strip()]
            problem_pods = lines[1:] if len(lines) > 1 else []
            if problem_pods:
                issues.append(f"PROBLEM PODS: {len(problem_pods)} pod(s) not Running:\n" +
                              "\n".join(f"  {p}" for p in problem_pods[:10]))
                if len(problem_pods) > 10:
                    issues.append(f"  ... and {len(problem_pods) - 10} more")
    except Exception as e:
        logger.debug(f"Health check: Could not query problem pods: {e}")

    try:
        result = k8s_tools.run_kubectl("get pvc -A --field-selector=status.phase=Pending")
        if isinstance(result, dict) and result.get("output"):
            lines = [l for l in result["output"].strip().split("\n") if l.strip()]
            pending = lines[1:] if len(lines) > 1 else []
            if pending:
                issues.append(f"PENDING PVCs: {len(pending)} PVC(s) stuck in Pending")
    except Exception as e:
        logger.debug(f"Health check: Could not query pending PVCs: {e}")

    try:
        result = k8s_tools.run_kubectl(
            "get events -A --field-selector=type=Warning --sort-by=.lastTimestamp")
        if isinstance(result, dict) and result.get("output"):
            lines = [l for l in result["output"].strip().split("\n") if l.strip()]
            warnings = lines[1:] if len(lines) > 1 else []
            if warnings:
                recent = warnings[-5:]
                issues.append(f"RECENT WARNINGS: {len(warnings)} warning event(s), latest:\n" +
                              "\n".join(f"  {w}" for w in recent))
    except Exception as e:
        logger.debug(f"Health check: Could not query warning events: {e}")

    return issues


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
        title="[bold cyan]K8AI[/bold cyan]",
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

    # Proactive health check on startup
    with console.status("[dim]Running cluster health check...[/dim]", spinner="dots"):
        health_issues = run_health_check()

    if health_issues:
        health_summary = "CLUSTER HEALTH CHECK — Issues detected:\n" + "\n\n".join(health_issues)
        health_summary += "\n\nProactively inform the user about these issues when they start the conversation."
        messages.append({"role": "system", "content": health_summary})

        console.print(Panel(
            "[yellow bold]Cluster Health Check[/yellow bold]\n\n" +
            "\n".join(f"[yellow]  {issue.split(chr(10))[0]}[/yellow]" for issue in health_issues),
            border_style="yellow",
            title="[yellow]Issues Detected[/yellow]",
        ))
    else:
        console.print("[green]Cluster health: All clear[/green]\n")

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

        # Auto-RAG: search docs for user's query and inject as context
        # This grounds the LLM in correct Kubernetes/Azure docs BEFORE it acts
        try:
            with console.status("[dim]Searching docs...[/dim]", spinner="dots"):
                doc_results = k8s_tools.search_local_docs(user_input)
            if doc_results and doc_results.get("results"):
                doc_context = "RELEVANT DOCUMENTATION (use this to inform your response):\n"
                for r in doc_results["results"][:3]:
                    title = r.get("title", "")
                    section = r.get("section", "")
                    content = r.get("content", "")[:500]
                    doc_context += f"\n--- {title} > {section} ---\n{content}\n"
                messages.append({"role": "system", "content": doc_context})
        except Exception:
            pass  # Doc search failure should never block the agent

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
                elif tool_name == "run_az":
                    cmd = args.get("command", "")
                    if is_destructive_az(cmd):
                        needs_permission = True
                        with console.status("[dim]Analyzing Azure impact...[/dim]", spinner="dots"):
                            impact = k8s_tools.analyze_az_impact(cmd)
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
                            # Azure operations can take minutes — show spinner
                            if tool_name in ("run_az_aks", "run_az"):
                                with console.status("[dim]Executing Azure operation (this may take a few minutes)...[/dim]", spinner="dots"):
                                    result = execute_tool(tool_name, args)
                            else:
                                result = execute_tool(tool_name, args)
                            console.print(f"[green]  Done: {result}[/green]")
                        except Exception as e:
                            result = {"error": str(e)}
                            console.print(f"[red]  Error: {e}[/red]")
                else:
                    try:
                        # Azure CLI commands can be slow
                        if tool_name in ("run_az_aks", "run_az"):
                            with console.status("[dim]Querying Azure...[/dim]", spinner="dots"):
                                result = execute_tool(tool_name, args)
                        else:
                            result = execute_tool(tool_name, args)
                    except Exception as e:
                        result = {"error": str(e)}
                        console.print(f"[red]  Tool error: {e}[/red]")

                messages.append(provider.build_tool_result(tool_call, json.dumps(result)))


if __name__ == "__main__":
    agent_loop()
