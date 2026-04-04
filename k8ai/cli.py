"""
k8ai CLI — entry point for 'k8ai' and 'k8ai init' commands.
"""

import sys
import subprocess
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm

from k8ai.config import (
    save_config, load_config, apply_config_to_env,
    show_config, is_configured,
)

console = Console()


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


def main():
    """Entry point for 'k8ai' command."""
    args = sys.argv[1:]

    # k8ai init
    if args and args[0] == "init":
        run_init()
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
            "  k8ai               Start the interactive AI agent\n"
            "  k8ai init          Set up AI provider and cluster\n"
            "  k8ai config show   Show current configuration\n"
            "  k8ai-mcp           Start MCP server for VS Code\n\n"
            "[bold]Options:[/bold]\n"
            "  --version, -v      Show version\n"
            "  --help, -h         Show this help",
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
