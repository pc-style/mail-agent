"""Simple TUI for email classification agent using Questionary and Rich."""

import asyncio
from typing import Optional

import questionary
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

from config.settings import get_config, ConfigurationManager
from agent.orchestrator import EmailClassificationOrchestrator


console = Console()


def draw_banner():
    """draw nice banner"""
    banner = Text()
    banner.append("Email Classification Agent\n", style="bold cyan")
    banner.append("AI-powered email organization", style="dim")
    console.print(Panel(banner, border_style="cyan", box=box.ROUNDED))


def show_stats(stats):
    """pokazuj statystyki w ładnej tabeli"""
    console.print("\n")
    
    # summary table
    summary = Table(title="Classification Results", box=box.ROUNDED, show_header=True, header_style="bold cyan")
    summary.add_column("Metric", style="cyan")
    summary.add_column("Value", justify="right", style="bold")
    
    summary.add_row("Total Processed", str(stats.total_emails))
    summary.add_row("Successful", f"[green]{stats.successful}[/green]")
    summary.add_row("Failed", f"[red]{stats.failed}[/red]")
    summary.add_row("Avg Confidence", f"{stats.average_confidence:.1%}")
    summary.add_row("Processing Time", f"{stats.processing_time_seconds:.2f}s")
    
    console.print(summary)
    
    # categories breakdown
    if stats.categories_breakdown:
        console.print("\n")
        cat_table = Table(title="Categories Breakdown", box=box.ROUNDED, show_header=True, header_style="bold cyan")
        cat_table.add_column("Category", style="cyan")
        cat_table.add_column("Count", justify="right")
        cat_table.add_column("Percentage", justify="right")
        
        for cat, count in sorted(stats.categories_breakdown.items(), key=lambda x: x[1], reverse=True):
            pct = (count / stats.successful * 100) if stats.successful > 0 else 0
            cat_table.add_row(cat, str(count), f"{pct:.1f}%")
        
        console.print(cat_table)
    
    console.print("\n")


async def run_classification(config: ConfigurationManager, provider: Optional[str] = None, limit: Optional[int] = None):
    """uruchom klasyfikację z live updates"""
    console.print("\n[bold cyan]Starting classification...[/bold cyan]\n")
    
    # create orchestrator with log callback
    def log_callback(msg: str):
        """callback do logowania - pokazuj na żywo"""
        console.print(f"[dim]{msg}[/dim]")
    
    orchestrator = EmailClassificationOrchestrator(config, log_callback=log_callback)
    
    try:
        # run classification (clients initialize automatically)
        stats = await orchestrator.classify_emails(limit=limit, provider=provider)
        
        # show results
        show_stats(stats)
        
        return stats
        
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
        return None
    except Exception as e:
        console.print(f"\n[bold red]Error:[/bold red] {e}")
        return None
    finally:
        await orchestrator.cleanup()


def show_config_info(config: ConfigurationManager):
    """pokazuj info o konfiguracji"""
    console.print("\n[bold cyan]Configuration:[/bold cyan]\n")
    
    info_table = Table(box=box.SIMPLE, show_header=False)
    info_table.add_column("Setting", style="cyan")
    info_table.add_column("Value", style="bold")
    
    info_table.add_row("Email Provider", config.settings.email_provider)
    info_table.add_row("OpenAI Model", config.settings.openai_model)
    info_table.add_row("Temperature", str(config.settings.openai_temperature))
    info_table.add_row("Max Tokens", str(config.settings.openai_max_tokens))
    info_table.add_row("Batch Size", str(config.settings.batch_size))
    info_table.add_row("Max Emails/Run", str(config.settings.max_emails_per_run))
    info_table.add_row("Categories", str(len(config.classification_config.categories)))
    
    console.print(info_table)
    console.print("\n")


async def main_menu():
    """główna pętla menu"""
    config: Optional[ConfigurationManager] = None
    
    while True:
        draw_banner()
        
        # load config if not loaded
        if not config:
            try:
                config = get_config()
                console.print("[green]Configuration loaded[/green]\n")
            except Exception as e:
                console.print(f"[bold red]Config error:[/bold red] {e}\n")
                return
        
        # main menu
        choice = await questionary.select(
            "What do you want to do?",
            choices=[
                questionary.Choice("Start Classification", "classify"),
                questionary.Choice("Show Configuration", "config"),
                questionary.Choice("Quit", "quit"),
            ],
        ).ask_async()
        
        if not choice:  # user cancelled
            break
        
        if choice == "quit":
            console.print("\n[yellow]Bye![/yellow]\n")
            break
        
        elif choice == "config":
            show_config_info(config)
            await questionary.confirm("Press Enter to continue...", default=True).ask_async()
            console.print("\n")
        
        elif choice == "classify":
            # provider selection
            provider_choice = await questionary.select(
                "Select email provider:",
                choices=[
                    questionary.Choice("Gmail", "gmail"),
                    questionary.Choice("Outlook", "outlook"),
                    questionary.Choice("Both", "both"),
                ],
                default=config.settings.email_provider.lower(),
            ).ask_async()
            
            if not provider_choice:
                console.print("\n")
                continue
            
            # limit selection
            limit_choice = await questionary.text(
                f"Max emails to process (default: {config.settings.max_emails_per_run}):",
                default=str(config.settings.max_emails_per_run),
                validate=lambda x: x.isdigit() and int(x) > 0 if x else True,
            ).ask_async()
            
            if not limit_choice:
                limit = None
            else:
                limit = int(limit_choice) if limit_choice.isdigit() else None
            
            # confirm
            confirm = await questionary.confirm(
                f"Start classification from {provider_choice}?",
                default=True,
            ).ask_async()
            
            if not confirm:
                console.print("\n")
                continue
            
            console.print("\n")
            
            # run classification
            await run_classification(config, provider=provider_choice, limit=limit)
            
            # ask if continue
            continue_choice = await questionary.confirm(
                "Continue?",
                default=True,
            ).ask_async()
            
            if not continue_choice:
                break
            
            console.print("\n")


def run_tui():
    """uruchom TUI"""
    try:
        asyncio.run(main_menu())
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted[/yellow]\n")
    except Exception as e:
        console.print(f"\n[bold red]Error:[/bold red] {e}\n")


if __name__ == "__main__":
    run_tui()
