"""Concurrency utilities for CaseCraft."""

import asyncio
import time
from asyncio import Semaphore
from typing import Any, Awaitable, Callable, List, Optional, TypeVar

T = TypeVar('T')


class RateLimiter:
    """Rate limiter for controlling request frequency."""
    
    def __init__(self, calls_per_second: float):
        """Initialize rate limiter.
        
        Args:
            calls_per_second: Maximum calls allowed per second
        """
        self.calls_per_second = calls_per_second
        self.min_interval = 1.0 / calls_per_second if calls_per_second > 0 else 0
        self.last_call_time = 0.0
        self._lock = asyncio.Lock()
    
    async def acquire(self) -> None:
        """Acquire permission to make a call, waiting if necessary."""
        async with self._lock:
            current_time = time.time()
            time_since_last_call = current_time - self.last_call_time
            
            if time_since_last_call < self.min_interval:
                wait_time = self.min_interval - time_since_last_call
                await asyncio.sleep(wait_time)
            
            self.last_call_time = time.time()


class ConcurrencyController:
    """Controls concurrent execution with semaphore and rate limiting."""
    
    def __init__(
        self,
        max_workers: int = 4,
        rate_limit: Optional[float] = None
    ):
        """Initialize concurrency controller.
        
        Args:
            max_workers: Maximum concurrent workers
            rate_limit: Optional rate limit (calls per second)
        """
        self.semaphore = Semaphore(max_workers)
        self.rate_limiter = RateLimiter(rate_limit) if rate_limit else None
    
    async def execute(self, coro: Awaitable[T]) -> T:
        """Execute coroutine with concurrency control.
        
        Args:
            coro: Coroutine to execute
            
        Returns:
            Coroutine result
        """
        async with self.semaphore:
            if self.rate_limiter:
                await self.rate_limiter.acquire()
            
            return await coro


async def execute_with_concurrency(
    tasks: List[Awaitable[T]],
    max_workers: int = 4,
    rate_limit: Optional[float] = None,
    return_exceptions: bool = True
) -> List[T]:
    """Execute tasks with controlled concurrency.
    
    Args:
        tasks: List of coroutines to execute
        max_workers: Maximum concurrent workers
        rate_limit: Optional rate limit (calls per second)
        return_exceptions: Whether to return exceptions instead of raising
        
    Returns:
        List of results (may include exceptions if return_exceptions=True)
    """
    if not tasks:
        return []
    
    controller = ConcurrencyController(max_workers, rate_limit)
    
    # Wrap tasks with concurrency control
    controlled_tasks = [controller.execute(task) for task in tasks]
    
    # Execute all tasks
    return await asyncio.gather(*controlled_tasks, return_exceptions=return_exceptions)


async def execute_with_retry(
    coro: Awaitable[T],
    max_retries: int = 3,
    retry_delay: float = 1.0,
    exponential_backoff: bool = True,
    retry_exceptions: tuple = (Exception,)
) -> T:
    """Execute coroutine with retry logic.
    
    Args:
        coro: Coroutine to execute
        max_retries: Maximum retry attempts
        retry_delay: Initial delay between retries
        exponential_backoff: Whether to use exponential backoff
        retry_exceptions: Exception types to retry on
        
    Returns:
        Coroutine result
        
    Raises:
        Exception: Last exception if all retries fail
    """
    last_exception = None
    
    for attempt in range(max_retries + 1):
        try:
            return await coro
        except retry_exceptions as e:
            last_exception = e
            
            if attempt == max_retries:
                raise
            
            # Calculate delay
            if exponential_backoff:
                delay = retry_delay * (2 ** attempt)
            else:
                delay = retry_delay
            
            await asyncio.sleep(delay)
    
    # This should never be reached due to the raise above
    raise last_exception


class TaskBatch:
    """Manages batches of tasks for controlled execution."""
    
    def __init__(self, batch_size: int = 10):
        """Initialize task batch.
        
        Args:
            batch_size: Number of tasks per batch
        """
        self.batch_size = batch_size
        self.tasks: List[Awaitable] = []
        self.results: List[Any] = []
    
    def add_task(self, task: Awaitable) -> None:
        """Add task to batch.
        
        Args:
            task: Task to add
        """
        self.tasks.append(task)
    
    async def execute_batch(
        self,
        max_workers: int = 4,
        return_exceptions: bool = True
    ) -> List[Any]:
        """Execute current batch of tasks.
        
        Args:
            max_workers: Maximum concurrent workers
            return_exceptions: Whether to return exceptions
            
        Returns:
            Batch results
        """
        if not self.tasks:
            return []
        
        # Split tasks into batches
        batches = [
            self.tasks[i:i + self.batch_size]
            for i in range(0, len(self.tasks), self.batch_size)
        ]
        
        all_results = []
        
        for batch in batches:
            batch_results = await execute_with_concurrency(
                batch,
                max_workers=max_workers,
                return_exceptions=return_exceptions
            )
            all_results.extend(batch_results)
        
        self.results.extend(all_results)
        self.tasks.clear()
        
        return all_results
    
    def get_all_results(self) -> List[Any]:
        """Get all accumulated results.
        
        Returns:
            All results from executed batches
        """
        return self.results.copy()
    
    def clear(self) -> None:
        """Clear all tasks and results."""
        self.tasks.clear()
        self.results.clear()


async def timeout_wrapper(
    coro: Awaitable[T],
    timeout_seconds: float,
    timeout_message: Optional[str] = None
) -> T:
    """Wrap coroutine with timeout.
    
    Args:
        coro: Coroutine to execute
        timeout_seconds: Timeout in seconds
        timeout_message: Custom timeout message
        
    Returns:
        Coroutine result
        
    Raises:
        asyncio.TimeoutError: If timeout is exceeded
    """
    try:
        return await asyncio.wait_for(coro, timeout=timeout_seconds)
    except asyncio.TimeoutError:
        if timeout_message:
            raise asyncio.TimeoutError(timeout_message)
        raise


class WorkerPool:
    """Manages a pool of worker tasks."""
    
    def __init__(self, worker_count: int = 4):
        """Initialize worker pool.
        
        Args:
            worker_count: Number of worker tasks
        """
        self.worker_count = worker_count
        self.task_queue: asyncio.Queue = asyncio.Queue()
        self.workers: List[asyncio.Task] = []
        self.results: List[Any] = []
        self._shutdown = False
    
    async def start(self) -> None:
        """Start worker tasks."""
        for i in range(self.worker_count):
            worker = asyncio.create_task(self._worker(f"worker-{i}"))
            self.workers.append(worker)
    
    async def add_task(self, coro: Awaitable) -> None:
        """Add task to queue.
        
        Args:
            coro: Coroutine to execute
        """
        await self.task_queue.put(coro)
    
    async def shutdown(self, wait: bool = True) -> None:
        """Shutdown worker pool.
        
        Args:
            wait: Whether to wait for workers to finish
        """
        self._shutdown = True
        
        # Add sentinel values to wake up workers
        for _ in self.workers:
            await self.task_queue.put(None)
        
        if wait:
            await asyncio.gather(*self.workers, return_exceptions=True)
        else:
            for worker in self.workers:
                worker.cancel()
    
    async def _worker(self, name: str) -> None:
        """Worker task implementation.
        
        Args:
            name: Worker name for debugging
        """
        while not self._shutdown:
            try:
                task = await self.task_queue.get()
                
                if task is None:  # Sentinel value
                    break
                
                result = await task
                self.results.append(result)
                
                self.task_queue.task_done()
                
            except Exception as e:
                # Log error but continue working
                self.results.append(e)
                self.task_queue.task_done()
    
    def get_results(self) -> List[Any]:
        """Get all worker results.
        
        Returns:
            List of results from all workers
        """
        return self.results.copy()