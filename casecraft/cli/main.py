"""Main CLI command group for CaseCraft."""

import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import click
from rich.console import Console

from casecraft import __version__

console = Console()


@click.group()
@click.version_option(version=__version__, prog_name="casecraft")
@click.option(
    "--verbose", "-v",
    is_flag=True,
    help="Enable verbose output (shows DEBUG level)"
)
@click.option(
    "--quiet", "-q",
    is_flag=True,
    help="Quiet mode - only show warnings and errors"
)
@click.option(
    "--log-file",
    type=click.Path(dir_okay=False, writable=True),
    help="Path to log file (default: logs/casecraft_TIMESTAMP.log)"
)
@click.option(
    "--log-dir",
    type=click.Path(file_okay=False, writable=True),
    default="logs",
    help="Directory for log files (default: logs/)"
)
@click.pass_context
def cli(ctx: click.Context, verbose: bool, quiet: bool, log_file: Optional[str], log_dir: str) -> None:
    """CaseCraft: Generate API test cases using multiple LLM providers.
    
    A CLI tool that parses API documentation (OpenAPI/Swagger) and uses
    various LLM providers (GLM, Qwen, local models) to generate 
    structured test case data in JSON format.
    """
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    ctx.obj["quiet"] = quiet
    
    # Configure logging based on flags
    if verbose and quiet:
        console.print("[yellow]Warning: Both --verbose and --quiet specified. Using verbose mode.[/yellow]")
        ctx.obj["quiet"] = False
    
    # Set up initial logging configuration
    from casecraft.utils.logging import configure_logging, CaseCraftLogger
    
    if quiet:
        log_level = "WARNING"
    elif verbose:
        log_level = "DEBUG"
    else:
        log_level = "INFO"
    
    # Determine log file path
    final_log_file = None
    if log_file:
        # Use specified log file
        final_log_file = log_file
    elif os.getenv("CASECRAFT_LOG_FILE"):
        # Use environment variable
        final_log_file = os.getenv("CASECRAFT_LOG_FILE")
    elif os.getenv("CASECRAFT_LOG_ENABLED", "").lower() == "true":
        # Auto-generate log file if logging is enabled
        log_dir_path = Path(os.getenv("CASECRAFT_LOG_DIR", log_dir))
        log_dir_path.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        final_log_file = log_dir_path / f"casecraft_{timestamp}.log"
    
    # Configure logging with file output
    configure_logging(log_level=log_level, log_file=final_log_file, console_output=False)
    
    # Set global log file for CaseCraftLogger
    if final_log_file:
        CaseCraftLogger.set_global_log_file(final_log_file)
        console.print(f"[dim]📝 Logging to: {final_log_file}[/dim]")
    
    # Store log file path in context for later use
    ctx.obj["log_file"] = final_log_file


@cli.command()
def init() -> None:
    """Initialize CaseCraft configuration.
    
    Creates a configuration file in ~/.casecraft/config.yaml with
    default settings and prompts for API key setup.
    """
    from casecraft.cli.init_command import init_command
    init_command()


@cli.command()
@click.argument("source", required=True)
@click.option(
    "--output", "-o",
    default="test_cases",
    help="Output directory for generated test cases"
)
@click.option(
    "--include-tag",
    multiple=True,
    help="Include only endpoints with these tags"
)
@click.option(
    "--exclude-tag", 
    multiple=True,
    help="Exclude endpoints with these tags"
)
@click.option(
    "--include-path",
    multiple=True,
    help="Include only paths matching these patterns"
)
@click.option(
    "--workers", "-w",
    required=True,
    type=int,
    help="Number of concurrent workers (required, provider-dependent)"
)
@click.option(
    "--force",
    is_flag=True,
    help="Force regenerate all test cases"
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Preview mode - no LLM calls"
)
@click.option(
    "--organize-by",
    type=click.Choice(["tag"]),
    help="Organize output files by criteria"
)
@click.option(
    "--provider",
    help="Use specific LLM provider for all endpoints (e.g., glm, qwen, local)"
)
@click.option(
    "--providers",
    help="Comma-separated list of providers for concurrent execution"
)
@click.option(
    "--provider-map",
    help="Manual provider mapping (format: path1:provider1,path2:provider2)"
)
@click.option(
    "--strategy",
    type=click.Choice(["round_robin", "random", "complexity_based", "manual"]),
    default="round_robin",
    help="Provider assignment strategy (used with --providers)"
)
@click.option(
    "--model", "-m",
    help="Specify model for the provider (e.g., glm-4-flash, qwen-plus)"
)
@click.option(
    "--log-file",
    is_flag=False,
    flag_value="auto",
    type=click.Path(dir_okay=False, writable=True),
    help="Path to log file, or just '--log-file' to auto-generate (casecraft_TIMESTAMP.log)"
)
@click.pass_context
def generate(
    ctx: click.Context,
    source: str,
    output: str,
    include_tag: tuple,
    exclude_tag: tuple,
    include_path: tuple,
    workers: int,
    force: bool,
    dry_run: bool,
    organize_by: str,
    provider: str,
    providers: str,
    provider_map: str,
    strategy: str,
    model: str,
    log_file: Optional[str],
) -> None:
    """Generate test cases from API documentation.
    
    SOURCE can be a URL (https://...) or local file path to OpenAPI/Swagger
    documentation in JSON or YAML format.
    
    IMPORTANT: You must specify an LLM provider using one of these options:
        --provider <name>: Use a single provider for all endpoints
        --providers <list>: Use multiple providers with a strategy
        --provider-map <mapping>: Map specific endpoints to providers
    
    Examples:
    
        # Single provider
        casecraft generate api.json --provider glm
        
        # Multiple providers with round-robin
        casecraft generate api.json --providers glm,qwen
        
        # Manual mapping
        casecraft generate api.json --provider-map "/users:qwen,/products:glm"
        
        # With filters and options
        casecraft generate ./api-docs.yaml --provider glm --include-tag users --force
    """
    from casecraft.cli.generate_command import run_generate_command
    from casecraft.utils.logging import CaseCraftLogger
    
    verbose = ctx.obj.get("verbose", False)
    quiet = ctx.obj.get("quiet", False)
    
    # Handle log_file option
    if log_file:
        # If log_file is "auto", generate a filename with timestamp
        if log_file == "auto":
            log_dir = Path("logs")
            log_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            log_file = log_dir / f"casecraft_{timestamp}.log"
        
        CaseCraftLogger.set_global_log_file(log_file)
        console.print(f"[dim]📝 Logging to: {log_file}[/dim]")
    
    run_generate_command(
        source=source,
        output=output,
        include_tag=include_tag,
        exclude_tag=exclude_tag,
        include_path=include_path,
        workers=workers,
        force=force,
        dry_run=dry_run,
        organize_by=organize_by,
        verbose=verbose,
        quiet=quiet,
        provider=provider,
        providers=providers,
        provider_map=provider_map,
        strategy=strategy,
        model=model
    )


def main() -> None:
    """Entry point for the CLI."""
    try:
        cli()
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise


if __name__ == "__main__":
    main()