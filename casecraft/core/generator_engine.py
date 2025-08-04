"""Main test case generation engine."""

import asyncio
import time
from pathlib import Path
from typing import Dict, List, Optional

from rich.console import Console
from rich.progress import Progress, TaskID, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn

from casecraft.core.api_parser import APIParser, APIParseError
from casecraft.core.llm_client import create_llm_client, LLMClient, LLMError, LLMRateLimitError
from casecraft.core.state_manager import StateManager, StateError
from casecraft.core.test_generator import TestCaseGenerator, TestGeneratorError
from casecraft.models.api_spec import APIEndpoint, APISpecification
from casecraft.models.config import CaseCraftConfig
from casecraft.models.test_case import TestCaseCollection
from casecraft.utils.logging import CaseCraftLogger, LoggingContext
from casecraft.utils.exceptions import ErrorHandler, ErrorContext, convert_exception_to_casecraft_error
from casecraft.utils.concurrency import ConcurrencyController


class GeneratorError(Exception):
    """Generator engine related errors."""
    pass


class GenerationResult:
    """Result of test case generation."""
    
    def __init__(self):
        self.total_endpoints = 0
        self.generated_count = 0
        self.skipped_count = 0
        self.failed_count = 0
        self.generated_files: List[str] = []
        self.failed_endpoints: List[str] = []
        self.duration = 0.0
        self.api_spec: Optional[APISpecification] = None


class GeneratorEngine:
    """Main engine for coordinating test case generation."""
    
    def __init__(self, config: CaseCraftConfig, console: Optional[Console] = None):
        """Initialize generator engine.
        
        Args:
            config: CaseCraft configuration
            console: Rich console for output
        """
        self.config = config
        self.console = console or Console()
        
        # Initialize logging and error handling
        self.logger = CaseCraftLogger("generator", console, verbose=False)
        self.error_handler = ErrorHandler(console, verbose=False)
        
        # Initialize components
        self.api_parser = APIParser(timeout=30)
        self.state_manager = StateManager()
        self._llm_client: Optional[LLMClient] = None
        self._test_generator: Optional[TestCaseGenerator] = None
    
    async def generate(
        self,
        source: str,
        include_tags: Optional[List[str]] = None,
        exclude_tags: Optional[List[str]] = None,
        include_paths: Optional[List[str]] = None,
        exclude_paths: Optional[List[str]] = None,
        force: bool = False,
        dry_run: bool = False
    ) -> GenerationResult:
        """Generate test cases from API documentation.
        
        Args:
            source: API documentation source (URL or file path)
            include_tags: Tags to include
            exclude_tags: Tags to exclude  
            include_paths: Path patterns to include
            exclude_paths: Path patterns to exclude
            force: Force regenerate all endpoints
            dry_run: Preview mode without LLM calls
            
        Returns:
            Generation result
            
        Raises:
            GeneratorError: If generation fails
        """
        start_time = time.time()
        result = GenerationResult()
        
        with LoggingContext(self.logger, "test_case_generation", source=source) as op_logger:
            try:
                # Parse API documentation
                op_logger.progress(f"Loading API documentation from: {source}")
                with ErrorContext(self.error_handler, "API documentation loading"):
                    api_spec, api_content = await self._load_api_spec(source)
                    result.api_spec = api_spec
                
                # Apply filters
                if include_tags or exclude_tags or include_paths or exclude_paths:
                    self.console.print("[blue]🔍 Applying filters...[/blue]")
                    api_spec = self.api_parser.filter_endpoints(
                        api_spec, include_tags, exclude_tags, include_paths, exclude_paths
                    )
                
                # Update project state
                await self.state_manager.update_project_config(source, api_content)
                
                # Analyze what needs to be generated
                endpoints_to_process = await self.state_manager.get_endpoints_to_process(api_spec, force)
                to_generate = endpoints_to_process["to_generate"]
                to_skip = endpoints_to_process["to_skip"]
                
                result.total_endpoints = len(api_spec.endpoints)
                result.skipped_count = len(to_skip)
                
                # Show summary
                self._show_generation_summary(api_spec, to_generate, to_skip, dry_run)
                
                if not to_generate:
                    self.console.print("[green]✨ All endpoints are up to date![/green]")
                    return result
                
                # Show batch generation optimization notice
                if len(to_generate) > 10:
                    self.console.print(f"[yellow]📊 Large batch detected: {len(to_generate)} endpoints[/yellow]")
                    self.console.print(f"[dim]   - Using {self.config.processing.workers} concurrent workers[/dim]")
                    self.console.print(f"[dim]   - Estimated time: ~{self._estimate_generation_time(len(to_generate))} minutes[/dim]")
                
                if dry_run:
                    self.console.print("[yellow]🔍 Dry run completed - no test cases generated[/yellow]")
                    return result
                
                # Initialize LLM components with API version
                await self._initialize_llm_components(api_spec.version)
                
                # Generate test cases
                await self._generate_test_cases(to_generate, result)
                
                # Update statistics
                result.duration = time.time() - start_time
                await self.state_manager.update_statistics(
                    total_endpoints=result.total_endpoints,
                    generated_count=result.generated_count,
                    skipped_count=result.skipped_count,
                    failed_count=result.failed_count,
                    duration=result.duration
                )
                
                # Cleanup removed endpoints
                current_endpoint_ids = {ep.get_endpoint_id() for ep in api_spec.endpoints}
                await self.state_manager.cleanup_removed_endpoints(current_endpoint_ids)
                
                return result
                
            except Exception as e:
                result.duration = time.time() - start_time
                raise GeneratorError(f"Generation failed: {e}") from e
            finally:
                await self._cleanup()
    
    async def _load_api_spec(self, source: str) -> tuple[APISpecification, str]:
        """Load and parse API specification.
        
        Args:
            source: API source (URL or file path)
            
        Returns:
            Tuple of (parsed spec, raw content)
        """
        try:
            api_spec = await self.api_parser.parse_from_source(source)
            
            # Get content for hashing
            if self.api_parser._is_url(source):
                api_content = await self.api_parser._fetch_from_url(source)
            else:
                api_content = await self.api_parser._read_from_file(source)
            
            self.console.print(f"[green]✓[/green] Loaded [bold]{api_spec.title}[/bold] v{api_spec.version}")
            self.console.print(f"  Found {len(api_spec.endpoints)} API endpoints")
            
            return api_spec, api_content
            
        except APIParseError as e:
            raise GeneratorError(f"Failed to parse API documentation: {e}") from e
    
    def _show_generation_summary(
        self,
        api_spec: APISpecification,
        to_generate: List[APIEndpoint],
        to_skip: List[APIEndpoint],
        dry_run: bool
    ) -> None:
        """Show generation summary."""
        action = "Would generate" if dry_run else "Generating"
        
        if to_generate:
            self.console.print(f"\n[yellow]📋 {action} test cases for {len(to_generate)} endpoints:[/yellow]")
            for endpoint in to_generate[:5]:  # Show first 5
                self.console.print(f"  • {endpoint.method} {endpoint.path}")
            
            if len(to_generate) > 5:
                self.console.print(f"  ... and {len(to_generate) - 5} more")
        
        if to_skip:
            self.console.print(f"\n[dim]⏭️  Skipping {len(to_skip)} unchanged endpoints[/dim]")
    
    async def _initialize_llm_components(self, api_version: Optional[str] = None) -> None:
        """Initialize LLM client and test generator.
        
        Args:
            api_version: API version string
        """
        try:
            self._llm_client = create_llm_client(self.config.llm)
            self._test_generator = TestCaseGenerator(self._llm_client, api_version)
            
        except Exception as e:
            raise GeneratorError(f"Failed to initialize LLM components: {e}") from e
    
    async def _generate_test_cases(
        self,
        endpoints: List[APIEndpoint],
        result: GenerationResult
    ) -> None:
        """Generate test cases for endpoints.
        
        Args:
            endpoints: Endpoints to process
            result: Result object to update
        """
        if not endpoints:
            return
        
        # Create concurrency controller with rate limiting
        # For 2 workers, use 1 request per second to avoid rate limits
        controller = ConcurrencyController(
            max_workers=self.config.processing.workers,
            rate_limit=1.0 if self.config.processing.workers >= 2 else 0.5
        )
        
        # Create progress tracking
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=self.console
        ) as progress:
            
            task = progress.add_task("Generating test cases...", total=len(endpoints))
            
            # Create tasks for concurrent processing with rate limiting
            tasks = [
                controller.execute(
                    self._generate_endpoint_test_cases(endpoint, None, progress, task, result)
                )
                for endpoint in endpoints
            ]
            
            # Execute all tasks
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _generate_endpoint_test_cases(
        self,
        endpoint: APIEndpoint,
        semaphore: Optional[asyncio.Semaphore],
        progress: Progress,
        task_id: TaskID,
        result: GenerationResult
    ) -> None:
        """Generate test cases for a single endpoint.
        
        Args:
            endpoint: API endpoint
            semaphore: Concurrency control (optional, not used with ConcurrencyController)
            progress: Progress tracker
            task_id: Progress task ID
            result: Result object to update
        """
        # Note: semaphore is now handled by ConcurrencyController
        endpoint_id = endpoint.get_endpoint_id()
        
        try:
            # Generate test cases
            collection = await self._test_generator.generate_test_cases(endpoint)
            
            # Save to file
            output_file = await self._save_test_cases(collection)
            
            # Update state
            await self.state_manager.mark_endpoint_generated(
                endpoint,
                len(collection.test_cases),
                str(output_file)
            )
            
            result.generated_count += 1
            result.generated_files.append(str(output_file))
            
            # Update progress
            progress.update(task_id, advance=1)
            
        except (TestGeneratorError, LLMError, LLMRateLimitError) as e:
            result.failed_count += 1
            result.failed_endpoints.append(f"{endpoint_id}: {str(e)}")
            
            self.console.print(f"[red]✗[/red] Failed to generate {endpoint_id}: {e}")
            progress.update(task_id, advance=1)
            
        except Exception as e:
            result.failed_count += 1
            result.failed_endpoints.append(f"{endpoint_id}: Unexpected error: {str(e)}")
            
            self.console.print(f"[red]✗[/red] Unexpected error for {endpoint_id}: {e}")
            progress.update(task_id, advance=1)
    
    async def _save_test_cases(self, collection: TestCaseCollection) -> Path:
        """Save test case collection to file.
        
        Args:
            collection: Test case collection
            
        Returns:
            Path to saved file
        """
        # Create output directory
        output_dir = Path(self.config.output.directory)
        
        # Organize by tag if requested
        if self.config.output.organize_by_tag and collection.tags:
            tag_dir = output_dir / collection.tags[0]  # Use first tag
            tag_dir.mkdir(parents=True, exist_ok=True)
            output_dir = tag_dir
        else:
            output_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate filename
        filename = self._generate_filename(collection)
        output_file = output_dir / filename
        
        # Save JSON
        output_file.write_text(collection.model_dump_json(indent=2), encoding='utf-8')
        
        return output_file
    
    def _generate_filename(self, collection: TestCaseCollection) -> str:
        """Generate filename for test case collection.
        
        Args:
            collection: Test case collection
            
        Returns:
            Generated filename
        """
        # Sanitize path for filename
        path_slug = collection.path.replace("/", "_").replace("{", "").replace("}", "").strip("_")
        if not path_slug:
            path_slug = "root"
        
        # Apply template
        template = self.config.output.filename_template
        filename = template.format(
            method=collection.method.lower(),
            path_slug=path_slug,
            endpoint_id=collection.endpoint_id.replace(":", "_").replace("/", "_")
        )
        
        # Ensure .json extension
        if not filename.endswith('.json'):
            filename += '.json'
        
        return filename
    
    def _estimate_generation_time(self, endpoint_count: int) -> float:
        """Estimate generation time for batch processing.
        
        Args:
            endpoint_count: Number of endpoints to process
            
        Returns:
            Estimated time in minutes
        """
        # Base time per endpoint (considering LLM response time)
        base_time_per_endpoint = 15  # seconds
        
        # Concurrent processing reduces total time
        workers = self.config.processing.workers
        concurrent_time = (endpoint_count * base_time_per_endpoint) / workers
        
        # Add some overhead for network and processing
        overhead = endpoint_count * 2  # 2 seconds overhead per endpoint
        
        total_seconds = concurrent_time + overhead
        return round(total_seconds / 60, 1)  # Convert to minutes
    
    async def _cleanup(self) -> None:
        """Cleanup resources."""
        if self._llm_client:
            await self._llm_client.close()