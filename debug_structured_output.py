#!/usr/bin/env python3
"""Debug script for testing structured output with different providers."""

import asyncio
import json
import os
from casecraft.core.providers.qwen_provider import QwenProvider
from casecraft.core.providers.kimi_provider import KimiProvider
from casecraft.core.providers.glm_provider import GLMProvider
from casecraft.core.providers.base import ProviderConfig


async def test_provider(provider_class, provider_name, config):
    """Test a single provider's structured output capability."""
    print(f"\n{'='*60}")
    print(f"Testing {provider_name} Provider")
    print(f"{'='*60}")
    
    # Create provider instance
    provider = provider_class(config)
    
    # Simple test prompt that should return JSON
    prompt = """Generate a test case in JSON format with the following structure:
{
  "test_id": 1,
  "name": "Test Name",
  "description": "Test Description",
  "status": 200
}

Return only the JSON object, no explanation."""
    
    system_prompt = "You are a JSON generator. Always return valid JSON format without any markdown or explanation."
    
    try:
        # Test generation
        print(f"Config: use_structured_output={config.use_structured_output}")
        print(f"Model: {config.model}")
        print("Sending request...")
        
        response = await provider.generate(
            prompt=prompt,
            system_prompt=system_prompt
        )
        
        print(f"\n✅ Response received!")
        print(f"Response length: {len(response.content)} characters")
        print(f"\n--- Raw Response Content ---")
        print(response.content[:500] if len(response.content) > 500 else response.content)
        
        # Try to parse as JSON
        try:
            parsed = json.loads(response.content)
            print(f"\n✅ Successfully parsed as JSON!")
            print(f"JSON structure: {json.dumps(parsed, indent=2)[:200]}...")
        except json.JSONDecodeError as e:
            print(f"\n❌ Failed to parse as JSON: {e}")
            print(f"First 100 chars: {repr(response.content[:100])}")
            
    except Exception as e:
        print(f"\n❌ Error during generation: {e}")
    finally:
        await provider.close()


async def main():
    """Test all providers."""
    
    # Qwen configuration (known to work)
    qwen_config = ProviderConfig(
        name="qwen",
        model="qwen-flash",
        api_key=os.getenv("CASECRAFT_QWEN_API_KEY", "sk-c9ab4ff814bd46b8a9a32299a87d1f43"),
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        use_structured_output=True,
        timeout=30
    )
    
    # Kimi configuration
    kimi_config = ProviderConfig(
        name="kimi",
        model="kimi-k2-turbo-preview",
        api_key=os.getenv("CASECRAFT_KIMI_API_KEY", "sk-FxANSMmm0n8arWtdvvlQ3iYWuZurSVBS1Iax7nH5xj1293sy"),
        base_url="https://api.moonshot.cn/v1",
        use_structured_output=True,
        timeout=30
    )
    
    # GLM configuration
    glm_config = ProviderConfig(
        name="glm",
        model="glm-4.5-x",
        api_key=os.getenv("CASECRAFT_GLM_API_KEY", "db474e8a869844bbbdcf1a111a5eafa4.0SY1uazDVWJQZPHA"),
        base_url="https://open.bigmodel.cn/api/paas/v4",
        use_structured_output=True,
        timeout=30
    )
    
    # Test each provider
    await test_provider(QwenProvider, "Qwen", qwen_config)
    await test_provider(KimiProvider, "Kimi", kimi_config)
    await test_provider(GLMProvider, "GLM", glm_config)
    
    print(f"\n{'='*60}")
    print("Testing Complete!")
    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())