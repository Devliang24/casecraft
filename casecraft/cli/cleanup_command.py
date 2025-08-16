"""文件清理CLI命令."""

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from casecraft.utils.file_cleanup import FileCleanupManager


console = Console()


@click.command()
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
    type=int,
    default=7,
    help="日志文件保留天数（默认7天）"
)
@click.option(
    "--summary",
    is_flag=True,
    help="显示可清理文件的摘要信息"
)
def cleanup(logs, test_cases, debug_files, all, dry_run, keep_days, summary):
    """清理临时文件和过期数据.
    
    此命令可以清理以下类型的文件：
    - 过期日志文件
    - 重复的测试用例文件  
    - 调试响应文件
    
    示例：
    casecraft cleanup --all --dry-run  # 预览所有清理操作
    casecraft cleanup --logs --keep-days 3  # 清理3天前的日志
    casecraft cleanup --test-cases  # 清理重复测试文件
    """
    cleanup_manager = FileCleanupManager(dry_run=dry_run)
    
    if dry_run:
        console.print("[yellow]🔍 预览模式 - 不会实际删除文件[/yellow]")
        console.print()
    
    if summary:
        _show_cleanup_summary(cleanup_manager)
        return
    
    # 如果没有指定任何选项，显示帮助
    if not any([logs, test_cases, debug_files, all]):
        console.print("[red]❌ 请指定要清理的文件类型[/red]")
        console.print("使用 --help 查看可用选项")
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


def _show_cleanup_summary(cleanup_manager: FileCleanupManager):
    """显示清理摘要信息."""
    summary = cleanup_manager.get_cleanup_summary()
    
    table = Table(title="📊 文件清理摘要")
    table.add_column("类型", style="cyan")
    table.add_column("文件数量", justify="right", style="yellow") 
    table.add_column("占用空间", justify="right", style="green")
    table.add_column("说明", style="dim")
    
    # 日志文件
    logs_info = summary["logs"]
    logs_size = _format_size(logs_info["size"])
    logs_desc = f"最老: {logs_info['oldest']}" if logs_info["oldest"] else "无"
    table.add_row("日志文件", str(logs_info["count"]), logs_size, logs_desc)
    
    # 重复测试文件
    test_info = summary["test_cases"]
    test_size = _format_size(test_info["size"])
    table.add_row("重复测试文件", str(test_info["duplicates"]), test_size, "带时间戳的重复文件")
    
    # 调试文件
    debug_info = summary["debug_files"]
    debug_size = _format_size(debug_info["size"])
    table.add_row("调试文件", str(debug_info["count"]), debug_size, "错误响应文件")
    
    console.print(table)
    console.print()
    
    total_files = logs_info["count"] + test_info["duplicates"] + debug_info["count"]
    total_size = logs_info["size"] + test_info["size"] + debug_info["size"]
    
    if total_files > 0:
        panel = Panel(
            f"总计: {total_files} 个文件, {_format_size(total_size)}\n"
            f"运行 [cyan]casecraft cleanup --all[/cyan] 清理所有文件",
            title="💡 清理建议",
            border_style="green"
        )
        console.print(panel)
    else:
        console.print("[green]✅ 没有需要清理的文件[/green]")


def _show_results_summary(results: dict, dry_run: bool):
    """显示清理结果摘要."""
    if not results:
        return
    
    action = "将" if dry_run else "已"
    
    table = Table(title=f"📋 清理结果摘要")
    table.add_column("类型", style="cyan")
    table.add_column("删除/归档", justify="right", style="red")
    table.add_column("保留", justify="right", style="green")
    table.add_column("释放空间", justify="right", style="yellow")
    
    total_deleted = 0
    total_size = 0
    
    for file_type, result in results.items():
        deleted = result.get("deleted", 0) + result.get("archived", 0)
        kept = result.get("kept", 0)
        size_freed = result.get("size_freed", 0)
        
        total_deleted += deleted
        total_size += size_freed
        
        table.add_row(
            file_type.replace("_", " ").title(),
            str(deleted),
            str(kept) if kept > 0 else "-",
            _format_size(size_freed)
        )
    
    console.print(table)
    console.print()
    
    if total_deleted > 0:
        status_icon = "🔍" if dry_run else "✅"
        panel = Panel(
            f"{action}删除 {total_deleted} 个文件\n"
            f"{action}释放 {_format_size(total_size)} 磁盘空间",
            title=f"{status_icon} 清理{'预览' if dry_run else '完成'}",
            border_style="yellow" if dry_run else "green"
        )
        console.print(panel)
    else:
        console.print("[green]✅ 没有文件需要清理[/green]")


def _format_size(size_bytes: int) -> str:
    """格式化文件大小."""
    if size_bytes == 0:
        return "0 B"
    
    units = ["B", "KB", "MB", "GB"]
    size = float(size_bytes)
    unit_index = 0
    
    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1
    
    if unit_index == 0:
        return f"{int(size)} {units[unit_index]}"
    else:
        return f"{size:.1f} {units[unit_index]}"