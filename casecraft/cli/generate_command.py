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
from casecraft.models.config import CaseCraftConfig
from casecraft.models.provider_config import MultiProviderConfig, ProviderConfig
from casecraft.core.providers.registry import ProviderRegistry


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
    verbose: bool,
    quiet: bool = False,
    provider: Optional[str] = None,
    providers: Optional[str] = None,
    provider_map: Optional[str] = None,
    strategy: str = "round_robin",
    model: Optional[str] = None
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
        quiet: Quiet mode (warnings/errors only)
        provider: Single provider name
        providers: Comma-separated provider list
        provider_map: Manual provider mapping
        strategy: Provider assignment strategy
    """
    # Check if multi-provider support is requested
    if provider or providers or provider_map or os.getenv("CASECRAFT_PROVIDER") or os.getenv("CASECRAFT_PROVIDERS"):
        # Use multi-provider implementation
        return await _generate_with_providers(
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
            provider=provider or os.getenv("CASECRAFT_PROVIDER"),
            providers=providers or os.getenv("CASECRAFT_PROVIDERS"),
            provider_map=provider_map,
            strategy=strategy,
            model=model
        )
    
    # Legacy single-provider mode (backward compatibility)
    try:
        # Load configuration
        config = await _load_configuration(
            output, workers, force, dry_run, organize_by, verbose
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
        
        # Generate test cases
        result = await engine.generate(
            source=source,
            include_tags=include_tags,
            exclude_tags=exclude_tags,
            include_paths=include_paths,
            force=force,
            dry_run=dry_run
        )
        
        # Show results (unless in quiet mode)
        if not quiet:
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
    console.print("[dim]────────────────────────────[/dim]\n")


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
    table.add_column(width=18, justify="left")  # Label column
    table.add_column(justify="left")            # Value column
    
    table.add_row("📁", "Found Endpoints:", f"[bold]{result.total_endpoints}[/bold]")
    table.add_row("✅", "Will Generate:", f"[green]{len(result.api_spec.endpoints) - result.skipped_count}[/green]")
    table.add_row("⏭️", "Will Skip:", f"[dim]{result.skipped_count}[/dim] (unchanged)")
    
    console.print(table)
    
    if result.api_spec and result.api_spec.endpoints:
        console.print(f"\n[yellow]💡 Tip: Remove --dry-run to start actual generation[/yellow]")
    console.print("[dim]────────────────────────────[/dim]")


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
    
    # Add retry statistics if available
    if summary.get('total_retries', 0) > 0:
        token_table.add_row("", "", "")  # Empty separator row
        token_table.add_row("🔄", "Total Retries:", f"[yellow]{summary['total_retries']}[/yellow]")
        token_table.add_row("📍", "Endpoints w/ Retries:", f"{summary['endpoints_with_retries']}")
        token_table.add_row("📈", "Max Retries (Single):", f"{summary['max_retries_for_single_endpoint']}")
        
        if summary['endpoints_with_retries'] > 0:
            avg_retries = summary['average_retries_per_endpoint']
            token_table.add_row("⚖️", "Avg Retries/Endpoint:", f"{avg_retries:.1f}")
    
    console.print(token_table)
    console.print("[dim]────────────────────────────[/dim]")


def _show_generation_results(result: GenerationResult) -> None:
    """Show generation results.
    
    Args:
        result: Generation result
    """
    console.print("\n[bold green]━━━━━━ ✨ Generation Complete ━━━━━━[/bold green]")
    
    # Create 3-column summary table for proper alignment
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column(width=2, justify="left")   # Emoji column
    table.add_column(width=18, justify="left")  # Label column
    table.add_column(justify="left")            # Value column
    
    table.add_row("📁", "Total Endpoints:", f"[bold]{result.total_endpoints}[/bold]")
    table.add_row("✅", "Generated:", f"[green bold]{result.generated_count}[/green bold]")
    table.add_row("⏸️ ", "Skipped:", f"[dim]{result.skipped_count}[/dim]")
    
    if result.failed_count > 0:
        table.add_row("❌", "Failed:", f"[red]{result.failed_count}[/red]")
    
    # Format duration
    table.add_row("⏱️", "Duration:", f"{result.duration:.1f}s")
    
    # Add retry summary if there were retries
    if result.has_token_usage():
        summary = result.get_token_summary()
        if summary.get('total_retries', 0) > 0:
            table.add_row("🔄", "Total Retries:", f"[yellow]{summary['total_retries']}[/yellow]")
    
    console.print(table)
    
    # Show token usage and cost statistics if available
    if result.has_token_usage():
        _show_token_statistics(result)
    
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


async def _generate_with_providers(
    source: str,
    output: str,
    include_tag: tuple,
    exclude_tag: tuple,
    include_path: tuple,
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
    model: Optional[str] = None
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
                workers, force, dry_run, organize_by, verbose, quiet, provider, model
            )
        else:
            # Multi-provider mode
            # If provider_map is specified but providers is not, extract providers from map
            if provider_map and not providers:
                mapping = _parse_provider_map(provider_map)
                providers = ",".join(set(mapping.values()))
            
            await _run_multi_provider(
                source, output, include_tag, exclude_tag, include_path,
                workers, force, dry_run, organize_by, verbose, quiet,
                providers, provider_map, strategy
            )
            
    except ConfigError as e:
        console.print(f"[red]Configuration Error:[/red] {e}")
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
    workers: int,
    force: bool,
    dry_run: bool,
    organize_by: Optional[str],
    verbose: bool,
    quiet: bool,
    provider: str,
    model: Optional[str] = None
) -> None:
    """Run generation with a single provider."""
    
    # Load configuration for single provider
    config = await _load_single_provider_config(provider, output, workers, force, dry_run, organize_by, verbose, model)
    
    # Register the provider
    _register_provider(provider)
    
    # Show configuration
    if not quiet:
        _show_single_provider_config(provider, config, verbose)
    
    # Use enhanced state manager
    state_manager = EnhancedStateManager()
    
    # Initialize engine
    engine = GeneratorEngine(config, console, verbose=verbose, quiet=quiet)
    
    # Convert tuples to lists
    include_tags = list(include_tag) if include_tag else None
    exclude_tags = list(exclude_tag) if exclude_tag else None
    include_paths = list(include_path) if include_path else None
    
    # Track start
    if not dry_run:
        await state_manager.load_state()
    
    # Generate test cases
    result = await engine.generate(
        source=source,
        include_tags=include_tags,
        exclude_tags=exclude_tags,
        include_paths=include_paths,
        force=force,
        dry_run=dry_run
    )
    
    # Update statistics
    if not dry_run:
        # Update overall statistics first
        await state_manager.update_statistics(
            total_endpoints=result.total_endpoints,
            generated_count=result.generated_count,
            skipped_count=result.skipped_count,
            failed_count=result.failed_count
        )
        
        # Update provider-specific statistics if we have token usage
        if result.has_token_usage():
            # Get actual token usage from result
            token_summary = result.get_token_summary()
            total_tokens = token_summary.get('total_tokens', 0)
            
            # Update provider stats for successful generation
            if result.generated_count > 0:
                state_manager.complete_provider_request(
                    provider=provider,
                    endpoint_id="batch",  # Use a generic ID for batch operations
                    success=True,
                    tokens=total_tokens
                )
        
        # Save state
        state = await state_manager.load_state()
        await state_manager.save_state(state)
    
    # Show results
    if not quiet:
        _show_results_with_provider_stats(result, state_manager, dry_run)


async def _run_multi_provider(
    source: str,
    output: str,
    include_tag: tuple,
    exclude_tag: tuple,
    include_path: tuple,
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
        include_paths
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
    elif provider_lower == "kimi":
        from casecraft.core.providers.kimi_provider import KimiProvider
        ProviderRegistry.register("kimi", KimiProvider)
    elif provider_lower == "local":
        from casecraft.core.providers.local_provider import LocalProvider
        ProviderRegistry.register("local", LocalProvider)


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


def _filter_endpoints(endpoints, include_tags, exclude_tags, include_paths):
    """Filter endpoints based on criteria."""
    filtered = endpoints
    
    if include_tags:
        filtered = [e for e in filtered if any(tag in e.tags for tag in include_tags)]
    
    if exclude_tags:
        filtered = [e for e in filtered if not any(tag in e.tags for tag in exclude_tags)]
    
    if include_paths:
        filtered = [e for e in filtered if any(pattern in e.path for pattern in include_paths)]
    
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
    if workers != 1:
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


def _show_single_provider_config(provider: str, config: CaseCraftConfig, verbose: bool) -> None:
    """Show single provider configuration."""
    console.print(f"\n[bold blue]━━━━━━ 🚀 LLM Provider Config ━━━━━━[/bold blue]")
    
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column(width=2, justify="left")   # emoji 列
    table.add_column(width=14, justify="left")  # 标签列（从 12 改为 14）
    table.add_column(justify="left")            # 值列
    
    # 基本信息
    table.add_row("🤖", "Provider:", f"[cyan bold]{provider}[/cyan bold]")
    table.add_row("📦", "Model:", f"[cyan]{config.llm.model}[/cyan]")
    table.add_row("🌐", "Base URL:", f"[dim]{config.llm.base_url}[/dim]")
    
    # 功能配置
    table.add_row("🧠", "Think:", f"[{'green' if config.llm.think else 'dim'}]{config.llm.think}[/]")
    table.add_row("📡", "Stream:", f"[{'green' if config.llm.stream else 'dim'}]{config.llm.stream}[/]")
    
    # 性能参数 - 使用单字符 emoji 避免对齐问题
    table.add_row("🔥", "Temperature:", f"[yellow]{config.llm.temperature:.1f}[/yellow]")
    table.add_row("⚡", "Workers:", f"[yellow]{config.processing.workers}[/yellow]")
    table.add_row("⏰", "Timeout:", f"[blue]{config.llm.timeout}s[/blue]")
    table.add_row("🔄", "Max Retries:", f"[blue]{config.llm.max_retries}[/blue]")
    
    console.print(table)
    console.print("[dim]────────────────────────────[/dim]\n")


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
    console.print("[dim]────────────────────────────[/dim]\n")


def _show_results_with_provider_stats(result: GenerationResult, state_manager: EnhancedStateManager, dry_run: bool) -> None:
    """Show results with provider statistics."""
    # Show standard results
    _show_results(result, dry_run)
    
    # Show provider statistics
    if not dry_run:
        state_manager.print_statistics_report()


def _show_multi_provider_results(result, state_manager: EnhancedStateManager) -> None:
    """Show multi-provider generation results."""
    console.print("\n[bold green]━━━━━━ ✨ Multi-Provider Generation Complete ━━━━━━[/bold green]")
    
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column(width=2, justify="left")
    table.add_column(width=18, justify="left")
    table.add_column(justify="left")
    
    table.add_row("✅", "Successful:", f"[green bold]{len(result.successful_endpoints)}[/green bold]")
    table.add_row("❌", "Failed:", f"[red]{len(result.failed_endpoints)}[/red]")
    table.add_row("📊", "Total Tokens:", f"[yellow]{result.total_tokens}[/yellow]")
    
    console.print(table)
    
    # Show provider usage
    if result.provider_usage:
        console.print("\n[blue]Provider Usage:[/blue]")
        for provider, count in result.provider_usage.items():
            console.print(f"  • {provider}: {count} endpoints")
    
    # Show statistics report
    state_manager.print_statistics_report()


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
   [cyan]casecraft generate api.json --providers glm,qwen,kimi[/cyan]

3. Manual mapping:
   [cyan]casecraft generate api.json --provider-map "/users:qwen,/products:glm"[/cyan]

4. Set via environment:
   [cyan]export CASECRAFT_PROVIDER=glm[/cyan]
   [cyan]export CASECRAFT_PROVIDERS=glm,qwen,kimi[/cyan]
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