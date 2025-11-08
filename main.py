"""Main CLI entry point for Email Classification Agent."""

import argparse
import asyncio
import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from config.settings import get_config, reload_config
from agent.orchestrator import EmailClassificationOrchestrator
from ui.app import run_tui


console = Console()


def print_banner():
    """Print application banner."""
    banner = """
[bold cyan]Email Classification Agent[/bold cyan]
[dim]AI-powered email organization with OpenAI[/dim]
    """
    console.print(Panel(banner, border_style="cyan"))


async def run_classify(args):
    """Run classification in non-interactive mode."""
    print_banner()

    try:
        # Load configuration
        console.print("\n[bold]Loading configuration...[/bold]")
        config = get_config(args.env_file) if args.env_file else get_config()

        # Validate configuration
        config.validate()
        console.print("[green]✓[/green] Configuration validated")

        # Show configuration summary
        console.print(f"\n[bold]Configuration:[/bold]")
        console.print(f"  Provider: {config.settings.email_provider}")
        console.print(f"  Model: {config.settings.openai_model}")
        console.print(f"  Max Emails: {args.limit or config.settings.max_emails_per_run}")
        console.print(f"  Categories: {len(config.classification_config.categories)}")

        # Initialize and run orchestrator
        console.print(f"\n[bold]Initializing agent...[/bold]")

        async with EmailClassificationOrchestrator(config, log_callback=console.print) as orchestrator:
            console.print("[green]✓[/green] Agent initialized\n")

            # Run classification
            stats = await orchestrator.classify_emails(
                limit=args.limit,
                provider=args.provider
            )

            # Display final statistics
            display_stats(stats)

    except KeyboardInterrupt:
        console.print("\n[yellow]Classification interrupted by user[/yellow]")
        sys.exit(0)
    except Exception as e:
        console.print(f"\n[bold red]Error:[/bold red] {e}")
        if args.debug:
            import traceback
            console.print_exception()
        sys.exit(1)


def display_stats(stats):
    """Display classification statistics in a table."""
    console.print("\n[bold]Classification Results[/bold]\n")

    # Summary table
    summary = Table(title="Summary", show_header=True, header_style="bold cyan")
    summary.add_column("Metric", style="cyan")
    summary.add_column("Value", justify="right")

    summary.add_row("Total Processed", str(stats.total_emails))
    summary.add_row("Successful", f"[green]{stats.successful}[/green]")
    summary.add_row("Failed", f"[red]{stats.failed}[/red]")
    summary.add_row("Average Confidence", f"{stats.average_confidence:.1%}")
    summary.add_row("Processing Time", f"{stats.processing_time_seconds:.2f}s")

    console.print(summary)

    # Categories breakdown
    if stats.categories_breakdown:
        console.print("\n[bold]Categories Breakdown[/bold]\n")
        categories_table = Table(show_header=True, header_style="bold cyan")
        categories_table.add_column("Category", style="cyan")
        categories_table.add_column("Count", justify="right")
        categories_table.add_column("Percentage", justify="right")

        for category, count in sorted(stats.categories_breakdown.items(), key=lambda x: x[1], reverse=True):
            percentage = (count / stats.successful * 100) if stats.successful > 0 else 0
            categories_table.add_row(category, str(count), f"{percentage:.1f}%")

        console.print(categories_table)


def run_tui_mode(args):
    """Run in TUI mode."""
    if args.env_file:
        reload_config(args.env_file)
    run_tui()


def run_config_check(args):
    """Check and display configuration."""
    print_banner()

    try:
        console.print("\n[bold]Checking configuration...[/bold]\n")

        # Load configuration
        config = get_config(args.env_file) if args.env_file else get_config()

        # Display settings
        console.print("[bold cyan]Settings:[/bold cyan]")
        console.print(f"  Email Provider: {config.settings.email_provider}")
        console.print(f"  OpenAI Model: {config.settings.openai_model}")
        console.print(f"  Temperature: {config.settings.openai_temperature}")
        console.print(f"  Max Tokens: {config.settings.openai_max_tokens}")
        console.print(f"  Batch Size: {config.settings.batch_size}")
        console.print(f"  Concurrency: {config.settings.classification_concurrency}")
        console.print(f"  Log Level: {config.settings.log_level}")

        # Display categories
        console.print(f"\n[bold cyan]Categories ({len(config.classification_config.categories)}):[/bold cyan]")
        for cat in config.classification_config.categories:
            console.print(f"  • {cat.name}: {cat.description}")

        # Validate
        console.print("\n[bold]Validating configuration...[/bold]")
        config.validate()
        console.print("[green]✓ Configuration is valid![/green]")

    except Exception as e:
        console.print(f"\n[bold red]Configuration Error:[/bold red] {e}")
        if args.debug:
            console.print_exception()
        sys.exit(1)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Email Classification Agent - AI-powered email organization",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run with TUI (interactive mode)
  email-classifier tui

  # Classify emails from Gmail
  email-classifier classify --provider gmail --limit 50

  # Classify from both providers
  email-classifier classify --provider both --limit 100

  # Check configuration
  email-classifier config-check

  # Use custom .env file
  email-classifier classify --env-file /path/to/.env --limit 25
        """
    )

    parser.add_argument(
        "--version",
        action="version",
        version="Email Classification Agent v0.1.0"
    )

    parser.add_argument(
        "--env-file",
        type=str,
        help="Path to .env file (default: .env in current directory)"
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode with full tracebacks"
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # TUI command
    tui_parser = subparsers.add_parser(
        "tui",
        help="Run with Terminal UI (interactive mode)"
    )

    # Classify command
    classify_parser = subparsers.add_parser(
        "classify",
        help="Run classification (non-interactive mode)"
    )
    classify_parser.add_argument(
        "--provider",
        type=str,
        choices=["gmail", "outlook", "both"],
        help="Email provider to use (overrides .env setting)"
    )
    classify_parser.add_argument(
        "--limit",
        type=int,
        help="Maximum number of emails to classify"
    )

    # Config check command
    config_parser = subparsers.add_parser(
        "config-check",
        help="Check and display configuration"
    )

    args = parser.parse_args()

    # Default to TUI if no command specified
    if not args.command:
        args.command = "tui"

    # Route to appropriate handler
    if args.command == "tui":
        run_tui_mode(args)
    elif args.command == "classify":
        asyncio.run(run_classify(args))
    elif args.command == "config-check":
        run_config_check(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
