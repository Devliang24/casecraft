"""Implementation of the generate command with multi-provider support."""

import asyncio
import os
import sys
from pathlib import Path
from typing import List, Optional, Dict

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from casecraft.core.management.config_manager import ConfigManager, ConfigError
from casecraft.core.management.multi_provider_config_manager import MultiProviderConfigManager
from casecraft.core.management.enhanced_state_manager import EnhancedStateManager
from casecraft.core.engine import GeneratorEngine, GeneratorError, GenerationResult
from casecraft.core.multi_provider_engine import MultiProviderEngine
from casecraft.models.config import CaseCraftConfig, PromptConfig
from casecraft.models.provider_config import MultiProviderConfig, ProviderConfig
from casecraft.core.providers.registry import ProviderRegistry
from casecraft.utils.constants import DEFAULT_API_PARSE_TIMEOUT


console = Console()


async def generate_command(
    source: str,
    output: str,
    include_tag: tuple,
    exclude_tag: tuple,
    include_path: tuple,
    include_method: Optional[list] = None,
    exclude_method: Optional[list] = None,
    workers: int = 1,
    force: bool = False,
    dry_run: bool = False,
    organize_by: Optional[str] = None,
    format: str = "json",
    config: Optional[str] = None,
    merge_excel: bool = False,
    priority: str = "all",
    verbose: bool = False,
    quiet: bool = False,
    provider: Optional[str] = None,
    providers: Optional[str] = None,
    provider_map: Optional[str] = None,
    strategy: str = "round_robin",
    model: Optional[str] = None,
    save_prompts: bool = False,
    prompts_dir: str = "prompts",
    prompt_format: str = "txt",
    save_responses: bool = False,
    lang: Optional[str] = None,
    auto_detect: bool = True
) -> None:
    """Generate test cases from API documentation.
    
    Args:
        source: API documentation source
        output: Output directory
        include_tag: Tags to include
        exclude_tag: Tags to exclude
        include_path: Path patterns to include
        include_method: HTTP methods to include
        exclude_method: HTTP methods to exclude
        workers: Number of workers
        force: Force regeneration
        dry_run: Dry run mode
        organize_by: Organization method
        verbose: Verbose output
        quiet: Quiet mode (warnings/errors only)
        provider: Single provider name
        providers: Comma-separated provider list
        provider_map: Manual provider mapping
        strategy: Provider assignment strategy
        model: Model to use for generation
    """
    # Load .env file early to ensure environment variables are available
    from pathlib import Path
    from dotenv import load_dotenv
    env_file = Path.cwd() / ".env"
    if env_file.exists():
        load_dotenv(env_file, override=False)
    else:
        # Show warning but continue - user might have env vars set
        console.print("[yellow]⚠️  No .env file found in current directory[/yellow]")
        console.print(f"[dim]Current directory: {Path.cwd()}[/dim]\n")
    
    # Check if multi-provider support is requested
    # Default to GLM provider if no provider is specified but LLM model is configured
    default_provider = None
    if os.getenv("CASECRAFT_LLM_MODEL") and not provider and not providers:
        default_provider = "glm"
    
    if provider or providers or provider_map or os.getenv("CASECRAFT_PROVIDER") or os.getenv("CASECRAFT_PROVIDERS") or default_provider:
        # Use multi-provider implementation
        return await _generate_with_providers(
            source=source,
            output=output,
            include_tag=include_tag,
            exclude_tag=exclude_tag,
            include_path=include_path,
            include_method=include_method,
            exclude_method=exclude_method,
            workers=workers,
            force=force,
            dry_run=dry_run,
            organize_by=organize_by,
            verbose=verbose,
            quiet=quiet,
            provider=provider or os.getenv("CASECRAFT_PROVIDER") or default_provider,
            providers=providers or os.getenv("CASECRAFT_PROVIDERS"),
            provider_map=provider_map,
            strategy=strategy,
            format=format,
            config=config,
            merge_excel=merge_excel,
            priority=priority,
            model=model,
            save_prompts=save_prompts,
            prompts_dir=prompts_dir,
            prompt_format=prompt_format,
            save_responses=save_responses,
            lang=lang,
            auto_detect=auto_detect
        )
    
    # Legacy single-provider mode (backward compatibility)
    try:
        # Load configuration
        config = await _load_configuration(
            output, workers, force, dry_run, organize_by, verbose,
            save_prompts, prompts_dir, prompt_format, save_responses
        )
        
        # Validate configuration
        config_manager = ConfigManager()
        config_manager.validate_config(config)
        
        # Initialize generator with appropriate verbosity
        engine = GeneratorEngine(config, console, verbose=verbose, quiet=quiet)
        
        # Show model configuration (unless in quiet mode)
        if not quiet:
            _show_model_config(config, verbose)
        
        # Convert tuples to lists
        include_tags = list(include_tag) if include_tag else None
        exclude_tags = list(exclude_tag) if exclude_tag else None
        include_paths = list(include_path) if include_path else None
        include_methods = include_method  # Already validated as list
        exclude_methods = exclude_method  # Already validated as list
        
        # Generate test cases
        result = await engine.generate(
            source=source,
            include_tags=include_tags,
            exclude_tags=exclude_tags,
            include_paths=include_paths,
            include_methods=include_methods,
            exclude_methods=exclude_methods,
            force=force,
            dry_run=dry_run
        )
        
        # Show results (unless in quiet mode)
        if not quiet:
            _show_results(result, dry_run)
        
    except ConfigError as e:
        error_msg = str(e)
        console.print(f"\n[red]❌ Configuration Error: {error_msg}[/red]")
        
        # Check if it's an API key error and provide better guidance
        if "API key not configured" in error_msg:
            # Extract provider name from error message
            import re
            match = re.search(r'for (\w+)', error_msg)
            provider_name = match.group(1) if match else 'unknown'
            
            env_file = Path.cwd() / ".env"
            if not env_file.exists():
                console.print("\n[yellow]💡 Tips:[/yellow]")
                console.print("1. No .env file found in current directory")
                console.print(f"   Current directory: [cyan]{Path.cwd()}[/cyan]")
                console.print("\n2. Please switch to project directory with .env file, or:")
                console.print("   - Copy configuration template: [cyan]cp /path/to/.env.example .env[/cyan]")
                console.print("   - Edit .env file and add your API key")
                console.print("\n3. Or set environment variable:")
                console.print(f"   [cyan]export CASECRAFT_{provider_name.upper()}_API_KEY=your-api-key[/cyan]")
            else:
                console.print("\n[yellow]💡 .env file exists but missing configuration:[/yellow]")
                console.print(f"Please edit .env file and add: [cyan]CASECRAFT_{provider_name.upper()}_API_KEY=your-api-key[/cyan]")
        else:
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
    verbose: bool,
    save_prompts: bool = False,
    prompts_dir: str = "prompts",
    prompt_format: str = "txt",
    save_responses: bool = False
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
    # Workers is always from CLI (required argument)
    cli_overrides["processing.workers"] = workers
    if force:
        cli_overrides["processing.force_regenerate"] = force
    if dry_run:
        cli_overrides["processing.dry_run"] = dry_run
    if organize_by:
        cli_overrides["output.organize_by_tag"] = (organize_by == "tag")
    
    # Add prompt configuration overrides
    if save_prompts:
        cli_overrides["prompt.save_prompts"] = save_prompts
    if prompts_dir != "prompts":  # Not default
        cli_overrides["prompt.prompts_dir"] = prompts_dir
    if prompt_format != "txt":  # Not default
        cli_overrides["prompt.prompt_format"] = prompt_format
    if save_responses:
        cli_overrides["prompt.save_responses"] = save_responses
    
    # Load with overrides
    config = config_manager.load_config_with_overrides(env_overrides, cli_overrides)
    
    if verbose:
        console.print("[dim]Configuration loaded with overrides applied[/dim]")
    
    return config


def _show_model_config(config: CaseCraftConfig, verbose: bool) -> None:
    """Show model configuration information.
    
    Args:
        config: CaseCraft configuration
        verbose: Whether to show verbose information
    """
    # Create 3-column configuration table for proper alignment
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column(width=2, justify="left")   # Emoji column
    table.add_column(width=12, justify="left")  # Label column  
    table.add_column(justify="left")            # Value column
    
    # Show configuration values with proper column alignment
    table.add_row("🤖", "Model:", f"[cyan bold]{config.llm.model}[/cyan bold]")
    table.add_row("🌐", "Base URL:", f"[dim]{config.llm.base_url}[/dim]")
    
    think_color = "green" if config.llm.think else "dim"
    table.add_row("🧠", "Think:", f"[{think_color}]{str(config.llm.think).lower()}[/{think_color}]")
    
    stream_color = "green" if config.llm.stream else "dim"
    table.add_row("📡", "Stream:", f"[{stream_color}]{str(config.llm.stream).lower()}[/{stream_color}]")
    
    table.add_row("⚡", "Workers:", f"[yellow]{config.processing.workers}[/yellow]")
    
    if verbose:
        # Additional verbose information with proper column alignment
        table.add_row("⏱️", "Timeout:", f"{config.llm.timeout}s")
        table.add_row("🔄", "Max Retries:", f"{config.llm.max_retries}")
        table.add_row("🌡️", "Temperature:", f"{config.llm.temperature}")
    
    console.print("\n[bold blue]━━━━━━ 🚀 Generation Config ━━━━━━[/bold blue]")
    console.print(table)
    console.print("[dim]──────────────────────────────────[/dim]\n")


def _show_config_help() -> None:
    """Show configuration help."""
    help_text = """
Configuration is missing or invalid. To fix this:

1. Run [cyan]casecraft init[/cyan] to create .env file
2. Set API key via environment variable:
   [cyan]export CASECRAFT_LLM_API_KEY=your-api-key[/cyan]
3. Or create .env file manually:
   [cyan]CASECRAFT_LLM_API_KEY=your-api-key[/cyan]
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
    console.print("\n[bold blue]━━━━━━ 🔍 Preview Mode ━━━━━━[/bold blue]")
    
    # Create 3-column table for proper alignment
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column(width=2, justify="left")   # Emoji column
    table.add_column(width=20, justify="left")  # Label column (与其他表格对齐)
    table.add_column(justify="left")            # Value column
    
    table.add_row("📁", "Found Endpoints:", f"[bold]{result.total_endpoints}[/bold]")
    table.add_row("✅", "Will Generate:", f"[green]{len(result.api_spec.endpoints) - result.skipped_count}[/green]")
    table.add_row("⏭️", "Will Skip:", f"[dim]{result.skipped_count}[/dim] (unchanged)")
    
    console.print(table)
    
    if result.api_spec and result.api_spec.endpoints:
        console.print(f"\n[yellow]💡 Tip: Remove --dry-run to start actual generation[/yellow]")
    console.print("[dim]──────────────────────────────────[/dim]")


def _show_retry_breakdown(result: GenerationResult) -> None:
    """Show detailed retry breakdown by layer and endpoint.
    
    Args:
        result: Generation result with retry statistics
    """
    retry_summary = result.get_retry_summary()
    
    if retry_summary.get('total_retries', 0) == 0:
        return
    
    console.print(f"\n[bold blue]━━━━━━ 🔄 Retry Breakdown ━━━━━━[/bold blue]")
    
    # Create breakdown table
    breakdown_table = Table(show_header=False, box=None, padding=(0, 1))
    breakdown_table.add_column(width=2, justify="left")   # Emoji column
    breakdown_table.add_column(width=20, justify="left")  # Label column
    breakdown_table.add_column(justify="left")            # Value column
    
    # Show overall statistics
    total_retries = retry_summary['total_retries']
    total_endpoints = retry_summary['total_endpoints']
    endpoints_with_retries = retry_summary['endpoints_with_retries']
    
    breakdown_table.add_row("📊", "Overall Summary:", f"{total_retries} retries across {endpoints_with_retries}/{total_endpoints} endpoints")
    
    # Show time breakdown if available
    if retry_summary.get('total_retry_time', 0) > 0:
        retry_time = retry_summary['total_retry_time']
        wait_time = retry_summary.get('total_wait_time', 0)
        breakdown_table.add_row("⏱️", "Total Retry Time:", f"{retry_time:.1f}s")
        if wait_time > 0:
            breakdown_table.add_row("⏳", "Total Wait Time:", f"{wait_time:.1f}s")
    
    # Show most retried endpoints with details
    most_retried = retry_summary.get('most_retried_endpoints', [])
    if most_retried:
        breakdown_table.add_row("", "", "")  # Separator
        breakdown_table.add_row("🔥", "Most Retried Endpoints:", "")
        for i, endpoint_info in enumerate(most_retried[:3]):
            prefix = f"#{i+1}:" if i < 3 else ""
            endpoint_id = endpoint_info['endpoint_id']
            retries = endpoint_info['retries']
            retry_time = endpoint_info.get('retry_time', 0)
            
            if retry_time > 0:
                breakdown_table.add_row("", f"  {prefix}", f"{endpoint_id} - {retries} retries ({retry_time:.1f}s)")
            else:
                breakdown_table.add_row("", f"  {prefix}", f"{endpoint_id} - {retries} retries")
    
    console.print(breakdown_table)
    console.print("[dim]──────────────────────────────────[/dim]")


def _show_token_statistics(result: GenerationResult) -> None:
    """Show token usage statistics.
    
    Args:
        result: Generation result with token statistics
    """
    summary = result.get_token_summary()
    
    console.print(f"\n[bold blue]━━━━━━ 📊 Usage Statistics ━━━━━━[/bold blue]")
    
    # Create 3-column token statistics table for proper alignment
    token_table = Table(show_header=False, box=None, padding=(0, 1))
    token_table.add_column(width=2, justify="left")   # Emoji column
    token_table.add_column(width=20, justify="left")  # Label column (从 22 改为 20)
    token_table.add_column(justify="left")            # Value column
    
    # Model and API call statistics
    token_table.add_row("🤖", "Model:", f"[cyan bold]{summary['model']}[/cyan bold]")
    
    success_ratio = summary['success_rate']
    progress_bar = "█" * int(success_ratio * 10) + "░" * (10 - int(success_ratio * 10))
    token_table.add_row("📡", "API Calls:", f"{summary['successful_calls']}/{summary['total_calls']} success")
    token_table.add_row("📈", "Success Rate:", f"[green]{progress_bar}[/green] {success_ratio:.0%}")
    
    # Token usage statistics
    token_table.add_row("📝", "Input:", f"{summary['prompt_tokens']} tokens")
    token_table.add_row("📤", "Output:", f"{summary['completion_tokens']} tokens")
    token_table.add_row("📊", "Total:", f"[bold yellow]{summary['total_tokens']} tokens[/bold yellow]")
    
    if summary['successful_calls'] > 0:
        avg_tokens = summary['average_tokens_per_call']
        token_table.add_row("⚡", "Avg/Call:", f"{avg_tokens}/call")
        
        # Calculate and show processing speed
        if result.duration > 0:
            endpoints_per_min = (result.generated_count / result.duration) * 60
            token_table.add_row("🚀", "Speed:", f"{endpoints_per_min:.1f} endpoints/min")
    
    # Add comprehensive retry statistics if available
    retry_summary = result.get_retry_summary()
    if retry_summary.get('total_retries', 0) > 0:
        token_table.add_row("", "", "")  # Empty separator row
        token_table.add_row("🔄", "Total Retries:", f"[yellow]{retry_summary['total_retries']}[/yellow]")
        token_table.add_row("📍", "Endpoints w/ Retries:", f"{retry_summary['endpoints_with_retries']}/{retry_summary['total_endpoints']}")
        
        # Show retry rate as percentage
        retry_rate = retry_summary['retry_rate'] * 100
        token_table.add_row("📊", "Retry Rate:", f"{retry_rate:.1f}%")
        
        # Show time breakdown if available
        if retry_summary.get('total_retry_time', 0) > 0:
            retry_time = retry_summary['total_retry_time']
            wait_time = retry_summary.get('total_wait_time', 0)
            token_table.add_row("⏱️", "Retry Time:", f"{retry_time:.1f}s")
            if wait_time > 0:
                token_table.add_row("⏳", "Wait Time:", f"{wait_time:.1f}s")
        
        # Show average retries per endpoint that had retries
        avg_retries = retry_summary['average_retries_per_endpoint']
        token_table.add_row("⚖️", "Avg Retries/Endpoint:", f"{avg_retries:.1f}")
        
        # Show most retried endpoints (top 3)
        most_retried = retry_summary.get('most_retried_endpoints', [])
        if most_retried:
            token_table.add_row("🔥", "Most Retried:", f"{most_retried[0]['endpoint_id']} ({most_retried[0]['retries']} retries)")
            if len(most_retried) > 1:
                for endpoint_info in most_retried[1:3]:  # Show up to 2 more
                    token_table.add_row("", "", f"{endpoint_info['endpoint_id']} ({endpoint_info['retries']} retries)")
    
    console.print(token_table)
    console.print("[dim]──────────────────────────────────[/dim]")


def _show_generation_results(result: GenerationResult) -> None:
    """Show generation results.
    
    Args:
        result: Generation result
    """
    console.print("\n[bold green]━━━━━━ ✨ Generation Complete ━━━━━━[/bold green]")
    
    # Create 3-column summary table for proper alignment
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column(width=2, justify="left")   # Emoji column
    table.add_column(width=20, justify="left")  # Label column (与Usage Statistics对齐)
    table.add_column(justify="left")            # Value column
    
    table.add_row("📊", "Total Endpoints:", f"[bold]{result.total_endpoints}[/bold]")
    table.add_row("✅", "Generated:      ", f"[green bold]{result.generated_count}[/green bold]")
    table.add_row("📋", "Test Cases:     ", f"[cyan bold]{result.total_test_cases}[/cyan bold]")
    table.add_row("⏩", "Skipped:        ", f"[dim]{result.skipped_count}[/dim]")
    
    if result.failed_count > 0:
        table.add_row("❌", "Failed:         ", f"[red]{result.failed_count}[/red]")
    
    # Format duration
    table.add_row("⏰", "Duration:       ", f"{result.duration:.1f}s")
    
    # Add retry summary if there were retries
    retry_summary = result.get_retry_summary()
    if retry_summary.get('total_retries', 0) > 0:
        table.add_row("🔄", "Total Retries:", f"[yellow]{retry_summary['total_retries']}[/yellow]")
        
        # Show retry efficiency (percentage of total time spent on retries)
        if retry_summary.get('total_retry_time', 0) > 0 and result.duration > 0:
            retry_time_percentage = (retry_summary['total_retry_time'] / result.duration) * 100
            table.add_row("⏱️", "Retry Time:", f"{retry_time_percentage:.1f}% of total")
    
    console.print(table)
    
    # Show token usage and cost statistics if available
    if result.has_token_usage():
        _show_token_statistics(result)
    
    # Show detailed retry breakdown if there were significant retries
    retry_summary = result.get_retry_summary()
    if retry_summary.get('total_retries', 0) >= 5:  # Show breakdown for 5+ retries
        _show_retry_breakdown(result)
    
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
            # Split endpoint and error for better formatting
            if ": " in failure:
                parts = failure.split(": ", 1)
                endpoint = parts[0]
                error = parts[1] if len(parts) > 1 else ""
                console.print(f"  • [bold]{endpoint}[/bold]:")
                # Show error with indentation and wrapping
                console.print(f"    [dim red]{error}[/dim red]", soft_wrap=True)
            else:
                console.print(f"  • {failure}", soft_wrap=True)
        
        if len(result.failed_endpoints) > 3:
            console.print(f"  ... and {len(result.failed_endpoints) - 3} more")
    
    # Next steps
    if result.generated_files:
        console.print(f"\n[dim]💡 Test case files are ready for use with your testing framework[/dim]")


async def _generate_with_providers(
    source: str,
    output: str,
    include_tag: tuple,
    exclude_tag: tuple,
    include_path: tuple,
    include_method: Optional[list],
    exclude_method: Optional[list],
    workers: int,
    force: bool,
    dry_run: bool,
    organize_by: Optional[str],
    verbose: bool,
    quiet: bool,
    provider: Optional[str],
    providers: Optional[str],
    provider_map: Optional[str],
    strategy: str,
    format: str = "json",
    config: Optional[str] = None,
    merge_excel: bool = False,
    priority: str = "all",
    model: Optional[str] = None,
    save_prompts: bool = False,
    prompts_dir: str = "prompts",
    prompt_format: str = "txt",
    save_responses: bool = False,
    lang: Optional[str] = None,
    auto_detect: bool = True
) -> None:
    """Generate test cases with multi-provider support."""
    try:
        # Validate provider specification
        config_manager = MultiProviderConfigManager()
        config_manager.validate_provider_specified(provider, 
                                                  providers.split(",") if providers else None,
                                                  _parse_provider_map(provider_map) if provider_map else None)
        
        # Determine mode
        if provider:
            # Single provider mode
            await _run_single_provider(
                source, output, include_tag, exclude_tag, include_path,
                include_method, exclude_method,
                workers, force, dry_run, organize_by, verbose, quiet, provider, model,
                format, config, merge_excel, priority,
                save_prompts, prompts_dir, prompt_format, save_responses,
                lang, auto_detect
            )
        else:
            # Multi-provider mode
            # If provider_map is specified but providers is not, extract providers from map
            if provider_map and not providers:
                mapping = _parse_provider_map(provider_map)
                providers = ",".join(set(mapping.values()))
            
            await _run_multi_provider(
                source, output, include_tag, exclude_tag, include_path,
                include_method, exclude_method,
                workers, force, dry_run, organize_by, verbose, quiet,
                providers, provider_map, strategy
            )
            
    except ConfigError as e:
        error_msg = str(e)
        console.print(f"\n[red]❌ Configuration Error: {error_msg}[/red]")
        
        # Check if it's an API key error and provide better guidance
        if "API key not configured" in error_msg:
            # Extract provider name from error message
            import re
            match = re.search(r'for (\w+)', error_msg)
            provider_name = match.group(1) if match else provider or 'unknown'
            
            env_file = Path.cwd() / ".env"
            if not env_file.exists():
                console.print("\n[yellow]💡 Tips:[/yellow]")
                console.print("1. No .env file found in current directory")
                console.print(f"   Current directory: [cyan]{Path.cwd()}[/cyan]")
                console.print("\n2. Please switch to project directory with .env file, or:")
                console.print("   - Copy configuration template: [cyan]cp /path/to/.env.example .env[/cyan]")
                console.print("   - Edit .env file and add your API key")
                console.print("\n3. Or set environment variable:")
                console.print(f"   [cyan]export CASECRAFT_{provider_name.upper()}_API_KEY=your-api-key[/cyan]")
            else:
                console.print("\n[yellow]💡 .env file exists but missing configuration:[/yellow]")
                console.print(f"Please edit .env file and add: [cyan]CASECRAFT_{provider_name.upper()}_API_KEY=your-api-key[/cyan]")
        else:
            _show_provider_config_help()
        
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


async def _run_single_provider(
    source: str,
    output: str,
    include_tag: tuple,
    exclude_tag: tuple,
    include_path: tuple,
    include_method: Optional[list],
    exclude_method: Optional[list],
    workers: int,
    force: bool,
    dry_run: bool,
    organize_by: Optional[str],
    verbose: bool,
    quiet: bool,
    provider: str,
    model: Optional[str] = None,
    format: str = "json",
    config: Optional[str] = None,
    merge_excel: bool = False,
    priority: str = "all",
    save_prompts: bool = False,
    prompts_dir: str = "prompts",
    prompt_format: str = "txt",
    save_responses: bool = False,
    lang: Optional[str] = None,
    auto_detect: bool = True
) -> None:
    """Run generation with a single provider - unified handling for all providers."""
    
    # 1. Initialize configuration manager (auto-loads .env)
    config_manager = ConfigManager(load_env=True)
    
    # 2. Import ProviderConfig first
    from casecraft.models.provider_config import ProviderConfig
    from casecraft.core.providers.registry import ProviderRegistry
    
    # 3. Get provider configuration
    try:
        provider_config = config_manager.get_provider_config(provider, workers=workers)
        
        # Override model if specified via CLI
        if model:
            # Create a new config with the updated model
            config_dict = provider_config.model_dump()
            config_dict['model'] = model
            provider_config = ProviderConfig(**config_dict)
            
    except ConfigError as e:
        error_msg = str(e)
        console.print(f"\n[red]❌ Configuration Error: {error_msg}[/red]")
        
        # Check if it's an API key error
        if "API key not configured" in error_msg:
            # Extract provider name from error message
            import re
            match = re.search(r'for (\w+)', error_msg)
            provider_name = match.group(1) if match else provider
            
            env_file = Path.cwd() / ".env"
            if not env_file.exists():
                console.print("\n[yellow]💡 Tips:[/yellow]")
                console.print("1. No .env file found in current directory")
                console.print(f"   Current directory: [cyan]{Path.cwd()}[/cyan]")
                console.print("\n2. Please switch to project directory with .env file, or:")
                console.print("   - Copy configuration template: [cyan]cp /path/to/.env.example .env[/cyan]")
                console.print("   - Edit .env file and add your API key")
                console.print("\n3. Or set environment variable:")
                console.print(f"   [cyan]export CASECRAFT_{provider_name.upper()}_API_KEY=your-api-key[/cyan]")
            else:
                console.print("\n[yellow]💡 .env file exists but missing configuration:[/yellow]")
                console.print(f"Please edit .env file and add: [cyan]CASECRAFT_{provider_name.upper()}_API_KEY=your-api-key[/cyan]")
        
        raise click.ClickException(str(e))
    
    # 4. Register provider class to Registry
    _register_provider(provider)
    
    # 5. Get provider instance
    try:
        provider_instance = ProviderRegistry.get_provider(provider, provider_config)
    except Exception as e:
        console.print(f"[red]Provider Error:[/red] Failed to initialize {provider}: {e}")
        raise click.ClickException(str(e))
    
    # 5.5. Validate worker count against provider's max_workers limit
    max_workers = provider_instance.get_max_workers()
    if workers > max_workers:
        console.print(f"[yellow]⚠️  友好提示：[/yellow]")
        console.print(f"[yellow]   {provider.upper()} 提供商最大支持 {max_workers} 个并发工作进程[/yellow]")
        console.print(f"[yellow]   当前设置: --workers {workers}[/yellow]")
        console.print(f"[yellow]   请使用: --workers {max_workers} 或更少[/yellow]")
        raise click.ClickException(f"{provider.upper()} 最大并发数为 {max_workers}")
    
    # 6. Create base configuration (for Engine's other components)
    base_config = config_manager.create_default_config()
    
    # Apply CLI parameter overrides
    base_config.output.directory = output
    base_config.processing.workers = workers
    base_config.processing.force_regenerate = force
    base_config.processing.dry_run = dry_run
    if organize_by:
        base_config.output.organize_by_tag = (organize_by == "tag")
    
    # Add prompt configuration if enabled
    if save_prompts:
        base_config.prompt = PromptConfig(
            save_prompts=save_prompts,
            prompts_dir=prompts_dir,
            prompt_format=prompt_format,
            save_responses=save_responses
        )
    
    # 7. Show configuration
    if not quiet:
        _show_provider_config(provider, provider_config, verbose)
    
    # 8. Initialize state manager
    state_manager = EnhancedStateManager()
    
    # 9. Create engine with provider instance
    engine = GeneratorEngine(
        base_config, 
        console, 
        verbose=verbose, 
        quiet=quiet,
        provider_instance=provider_instance,
        config_path=config
    )
    
    # 10. Convert parameter formats
    include_tags = list(include_tag) if include_tag else None
    exclude_tags = list(exclude_tag) if exclude_tag else None
    include_paths = list(include_path) if include_path else None
    
    # 11. Load state (if not dry run)
    if not dry_run:
        await state_manager.load_state()
    
    # 11.5 Pre-check endpoints count and validate workers
    # First do a quick parse to count endpoints
    from casecraft.core.parsing.api_parser import APIParser
    api_parse_timeout = int(os.getenv("CASECRAFT_API_PARSE_TIMEOUT", str(DEFAULT_API_PARSE_TIMEOUT)))
    api_parser = APIParser(timeout=api_parse_timeout)
    api_spec = await api_parser.parse_from_source(source)
    
    # Apply filters to get actual endpoint count
    if include_tags or exclude_tags or include_paths:
        api_spec = api_parser.filter_endpoints(
            api_spec, 
            list(include_tag) if include_tag else None,
            list(exclude_tag) if exclude_tag else None, 
            list(include_path) if include_path else None,
            None
        )
    
    # Check if only 1 endpoint and workers > 1
    if len(api_spec.endpoints) == 1 and workers > 1:
        console.print(f"[yellow]⚠️  友好提示：[/yellow]")
        console.print(f"[yellow]   当只处理单个端点时，workers 必须设置为 1[/yellow]")
        console.print(f"[yellow]   当前设置: --workers {workers}[/yellow]")
        console.print(f"[yellow]   请使用: --workers 1[/yellow]")
        raise click.ClickException("单个端点只能使用 --workers 1")
    
    # 12. Execute generation
    result = await engine.generate(
        source=source,
        include_tags=include_tags,
        exclude_tags=exclude_tags,
        include_paths=include_paths,
        include_methods=include_method,
        exclude_methods=exclude_method,
        force=force,
        dry_run=dry_run,
        format=format,
        priority=priority,
        merge_excel=merge_excel,
        lang=lang,
        auto_detect=auto_detect
    )
    
    # 13. Update statistics
    if not dry_run:
        await state_manager.update_statistics(
            total_endpoints=result.total_endpoints,
            generated_count=result.generated_count,
            skipped_count=result.skipped_count,
            failed_count=result.failed_count
        )
        
        # Update provider-specific statistics if we have token usage
        if result.has_token_usage():
            token_summary = result.get_token_summary()
            total_tokens = token_summary.get('total_tokens', 0)
            
            if result.generated_count > 0:
                state_manager.complete_provider_request(
                    provider=provider,
                    endpoint_id="batch",
                    success=True,
                    tokens=total_tokens
                )
        
        # Save state
        state = await state_manager.load_state()
        await state_manager.save_state(state)
    
    # 14. Show results
    if not quiet:
        _show_results_with_provider_stats(result, state_manager, dry_run)


async def _run_multi_provider(
    source: str,
    output: str,
    include_tag: tuple,
    exclude_tag: tuple,
    include_path: tuple,
    include_method: Optional[list],
    exclude_method: Optional[list],
    workers: int,
    force: bool,
    dry_run: bool,
    organize_by: Optional[str],
    verbose: bool,
    quiet: bool,
    providers: Optional[str],
    provider_map: Optional[str],
    strategy: str
) -> None:
    """Run generation with multiple providers."""
    
    # Parse provider configuration
    provider_list = providers.split(",") if providers else []
    mapping = _parse_provider_map(provider_map) if provider_map else None
    
    # Load multi-provider configuration
    multi_config = await _load_multi_provider_config(
        provider_list, mapping, strategy, output, workers, force, dry_run, organize_by, verbose
    )
    
    # Register all providers
    for provider_name in multi_config.get_active_providers():
        _register_provider(provider_name)
    
    # Show configuration
    if not quiet:
        _show_multi_provider_config(multi_config, verbose)
    
    # Initialize state manager early if not dry run
    state_manager = None
    if not dry_run:
        state_manager = EnhancedStateManager()
        await state_manager.load_state()
    
    # Initialize multi-provider engine with state manager
    engine = MultiProviderEngine(multi_config, output_dir=output, state_manager=state_manager)
    
    # Load and parse API specification
    from casecraft.core.parsing.api_parser import APIParser
    parser = APIParser()
    api_spec = await parser.parse_from_source(source)
    
    # Filter endpoints
    include_tags = list(include_tag) if include_tag else None
    exclude_tags = list(exclude_tag) if exclude_tag else None
    include_paths = list(include_path) if include_path else None
    
    filtered_endpoints = _filter_endpoints(
        api_spec.endpoints,
        include_tags,
        exclude_tags,
        include_paths,
        include_method,
        exclude_method
    )
    
    # Perform health checks
    if not dry_run and not quiet:
        console.print("\n[blue]🏥 Performing provider health checks...[/blue]")
        health_status = await engine.health_check_all()
        for provider_name, is_healthy in health_status.items():
            status = "[green]✓[/green]" if is_healthy else "[red]✗[/red]"
            console.print(f"  {status} {provider_name}")
    
    # Generate with providers
    if not dry_run:
        # Generate
        result = await engine.generate_with_providers(
            filtered_endpoints,
            _parse_provider_map(provider_map) if provider_map else None
        )
        
        # Update state manager with generation results
        await _update_multi_provider_stats(state_manager, result, filtered_endpoints)
        
        # Save state
        state = await state_manager.load_state()
        await state_manager.save_state(state)
        
        # Show results with statistics
        if not quiet:
            _show_multi_provider_results(result, state_manager)
    else:
        # Dry run
        if not quiet:
            console.print(f"\n[yellow]🔍 Preview: Would generate {len(filtered_endpoints)} endpoints using {len(multi_config.get_active_providers())} providers[/yellow]")


def _register_provider(provider_name: str) -> None:
    """Register a provider with the registry."""
    provider_lower = provider_name.lower()
    
    if provider_lower == "glm":
        from casecraft.core.providers.glm_provider import GLMProvider
        ProviderRegistry.register("glm", GLMProvider)
    elif provider_lower == "qwen":
        from casecraft.core.providers.qwen_provider import QwenProvider
        ProviderRegistry.register("qwen", QwenProvider)
    elif provider_lower == "local":
        from casecraft.core.providers.local_provider import LocalProvider
        ProviderRegistry.register("local", LocalProvider)
    elif provider_lower == "deepseek":
        from casecraft.core.providers.deepseek_provider import DeepSeekProvider
        ProviderRegistry.register("deepseek", DeepSeekProvider)


def _parse_provider_map(mapping_str: str) -> Dict[str, str]:
    """Parse provider mapping string."""
    if not mapping_str:
        return {}
    
    mapping = {}
    for item in mapping_str.split(","):
        if ":" in item:
            path, provider = item.split(":", 1)
            mapping[path.strip()] = provider.strip()
    
    return mapping


def _path_matches(endpoint_path: str, pattern: str) -> bool:
    """Smart path matching that handles trailing slash differences.
    
    Args:
        endpoint_path: The endpoint path from API spec
        pattern: The pattern to match against
        
    Returns:
        True if paths match (considering trailing slash flexibility)
    """
    import fnmatch
    
    # Normalize paths by removing trailing slashes for comparison
    def normalize_path(path: str) -> str:
        return path.rstrip('/')
    
    endpoint_normalized = normalize_path(endpoint_path)
    pattern_normalized = normalize_path(pattern)
    
    # Try exact match first (normalized)
    if endpoint_normalized == pattern_normalized:
        return True
    
    # Try fnmatch with both original and normalized versions
    if fnmatch.fnmatch(endpoint_path, pattern):
        return True
    
    if fnmatch.fnmatch(endpoint_normalized, pattern_normalized):
        return True
    
    # Try substring matching (for backward compatibility)
    if pattern in endpoint_path or pattern_normalized in endpoint_normalized:
        return True
    
    return False


def _filter_endpoints(endpoints, include_tags, exclude_tags, include_paths, include_methods=None, exclude_methods=None):
    """Filter endpoints based on criteria."""
    filtered = endpoints
    
    # Filter by HTTP methods
    if include_methods:
        filtered = [e for e in filtered if e.method.upper() in [m.upper() if isinstance(m, str) else m for m in include_methods]]
    
    if exclude_methods:
        filtered = [e for e in filtered if e.method.upper() not in [m.upper() if isinstance(m, str) else m for m in exclude_methods]]
    
    # Filter by tags
    if include_tags:
        filtered = [e for e in filtered if any(tag in e.tags for tag in include_tags)]
    
    if exclude_tags:
        filtered = [e for e in filtered if not any(tag in e.tags for tag in exclude_tags)]
    
    # Filter by paths
    if include_paths:
        filtered = [e for e in filtered if any(_path_matches(e.path, pattern) for pattern in include_paths)]
    
    return filtered


async def _load_single_provider_config(
    provider: str,
    output: str,
    workers: int,
    force: bool,
    dry_run: bool,
    organize_by: Optional[str],
    verbose: bool,
    model: Optional[str] = None
) -> CaseCraftConfig:
    """Load configuration for single provider mode."""
    config_manager = MultiProviderConfigManager()
    
    # Get base configuration
    base_config = config_manager.create_default_config()
    
    # Apply overrides for the specific provider
    provider_upper = provider.upper()
    
    # Use --model parameter if provided, otherwise use environment variable
    if model:
        base_config.llm.model = model
    else:
        base_config.llm.model = os.getenv(f"CASECRAFT_{provider_upper}_MODEL", f"{provider}-model")
    
    base_config.llm.api_key = os.getenv(f"CASECRAFT_{provider_upper}_API_KEY")
    base_config.llm.base_url = os.getenv(f"CASECRAFT_{provider_upper}_BASE_URL")
    
    # Apply CLI overrides
    if output != "test_cases":
        base_config.output.directory = output
    # Workers is always from CLI (required argument)
    base_config.processing.workers = workers
    base_config.processing.force_regenerate = force
    base_config.processing.dry_run = dry_run
    if organize_by:
        base_config.output.organize_by_tag = (organize_by == "tag")
    
    return base_config


async def _load_multi_provider_config(
    providers: List[str],
    mapping: Optional[Dict[str, str]],
    strategy: str,
    output: str,
    workers: int,
    force: bool,
    dry_run: bool,
    organize_by: Optional[str],
    verbose: bool
) -> MultiProviderConfig:
    """Load multi-provider configuration."""
    config_manager = MultiProviderConfigManager()
    
    # Get multi-provider config from environment
    multi_config = config_manager.get_multi_provider_config()
    
    # Override with CLI parameters
    if providers:
        multi_config.providers = providers
    
    multi_config.strategy = strategy
    
    # Add provider configs
    for provider_name in providers:
        if provider_name not in multi_config.configs:
            # Create config from environment
            provider_upper = provider_name.upper()
            provider_config = ProviderConfig(
                name=provider_name,
                model=os.getenv(f"CASECRAFT_{provider_upper}_MODEL", f"{provider_name}-model"),
                api_key=os.getenv(f"CASECRAFT_{provider_upper}_API_KEY"),
                base_url=os.getenv(f"CASECRAFT_{provider_upper}_BASE_URL"),
                workers=workers
            )
            multi_config.configs[provider_name] = provider_config
    
    return multi_config


def _show_provider_config(provider: str, config: ProviderConfig, verbose: bool) -> None:
    """Show provider configuration - unified format."""
    console.print(f"\n[bold blue]━━━━━━ 🚀 Generation Config ━━━━━━[/bold blue]")
    
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column(width=2, justify="left")   # emoji column
    table.add_column(width=12, justify="left")  # label column
    table.add_column(justify="left")            # value column
    
    # Basic information
    table.add_row("🤖", "Provider:", f"[cyan bold]{provider.upper()}[/cyan bold]")
    table.add_row("📦", "Model:", f"[cyan]{config.model}[/cyan]")
    table.add_row("🌐", "Base URL:", f"[dim]{config.base_url}[/dim]")
    
    # Feature configuration
    stream_color = "green" if config.stream else "dim"
    table.add_row("📡", "Stream:", f"[{stream_color}]{config.stream}[/{stream_color}]")
    table.add_row("⚡", "Workers:", f"[yellow]{config.workers}[/yellow]")
    
    # Show max tokens configuration (from provider config)
    table.add_row("📝", "Max Tokens:", f"[cyan]{config.max_tokens}[/cyan]")
    
    if verbose:
        # Detailed parameters
        table.add_row("🔥", "Temperature:", f"[yellow]{config.temperature:.1f}[/yellow]")
        table.add_row("⏰", "Timeout:", f"[blue]{config.timeout}s[/blue]")
        table.add_row("🔄", "Max Retries:", f"[blue]{config.max_retries}[/blue]")
    
    console.print(table)
    console.print("[dim]──────────────────────────────────[/dim]\n")


def _show_multi_provider_config(config: MultiProviderConfig, verbose: bool) -> None:
    """Show multi-provider configuration."""
    console.print(f"\n[bold blue]━━━━━━ 🚀 Multi-Provider Config ━━━━━━[/bold blue]")
    
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column(width=2, justify="left")
    table.add_column(width=12, justify="left")
    table.add_column(justify="left")
    
    providers_str = ", ".join(config.get_active_providers())
    table.add_row("🤖", "Providers:", f"[cyan bold]{providers_str}[/cyan bold]")
    table.add_row("🎯", "Strategy:", f"[yellow]{config.strategy}[/yellow]")
    table.add_row("🔄", "Fallback:", f"[{'green' if config.fallback_enabled else 'dim'}]{config.fallback_enabled}[/]")
    
    if verbose:
        for provider_name, provider_config in config.configs.items():
            table.add_row("", f"{provider_name}:", f"{provider_config.model} (workers: {provider_config.workers})")
    
    console.print(table)
    console.print("[dim]──────────────────────────────────[/dim]\n")


def _show_results_with_provider_stats(result: GenerationResult, state_manager: EnhancedStateManager, dry_run: bool) -> None:
    """Show results with provider statistics."""
    # Show standard results
    _show_results(result, dry_run)
    
    # Show provider statistics
    if not dry_run:
        state_manager.print_statistics_report(console)


def _show_multi_provider_results(result, state_manager: EnhancedStateManager) -> None:
    """Show multi-provider generation results."""
    console.print("\n[bold green]━━━━━━ ✨ Multi-Provider Generation Complete ━━━━━━[/bold green]")
    
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column(width=2, justify="left")
    table.add_column(width=20, justify="left")  # 与其他表格对齐
    table.add_column(justify="left")
    
    table.add_row("✅", "Successful:", f"[green bold]{len(result.successful_endpoints)}[/green bold]")
    table.add_row("📋", "Test Cases:", f"[cyan bold]{result.total_test_cases}[/cyan bold]")
    table.add_row("❌", "Failed:", f"[red]{len(result.failed_endpoints)}[/red]")
    table.add_row("📊", "Total Tokens:", f"[yellow]{result.total_tokens}[/yellow]")
    
    console.print(table)
    
    # Show provider usage
    if result.provider_usage:
        console.print("\n[blue]Provider Usage:[/blue]")
        for provider, count in result.provider_usage.items():
            console.print(f"  • {provider}: {count} endpoints")
    
    # Show statistics report
    state_manager.print_statistics_report(console)


async def _update_multi_provider_stats(
    state_manager: EnhancedStateManager,
    result,
    filtered_endpoints
) -> None:
    """Update state manager with multi-provider generation results.
    
    Args:
        state_manager: Enhanced state manager
        result: Generation result from multi-provider engine
        filtered_endpoints: List of filtered endpoints that were processed
    """
    # Create a mapping of endpoint IDs to endpoint objects
    endpoint_map = {ep.get_endpoint_id(): ep for ep in filtered_endpoints}
    
    # Update state for each successfully generated endpoint
    for endpoint_id in result.successful_endpoints:
        if endpoint_id in endpoint_map:
            endpoint = endpoint_map[endpoint_id]
            
            # Get the provider that was used (from result.provider_usage tracking)
            provider_used = None
            for provider_name in result.provider_usage:
                provider_used = provider_name
                break  # We'll use the first provider found for simplicity
            
            # Estimate tokens per endpoint (divide total by number of successful)
            tokens_per_endpoint = result.total_tokens // len(result.successful_endpoints) if result.successful_endpoints else 0
            
            # Mark endpoint as generated
            await state_manager.mark_endpoint_generated(
                endpoint=endpoint,
                test_cases_count=5,  # Default estimate, actual count would need to be tracked
                output_file=None,  # File path already tracked in result.generated_files
                provider_used=provider_used,
                tokens_used=tokens_per_endpoint
            )
            
            # Update provider request statistics
            if provider_used:
                state_manager.complete_provider_request(
                    provider=provider_used,
                    endpoint_id=endpoint_id,
                    success=True,
                    tokens=tokens_per_endpoint
                )
    
    # Update state for failed endpoints
    for endpoint_id in result.failed_endpoints:
        if endpoint_id in endpoint_map:
            # Track failure in provider stats
            for provider_name in result.provider_usage:
                state_manager.complete_provider_request(
                    provider=provider_name,
                    endpoint_id=endpoint_id,
                    success=False,
                    error_type="generation_failed"
                )
                break
    
    # Update overall statistics
    total_endpoints = len(result.successful_endpoints) + len(result.failed_endpoints)
    await state_manager.update_statistics(
        total_endpoints=total_endpoints,
        generated_count=len(result.successful_endpoints),
        skipped_count=0,  # Multi-provider doesn't track skipped separately
        failed_count=len(result.failed_endpoints)
    )


def _show_provider_config_help() -> None:
    """Show provider configuration help."""
    help_text = """
You must specify an LLM provider. Options:

1. Single provider:
   [cyan]casecraft generate api.json --provider glm[/cyan]

2. Multiple providers:
   [cyan]casecraft generate api.json --providers glm,qwen[/cyan]

3. Manual mapping:
   [cyan]casecraft generate api.json --provider-map "/users:qwen,/products:glm"[/cyan]

4. Set via environment:
   [cyan]export CASECRAFT_PROVIDER=glm[/cyan]
   [cyan]export CASECRAFT_PROVIDERS=glm,qwen[/cyan]
"""
    
    console.print(Panel(
        help_text.strip(),
        title="Provider Configuration Required",
        border_style="yellow"
    ))


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