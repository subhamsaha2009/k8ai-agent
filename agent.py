import json
import os
from openai import AzureOpenAI
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box
import k8s_tools
from tools_schema import TOOLS

load_dotenv()

console = Console()

azure_client = AzureOpenAI(
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
)

DESTRUCTIVE_TOOLS = {"deploy_pod", "delete_pod", "deploy_web_pod", "create_service", "delete_service", "update_configmap"}

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
"""


def ask_permission(tool_name, args):
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
    table.add_row("Cluster", "k8ai-cluster (AKS)")
    table.add_row("AI Model", "GPT-4o (Azure AI Foundry)")
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
    console.print("[dim]  • create a todo app and expose it publicly[/dim]")
    console.print("[dim]  • change the web content to show a calculator[/dim]")
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
                response = azure_client.chat.completions.create(
                    model=os.getenv("AZURE_OPENAI_DEPLOYMENT"),
                    messages=messages,
                    tools=TOOLS,
                    tool_choice="auto",
                )

            msg = response.choices[0].message
            messages.append(msg)

            # No tool calls — model has a final answer
            if not msg.tool_calls:
                console.print(f"\n[bold cyan]Agent:[/bold cyan] {msg.content}\n")
                break

            # Process each tool call
            for tool_call in msg.tool_calls:
                tool_name = tool_call.function.name
                args = json.loads(tool_call.function.arguments)

                console.print(f"[dim]  → {tool_name}({json.dumps(args)})[/dim]")

                if tool_name in DESTRUCTIVE_TOOLS:
                    if not ask_permission(tool_name, args):
                        result = {"status": "denied", "message": "User denied this action."}
                        console.print("[yellow]  Action denied.[/yellow]")
                    else:
                        try:
                            result = execute_tool(tool_name, args)
                            console.print(f"[green]  Done: {result}[/green]")
                        except Exception as e:
                            result = {"error": str(e)}
                            console.print(f"[red]  Error: {e}[/red]")
                else:
                    try:
                        result = execute_tool(tool_name, args)
                    except Exception as e:
                        result = {"error": str(e)}
                        console.print(f"[red]  Tool error: {e}[/red]")

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(result),
                })


if __name__ == "__main__":
    agent_loop()
