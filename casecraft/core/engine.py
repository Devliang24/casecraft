"""Main test case generation engine."""

import asyncio
import os
import time
from pathlib import Path
from typing import Dict, List, Optional, Any

from rich.console import Console
from rich.progress import Progress, TaskID, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn

from casecraft.core.parsing.api_parser import APIParser, APIParseError
from casecraft.core.generation.llm_client import LLMClient, LLMError, LLMRateLimitError
from casecraft.core.providers.exceptions import ProviderError
from casecraft.core.management.enhanced_state_manager import EnhancedStateManager, StateError
from casecraft.core.generation.test_generator import TestCaseGenerator, TestGeneratorError, GenerationResult as TestGenerationResult
from casecraft.models.api_spec import APIEndpoint, APISpecification
from casecraft.models.config import CaseCraftConfig
from casecraft.models.test_case import TestCaseCollection
from casecraft.models.usage import TokenUsage, TokenStatistics, CostCalculator, RetryTracker
from casecraft.utils.logging import CaseCraftLogger, LoggingContext
from casecraft.utils.exceptions import ErrorHandler, ErrorContext, convert_exception_to_casecraft_error
from casecraft.utils.concurrency import ConcurrencyController
from casecraft.utils.constants import DEFAULT_API_PARSE_TIMEOUT


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
        self.total_test_cases = 0
        self.generated_files: List[str] = []
        self.failed_endpoints: List[str] = []
        self.duration = 0.0
        self.api_spec: Optional[APISpecification] = None
        
        # Token usage statistics
        self.token_statistics = TokenStatistics()
        self.model_name: Optional[str] = None
        
        # Retry statistics
        self.retry_trackers: Dict[str, RetryTracker] = {}  # endpoint_id -> RetryTracker
    
    def add_token_usage(self, usage: TokenUsage, success: bool = True) -> None:
        """Add token usage from a single LLM API call.
        
        Args:
            usage: Token usage data
            success: Whether the API call was successful
        """
        self.token_statistics.add_usage(usage, success)
        
        # Update model name from usage if available
        if usage.model:
            self.model_name = usage.model
    
    def get_token_summary(self) -> Dict[str, Any]:
        """Get summary of token usage.
        
        Returns:
            Dictionary with token usage summary
        """
        base_summary = {
            "prompt_tokens": self.token_statistics.total_prompt_tokens,
            "completion_tokens": self.token_statistics.total_completion_tokens, 
            "total_tokens": self.token_statistics.total_tokens,
            "total_calls": self.token_statistics.total_calls,
            "successful_calls": self.token_statistics.successful_calls,
            "failed_calls": self.token_statistics.failed_calls,
            "success_rate": self.token_statistics.get_success_rate(),
            "average_tokens_per_call": self.token_statistics.get_average_tokens_per_call(),
            "model": self.model_name
        }
        
        # Add retry statistics if available
        retry_summary = self.token_statistics.get_retry_summary()
        base_summary.update(retry_summary)
        
        return base_summary
    
    def get_or_create_retry_tracker(self, endpoint_id: str) -> RetryTracker:
        """Get or create retry tracker for an endpoint.
        
        Args:
            endpoint_id: API endpoint identifier
            
        Returns:
            RetryTracker instance for the endpoint
        """
        if endpoint_id not in self.retry_trackers:
            self.retry_trackers[endpoint_id] = RetryTracker(endpoint_id=endpoint_id)
        return self.retry_trackers[endpoint_id]
    
    def get_retry_summary(self) -> Dict[str, Any]:
        """Get comprehensive retry statistics summary.
        
        Returns:
            Dictionary with retry statistics across all endpoints
        """
        if not self.retry_trackers:
            return {"total_retries": 0, "total_retry_time": 0, "endpoints_with_retries": 0}
        
        total_retries = 0
        total_retry_time = 0.0
        total_wait_time = 0.0
        endpoints_with_retries = 0
        
        endpoint_summaries = []
        
        for endpoint_id, tracker in self.retry_trackers.items():
            tracker.complete_operation()  # Ensure operation is marked complete
            stats = tracker.get_comprehensive_stats()
            
            total_retries += stats["total_retries"]
            total_retry_time += stats["total_retry_time"]
            total_wait_time += stats["total_wait_time"]
            
            if stats["total_retries"] > 0:
                endpoints_with_retries += 1
                endpoint_summaries.append({
                    "endpoint_id": endpoint_id,
                    "retries": stats["total_retries"],
                    "retry_time": stats["total_retry_time"]
                })
        
        # Sort endpoints by retry count (most retried first)
        endpoint_summaries.sort(key=lambda x: x["retries"], reverse=True)
        
        return {
            "total_retries": total_retries,
            "total_retry_time": total_retry_time,
            "total_wait_time": total_wait_time,
            "endpoints_with_retries": endpoints_with_retries,
            "total_endpoints": len(self.retry_trackers),
            "retry_rate": endpoints_with_retries / max(len(self.retry_trackers), 1),
            "average_retries_per_endpoint": total_retries / max(len(self.retry_trackers), 1),
            "most_retried_endpoints": endpoint_summaries[:3]  # Top 3
        }
    
    def has_token_usage(self) -> bool:
        """Check if any token usage data is available.
        
        Returns:
            True if token usage data is available
        """
        return self.token_statistics.total_calls > 0
    
    def add_test_cases(self, count: int) -> None:
        """Add test case count to total.
        
        Args:
            count: Number of test cases to add
        """
        self.total_test_cases += count


class GeneratorEngine:
    """Main engine for coordinating test case generation."""
    
    def __init__(self, config: CaseCraftConfig, console: Optional[Console] = None, 
                 verbose: bool = False, quiet: bool = False, provider_instance: Optional[Any] = None):
        """Initialize generator engine.
        
        Args:
            config: CaseCraft configuration
            console: Rich console for output
            verbose: Enable verbose output
            quiet: Enable quiet mode (warnings/errors only)
            provider_instance: Provider instance for LLM operations
        """
        self.config = config
        self.console = console or Console()
        self.verbose = verbose
        self.quiet = quiet
        self.provider_instance = provider_instance
        
        # Initialize logging and error handling
        # In quiet mode, we only show critical messages
        self.logger = CaseCraftLogger(
            "generator", 
            console, 
            verbose=verbose,
            show_timestamp=True,
            show_level=True
        )
        self.error_handler = ErrorHandler(console, verbose=verbose)
        
        # Initialize components
        api_parse_timeout = int(os.getenv("CASECRAFT_API_PARSE_TIMEOUT", str(DEFAULT_API_PARSE_TIMEOUT)))
        self.api_parser = APIParser(timeout=api_parse_timeout)
        self.state_manager = EnhancedStateManager()
        self._llm_client: Optional[LLMClient] = None
        self._test_generator: Optional[TestCaseGenerator] = None
    
    async def generate(
        self,
        source: str,
        include_tags: Optional[List[str]] = None,
        exclude_tags: Optional[List[str]] = None,
        include_paths: Optional[List[str]] = None,
        exclude_paths: Optional[List[str]] = None,
        include_methods: Optional[List[str]] = None,
        exclude_methods: Optional[List[str]] = None,
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
            include_methods: HTTP methods to include
            exclude_methods: HTTP methods to exclude
            force: Force regenerate all endpoints
            dry_run: Preview mode without LLM calls
            
        Returns:
            Generation result
            
        Raises:
            GeneratorError: If generation fails
        """
        start_time = time.time()
        result = GenerationResult()
        
        logging_context = LoggingContext(self.logger, "test_case_generation", source=source)
        with logging_context as op_logger:
            try:
                # Parse API documentation
                op_logger.progress(f"Loading API documentation from: {source}")
                with ErrorContext(self.error_handler, "API documentation loading"):
                    api_spec, api_content = await self._load_api_spec(source)
                    result.api_spec = api_spec
                
                # Apply filters
                if include_tags or exclude_tags or include_paths or exclude_paths or include_methods or exclude_methods:
                    original_count = len(api_spec.endpoints)
                    self.logger.file_only(f"Applying filters: include_tags={include_tags}, exclude_tags={exclude_tags}, "
                                    f"include_paths={include_paths}, exclude_paths={exclude_paths}, "
                                    f"include_methods={include_methods}, exclude_methods={exclude_methods}", level="DEBUG")
                    
                    if not self.quiet:
                        filters = []
                        if include_methods:
                            filters.append(f"methods={','.join(include_methods)}")
                        if exclude_methods:
                            filters.append(f"exclude_methods={','.join(exclude_methods)}")
                        if include_paths:
                            filters.append(f"paths included")
                        if include_tags:
                            filters.append(f"tags included")
                        
                        if filters:
                            self.console.print(f"[blue]🔍 Applying filters: {', '.join(filters)}[/blue]")
                        else:
                            self.console.print("[blue]🔍 Applying filters...[/blue]")
                    
                    api_spec = self.api_parser.filter_endpoints(
                        api_spec, include_tags, exclude_tags, include_paths, exclude_paths,
                        include_methods, exclude_methods
                    )
                    
                    filtered_count = len(api_spec.endpoints)
                    if not self.quiet:
                        self.console.print(f"[blue]🔍 After filtering: {filtered_count}/{original_count} endpoint(s) to process[/blue]")
                    self.logger.file_only(f"After filtering: {filtered_count}/{original_count} endpoint(s) to process", level="INFO")
                    if filtered_count < original_count:
                        self.logger.file_only(f"Filtered out {original_count - filtered_count} endpoints", level="DEBUG")
                
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
                    if not self.quiet:
                        self.console.print("[green]✨ All endpoints are up to date, no regeneration needed![/green]")
                    # All endpoints up to date is considered success
                    logging_context.set_success(True)
                    return result
                
                # Show batch generation optimization notice
                if len(to_generate) > 10 and not self.quiet:
                    self.console.print(f"[yellow]📊 Detected batch task: {len(to_generate)} endpoints[/yellow]")
                    workers_text = "1" if self.config.processing.workers == 1 else str(self.config.processing.workers)
                    self.console.print(f"[dim]   • Workers: {workers_text}[/dim]")
                    self.console.print(f"[dim]   • Estimated time: ~{self._estimate_generation_time(len(to_generate))} minutes[/dim]")
                
                if dry_run:
                    if not self.quiet:
                        self.console.print("[yellow]🔍 Preview completed - no test cases generated[/yellow]")
                    # Dry run is considered success (no actual generation expected)
                    logging_context.set_success(True)
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
                
                # Determine business success based on actual results
                business_success = self._determine_business_success(result, to_generate, dry_run)
                logging_context.set_success(business_success)
                
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
            # Log loading start
            self.logger.file_only(f"📂 Loading API documentation from: {source}")
            
            # Detect source type
            is_url = self.api_parser._is_url(source)
            self.logger.file_only(f"Source type: {'URL' if is_url else 'Local file'}", level="DEBUG")
            
            api_spec = await self.api_parser.parse_from_source(source)
            
            # Log format detection
            if hasattr(api_spec, 'openapi'):
                format_info = f"OpenAPI {api_spec.openapi if hasattr(api_spec, 'openapi') else '3.x'}"
            else:
                format_info = "Swagger 2.0"
            self.logger.file_only(f"Document format detected: {format_info}", level="DEBUG")
            
            # Get content for hashing
            if is_url:
                api_content = await self.api_parser._fetch_from_url(source)
                self.logger.file_only(f"Fetched {len(api_content)} bytes from URL", level="DEBUG")
            else:
                api_content = await self.api_parser._read_from_file(source)
                self.logger.file_only(f"Read {len(api_content)} bytes from file", level="DEBUG")
            
            # Log endpoint statistics to file
            self.logger.file_only(f"📊 Loaded {len(api_spec.endpoints)} endpoints from API specification", level="INFO")
            self.logger.file_only(f"Endpoints by method: " + 
                            ", ".join(f"{method}: {count}" 
                                    for method, count in self._count_endpoints_by_method(api_spec).items()), level="DEBUG")
            
            self.console.print(f"\n[green]✓[/green] API documentation loaded successfully")
            self.console.print(f"  📄 Name: [bold]{api_spec.title}[/bold]")
            self.console.print(f"  🎯 Version: v{api_spec.version}")
            self.console.print(f"  📊 Endpoints: {len(api_spec.endpoints)}\n")
            
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
        action = "Will generate" if dry_run else "Generating"
        
        if to_generate:
            self.console.print(f"[yellow]📋 {action} test cases for {len(to_generate)} endpoints:[/yellow]")
            for endpoint in to_generate[:5]:  # Show first 5
                self.console.print(f"  • {endpoint.method:6} {endpoint.path}")
            
            if len(to_generate) > 5:
                self.console.print(f"  ... and {len(to_generate) - 5} more endpoints")
        
        if to_skip:
            self.console.print(f"\n[dim]⏭️ Skipping {len(to_skip)} unchanged endpoints[/dim]")
        
        self.console.print()
    
    async def _initialize_llm_components(self, api_version: Optional[str] = None) -> None:
        """Initialize LLM client and test generator.
        
        Args:
            api_version: API version string
        """
        try:
            if self.provider_instance:
                # Use the provided provider instance
                from casecraft.core.generation.llm_client import LLMClient
                self._llm_client = LLMClient(provider=self.provider_instance)
            else:
                # Provider instance is required
                self.logger.error(f"Provider instance is None. self.provider_instance={self.provider_instance}")
                raise GeneratorError("Provider instance is required")
                
            self._test_generator = TestCaseGenerator(self._llm_client, api_version, console=self.console)
            
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
        
        # Always show progress bar for overall progress
        # The streaming display will show below it
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=self.console,
            transient=False  # Keep progress bar visible after completion
        ) as progress:
            
            task = progress.add_task("🚀 Generating test cases...", total=100)  # Use percentage
            
            # Create tasks for concurrent processing with rate limiting
            tasks = [
                controller.execute(
                    self._generate_endpoint_test_cases(
                        endpoint, None, progress, task, result,
                        endpoint_index=i, total_endpoints=len(endpoints)
                    )
                )
                for i, endpoint in enumerate(endpoints)
            ]
            
            # Execute all tasks
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _generate_endpoint_test_cases(
        self,
        endpoint: APIEndpoint,
        semaphore: Optional[asyncio.Semaphore],
        progress: Progress,
        task_id: TaskID,
        result: GenerationResult,
        endpoint_index: int = 0,
        total_endpoints: int = 1
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
            # Create enhanced progress callback for streaming updates
            def update_progress(stream_progress: float, retry_info: Optional[Dict[str, Any]] = None):
                # Calculate total progress: endpoint progress + stream progress within endpoint
                total_progress = (endpoint_index + stream_progress) / total_endpoints
                
                # Build enhanced progress description with retry information
                base_description = f"Generating test cases: {endpoint_id}"
                
                if retry_info:
                    generation_retry = retry_info.get('generation_retry', {})
                    http_retry = retry_info.get('http_retry', {})
                    
                    retry_parts = []
                    
                    # Enhanced generation retry display
                    if generation_retry.get('current', 0) > 0:
                        attempt_phase = generation_retry.get('attempt_phase', 'retry')
                        retry_parts.append(f"{attempt_phase} {generation_retry['current']}/{generation_retry['total']}")
                        
                        # Show last error hint if available
                        last_error = generation_retry.get('last_error')
                        if last_error and len(last_error) > 0:
                            error_hint = last_error.split(':')[0] if ':' in last_error else last_error[:20]
                            retry_parts.append(f"({error_hint})")
                    
                    # Enhanced HTTP retry display with timing
                    if http_retry.get('current', 0) > 0:
                        retry_parts.append(f"HTTP {http_retry['current']}/{http_retry['total']}")
                    
                    if retry_parts:
                        retry_text = f" [{', '.join(retry_parts)}]"
                        base_description += retry_text
                
                # Non-blocking progress update with error handling
                try:
                    progress.update(
                        task_id, 
                        completed=int(total_progress * 100),
                        description=base_description
                    )
                except Exception as e:
                    # Log but don't fail on progress update errors
                    self.logger.file_only(f"Progress update error: {e}", level="DEBUG")
            
            # Generate test cases with progress callback
            generation_result = await self._test_generator.generate_test_cases(
                endpoint,
                progress_callback=update_progress if self.config.llm.stream else None
            )
            collection = generation_result.test_cases
            
            # Add token usage to result statistics
            if generation_result.token_usage:
                # Format token usage for better display
                usage = generation_result.token_usage
                self.logger.file_only(
                    f"📊 Token Usage - Model: {usage.model} | "
                    f"Input: {usage.prompt_tokens:,} | "
                    f"Output: {usage.completion_tokens:,} | "
                    f"Total: {usage.total_tokens:,} | "
                    f"Endpoint: {usage.endpoint_id}",
                    level="INFO"
                )
                result.add_token_usage(generation_result.token_usage, success=True)
                self.logger.file_only(f"Result has_token_usage: {result.has_token_usage()}, total_calls: {result.token_statistics.total_calls}", level="DEBUG")
            else:
                self.logger.file_only("No token usage data available from generation_result", level="WARNING")
            
            # Show detailed progress with token usage
            if generation_result.token_usage:
                # Show raw token count
                tokens = generation_result.token_usage.total_tokens
                token_info = f" ({tokens} tokens)"
            else:
                token_info = ""
            
            # Brief success log with friendly formatting
            self.console.print(f"  [green]✓[/green] Generated [bold]{len(collection.test_cases)}[/bold] test cases - {endpoint_id} [dim]{token_info}[/dim]")
            
            # Save to file
            output_file = await self._save_test_cases(collection)
            
            # Log file write completion
            self.console.print(f"  [blue]📝[/blue] Written to file: [cyan]{output_file.name}[/cyan]")
            
            # Update state
            await self.state_manager.mark_endpoint_generated(
                endpoint,
                len(collection.test_cases),
                str(output_file)
            )
            
            result.generated_count += 1
            result.add_test_cases(len(collection.test_cases))
            result.generated_files.append(str(output_file))
            
            # Final update to mark this endpoint as complete
            # Use actual completion count instead of endpoint_index for concurrent execution
            completed_count = result.generated_count + result.failed_count + result.skipped_count
            progress.update(
                task_id, 
                completed=int((completed_count / total_endpoints) * 100),
                description=f"Completed: {endpoint_id}"
            )
            
        except (TestGeneratorError, LLMError, LLMRateLimitError) as e:
            result.failed_count += 1
            result.failed_endpoints.append(f"{endpoint_id}: {str(e)}")
            
            # Update progress on failure - based on actual success count
            if result.generated_count == 0:
                # Stop progress bar completely on total failure to prevent redraw
                progress.stop()
            else:
                # If partial success, update progress
                current_progress = int((result.generated_count / total_endpoints) * 100)
                progress.update(
                    task_id,
                    completed=current_progress
                    # Don't update description on failure, keep original "🚀 Generating test cases..."
                )
            
            # Then show error messages
            self.console.print(f"  [red]✗[/red] Generation failed - {endpoint_id}")
            
            # Check if this is a friendly ProviderError
            if isinstance(e, ProviderError):
                # Show friendly error message
                friendly_msg = e.get_friendly_message()
                for line in friendly_msg.split('\n'):
                    if line.strip():
                        self.console.print(f"    [dim red]{line}[/dim red]")
                
                # Log detailed error information for debugging
                self.logger.file_only(f"Provider error for {endpoint_id}: {friendly_msg}", level="ERROR")
            else:
                # Show detailed error in verbose mode, truncated otherwise
                if self.verbose:
                    # Show full error details in verbose mode
                    full_error = str(e)
                    self.console.print(f"    [dim red]Detailed error: {full_error}[/dim red]")
                    
                    # Log detailed error information for debugging
                    self.logger.file_only(f"LLM generation failed for {endpoint_id}: {full_error}", level="ERROR")
                    
                    # If this is an LLMError, try to extract more details
                    if isinstance(e, (LLMError, LLMRateLimitError)):
                        self.logger.file_only(f"LLM error type: {type(e).__name__}", level="DEBUG")
                        if hasattr(e, '__cause__') and e.__cause__:
                            self.logger.file_only(f"Underlying cause: {e.__cause__}", level="DEBUG")
                else:
                    # Show error in normal mode with proper wrapping
                    error_msg = str(e)
                    self.console.print(f"    [dim red]Reason: {error_msg}[/dim red]", soft_wrap=True)
            
        except Exception as e:
            result.failed_count += 1
            result.failed_endpoints.append(f"{endpoint_id}: Unexpected error: {str(e)}")
            
            # Update progress on failure - based on actual success count
            if result.generated_count == 0:
                # Stop progress bar completely on total failure to prevent redraw
                progress.stop()
            else:
                # If partial success, update progress
                current_progress = int((result.generated_count / total_endpoints) * 100)
                progress.update(
                    task_id,
                    completed=current_progress
                    # Don't update description on failure, keep original "🚀 Generating test cases..."
                )
            
            # Then show error messages
            self.console.print(f"  [red]✗[/red] Unexpected error - {endpoint_id}")
            
            # Show detailed error in verbose mode, truncated otherwise
            if self.verbose:
                # Show full error details in verbose mode
                full_error = str(e)
                self.console.print(f"    [dim red]Detailed error: {full_error}[/dim red]")
                
                # Log detailed error information for debugging
                self.logger.file_only(f"Unexpected error for {endpoint_id}: {full_error}", level="ERROR")
                self.logger.file_only(f"Error type: {type(e).__name__}", level="DEBUG")
                if hasattr(e, '__cause__') and e.__cause__:
                    self.logger.file_only(f"Underlying cause: {e.__cause__}", level="DEBUG")
            else:
                # Show error in normal mode with proper wrapping
                error_msg = str(e)
                self.console.print(f"    [dim red]Error: {error_msg}[/dim red]", soft_wrap=True)
    
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
        
        # Log save operation
        self.logger.file_only(f"💾 Saving {len(collection.test_cases)} test cases to: {output_file}")
        
        # Save JSON
        json_content = collection.model_dump_json(indent=2)
        output_file.write_text(json_content, encoding='utf-8')
        
        # Log file size
        file_size = len(json_content.encode('utf-8'))
        self.logger.file_only(f"File saved successfully ({file_size:,} bytes)", level="DEBUG")
        
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
        
        # Prepare template variables
        template_vars = {
            'method': collection.method.lower(),
            'path_slug': path_slug,
            'endpoint_id': collection.endpoint_id.replace(":", "_").replace("/", "_")
        }
        
        # Add timestamp if enabled
        if self.config.output.include_timestamp:
            from datetime import datetime
            timestamp = datetime.now().strftime(self.config.output.timestamp_format)
            template_vars['timestamp'] = timestamp
        
        # Apply template
        template = self.config.output.filename_template
        
        # Handle timestamp in template
        if self.config.output.include_timestamp:
            # If template doesn't include timestamp, add it before extension
            if '{timestamp}' not in template:
                base_template, ext = template.rsplit('.', 1) if '.' in template else (template, '')
                template = f"{base_template}_{{timestamp}}" + (f".{ext}" if ext else "")
        
        filename = template.format(**template_vars)
        
        # Ensure .json extension
        if not filename.endswith('.json'):
            filename += '.json'
        
        return filename
    
    def _count_endpoints_by_method(self, api_spec: APISpecification) -> Dict[str, int]:
        """Count endpoints by HTTP method.
        
        Args:
            api_spec: API specification
            
        Returns:
            Dictionary of method counts
        """
        from collections import Counter
        return dict(Counter(ep.method for ep in api_spec.endpoints))
    
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
    
    def _determine_business_success(
        self,
        result: GenerationResult,
        to_generate: List[APIEndpoint],
        dry_run: bool
    ) -> bool:
        """Determine business success based on actual generation results.
        
        Args:
            result: Generation result with statistics
            to_generate: List of endpoints that were supposed to be generated
            dry_run: Whether this was a dry run
            
        Returns:
            True if the operation was successful from a business perspective
        """
        # For dry runs, success is determined by whether we could analyze the endpoints
        if dry_run:
            return True
        
        # If there were endpoints to generate, success means at least one was generated
        if to_generate:
            return result.generated_count > 0
        
        # If no endpoints needed generation, that's also success
        return True