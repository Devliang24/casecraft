"""Token usage and cost calculation models."""

from typing import Dict, Optional
from dataclasses import dataclass
from decimal import Decimal


@dataclass
class TokenUsage:
    """Token usage data for a single LLM API call."""
    
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    model: str = ""
    endpoint_id: str = ""
    
    def __post_init__(self):
        """Validate and normalize token counts."""
        # Ensure total_tokens is consistent
        if self.total_tokens == 0 and (self.prompt_tokens > 0 or self.completion_tokens > 0):
            self.total_tokens = self.prompt_tokens + self.completion_tokens
        
        # Validate non-negative values
        if self.prompt_tokens < 0 or self.completion_tokens < 0 or self.total_tokens < 0:
            raise ValueError("Token counts must be non-negative")


@dataclass 
class TokenStatistics:
    """Aggregated token usage statistics."""
    
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    
    def add_usage(self, usage: TokenUsage, success: bool = True) -> None:
        """Add token usage from a single API call.
        
        Args:
            usage: Token usage data
            success: Whether the API call was successful
        """
        self.total_prompt_tokens += usage.prompt_tokens
        self.total_completion_tokens += usage.completion_tokens
        self.total_tokens += usage.total_tokens
        self.total_calls += 1
        
        if success:
            self.successful_calls += 1
        else:
            self.failed_calls += 1
    
    def get_average_tokens_per_call(self) -> float:
        """Get average total tokens per successful call."""
        if self.successful_calls == 0:
            return 0.0
        return self.total_tokens / self.successful_calls
    
    def get_success_rate(self) -> float:
        """Get success rate of API calls."""
        if self.total_calls == 0:
            return 0.0
        return self.successful_calls / self.total_calls


class CostCalculator:
    """Calculate costs based on token usage and pricing."""
    
    # BigModel GLM-4.5-X pricing (2025年最新定价)
    # 价格单位：USD per 1M tokens
    PRICING = {
        "glm-4.5-x": {
            "input": Decimal("0.50"),   # $0.50 per 1M input tokens
            "output": Decimal("2.00")   # $2.00 per 1M output tokens  
        },
        "glm-4.5-air": {
            "input": Decimal("0.14"),   # $0.14 per 1M input tokens
            "output": Decimal("0.86")   # $0.86 per 1M output tokens
        }
    }
    
    @classmethod
    def calculate_cost(
        cls, 
        usage: TokenUsage, 
        model: Optional[str] = None
    ) -> Decimal:
        """Calculate cost for token usage.
        
        Args:
            usage: Token usage data
            model: Model name (if different from usage.model)
            
        Returns:
            Cost in USD
        """
        model_name = model or usage.model or "glm-4.5-x"
        
        # Normalize model name
        if "glm-4.5" in model_name.lower():
            if "air" in model_name.lower():
                pricing_key = "glm-4.5-air"
            else:
                pricing_key = "glm-4.5-x"
        else:
            # Default to glm-4.5-x pricing
            pricing_key = "glm-4.5-x"
        
        if pricing_key not in cls.PRICING:
            # Unknown model, use default pricing
            pricing_key = "glm-4.5-x"
        
        pricing = cls.PRICING[pricing_key]
        
        # Calculate cost (pricing is per 1M tokens)
        input_cost = (Decimal(usage.prompt_tokens) / Decimal(1_000_000)) * pricing["input"]
        output_cost = (Decimal(usage.completion_tokens) / Decimal(1_000_000)) * pricing["output"]
        
        return input_cost + output_cost
    
    @classmethod
    def calculate_total_cost(cls, statistics: TokenStatistics, model: str = "glm-4.5-x") -> Decimal:
        """Calculate total cost from aggregated statistics.
        
        Args:
            statistics: Aggregated token statistics
            model: Model name for pricing
            
        Returns:
            Total cost in USD
        """
        # Create a fake TokenUsage for calculation
        total_usage = TokenUsage(
            prompt_tokens=statistics.total_prompt_tokens,
            completion_tokens=statistics.total_completion_tokens,
            total_tokens=statistics.total_tokens,
            model=model
        )
        
        return cls.calculate_cost(total_usage, model)
    
    @classmethod
    def format_cost(cls, cost: Decimal) -> str:
        """Format cost for display.
        
        Args:
            cost: Cost in USD
            
        Returns:
            Formatted cost string
        """
        if cost < Decimal("0.01"):
            return f"${cost:.4f} USD"
        else:
            return f"${cost:.4f} USD"
    
    @classmethod
    def get_model_pricing_info(cls, model: str = "glm-4.5-x") -> Dict[str, str]:
        """Get pricing information for a model.
        
        Args:
            model: Model name
            
        Returns:
            Dict with input/output pricing info
        """
        # Normalize model name
        if "glm-4.5" in model.lower():
            if "air" in model.lower():
                pricing_key = "glm-4.5-air"
            else:
                pricing_key = "glm-4.5-x"
        else:
            pricing_key = "glm-4.5-x"
        
        if pricing_key not in cls.PRICING:
            pricing_key = "glm-4.5-x"
        
        pricing = cls.PRICING[pricing_key]
        
        return {
            "input_price": f"${pricing['input']}/1M tokens",
            "output_price": f"${pricing['output']}/1M tokens",
            "model": pricing_key
        }