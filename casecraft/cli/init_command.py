"""Implementation of the init command."""

import os
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.table import Table

from casecraft.core.management.config_manager import ConfigManager, ConfigError
from casecraft.models.config import CaseCraftConfig, LLMConfig


console = Console()


def init_command() -> None:
    """Initialize CaseCraft configuration."""
    console.print(Panel.fit(
        "[bold blue]CaseCraft Configuration Setup[/bold blue]",
        subtitle="Setting up your API testing environment"
    ))
    
    config_manager = ConfigManager()
    
    # Check if config already exists
    if config_manager.config_exists():
        console.print(f"[yellow]Configuration file already exists at: {config_manager.config_path}[/yellow]")
        
        if not Confirm.ask("Do you want to overwrite the existing configuration?"):
            console.print("[green]Keeping existing configuration. Setup cancelled.[/green]")
            return
    
    try:
        # Create default config
        config = config_manager.create_default_config()
        
        # Interactive setup
        config = _interactive_setup(config)
        
        # Save configuration
        config_manager.save_config(config)
        
        console.print(f"\n[green]✓[/green] Configuration saved to: [bold]{config_manager.config_path}[/bold]")
        
        # Show next steps
        _show_next_steps()
        
    except ConfigError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise click.ClickException(str(e))
    except KeyboardInterrupt:
        console.print("\n[yellow]Setup cancelled by user.[/yellow]")
        raise click.Abort()


def _interactive_setup(config: CaseCraftConfig) -> CaseCraftConfig:
    """Interactive configuration setup.
    
    Args:
        config: Base configuration to modify
        
    Returns:
        Updated configuration
    """
    console.print("\n[bold]BigModel LLM Configuration[/bold]")
    console.print("CaseCraft 使用 BigModel (GLM-4.5-X) 作为 LLM 服务")
    console.print(f"模型: [cyan]glm-4.5-x[/cyan]")
    console.print(f"API 地址: [cyan]https://open.bigmodel.cn/api/paas/v4[/cyan]")
    
    # API Key
    api_key = _prompt_api_key("bigmodel")
    
    # BigModel only supports single concurrency
    console.print("[yellow]注意: BigModel 仅支持单并发，workers 设置为 1[/yellow]")
    
    # Update LLM config
    config.llm = LLMConfig(
        model="glm-4.5-x",
        api_key=api_key,
        base_url="https://open.bigmodel.cn/api/paas/v4",
    )
    
    # Output configuration
    console.print("\n[bold]Output Configuration[/bold]")
    
    output_dir = Prompt.ask(
        "Output directory for test cases",
        default=config.output.directory
    )
    config.output.directory = output_dir
    
    organize_by_tag = Confirm.ask(
        "Organize output files by API tags?",
        default=config.output.organize_by_tag
    )
    config.output.organize_by_tag = organize_by_tag
    
    # Processing configuration
    console.print("\n[bold]Processing Configuration[/bold]")
    
    # BigModel only supports single worker
    config.processing.workers = 1
    console.print("Workers: [cyan]1[/cyan] (BigModel 单并发限制)"
    
    return config


def _prompt_api_key(provider: str) -> Optional[str]:
    """Prompt for API key with provider-specific guidance.
    
    Args:
        provider: LLM provider name
        
    Returns:
        API key or None if skipped
    """
    # Check environment variable first
    env_var = "BIGMODEL_API_KEY"
    existing_key = os.getenv(env_var)
    
    if existing_key:
        console.print(f"[green]✓[/green] Found API key in environment variable {env_var}")
        if Confirm.ask("Use existing API key from environment?", default=True):
            return existing_key
    
    # Provide guidance for obtaining API key
    console.print(f"[dim]获取API密钥: https://open.bigmodel.cn/console/apikey[/dim]")
    
    # Prompt for API key
    api_key = Prompt.ask(
        "输入你的 BIGMODEL API 密钥",
        password=True,
        default=""
    )
    
    if not api_key:
        console.print(f"[yellow]No API key provided. You can set it later in the config file or via {env_var}[/yellow]")
        return None
    
    # Basic validation
    if len(api_key) < 10:
        console.print("[yellow]Warning: API key seems too short. Please verify it's correct.[/yellow]")
    
    return api_key


def _show_next_steps() -> None:
    """Display next steps after configuration."""
    console.print("\n[bold green]Setup Complete! 🎉[/bold green]")
    
    next_steps = [
        "Generate test cases from API documentation:",
        "  [cyan]casecraft generate https://petstore.swagger.io/v2/swagger.json[/cyan]",
        "",
        "Or from a local file:",
        "  [cyan]casecraft generate ./openapi.yaml[/cyan]",
        "",
        "Use [cyan]--dry-run[/cyan] to preview without making LLM calls:",
        "  [cyan]casecraft generate ./api.json --dry-run[/cyan]"
    ]
    
    console.print(Panel(
        "\n".join(next_steps),
        title="Next Steps",
        border_style="green"
    ))