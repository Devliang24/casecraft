"""Unified UI output utilities."""

from typing import Optional
from casecraft.utils.constants import UI_COLORS, UI_ICONS


class UI:
    """Unified UI output formatting."""
    
    @staticmethod
    def format_color(text: str, color: str, bold: bool = False) -> str:
        """Format text with color."""
        if bold:
            return f"[bold {UI_COLORS.get(color, color)}]{text}[/bold {UI_COLORS.get(color, color)}]"
        return f"[{UI_COLORS.get(color, color)}]{text}[/{UI_COLORS.get(color, color)}]"
    
    @staticmethod
    def success(text: str, icon: bool = True, bold: bool = False) -> str:
        """Format success message."""
        msg = f"{UI_ICONS['success']} {text}" if icon else text
        return UI.format_color(msg, 'success', bold)
    
    @staticmethod
    def error(text: str, icon: bool = True) -> str:
        """Format error message."""
        msg = f"{UI_ICONS['error']} {text}" if icon else text
        return UI.format_color(msg, 'error')
    
    @staticmethod
    def warning(text: str, icon: bool = True) -> str:
        """Format warning message."""
        msg = f"{UI_ICONS['warning']} {text}" if icon else text
        return UI.format_color(msg, 'warning')
    
    @staticmethod
    def info(text: str, icon: bool = False) -> str:
        """Format info message."""
        msg = f"{UI_ICONS['info']} {text}" if icon else text
        return UI.format_color(msg, 'info')
    
    @staticmethod
    def dim(text: str) -> str:
        """Format dimmed text."""
        return UI.format_color(text, 'dim')
    
    @staticmethod
    def highlight(text: str, bold: bool = True) -> str:
        """Format highlighted text."""
        return UI.format_color(text, 'highlight', bold)
    
    @staticmethod
    def loading(text: str) -> str:
        """Format loading message."""
        return f"{UI_ICONS['loading']} {text}"
    
    @staticmethod
    def sparkles(text: str) -> str:
        """Format sparkles message."""
        return f"{UI_ICONS['sparkles']} {text}"