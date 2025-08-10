"""Main CLI command group for CaseCraft."""

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
@click.pass_context
def cli(ctx: click.Context, verbose: bool, quiet: bool) -> None:
    """CaseCraft: Generate API test cases using multiple LLM providers.
    
    A CLI tool that parses API documentation (OpenAPI/Swagger) and uses
    various LLM providers (GLM, Qwen, Kimi, local models) to generate 
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
    from casecraft.utils.logging import configure_logging
    
    if quiet:
        log_level = "WARNING"
    elif verbose:
        log_level = "DEBUG"
    else:
        log_level = "INFO"
    
    # Configure logging with console output disabled (we use CaseCraftLogger for console)
    configure_logging(log_level=log_level, console_output=False)


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
    default=1,
    type=int,
    help="Number of concurrent workers (provider-dependent)"
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
    help="Use specific LLM provider for all endpoints (e.g., glm, qwen, kimi, local)"
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
        casecraft generate api.json --providers glm,qwen,kimi
        
        # Manual mapping
        casecraft generate api.json --provider-map "/users:qwen,/products:glm"
        
        # With filters and options
        casecraft generate ./api-docs.yaml --provider glm --include-tag users --force
    """
    from casecraft.cli.generate_command import run_generate_command
    
    verbose = ctx.obj.get("verbose", False)
    quiet = ctx.obj.get("quiet", False)
    
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