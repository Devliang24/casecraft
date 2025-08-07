"""Output management for test case files."""

import asyncio
from pathlib import Path
from typing import Dict, List, Optional, Union

import aiofiles
from rich.console import Console

from casecraft.models.config import OutputConfig
from casecraft.models.test_case import TestCaseCollection
from casecraft.utils.file_utils import (
    create_path_slug, ensure_directory, format_file_size,
    get_unique_filename, sanitize_filename
)
from casecraft.utils.formatters import OutputFormatter, get_formatter


class OutputError(Exception):
    """Output management related errors."""
    pass


class OutputManager:
    """Manages output of test case files."""
    
    def __init__(
        self,
        config: OutputConfig,
        formatter: Optional[OutputFormatter] = None,
        console: Optional[Console] = None
    ):
        """Initialize output manager.
        
        Args:
            config: Output configuration
            formatter: Output formatter (defaults to JSON)
            console: Rich console for output
        """
        self.config = config
        self.formatter = formatter or get_formatter("json")
        self.console = console or Console()
        
        # Track generated files
        self.generated_files: List[Path] = []
        self.total_size = 0
    
    async def save_test_cases(
        self,
        collection: TestCaseCollection,
        custom_filename: Optional[str] = None
    ) -> Path:
        """Save test case collection to file.
        
        Args:
            collection: Test case collection to save
            custom_filename: Optional custom filename
            
        Returns:
            Path to saved file
            
        Raises:
            OutputError: If save operation fails
        """
        try:
            # Determine output path
            output_path = await self._get_output_path(collection, custom_filename)
            
            # Format content
            content = self.formatter.format(collection)
            
            # Save file
            async with aiofiles.open(output_path, 'w', encoding='utf-8') as f:
                await f.write(content)
            
            # Update tracking
            file_size = len(content.encode('utf-8'))
            self.generated_files.append(output_path)
            self.total_size += file_size
            
            return output_path
            
        except Exception as e:
            raise OutputError(f"Failed to save test cases: {e}") from e
    
    async def save_multiple_collections(
        self,
        collections: List[TestCaseCollection],
        max_workers: int = 4
    ) -> List[Path]:
        """Save multiple test case collections concurrently.
        
        Args:
            collections: List of collections to save
            max_workers: Maximum concurrent save operations
            
        Returns:
            List of saved file paths
        """
        semaphore = asyncio.Semaphore(max_workers)
        
        async def save_with_semaphore(collection: TestCaseCollection) -> Path:
            async with semaphore:
                return await self.save_test_cases(collection)
        
        tasks = [save_with_semaphore(collection) for collection in collections]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter out exceptions and collect successful paths
        saved_paths = []
        for result in results:
            if isinstance(result, Exception):
                self.console.print(f"[red]Error saving collection: {result}[/red]")
            else:
                saved_paths.append(result)
        
        return saved_paths
    
    async def _get_output_path(
        self,
        collection: TestCaseCollection,
        custom_filename: Optional[str] = None
    ) -> Path:
        """Determine output path for collection.
        
        Args:
            collection: Test case collection
            custom_filename: Optional custom filename
            
        Returns:
            Output file path
        """
        # Base output directory
        output_dir = Path(self.config.directory)
        
        # Ensure directory exists
        ensure_directory(output_dir)
        
        # Generate filename
        if custom_filename:
            filename = custom_filename
        else:
            filename = self._generate_filename(collection)
        
        # Ensure proper extension
        if not filename.endswith(self.formatter.get_file_extension()):
            filename += self.formatter.get_file_extension()
        
        file_path = output_dir / filename
        
        # Handle file conflicts
        if file_path.exists():
            file_path = get_unique_filename(file_path)
        
        return file_path
    
    def _generate_filename(self, collection: TestCaseCollection) -> str:
        """Generate filename for collection.
        
        Args:
            collection: Test case collection
            
        Returns:
            Generated filename
        """
        # Create path slug
        path_slug = create_path_slug(collection.path)
        
        # Apply filename template
        template = self.config.filename_template
        filename = template.format(
            method=collection.method.lower(),
            path_slug=path_slug,
            endpoint_id=collection.endpoint_id.replace(":", "_").replace("/", "_")
        )
        
        return sanitize_filename(filename)
    
    def get_output_summary(self) -> Dict[str, Union[int, str, List[str]]]:
        """Get summary of output operations.
        
        Returns:
            Summary dictionary
        """
        return {
            "files_generated": len(self.generated_files),
            "total_size": self.total_size,
            "total_size_formatted": format_file_size(self.total_size),
            "output_directory": str(Path(self.config.directory).resolve()),
            "files": [str(path) for path in self.generated_files]
        }
    
    def clear_tracking(self) -> None:
        """Clear file tracking."""
        self.generated_files.clear()
        self.total_size = 0
    
    async def cleanup_old_files(
        self,
        pattern: str = "*.json",
        keep_count: int = 100,
        dry_run: bool = False
    ) -> int:
        """Clean up old test case files.
        
        Args:
            pattern: File pattern to match
            keep_count: Number of newest files to keep
            dry_run: If True, only count files without deleting
            
        Returns:
            Number of files cleaned up
        """
        output_dir = Path(self.config.directory)
        
        if not output_dir.exists():
            return 0
        
        # Find all matching files
        files = list(output_dir.rglob(pattern))
        
        # Sort by modification time (newest first)
        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        
        # Files to delete (beyond keep_count)
        files_to_delete = files[keep_count:]
        
        if not files_to_delete:
            return 0
        
        if dry_run:
            return len(files_to_delete)
        
        # Delete old files
        deleted_count = 0
        for file_path in files_to_delete:
            try:
                file_path.unlink()
                deleted_count += 1
            except OSError:
                # Skip files that can't be deleted
                continue
        
        return deleted_count
    
    async def validate_output_directory(self) -> bool:
        """Validate that output directory is accessible.
        
        Returns:
            True if directory is valid and writable
        """
        try:
            output_dir = Path(self.config.directory)
            
            # Create directory if it doesn't exist
            ensure_directory(output_dir)
            
            # Test write access
            test_file = output_dir / ".casecraft_test"
            test_file.write_text("test")
            test_file.unlink()
            
            return True
            
        except Exception:
            return False
    
    def get_organized_files(self) -> Dict[str, List[Path]]:
        """Get generated files organized by directory.
        
        Returns:
            Dictionary mapping directory names to file lists
        """
        organized = {}
        
        for file_path in self.generated_files:
            dir_name = str(file_path.parent.name)
            if dir_name not in organized:
                organized[dir_name] = []
            organized[dir_name].append(file_path)
        
        return organized