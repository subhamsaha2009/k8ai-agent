"""
k8ai CLI — entry point for 'k8ai' and 'k8ai init' commands.
"""

import sys
import os
import json
import subprocess
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm

from k8ai.config import (
    save_config, load_config, apply_config_to_env,
    show_config, is_configured,
)

console = Console()

MCP_SAFE_TOOLS = [
    "list_pods", "describe_pod", "get_pod_logs",
    "list_namespaces", "get_node_status", "get_node_names",
    "get_service", "get_pod_resource_usage", "get_pod_resource_limits",
    "check_metrics_server", "exec_in_pod", "get_kubelet_logs",
    "run_kubectl", "create_configmap",
    "get_az_aks_help", "run_az_aks", "run_az", "search_local_docs",
]


def run_init():
    """Interactive setup wizard — asks provider, API key, model, verifies cluster."""
    console.print(Panel(
        "[bold cyan]K8AI Setup Wizard[/bold cyan]\n\n"
        "This will configure your AI provider and verify your Kubernetes cluster.\n"
        "API keys are stored securely in your OS keychain.",
        border_style="cyan",
    ))

    # ── Step 1: AI Provider ──
    console.print("\n[bold]Step 1/3: AI Provider[/bold]")
    console.print("  [1] Azure OpenAI")
    console.print("  [2] OpenAI (direct)")
    console.print("  [3] Anthropic Claude")

    choice = Prompt.ask("  Choose provider", choices=["1", "2", "3"])
    provider_map = {"1": "azure", "2": "openai", "3": "claude"}
    provider = provider_map[choice]

    # ── Step 2: AI Configuration ──
    console.print(f"\n[bold]Step 2/3: {provider.title()} Configuration[/bold]")

    api_key = Prompt.ask("  API Key", password=True)

    endpoint = None
    api_version = None
    if provider == "azure":
        endpoint = Prompt.ask("  Endpoint (e.g. https://my-resource.openai.azure.com/)")
        api_version = Prompt.ask("  API Version", default="2024-10-21")

    default_models = {"azure": "gpt-4o", "openai": "gpt-4o", "claude": "claude-sonnet-4-6"}
    model = Prompt.ask("  Model/Deployment name", default=default_models[provider])

    # ── Step 3: Kubernetes Cluster ──
    console.print("\n[bold]Step 3/3: Kubernetes Cluster[/bold]")

    try:
        result = subprocess.run(
            ["kubectl", "cluster-info"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            first_line = result.stdout.strip().split("\n")[0] if result.stdout else ""
            console.print(f"  [green]Cluster detected:[/green] {first_line}")

            # Check if AKS
            server_check = subprocess.run(
                ["kubectl", "config", "view", "--minify", "-o",
                 "jsonpath={.clusters[0].cluster.server}"],
                capture_output=True, text=True, timeout=10,
            )
            if server_check.returncode == 0 and ".azmk8s.io" in server_check.stdout:
                console.print("  [green]AKS cluster detected[/green] — az aks commands will be available")
            else:
                console.print("  [dim]Non-AKS cluster — basic Kubernetes tools available[/dim]")
        else:
            console.print("  [yellow]Warning:[/yellow] Could not connect to cluster.")
            console.print(f"  [dim]{result.stderr.strip()}[/dim]")
            if not Confirm.ask("  Continue without cluster verification?"):
                console.print("[dim]Setup cancelled.[/dim]")
                return
    except FileNotFoundError:
        console.print("  [yellow]Warning:[/yellow] kubectl not found in PATH.")
        if not Confirm.ask("  Continue without cluster verification?"):
            console.print("[dim]Setup cancelled.[/dim]")
            return
    except subprocess.TimeoutExpired:
        console.print("  [yellow]Warning:[/yellow] Cluster connection timed out.")
        if not Confirm.ask("  Continue without cluster verification?"):
            console.print("[dim]Setup cancelled.[/dim]")
            return

    # ── Save ──
    save_config(
        provider=provider,
        model=model,
        endpoint=endpoint,
        api_version=api_version,
        api_key=api_key,
    )

    console.print(Panel(
        "[green bold]Setup complete![/green bold]\n\n"
        f"Provider:  {provider}\n"
        f"Model:     {model}\n"
        f"API Key:   stored in OS keychain\n\n"
        "Run [bold]k8ai[/bold] to start the AI agent\n"
        "Run [bold]k8ai-mcp[/bold] to start the MCP server for VS Code",
        title="[green]Done[/green]",
        border_style="green",
    ))


def _get_vscode_settings_path():
    """Get the VS Code user settings.json path based on OS."""
    if sys.platform == "win32":
        return os.path.join(os.environ.get("APPDATA", ""), "Code", "User", "settings.json")
    elif sys.platform == "darwin":
        return os.path.join(os.path.expanduser("~"), "Library", "Application Support", "Code", "User", "settings.json")
    else:
        return os.path.join(os.path.expanduser("~"), ".config", "Code", "User", "settings.json")


def run_mcp_install():
    """Auto-configure k8ai MCP server in VS Code settings.json."""
    settings_path = _get_vscode_settings_path()

    if not os.path.exists(settings_path):
        console.print(f"[yellow]VS Code settings not found at:[/yellow] {settings_path}")
        console.print("Make sure VS Code is installed.")
        return

    # Read existing settings
    with open(settings_path, "r") as f:
        content = f.read().strip()

    # Parse JSON (handle empty file)
    try:
        settings = json.loads(content) if content else {}
    except json.JSONDecodeError:
        console.print("[red]Could not parse VS Code settings.json. Please fix any syntax errors first.[/red]")
        return

    # Check if already configured
    mcp_servers = settings.get("github.copilot.chat.mcpServers", {})
    if "k8ai" in mcp_servers:
        console.print("[green]k8ai MCP server is already configured in VS Code.[/green]")
        if not Confirm.ask("  Overwrite existing config?", default=False):
            return

    # Add k8ai MCP config
    mcp_servers["k8ai"] = {
        "command": "k8ai-mcp",
        "alwaysAllow": MCP_SAFE_TOOLS,
    }
    settings["github.copilot.chat.mcpServers"] = mcp_servers

    # Write back
    with open(settings_path, "w") as f:
        json.dump(settings, f, indent=4)
        f.write("\n")

    console.print(Panel(
        "[green bold]MCP server configured in VS Code![/green bold]\n\n"
        f"Settings file: {settings_path}\n\n"
        "Next steps:\n"
        "  1. Reload VS Code (Ctrl+Shift+P > Reload Window)\n"
        "  2. Open Copilot Chat (Ctrl+Shift+I)\n"
        "  3. Enable k8ai in the tools menu\n"
        "  4. Ask: \"List all pods in my cluster\"",
        title="[green]Done[/green]",
        border_style="green",
    ))


def _run_docs_sync():
    """Download and index Azure + K8s docs locally."""
    from k8ai.docs_sync import sync_all

    console.print(Panel(
        "[bold cyan]Docs Sync[/bold cyan]\n\n"
        "Downloading official Azure AKS + Kubernetes documentation.\n"
        "This runs once and stores everything locally for offline search.",
        border_style="cyan",
    ))

    def progress(msg):
        if isinstance(msg, str):
            console.print(f"  {msg}")

    try:
        with console.status("[dim]Syncing docs...[/dim]", spinner="dots"):
            status = sync_all(progress_callback=progress)

        rag_line = ""
        if status.get("rag_enabled"):
            rag_line = f"Embeddings: {status['embeddings']} vectors (RAG enabled)\n"
        else:
            rag_line = "RAG:       disabled (Claude provider — keyword search only)\n"

        console.print(Panel(
            f"[green bold]Docs synced![/green bold]\n\n"
            f"AKS docs:  {status['aks_chunks']} chunks\n"
            f"K8s docs:  {status['k8s_chunks']} chunks\n"
            f"Total:     {status['total_chunks']} chunks\n"
            f"{rag_line}\n"
            "Your agent can now search docs offline.\n"
            "Run [bold]k8ai docs sync[/bold] anytime to update.",
            title="[green]Done[/green]",
            border_style="green",
        ))
    except Exception as e:
        console.print(f"[red]Error syncing docs:[/red] {e}")


def _run_docs_status():
    """Show docs sync stats."""
    from k8ai.docs_sync import get_sync_status
    from k8ai.kb import get_stats

    sync = get_sync_status()
    if not sync:
        console.print("[yellow]Docs not synced yet.[/yellow] Run [bold]k8ai docs sync[/bold]")
        return

    stats = get_stats()
    console.print(f"Last sync:    {sync.get('last_sync', 'unknown')}")
    console.print(f"AKS chunks:   {sync.get('aks_chunks', 0)}")
    console.print(f"K8s chunks:   {sync.get('k8s_chunks', 0)}")
    console.print(f"Total chunks: {sync.get('total_chunks', 0)}")
    console.print(f"DB size:      {stats.get('db_size_mb', '?')} MB")
    console.print(f"DB path:      {stats.get('db_path', '?')}")


def _run_kb_status():
    """Show knowledge base stats."""
    from k8ai.kb import get_stats, is_azure_search_configured

    stats = get_stats()
    if stats["total"] == 0:
        console.print("[yellow]Knowledge base is empty.[/yellow]")
        console.print("  Run [bold]k8ai docs sync[/bold] to download docs")
        console.print("  Run [bold]k8ai kb import[/bold] to add your own data")
        return

    console.print(f"Docs chunks:  {stats.get('docs', 0)}")
    console.print(f"Incidents:    {stats.get('incident', 0)}")
    console.print(f"Runbooks:     {stats.get('runbook', 0)}")
    console.print(f"Total:        {stats['total']}")
    console.print(f"Embeddings:   {stats.get('embeddings', 0)}")
    console.print(f"RAG:          {'enabled' if stats.get('rag_enabled') else 'disabled'}")
    console.print(f"DB size:      {stats.get('db_size_mb', '?')} MB")
    console.print(f"DB path:      {stats.get('db_path', '?')}")
    console.print(f"Azure Search: {'connected' if is_azure_search_configured() else 'not configured'}")


def _run_kb_import(args):
    """Import data from a JSON file or markdown folder."""
    from k8ai.kb import add_chunk
    import json as _json
    import glob

    if not args or args[0] not in ("--file", "--folder"):
        console.print("Usage:")
        console.print("  k8ai kb import --file runbooks.json")
        console.print("  k8ai kb import --folder ./postmortems/")
        return

    if args[0] == "--file":
        if len(args) < 2:
            console.print("[red]Missing file path.[/red] Usage: k8ai kb import --file data.json")
            return
        filepath = args[1]
        if not os.path.exists(filepath):
            console.print(f"[red]File not found:[/red] {filepath}")
            return

        with open(filepath, "r", encoding="utf-8") as f:
            data = _json.load(f)

        if not isinstance(data, list):
            data = [data]

        count = 0
        for item in data:
            add_chunk(
                source="import",
                category=item.get("category", "runbook"),
                title=item.get("title", ""),
                section=item.get("section", ""),
                content=item.get("description", item.get("content", "")),
                url=item.get("url", ""),
                tags=item.get("tags", ""),
            )
            count += 1

        console.print(f"[green]Imported {count} entries from {filepath}[/green]")

    elif args[0] == "--folder":
        if len(args) < 2:
            console.print("[red]Missing folder path.[/red] Usage: k8ai kb import --folder ./docs/")
            return
        folder = args[1]
        if not os.path.isdir(folder):
            console.print(f"[red]Folder not found:[/red] {folder}")
            return

        md_files = glob.glob(os.path.join(folder, "**/*.md"), recursive=True)
        if not md_files:
            console.print(f"[yellow]No .md files found in {folder}[/yellow]")
            return

        count = 0
        for md_file in md_files:
            with open(md_file, "r", encoding="utf-8") as f:
                content = f.read()
            title = os.path.basename(md_file).replace(".md", "").replace("-", " ").replace("_", " ").title()
            add_chunk(
                source=md_file,
                category="runbook",
                title=title,
                section="",
                content=content,
                tags=title.lower(),
            )
            count += 1

        console.print(f"[green]Imported {count} markdown files from {folder}[/green]")


def _run_kb_setup_azure():
    """Configure Azure AI Search backend."""
    from k8ai.kb import setup_azure_search

    console.print(Panel(
        "[bold cyan]Azure AI Search Setup[/bold cyan]\n\n"
        "Connect your team's shared knowledge base.\n"
        "All searches will check both local + Azure AI Search.",
        border_style="cyan",
    ))

    endpoint = Prompt.ask("  Search endpoint (e.g. https://my-search.search.windows.net)")
    api_key = Prompt.ask("  API key", password=True)
    index_name = Prompt.ask("  Index name", default="k8ai-kb")

    setup_azure_search(endpoint, api_key, index_name)

    console.print(Panel(
        "[green bold]Azure AI Search connected![/green bold]\n\n"
        f"Endpoint:   {endpoint}\n"
        f"Index:      {index_name}\n\n"
        "The agent will now search both local KB and Azure AI Search.",
        title="[green]Done[/green]",
        border_style="green",
    ))


def main():
    """Entry point for 'k8ai' command."""
    args = sys.argv[1:]

    # k8ai init
    if args and args[0] == "init":
        run_init()
        return

    # k8ai mcp install
    if args and args[0] == "mcp":
        if len(args) >= 2 and args[1] == "install":
            run_mcp_install()
        else:
            console.print("Usage: k8ai mcp install")
        return

    # k8ai docs sync / status
    if args and args[0] == "docs":
        # Load config so embedding model is available during sync
        if is_configured():
            _cfg = load_config()
            if _cfg:
                apply_config_to_env(_cfg)
        if len(args) >= 2 and args[1] == "sync":
            _run_docs_sync()
        elif len(args) >= 2 and args[1] == "status":
            _run_docs_status()
        else:
            console.print("Usage: k8ai docs sync | k8ai docs status")
        return

    # k8ai kb import / setup / status
    if args and args[0] == "kb":
        if len(args) >= 2 and args[1] == "status":
            _run_kb_status()
        elif len(args) >= 2 and args[1] == "import":
            _run_kb_import(args[2:])
        elif len(args) >= 2 and args[1] == "setup":
            if len(args) >= 3 and args[2] == "--azure":
                _run_kb_setup_azure()
            else:
                console.print("Usage: k8ai kb setup --azure")
        else:
            console.print("Usage: k8ai kb import --file x.json | k8ai kb import --folder ./docs/ | k8ai kb setup --azure | k8ai kb status")
        return

    # k8ai config show
    if args and args[0] == "config":
        if len(args) >= 2 and args[1] == "show":
            console.print(show_config())
        else:
            console.print("Usage: k8ai config show")
        return

    # k8ai --version
    if args and args[0] in ("--version", "-v"):
        from k8ai import __version__
        console.print(f"k8ai {__version__}")
        return

    # k8ai --help
    if args and args[0] in ("--help", "-h"):
        console.print(Panel(
            "[bold]k8ai[/bold] — AI-powered Kubernetes cluster management\n\n"
            "[bold]Commands:[/bold]\n"
            "  k8ai                    Start the interactive AI agent\n"
            "  k8ai init               Set up AI provider and cluster\n"
            "  k8ai docs sync          Download Azure + K8s docs locally\n"
            "  k8ai docs status        Show docs sync stats\n"
            "  k8ai kb import --file   Import knowledge from JSON file\n"
            "  k8ai kb import --folder Import knowledge from markdown folder\n"
            "  k8ai kb setup --azure   Connect Azure AI Search (optional)\n"
            "  k8ai kb status          Show knowledge base stats\n"
            "  k8ai mcp install        Auto-configure MCP server in VS Code\n"
            "  k8ai config show        Show current configuration\n"
            "  k8ai-mcp                Start MCP server for VS Code\n\n"
            "[bold]Options:[/bold]\n"
            "  --version, -v           Show version\n"
            "  --help, -h              Show this help",
            title="[cyan]K8AI[/cyan]",
            border_style="cyan",
        ))
        return

    # Default: start the agent
    if not is_configured():
        console.print("[yellow]K8AI is not configured yet.[/yellow]")
        console.print("Run [bold]k8ai init[/bold] to set up your AI provider and cluster.")
        return

    # Load config and set env vars
    config = load_config()
    apply_config_to_env(config)

    # Now import and run the agent (after env vars are set)
    from k8ai.agent import agent_loop
    agent_loop()


if __name__ == "__main__":
    main()
