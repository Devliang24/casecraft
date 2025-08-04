"""Implementation of the generate command."""

import asyncio
import sys
from pathlib import Path
from typing import List, Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from casecraft.core.config_manager import ConfigManager, ConfigError
from casecraft.core.generator_engine import GeneratorEngine, GeneratorError, GenerationResult
from casecraft.models.config import CaseCraftConfig


console = Console()


async def generate_command(
    source: str,
    output: str,
    include_tag: tuple,
    exclude_tag: tuple,
    include_path: tuple,
    workers: int,
    force: bool,
    dry_run: bool,
    organize_by: Optional[str],
    verbose: bool
) -> None:
    """Generate test cases from API documentation.
    
    Args:
        source: API documentation source
        output: Output directory
        include_tag: Tags to include
        exclude_tag: Tags to exclude
        include_path: Path patterns to include
        workers: Number of workers
        force: Force regeneration
        dry_run: Dry run mode
        organize_by: Organization method
        verbose: Verbose output
    """
    try:
        # Load configuration
        config = await _load_configuration(
            output, workers, force, dry_run, organize_by, verbose
        )
        
        # Validate configuration
        config_manager = ConfigManager()
        config_manager.validate_config(config)
        
        # Initialize generator
        engine = GeneratorEngine(config, console)
        
        # Convert tuples to lists
        include_tags = list(include_tag) if include_tag else None
        exclude_tags = list(exclude_tag) if exclude_tag else None
        include_paths = list(include_path) if include_path else None
        
        # Generate test cases
        result = await engine.generate(
            source=source,
            include_tags=include_tags,
            exclude_tags=exclude_tags,
            include_paths=include_paths,
            force=force,
            dry_run=dry_run
        )
        
        # Show results
        _show_results(result, dry_run)
        
    except ConfigError as e:
        console.print(f"[red]Configuration Error:[/red] {e}")
        _show_config_help()
        raise click.ClickException(str(e))
    except GeneratorError as e:
        console.print(f"[red]Generation Error:[/red] {e}")
        raise click.ClickException(str(e))
    except KeyboardInterrupt:
        console.print("\n[yellow]Generation cancelled by user.[/yellow]")
        raise click.Abort()
    except Exception as e:
        console.print(f"[red]Unexpected Error:[/red] {e}")
        if verbose:
            console.print_exception()
        raise click.ClickException(str(e))


async def _load_configuration(
    output: str,
    workers: int,
    force: bool,
    dry_run: bool,
    organize_by: Optional[str],
    verbose: bool
) -> CaseCraftConfig:
    """Load and merge configuration from all sources.
    
    Args:
        output: Output directory override
        workers: Workers override
        force: Force flag override
        dry_run: Dry run flag override
        organize_by: Organization override
        verbose: Verbose flag
        
    Returns:
        Merged configuration
    """
    config_manager = ConfigManager()
    
    # Get environment overrides
    env_overrides = config_manager.get_env_overrides()
    
    # Build CLI overrides
    cli_overrides = {}
    if output != "test_cases":  # Not default
        cli_overrides["output.directory"] = output
    if workers != 4:  # Not default
        cli_overrides["processing.workers"] = workers
    if force:
        cli_overrides["processing.force_regenerate"] = force
    if dry_run:
        cli_overrides["processing.dry_run"] = dry_run
    if organize_by:
        cli_overrides["output.organize_by_tag"] = (organize_by == "tag")
    
    # Load with overrides
    config = config_manager.load_config_with_overrides(env_overrides, cli_overrides)
    
    if verbose:
        console.print("[dim]Configuration loaded with overrides applied[/dim]")
    
    return config


def _show_config_help() -> None:
    """Show configuration help."""
    help_text = """
Configuration is missing or invalid. To fix this:

1. Run [cyan]casecraft init[/cyan] to set up configuration
2. Set API key via environment variable:
   [cyan]export CASECRAFT_LLM_API_KEY=your-api-key[/cyan]
3. Or edit the config file directly:
   [cyan]~/.casecraft/config.yaml[/cyan]
"""
    
    console.print(Panel(
        help_text.strip(),
        title="Configuration Help",
        border_style="yellow"
    ))


def _show_results(result: GenerationResult, dry_run: bool) -> None:
    """Show generation results.
    
    Args:
        result: Generation result
        dry_run: Whether this was a dry run
    """
    if dry_run:
        _show_dry_run_results(result)
    else:
        _show_generation_results(result)


def _show_dry_run_results(result: GenerationResult) -> None:
    """Show dry run results.
    
    Args:
        result: Generation result
    """
    console.print("\n[bold blue]🔍 Dry Run Summary[/bold blue]")
    
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_row("Total endpoints:", str(result.total_endpoints))
    table.add_row("Would generate:", str(len(result.api_spec.endpoints) - result.skipped_count))
    table.add_row("Would skip:", str(result.skipped_count))
    
    console.print(table)
    
    if result.api_spec and result.api_spec.endpoints:
        console.print(f"\n[dim]Run without --dry-run to generate test cases[/dim]")


def _show_generation_results(result: GenerationResult) -> None:
    """Show generation results.
    
    Args:
        result: Generation result
    """
    console.print("\n[bold green]✨ Generation Complete![/bold green]")
    
    # Summary table
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_row("Total endpoints:", str(result.total_endpoints))
    table.add_row("✓ Generated:", f"[green]{result.generated_count}[/green]")
    table.add_row("⏭️  Skipped:", f"[dim]{result.skipped_count}[/dim]")
    
    if result.failed_count > 0:
        table.add_row("✗ Failed:", f"[red]{result.failed_count}[/red]")
    
    table.add_row("⏱️  Duration:", f"{result.duration:.1f}s")
    
    console.print(table)
    
    # Show generated files
    if result.generated_files:
        console.print(f"\n[blue]📁 Generated {len(result.generated_files)} test case files:[/blue]")
        for file_path in result.generated_files[:5]:  # Show first 5
            console.print(f"  • {file_path}")
        
        if len(result.generated_files) > 5:
            console.print(f"  ... and {len(result.generated_files) - 5} more")
    
    # Show failures
    if result.failed_endpoints:
        console.print(f"\n[red]❌ Failed endpoints:[/red]")
        for failure in result.failed_endpoints[:3]:  # Show first 3
            console.print(f"  • {failure}")
        
        if len(result.failed_endpoints) > 3:
            console.print(f"  ... and {len(result.failed_endpoints) - 3} more")
    
    # Next steps
    if result.generated_files:
        console.print(f"\n[dim]💡 Test case files are ready for use with your testing framework[/dim]")


def run_generate_command(*args, **kwargs) -> None:
    """Synchronous wrapper for generate command."""
    try:
        asyncio.run(generate_command(*args, **kwargs))
    except RuntimeError as e:
        if "asyncio.run() cannot be called from a running event loop" in str(e):
            # Handle case where we're already in an event loop
            loop = asyncio.get_event_loop()
            task = loop.create_task(generate_command(*args, **kwargs))
            loop.run_until_complete(task)
        else:
            raise