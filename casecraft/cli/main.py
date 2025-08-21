"""Main CLI command group for CaseCraft."""

import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import click
from rich.console import Console

from casecraft import __version__

console = Console()

# 保存原始的 show 方法
original_show = click.exceptions.UsageError.show

def custom_show(self, file=None):
    """自定义错误显示方法，提供更友好的错误提示"""
    if file is None:
        file = sys.stderr
    
    error_msg = self.format_message()
    
    # 检查是否是 --keep-days 缺少参数的错误
    if "--keep-days" in error_msg and "requires an argument" in error_msg:
        console.print("[red]❌ 错误：--keep-days 参数需要指定天数（1-365）[/red]\n")
        console.print("📝 [bold]正确用法示例：[/bold]")
        console.print("  • [green]casecraft cleanup --logs --keep-days 7[/green]   # 保留最近7天的日志")
        console.print("  • [green]casecraft cleanup --logs --keep-days 30[/green]  # 保留最近30天的日志")
        console.print("  • [green]casecraft cleanup --logs[/green]                 # 使用默认值（7天）")
        console.print("\n💡 [yellow]提示：[/yellow]使用 [cyan]casecraft cleanup --help[/cyan] 查看完整帮助")
    else:
        # 其他错误使用原始方法
        original_show(self, file)

# 替换 show 方法
click.exceptions.UsageError.show = custom_show


def main():
    """主程序入口，提供友好的错误处理"""
    cli()



class KeepDaysType(click.ParamType):
    """自定义的保留天数参数类型"""
    name = "keep_days"
    
    def convert(self, value, param, ctx):
        if value is None:
            return 7  # 默认值
        
        try:
            days = int(value)
            if days < 1 or days > 365:
                raise ValueError()
            return days
        except (ValueError, TypeError):
            # 使用 Click 的失败方法，但提供友好的错误消息
            self.fail(
                f"保留天数必须在 1-365 之间，当前值: {value}\n\n"
                f"📝 正确用法示例：\n"
                f"  • casecraft cleanup --logs --keep-days 7   # 保留最近7天的日志\n"
                f"  • casecraft cleanup --logs --keep-days 30  # 保留最近30天的日志\n"
                f"  • casecraft cleanup --logs                 # 使用默认值（7天）\n\n"
                f"💡 提示：使用 casecraft cleanup --help 查看完整帮助",
                param, ctx
            )


def validate_http_methods(methods: tuple) -> list:
    """验证HTTP方法是否有效
    
    Args:
        methods: HTTP方法元组
        
    Returns:
        规范化的HTTP方法列表（大写）
        
    Raises:
        click.BadParameter: 如果方法无效
    """
    if not methods:
        return None
    
    valid_methods = {'GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS'}
    normalized = []
    invalid = []
    
    for method in methods:
        method_upper = method.upper()
        if method_upper in valid_methods:
            normalized.append(method_upper)
        else:
            invalid.append(method)
    
    if invalid:
        raise click.BadParameter(
            f"Invalid HTTP method(s): {', '.join(invalid)}. "
            f"Valid methods are: {', '.join(sorted(valid_methods))}"
        )
    
    return normalized


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
@click.option(
    "--logs",
    is_flag=True,
    help="清理过期日志文件"
)
@click.option(
    "--test-cases", 
    is_flag=True,
    help="清理重复的测试用例文件"
)
@click.option(
    "--debug-files",
    is_flag=True, 
    help="清理调试文件"
)
@click.option(
    "--all",
    is_flag=True,
    help="清理所有类型的文件"
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="预览模式，不实际删除文件"
)
@click.option(
    "--keep-days",
    type=KeepDaysType(),
    default=7,
    help="日志文件保留天数（1-365天，默认7天）"
)
@click.option(
    "--summary",
    is_flag=True,
    help="显示可清理文件的摘要信息"
)
@click.option(
    "--force",
    is_flag=True,
    help="强制清理所有文件（不保留任何文件）"
)
@click.pass_context  
def cleanup(ctx, logs, test_cases, debug_files, all, dry_run, keep_days, summary, force):
    """清理临时文件和过期数据.
    
    该命令可以清理以下类型的文件：
    - 过期日志文件（可自定义保留天数）
    - 重复的测试用例文件（带时间戳的副本）
    - 调试响应文件
    
    📋 常用示例：
    
    \b
    casecraft cleanup --summary                      # 查看可清理文件统计
    casecraft cleanup --all --dry-run              # 预览所有清理操作
    casecraft cleanup --logs --keep-days 3         # 清理3天前的日志
    casecraft cleanup --test-cases                 # 清理重复测试文件
    casecraft cleanup --all                        # 清理所有类型文件
    casecraft cleanup --all --force                # 强制清理所有文件
    casecraft cleanup --logs --force --dry-run     # 预览强制清理日志
    
    💡 提示：建议先使用 --dry-run 预览要删除的文件
    """
    from rich.console import Console
    from casecraft.utils.file_cleanup import FileCleanupManager
    from casecraft.cli.cleanup_command import _show_cleanup_summary, _show_results_summary
    
    console = Console()
    cleanup_manager = FileCleanupManager(dry_run=dry_run, force=force)
    
    if dry_run:
        console.print("[yellow]🔍 预览模式 - 不会实际删除文件[/yellow]")
        console.print()
    
    if force:
        console.print("[red bold]⚠️  强制模式 - 将删除所有文件！[/red bold]")
        if not dry_run:
            if not click.confirm("确定要强制删除所有文件吗？", default=False):
                console.print("[yellow]已取消操作[/yellow]")
                return
        console.print()
    
    if summary:
        _show_cleanup_summary(cleanup_manager)
        return
    
    # 如果没有指定任何选项，显示友好的帮助信息
    if not any([logs, test_cases, debug_files, all]):
        console.print("[yellow]⚠️  未指定清理类型[/yellow]\n")
        console.print("📋 可用选项：")
        console.print("  • [cyan]casecraft cleanup --all[/cyan]          # 清理所有类型文件")
        console.print("  • [cyan]casecraft cleanup --logs[/cyan]         # 清理过期日志（保留7天）")  
        console.print("  • [cyan]casecraft cleanup --test-cases[/cyan]   # 清理重复测试文件")
        console.print("  • [cyan]casecraft cleanup --summary[/cyan]      # 查看可清理文件统计")
        console.print("\n💡 [bold]常用示例：[/bold]")
        console.print("  • [green]casecraft cleanup --logs --keep-days 3[/green]  # 清理3天前的日志")
        console.print("  • [green]casecraft cleanup --all --dry-run[/green]       # 预览所有清理操作")
        console.print("\n🔍 使用 [cyan]casecraft cleanup --help[/cyan] 查看完整帮助")
        return
    
    results = {}
    
    # 执行清理操作
    if all or logs:
        console.print("[blue]🧹 清理日志文件...[/blue]")
        results["logs"] = cleanup_manager.clean_logs(keep_days=keep_days)
    
    if all or test_cases:
        console.print("[blue]🧹 清理测试用例文件...[/blue]")
        results["test_cases"] = cleanup_manager.clean_test_cases()
    
    if all or debug_files:
        console.print("[blue]🧹 清理调试文件...[/blue]")
        results["debug_files"] = cleanup_manager.clean_debug_files()
    
    # 显示结果摘要
    _show_results_summary(results, dry_run)


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
    "--include-method",
    multiple=True,
    help="Include only endpoints with specific HTTP methods (e.g., POST, GET)"
)
@click.option(
    "--exclude-method",
    multiple=True,
    help="Exclude endpoints with specific HTTP methods"
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
    "--format",
    type=click.Choice(["json", "excel", "compact", "pretty"]),
    default="json",
    help="Output format for test cases"
)
@click.option(
    "--config",
    type=click.Path(exists=True, readable=True),
    help="Custom template configuration file for Excel format"
)
@click.option(
    "--merge-excel",
    is_flag=True,
    help="Merge all endpoints into one Excel file with multiple sheets"
)
@click.option(
    "--priority",
    type=click.Choice(["P0", "P1", "P2", "all"]),
    default="all",
    help="Filter test cases by priority level"
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
    include_method: tuple,
    exclude_method: tuple,
    workers: int,
    force: bool,
    dry_run: bool,
    organize_by: str,
    format: str,
    config: Optional[str],
    merge_excel: bool,
    priority: str,
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
        
        # Filter by HTTP methods
        casecraft generate api.json --provider glm --include-method POST
        casecraft generate api.json --provider glm --exclude-method DELETE
    """
    from casecraft.cli.generate_command import run_generate_command
    from casecraft.utils.logging import CaseCraftLogger
    
    verbose = ctx.obj.get("verbose", False)
    quiet = ctx.obj.get("quiet", False)
    
    # 验证HTTP方法
    try:
        validated_include_methods = validate_http_methods(include_method)
        validated_exclude_methods = validate_http_methods(exclude_method)
    except click.BadParameter as e:
        console.print(f"[red]❌ Error: {e}[/red]")
        raise click.Abort()
    
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
        include_method=validated_include_methods,
        exclude_method=validated_exclude_methods,
        workers=workers,
        force=force,
        dry_run=dry_run,
        organize_by=organize_by,
        format=format,
        config=config,
        merge_excel=merge_excel,
        priority=priority,
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