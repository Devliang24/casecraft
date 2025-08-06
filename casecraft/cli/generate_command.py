"""Implementation of the generate command."""

import asyncio
import sys
from pathlib import Path
from typing import List, Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from casecraft.core.management.config_manager import ConfigManager, ConfigError
from casecraft.core.engine import GeneratorEngine, GeneratorError, GenerationResult
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
        
        # Show model configuration
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


def _show_model_config(config: CaseCraftConfig, verbose: bool) -> None:
    """Show model configuration information.
    
    Args:
        config: CaseCraft configuration
        verbose: Whether to show verbose information
    """
    # Create configuration table
    table = Table(show_header=False, box=None, padding=(0, 2))
    
    # Format model name in a friendly way
    model_display = config.llm.model.upper().replace("-X", "").replace("GLM-", "GLM ")
    table.add_row("🤖 使用模型:", f"[cyan bold]{model_display}[/cyan bold]")
    
    # Format API endpoint to show only domain
    from urllib.parse import urlparse
    parsed_url = urlparse(config.llm.base_url)
    domain_display = parsed_url.netloc if parsed_url.netloc else "BigModel API"
    table.add_row("🌐 服务端点:", f"[dim]{domain_display}[/dim]")
    
    # Think and Stream status with friendly descriptions
    think_desc = "深度思考模式 (已开启)" if config.llm.think else "深度思考模式 (已关闭)"
    think_color = "green" if config.llm.think else "dim"
    table.add_row("🧠 思考模式:", f"[{think_color}]{think_desc}[/{think_color}]")
    
    stream_desc = "流式响应 (已开启)" if config.llm.stream else "流式响应 (已关闭)"
    stream_color = "green" if config.llm.stream else "dim"
    table.add_row("📡 响应模式:", f"[{stream_color}]{stream_desc}[/{stream_color}]")
    
    # Processing configuration with description
    workers_desc = "单线程处理" if config.processing.workers == 1 else f"{config.processing.workers} 线程并行"
    table.add_row("⚡ 处理模式:", f"[yellow]{workers_desc}[/yellow]")
    
    if verbose:
        # Additional verbose information with friendly formatting
        table.add_row("⏱️ 响应超时:", f"{config.llm.timeout} 秒")
        table.add_row("🔄 重试策略:", f"最多 {config.llm.max_retries} 次")
        
        # Temperature with description
        temp_desc = "保守" if config.llm.temperature < 0.5 else "均衡" if config.llm.temperature < 0.8 else "创新"
        table.add_row("🌡️ 创造性:", f"{config.llm.temperature} ({temp_desc})")
    
    console.print("\n[bold blue]━━━━━━ 🚀 生成配置 ━━━━━━[/bold blue]")
    console.print(table)
    console.print("[dim]────────────────────────────[/dim]\n")


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
    console.print("\n[bold blue]━━━━━━ 🔍 预览模式 ━━━━━━[/bold blue]")
    
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_row("📁 发现端点:", f"[bold]{result.total_endpoints}[/bold] 个")
    table.add_row("✅ 将生成:", f"[green]{len(result.api_spec.endpoints) - result.skipped_count}[/green] 个")
    table.add_row("⏭️ 将跳过:", f"[dim]{result.skipped_count}[/dim] 个 (未变更)")
    
    console.print(table)
    
    if result.api_spec and result.api_spec.endpoints:
        console.print(f"\n[yellow]💡 提示: 去掉 --dry-run 参数开始真正生成测试用例[/yellow]")
    console.print("[dim]────────────────────────────[/dim]")


def _show_token_statistics(result: GenerationResult) -> None:
    """Show token usage statistics.
    
    Args:
        result: Generation result with token statistics
    """
    summary = result.get_token_summary()
    
    # Format token numbers in a friendly way
    def format_tokens(num):
        if num >= 1000000:
            return f"{num/1000000:.1f}M"
        elif num >= 1000:
            return f"{num/1000:.1f}K"
        else:
            return str(num)
    
    console.print(f"\n[bold blue]━━━━━━ 📊 使用统计 ━━━━━━[/bold blue]")
    
    # Token usage table with friendly formatting
    token_table = Table(show_header=False, box=None, padding=(0, 2))
    
    # Model name
    model_display = summary['model'].upper().replace("-X", "").replace("GLM-", "GLM ")
    token_table.add_row("🤖 使用模型:", f"[cyan bold]{model_display}[/cyan bold]")
    
    # API call statistics with visual progress bar
    success_ratio = summary['success_rate']
    progress_bar = "█" * int(success_ratio * 10) + "░" * (10 - int(success_ratio * 10))
    token_table.add_row("📡 API调用:", f"{summary['successful_calls']}/{summary['total_calls']} 成功")
    token_table.add_row("📈 成功率:", f"[green]{progress_bar}[/green] {success_ratio:.0%}")
    
    # Token usage with friendly formatting
    token_table.add_row("📝 输入量:", f"{format_tokens(summary['prompt_tokens'])} tokens")
    token_table.add_row("📤 输出量:", f"{format_tokens(summary['completion_tokens'])} tokens")
    token_table.add_row("📊 总计:", f"[bold yellow]{format_tokens(summary['total_tokens'])} tokens[/bold yellow]")
    
    if summary['successful_calls'] > 0:
        avg_tokens = summary['average_tokens_per_call']
        token_table.add_row("⚡ 平均用量:", f"{format_tokens(avg_tokens)}/调用")
        
        # Calculate and show processing speed
        if result.duration > 0:
            endpoints_per_min = (result.generated_count / result.duration) * 60
            token_table.add_row("🚀 处理速度:", f"{endpoints_per_min:.1f} 端点/分钟")
    
    console.print(token_table)
    console.print("[dim]────────────────────────────[/dim]")


def _show_generation_results(result: GenerationResult) -> None:
    """Show generation results.
    
    Args:
        result: Generation result
    """
    console.print("\n[bold green]━━━━━━ ✨ 生成完成 ━━━━━━[/bold green]")
    
    # Summary table with friendly formatting
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_row("📁 总端点数:", f"[bold]{result.total_endpoints}[/bold] 个")
    table.add_row("✅ 已生成:", f"[green bold]{result.generated_count}[/green bold] 个")
    table.add_row("⏭️ 已跳过:", f"[dim]{result.skipped_count}[/dim] 个")
    
    if result.failed_count > 0:
        table.add_row("❌ 失败:", f"[red]{result.failed_count}[/red] 个")
    
    # Format duration in a friendly way
    duration_str = f"{result.duration:.1f} 秒"
    if result.duration >= 60:
        minutes = int(result.duration / 60)
        seconds = int(result.duration % 60)
        duration_str = f"{minutes} 分 {seconds} 秒"
    table.add_row("⏱️ 耗时:", duration_str)
    
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