"""File utility functions."""

import os
import re
from pathlib import Path
from typing import Optional, Union


def sanitize_filename(filename: str, replacement: str = "_") -> str:
    """Sanitize filename by removing invalid characters.
    
    Args:
        filename: Original filename
        replacement: Character to replace invalid chars with
        
    Returns:
        Sanitized filename
    """
    # Remove or replace invalid characters
    invalid_chars = r'[<>:"/\\|?*]'
    filename = re.sub(invalid_chars, replacement, filename)
    
    # Remove control characters
    filename = ''.join(char for char in filename if ord(char) >= 32)
    
    # Remove leading/trailing whitespace and dots
    filename = filename.strip(' .')
    
    # Ensure filename is not empty
    if not filename:
        filename = "unnamed"
    
    # Limit length
    if len(filename) > 200:
        filename = filename[:200]
    
    return filename


def ensure_directory(path: Union[str, Path]) -> Path:
    """Ensure directory exists, creating if necessary.
    
    Args:
        path: Directory path
        
    Returns:
        Path object for the directory
        
    Raises:
        OSError: If directory cannot be created
    """
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def safe_write_file(
    file_path: Union[str, Path],
    content: str,
    encoding: str = "utf-8",
    backup: bool = False
) -> Path:
    """Safely write content to file with optional backup.
    
    Args:
        file_path: Path to write to
        content: Content to write
        encoding: Text encoding
        backup: Whether to create backup of existing file
        
    Returns:
        Path to written file
        
    Raises:
        OSError: If file cannot be written
    """
    file_path = Path(file_path)
    
    # Ensure parent directory exists
    ensure_directory(file_path.parent)
    
    # Create backup if requested and file exists
    if backup and file_path.exists():
        backup_path = file_path.with_suffix(file_path.suffix + ".bak")
        file_path.replace(backup_path)
    
    # Write content
    file_path.write_text(content, encoding=encoding)
    
    return file_path


def get_unique_filename(
    base_path: Union[str, Path],
    max_attempts: int = 1000
) -> Path:
    """Get unique filename by appending counter if file exists.
    
    Args:
        base_path: Base file path
        max_attempts: Maximum attempts to find unique name
        
    Returns:
        Unique file path
        
    Raises:
        ValueError: If unable to find unique name within max_attempts
    """
    base_path = Path(base_path)
    
    if not base_path.exists():
        return base_path
    
    stem = base_path.stem
    suffix = base_path.suffix
    parent = base_path.parent
    
    for i in range(1, max_attempts + 1):
        new_path = parent / f"{stem}_{i}{suffix}"
        if not new_path.exists():
            return new_path
    
    raise ValueError(f"Unable to find unique filename after {max_attempts} attempts")


def calculate_file_size(file_path: Union[str, Path]) -> int:
    """Calculate file size in bytes.
    
    Args:
        file_path: Path to file
        
    Returns:
        File size in bytes
        
    Raises:
        OSError: If file cannot be accessed
    """
    return Path(file_path).stat().st_size


def format_file_size(size_bytes: int) -> str:
    """Format file size in human-readable format.
    
    Args:
        size_bytes: Size in bytes
        
    Returns:
        Formatted size string
    """
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 ** 2:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 ** 3:
        return f"{size_bytes / (1024 ** 2):.1f} MB"
    else:
        return f"{size_bytes / (1024 ** 3):.1f} GB"


def is_file_writable(file_path: Union[str, Path]) -> bool:
    """Check if file path is writable.
    
    Args:
        file_path: Path to check
        
    Returns:
        True if writable, False otherwise
    """
    file_path = Path(file_path)
    
    # If file exists, check if it's writable
    if file_path.exists():
        return os.access(file_path, os.W_OK)
    
    # If file doesn't exist, check if parent directory is writable
    parent = file_path.parent
    return parent.exists() and os.access(parent, os.W_OK)


def clean_directory(
    directory: Union[str, Path],
    pattern: str = "*",
    dry_run: bool = False
) -> int:
    """Clean files matching pattern from directory.
    
    Args:
        directory: Directory to clean
        pattern: File pattern to match (glob style)
        dry_run: If True, only count files without deleting
        
    Returns:
        Number of files that were (or would be) deleted
    """
    directory = Path(directory)
    
    if not directory.exists():
        return 0
    
    files_to_delete = list(directory.glob(pattern))
    count = 0
    
    for file_path in files_to_delete:
        if file_path.is_file():
            if not dry_run:
                file_path.unlink()
            count += 1
    
    return count


def create_path_slug(path: str) -> str:
    """Create a filesystem-safe slug from API path.
    
    Args:
        path: API path like "/users/{id}/posts"
        
    Returns:
        Safe slug like "users_id_posts"
    """
    # Remove leading/trailing slashes
    path = path.strip("/")
    
    # Replace path separators and parameter braces
    slug = path.replace("/", "_").replace("{", "").replace("}", "")
    
    # Remove multiple underscores
    slug = re.sub(r"_+", "_", slug)
    
    # Remove leading/trailing underscores
    slug = slug.strip("_")
    
    # Ensure not empty
    if not slug:
        slug = "root"
    
    return sanitize_filename(slug)


def get_relative_path(file_path: Union[str, Path], base_path: Union[str, Path]) -> Path:
    """Get relative path from base path.
    
    Args:
        file_path: Target file path
        base_path: Base directory path
        
    Returns:
        Relative path from base to file
    """
    file_path = Path(file_path).resolve()
    base_path = Path(base_path).resolve()
    
    try:
        return file_path.relative_to(base_path)
    except ValueError:
        # Paths are not relative, return absolute path
        return file_path