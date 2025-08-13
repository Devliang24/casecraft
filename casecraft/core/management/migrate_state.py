"""Migration utility for consolidating state files."""

import json
import asyncio
from pathlib import Path
from typing import Optional

from casecraft.models.state import CaseCraftState
from casecraft.models.provider_state import ProviderStatistics


async def migrate_state_files(state_file_path: Optional[Path] = None) -> bool:
    """Migrate legacy state files to unified format.
    
    Args:
        state_file_path: Path to state file (defaults to .casecraft_state.json)
        
    Returns:
        True if migration was performed, False otherwise
    """
    state_path = state_file_path or Path(".casecraft_state.json")
    stats_path = state_path.parent / ".casecraft_provider_stats.json"
    
    # Check if migration is needed
    if not stats_path.exists():
        print("No legacy provider stats file found, migration not needed")
        return False
    
    print(f"Found legacy provider stats file: {stats_path}")
    
    # Load current state
    state = None
    if state_path.exists():
        try:
            with open(state_path, 'r', encoding='utf-8') as f:
                state_data = json.load(f)
                state = CaseCraftState(**state_data)
                print(f"Loaded existing state from {state_path}")
        except Exception as e:
            print(f"Warning: Failed to load state file: {e}")
            state = CaseCraftState()
    else:
        state = CaseCraftState()
        print("Creating new state file")
    
    # Check if already migrated
    if state.provider_stats is not None:
        print("State already contains provider_stats, checking if cleanup needed...")
        if stats_path.exists():
            stats_path.unlink()
            print(f"Removed redundant legacy file: {stats_path}")
        return False
    
    # Load provider stats
    try:
        with open(stats_path, 'r', encoding='utf-8') as f:
            stats_data = json.load(f)
            provider_stats = ProviderStatistics(**stats_data)
            print(f"Loaded provider statistics from {stats_path}")
    except Exception as e:
        print(f"Error loading provider stats: {e}")
        return False
    
    # Merge provider stats into state
    state.provider_stats = provider_stats
    
    # Save merged state
    try:
        state_json = state.model_dump_json(indent=2)
        with open(state_path, 'w', encoding='utf-8') as f:
            f.write(state_json)
        print(f"✓ Saved unified state to {state_path}")
    except Exception as e:
        print(f"Error saving unified state: {e}")
        return False
    
    # Remove legacy file
    try:
        stats_path.unlink()
        print(f"✓ Removed legacy file: {stats_path}")
    except Exception as e:
        print(f"Warning: Failed to remove legacy file: {e}")
    
    print("\n✅ Migration completed successfully!")
    print("State files have been consolidated into a single unified format.")
    return True


async def cleanup_legacy_files(project_root: Optional[Path] = None) -> None:
    """Clean up any remaining legacy files in the project.
    
    Args:
        project_root: Root directory to clean (defaults to current directory)
    """
    root = project_root or Path(".")
    
    # List of legacy files to clean up
    legacy_files = [
        ".casecraft_provider_stats.json",
        "test_kimi_fix.py",
        "merge_record.txt",
        "merge_report.txt"
    ]
    
    cleaned = []
    for filename in legacy_files:
        file_path = root / filename
        if file_path.exists():
            try:
                file_path.unlink()
                cleaned.append(filename)
            except Exception as e:
                print(f"Warning: Failed to remove {filename}: {e}")
    
    if cleaned:
        print(f"✓ Cleaned up legacy files: {', '.join(cleaned)}")
    else:
        print("No legacy files to clean up")


async def main():
    """Run migration and cleanup."""
    print("=" * 60)
    print("CaseCraft State Migration Utility")
    print("=" * 60)
    print()
    
    # Run migration
    migrated = await migrate_state_files()
    
    print()
    
    # Run cleanup
    await cleanup_legacy_files()
    
    print()
    print("=" * 60)
    print("Migration complete")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())