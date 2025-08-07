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


console = Console()


def init_command() -> None:
    """Initialize CaseCraft configuration via .env file setup."""
    console.print(Panel.fit(
        "[bold blue]CaseCraft Configuration Setup[/bold blue]",
        subtitle="Setting up your API testing environment with .env file"
    ))
    
    # Check if .env file already exists
    env_file = Path(".env")
    if env_file.exists():
        console.print(f"[yellow].env file already exists in current directory[/yellow]")
        
        if not Confirm.ask("Do you want to overwrite the existing .env file?"):
            console.print("[green]Keeping existing .env file. Setup cancelled.[/green]")
            return
    
    try:
        # Interactive setup to create .env file
        env_vars = _interactive_setup()
        
        # Write .env file
        _write_env_file(env_file, env_vars)
        
        console.print(f"\n[green]✓[/green] Configuration saved to: [bold].env[/bold]")
        console.print("[dim]Remember to add .env to your .gitignore file![/dim]")
        
        # Show next steps
        _show_next_steps()
        
    except ConfigError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise click.ClickException(str(e))
    except KeyboardInterrupt:
        console.print("\n[yellow]Setup cancelled by user.[/yellow]")
        raise click.Abort()


def _interactive_setup() -> dict:
    """Interactive configuration setup.
    
    Returns:
        Dictionary of environment variables to write
    """
    console.print("\n[bold]BigModel LLM Configuration[/bold]")
    console.print("CaseCraft 使用 BigModel (GLM-4.5-X) 作为 LLM 服务")
    
    env_vars = {}
    
    # API Key
    api_key = _prompt_api_key()
    if api_key:
        env_vars["CASECRAFT_LLM_API_KEY"] = api_key
    
    # Model configuration (with defaults)
    console.print("\n[bold]Model Configuration[/bold]")
    
    model = Prompt.ask("Model name", default="glm-4.5-x")
    if model != "glm-4.5-x":
        env_vars["CASECRAFT_LLM_MODEL"] = model
    
    base_url = Prompt.ask("Base URL", default="https://open.bigmodel.cn/api/paas/v4")
    if base_url != "https://open.bigmodel.cn/api/paas/v4":
        env_vars["CASECRAFT_LLM_BASE_URL"] = base_url
    
    # Advanced settings (optional)
    if Confirm.ask("Configure advanced settings?", default=False):
        timeout = Prompt.ask("Request timeout (seconds)", default="60")
        if timeout != "60":
            env_vars["CASECRAFT_LLM_TIMEOUT"] = timeout
            
        max_retries = Prompt.ask("Max retries", default="3")
        if max_retries != "3":
            env_vars["CASECRAFT_LLM_MAX_RETRIES"] = max_retries
            
        temperature = Prompt.ask("Temperature", default="0.7")
        if temperature != "0.7":
            env_vars["CASECRAFT_LLM_TEMPERATURE"] = temperature
        
        think = Confirm.ask("Enable thinking process output?", default=False)
        if think:
            env_vars["CASECRAFT_LLM_THINK"] = "true"
            
        stream = Confirm.ask("Enable streaming response?", default=False)
        if stream:
            env_vars["CASECRAFT_LLM_STREAM"] = "true"
    
    # Output configuration
    console.print("\n[bold]Output Configuration[/bold]")
    
    output_dir = Prompt.ask("Output directory for test cases", default="test_cases")
    if output_dir != "test_cases":
        env_vars["CASECRAFT_OUTPUT_DIRECTORY"] = output_dir
    
    organize_by_tag = Confirm.ask("Organize output files by API tags?", default=False)
    if organize_by_tag:
        env_vars["CASECRAFT_OUTPUT_ORGANIZE_BY_TAG"] = "true"
    
    # Processing configuration
    console.print("\n[bold]Processing Configuration[/bold]")
    console.print("[yellow]Note: BigModel only supports single concurrency, workers set to 1[/yellow]")
    env_vars["CASECRAFT_PROCESSING_WORKERS"] = "1"
    
    return env_vars


def _prompt_api_key() -> Optional[str]:
    """Prompt for API key with guidance.
    
    Returns:
        API key or None if skipped
    """
    # Check existing environment variables first
    existing_key = os.getenv("CASECRAFT_LLM_API_KEY") or os.getenv("BIGMODEL_API_KEY")
    
    if existing_key:
        console.print(f"[green]✓[/green] Found API key in environment variables")
        if Confirm.ask("Use existing API key from environment?", default=True):
            return existing_key
    
    # Provide guidance for obtaining API key
    console.print(f"[dim]Get API key from: https://open.bigmodel.cn/console/apikey[/dim]")
    
    # Prompt for API key
    api_key = Prompt.ask(
        "Enter your BigModel API key",
        password=True,
        default=""
    )
    
    if not api_key:
        console.print("[yellow]No API key provided. You can add it to .env file later.[/yellow]")
        return None
    
    # Basic validation
    if len(api_key) < 10:
        console.print("[yellow]Warning: API key seems too short. Please verify it's correct.[/yellow]")
    
    return api_key


def _write_env_file(env_file: Path, env_vars: dict) -> None:
    """Write environment variables to .env file.
    
    Args:
        env_file: Path to .env file
        env_vars: Dictionary of environment variables
    """
    with open(env_file, 'w', encoding='utf-8') as f:
        f.write("# CaseCraft Configuration\n")
        f.write("# Generated by 'casecraft init'\n")
        f.write("# Add this file to .gitignore to keep your API key secure\n\n")
        
        f.write("# BigModel LLM Configuration\n")
        for key, value in env_vars.items():
            if key.startswith("CASECRAFT_LLM_"):
                f.write(f"{key}={value}\n")
        
        f.write("\n# Output Configuration\n")
        for key, value in env_vars.items():
            if key.startswith("CASECRAFT_OUTPUT_"):
                f.write(f"{key}={value}\n")
        
        f.write("\n# Processing Configuration\n")
        for key, value in env_vars.items():
            if key.startswith("CASECRAFT_PROCESSING_"):
                f.write(f"{key}={value}\n")
        
        f.write("\n# Optional: Alternative API key variable\n")
        f.write("# BIGMODEL_API_KEY=your-api-key-here\n")


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
        "  [cyan]casecraft generate ./api.json --dry-run[/cyan]",
        "",
        "Environment variables in .env file will be loaded automatically."
    ]
    
    console.print(Panel(
        "\n".join(next_steps),
        title="Next Steps",
        border_style="green"
    ))