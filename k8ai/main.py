"""
Entry point for the k8ai CLI tool.
Run with: k8ai
Or: python -m k8ai
"""

import os
import sys
from pathlib import Path
from rich.console import Console
from rich.panel import Panel

console = Console()


def check_env():
    """Check required environment variables are set before starting."""
    required = [
        "AZURE_OPENAI_ENDPOINT",
        "AZURE_OPENAI_API_KEY",
        "AZURE_OPENAI_DEPLOYMENT",
        "AZURE_OPENAI_API_VERSION",
    ]
    missing = [k for k in required if not os.getenv(k)]
    if missing:
        console.print(Panel(
            f"[red]Missing environment variables:[/red]\n" +
            "\n".join(f"  • {k}" for k in missing) +
            "\n\n[yellow]Create a .env file in your current directory:[/yellow]\n"
            "  AZURE_OPENAI_ENDPOINT=https://<resource>.openai.azure.com/\n"
            "  AZURE_OPENAI_API_KEY=<your-key>\n"
            "  AZURE_OPENAI_DEPLOYMENT=gpt-4o\n"
            "  AZURE_OPENAI_API_VERSION=2024-10-21\n\n"
            "[dim]Get your credentials: https://github.com/subhamsaha/k8AI#setup[/dim]",
            title="[red]Configuration Missing[/red]",
            border_style="red"
        ))
        sys.exit(1)


def check_kubeconfig():
    """Check kubectl is configured."""
    kubeconfig = Path.home() / ".kube" / "config"
    if not kubeconfig.exists():
        console.print(Panel(
            "[red]kubectl is not configured.[/red]\n\n"
            "Connect to your AKS cluster first:\n"
            "  [bold]az aks get-credentials --resource-group <rg> --name <cluster>[/bold]",
            title="[red]Cluster Not Connected[/red]",
            border_style="red"
        ))
        sys.exit(1)


def main():
    """Main CLI entry point."""
    # Load .env from current working directory if it exists
    env_file = Path.cwd() / ".env"
    if env_file.exists():
        from dotenv import load_dotenv
        load_dotenv(env_file)

    check_env()
    check_kubeconfig()

    from k8ai.agent import agent_loop
    agent_loop()


if __name__ == "__main__":
    main()
