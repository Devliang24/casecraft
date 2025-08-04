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
    help="Enable verbose output"
)
@click.pass_context
def cli(ctx: click.Context, verbose: bool) -> None:
    """CaseCraft: Generate API test cases using BigModel LLM.
    
    A CLI tool that parses API documentation (OpenAPI/Swagger) and uses
    BigModel GLM-4.5-X to generate structured test case data in JSON format.
    """
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose


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
    help="Number of concurrent workers (BigModel only supports 1)"
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
) -> None:
    """Generate test cases from API documentation.
    
    SOURCE can be a URL (https://...) or local file path to OpenAPI/Swagger
    documentation in JSON or YAML format.
    
    Examples:
    
        casecraft generate https://petstore.swagger.io/v2/swagger.json
        
        casecraft generate ./api-docs.yaml --include-tag users
        
        casecraft generate ./openapi.json --force --dry-run
    """
    from casecraft.cli.generate_command import run_generate_command
    
    verbose = ctx.obj.get("verbose", False)
    
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
        verbose=verbose
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