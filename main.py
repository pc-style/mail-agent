"""Main CLI entry point for Email Classification Agent."""

import argparse
import asyncio
import sys
from pathlib import Path
import shutil

import questionary
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from config.settings import get_config, reload_config, get_config_dir
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


async def run_setup(args):
    """Interactive setup wizard."""
    print_banner()
    console.print("\n[bold cyan]Welcome to Email Classification Agent Setup![/bold cyan]\n")
    console.print("This will guide you through configuring the agent.\n")

    config_dir = get_config_dir()
    env_file = config_dir / ".env"

    # check if already configured
    if env_file.exists():
        overwrite = await questionary.confirm(
            f"Configuration file already exists at {env_file}.\n"
            "Do you want to overwrite it?",
            default=False
        ).ask_async()
        if not overwrite:
            console.print("\n[yellow]Setup cancelled.[/yellow]")
            return

    # collect configuration
    config_lines = []

    # OpenAI API Key
    console.print("\n[bold]Step 1: OpenAI Configuration[/bold]")
    openai_key = await questionary.password(
        "Enter your OpenAI API key (sk-...):",
        validate=lambda x: x.startswith("sk-") if x else False
    ).ask_async()
    if not openai_key:
        console.print("\n[red]Setup cancelled - OpenAI API key is required[/red]")
        return
    
    config_lines.append(f"OPENAI_API_KEY={openai_key}")

    # OpenAI Model
    model = await questionary.select(
        "Select OpenAI model:",
        choices=[
            questionary.Choice("gpt-4o-mini (recommended - fast & cheap)", "gpt-4o-mini"),
            questionary.Choice("gpt-4o (more powerful, expensive)", "gpt-4o"),
            questionary.Choice("gpt-5-nano (advanced reasoning)", "gpt-5-nano"),
        ],
        default="gpt-4o-mini"
    ).ask_async()
    config_lines.append(f"OPENAI_MODEL={model}")

    # Email Provider
    console.print("\n[bold]Step 2: Email Provider[/bold]")
    provider = await questionary.select(
        "Select email provider:",
        choices=[
            questionary.Choice("Gmail", "gmail"),
            questionary.Choice("Outlook", "outlook"),
            questionary.Choice("Both", "both"),
        ],
        default="gmail"
    ).ask_async()
    config_lines.append(f"EMAIL_PROVIDER={provider}")

    # Gmail Setup
    if provider in ("gmail", "both"):
        console.print("\n[bold]Step 3: Gmail Configuration[/bold]")
        console.print("To use Gmail, you need OAuth credentials from Google Cloud Console.")
        console.print("1. Go to https://console.cloud.google.com")
        console.print("2. Create a project and enable Gmail API")
        console.print("3. Create OAuth 2.0 Desktop App credentials")
        console.print("4. Download the JSON file\n")

        has_creds = await questionary.confirm(
            "Do you have Gmail OAuth credentials ready?",
            default=False
        ).ask_async()

        if has_creds:
            creds_path = await questionary.path(
                "Enter path to credentials.json file:",
                default=str(config_dir / "credentials.json")
            ).ask_async()
            
            if creds_path and Path(creds_path).exists():
                # copy to config dir
                target_creds = config_dir / "credentials.json"
                shutil.copy(creds_path, target_creds)
                console.print(f"[green]Copied credentials to {target_creds}[/green]")
            else:
                console.print("[yellow]Credentials file not found. You can add it later to ~/.mail-agent/credentials.json[/yellow]")
        else:
            console.print("\n[yellow]You can add credentials later by:")
            console.print(f"  1. Download credentials.json from Google Cloud Console")
            console.print(f"  2. Save it to {config_dir / 'credentials.json'}")
            console.print(f"  3. Run: email-classifier tui[/yellow]\n")

    # Outlook Setup
    if provider in ("outlook", "both"):
        console.print("\n[bold]Step 4: Outlook Configuration[/bold]")
        console.print("To use Outlook, you need Azure App Registration credentials.\n")

        has_outlook = await questionary.confirm(
            "Do you have Outlook/Azure credentials ready?",
            default=False
        ).ask_async()

        if has_outlook:
            outlook_client_id = await questionary.text(
                "Azure Client ID:"
            ).ask_async()
            if outlook_client_id:
                config_lines.append(f"OUTLOOK_CLIENT_ID={outlook_client_id}")

            outlook_secret = await questionary.password(
                "Azure Client Secret:"
            ).ask_async()
            if outlook_secret:
                config_lines.append(f"OUTLOOK_CLIENT_SECRET={outlook_secret}")

            outlook_tenant = await questionary.text(
                "Azure Tenant ID (or 'common' for multi-tenant):",
                default="common"
            ).ask_async()
            if outlook_tenant:
                config_lines.append(f"OUTLOOK_TENANT_ID={outlook_tenant}")

            outlook_user = await questionary.text(
                "Outlook User ID (userPrincipalName, e.g., user@example.com):"
            ).ask_async()
            if outlook_user:
                config_lines.append(f"OUTLOOK_USER_ID={outlook_user}")
        else:
            console.print("\n[yellow]You can add Outlook credentials later to ~/.mail-agent/.env[/yellow]\n")

    # Additional settings
    console.print("\n[bold]Step 5: Advanced Settings (optional)[/bold]")
    advanced = await questionary.confirm(
        "Configure advanced settings?",
        default=False
    ).ask_async()

    if advanced:
        max_emails = await questionary.text(
            "Max emails per run:",
            default="100",
            validate=lambda x: x.isdigit() and int(x) > 0 if x else True
        ).ask_async()
        if max_emails:
            config_lines.append(f"MAX_EMAILS_PER_RUN={max_emails}")

        batch_size = await questionary.text(
            "Batch size:",
            default="10",
            validate=lambda x: x.isdigit() and int(x) > 0 if x else True
        ).ask_async()
        if batch_size:
            config_lines.append(f"BATCH_SIZE={batch_size}")

    # Write config
    console.print(f"\n[bold]Writing configuration to {env_file}...[/bold]")
    config_dir.mkdir(parents=True, exist_ok=True)
    
    with open(env_file, "w") as f:
        f.write("# Email Classification Agent Configuration\n")
        f.write("# Generated by: email-classifier setup\n\n")
        for line in config_lines:
            f.write(line + "\n")

    console.print(f"[green]Configuration saved to {env_file}[/green]")

    # Copy categories.yaml if it doesn't exist
    categories_file = config_dir / "categories.yaml"
    if not categories_file.exists():
        package_categories = Path(__file__).parent / "config" / "categories.yaml"
        if package_categories.exists():
            shutil.copy(package_categories, categories_file)
            console.print(f"[green]Created default categories.yaml[/green]")

    # Summary
    console.print("\n[bold green]Setup Complete![/bold green]\n")
    console.print("Next steps:")
    if provider in ("gmail", "both"):
        console.print("  1. Make sure ~/.mail-agent/credentials.json exists")
        console.print("  2. Run: email-classifier tui")
        console.print("  3. The first run will guide you through Gmail authentication")
    else:
        console.print("  1. Run: email-classifier tui")
    console.print("\n")


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
  # Initial setup (interactive wizard)
  email-classifier setup

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

    # Setup command
    setup_parser = subparsers.add_parser(
        "setup",
        help="Interactive setup wizard"
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
    elif args.command == "setup":
        asyncio.run(run_setup(args))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
