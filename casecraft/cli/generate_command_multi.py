"""Enhanced generate command with multi-provider support."""

import asyncio
import os
from typing import List, Optional, Dict

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from casecraft.core.management.config_manager import ConfigError
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
    strategy: str = "round_robin"
) -> None:
    """Generate test cases with multi-provider support.
    
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
        quiet: Quiet mode
        provider: Single provider name
        providers: Comma-separated provider list
        provider_map: Manual provider mapping
        strategy: Provider assignment strategy
    """
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
                workers, force, dry_run, organize_by, verbose, quiet, provider
            )
        else:
            # Multi-provider mode
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
    provider: str
) -> None:
    """Run generation with a single provider."""
    
    # Load configuration for single provider
    config = await _load_single_provider_config(provider, output, workers, force, dry_run, organize_by, verbose)
    
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
    if not dry_run and result.has_token_usage():
        for endpoint_id in result.generated_files:
            state_manager.complete_provider_request(
                provider=provider,
                endpoint_id=endpoint_id,
                success=True,
                tokens=100  # Estimate, would need actual usage
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
    
    # Initialize multi-provider engine
    engine = MultiProviderEngine(multi_config)
    
    # Load and parse API specification
    from casecraft.core.parsing.api_parser import APIParser
    parser = APIParser()
    api_spec = await parser.parse(source)
    
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
        # Use enhanced state manager
        state_manager = EnhancedStateManager()
        await state_manager.load_state()
        
        # Generate
        result = await engine.generate_with_providers(
            filtered_endpoints,
            _parse_provider_map(provider_map) if provider_map else None
        )
        
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
    verbose: bool
) -> CaseCraftConfig:
    """Load configuration for single provider mode."""
    config_manager = MultiProviderConfigManager()
    
    # Get base configuration
    base_config = config_manager.create_default_config()
    
    # Apply overrides for the specific provider
    provider_upper = provider.upper()
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
    console.print(f"\n[bold blue]━━━━━━ 🚀 {provider.upper()} Provider Config ━━━━━━[/bold blue]")
    
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column(width=2, justify="left")
    table.add_column(width=12, justify="left")
    table.add_column(justify="left")
    
    table.add_row("🤖", "Provider:", f"[cyan bold]{provider}[/cyan bold]")
    table.add_row("📦", "Model:", f"[cyan]{config.llm.model}[/cyan]")
    table.add_row("🌐", "Base URL:", f"[dim]{config.llm.base_url}[/dim]")
    table.add_row("⚡", "Workers:", f"[yellow]{config.processing.workers}[/yellow]")
    
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
    from casecraft.cli.generate_command import _show_results
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
    import os
    
    try:
        asyncio.run(generate_command(*args, **kwargs))
    except RuntimeError as e:
        if "asyncio.run() cannot be called from a running event loop" in str(e):
            loop = asyncio.get_event_loop()
            task = loop.create_task(generate_command(*args, **kwargs))
            loop.run_until_complete(task)
        else:
            raise