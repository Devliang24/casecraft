"""Test case generator using LLM."""

import json
import os
import asyncio
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

from jsonschema import ValidationError, validate
from pydantic import ValidationError as PydanticValidationError

from casecraft.core.generation.llm_client import LLMClient, LLMError
from casecraft.core.parsing.headers_analyzer import HeadersAnalyzer
from casecraft.core.analysis import PathAnalyzer, SmartDescriptionGenerator, CriticalityAnalyzer
from casecraft.core.analysis.constants import METHOD_BASE_COUNTS, COMPLEXITY_THRESHOLDS, TEST_TYPE_RATIOS, MIN_TEST_COUNTS, MAX_TEST_COUNTS
from casecraft.models.api_spec import APIEndpoint
from casecraft.models.test_case import TestCase, TestCaseCollection, TestType
from casecraft.models.usage import TokenUsage
from casecraft.utils.logging import CaseCraftLogger


class TestGeneratorError(Exception):
    """Test generation related errors."""
    pass


@dataclass
class GenerationResult:
    """Result of test case generation including token usage."""
    
    test_cases: TestCaseCollection
    token_usage: Optional[TokenUsage] = None
    retry_count: int = 0  # Number of retries performed


class TestCaseGenerator:
    """Generates test cases for API endpoints using LLM."""
    
    def __init__(self, llm_client: LLMClient, api_version: Optional[str] = None, console=None):
        """Initialize test case generator.
        
        Args:
            llm_client: LLM client instance
            api_version: API version string
            console: Optional Rich console for output (helps with progress bar coordination)
        """
        self.llm_client = llm_client
        self.api_version = api_version
        self.headers_analyzer = HeadersAnalyzer()
        self.logger = CaseCraftLogger("test_generator", console=console, show_timestamp=True, show_level=True)
        self._test_case_schema = self._get_test_case_schema()
        
        # 初始化智能分析器
        self.path_analyzer = PathAnalyzer()
        self.description_generator = SmartDescriptionGenerator()
        self.criticality_analyzer = CriticalityAnalyzer()
    
    def _generate_concise_chinese_description(self, endpoint: APIEndpoint) -> str:
        """Generate concise Chinese description for endpoint using smart inference.
        
        Args:
            endpoint: API endpoint
            
        Returns:
            Concise Chinese description
        """
        # 使用智能描述生成器替代硬编码
        return self.description_generator.generate(endpoint)
    
    async def generate_test_cases(self, endpoint: APIEndpoint, progress_callback: Optional[callable] = None) -> GenerationResult:
        """Generate test cases for an API endpoint with intelligent retry mechanism.
        
        Args:
            endpoint: API endpoint to generate tests for
            progress_callback: Optional callback for progress updates
            
        Returns:
            Generation result including test cases and token usage information
            
        Raises:
            TestGeneratorError: If test generation fails after all retries
        """
        max_attempts = 3
        last_error = None
        total_tokens_used = 0
        endpoint_id = endpoint.get_endpoint_id()
        
        # Log start of generation
        self.logger.file_only(f"🔨 Preparing test generation for {endpoint_id}")
        
        # Analyze endpoint complexity
        complexity = self._evaluate_endpoint_complexity(endpoint)
        self.logger.file_only(f"Endpoint complexity: score={complexity['complexity_score']}, level={complexity['complexity_level']}", level="DEBUG")
        
        for attempt in range(max_attempts):
            try:
                # Build prompt - use enhanced version for retries
                if attempt > 0 and last_error:
                    # Log retry attempt
                    retry_msg = f"Retry attempt {attempt + 1}/{max_attempts} for {endpoint_id}"
                    self.logger.info(retry_msg)
                    prompt = self._build_prompt_with_retry_hints(endpoint, last_error, attempt)
                    system_prompt = self._get_system_prompt_with_retry_emphasis()
                else:
                    self.logger.file_only(f"Building prompt for {endpoint_id}", level="DEBUG")
                    prompt = self._build_prompt(endpoint)
                    system_prompt = self._get_system_prompt()
                
                # Log prompt info
                prompt_tokens = len(prompt) // 4  # Rough estimate
                self.logger.file_only(f"Prompt prepared: ~{prompt_tokens} tokens", level="DEBUG")
                
                # Generate with streaming support
                # Check if streaming is enabled (handle both provider and legacy config modes)
                is_streaming = False
                if hasattr(self.llm_client, 'provider') and self.llm_client.provider:
                    is_streaming = getattr(self.llm_client.provider.config, 'stream', False)
                elif hasattr(self.llm_client, 'config') and self.llm_client.config:
                    is_streaming = getattr(self.llm_client.config, 'stream', False)
                
                if is_streaming and attempt == 0:  # Only show streaming on first attempt
                    self.logger.file_only(f"Using streaming mode for {endpoint.get_endpoint_id()}")
                
                # Create enhanced retry-aware progress callback
                retry_aware_callback = None
                if progress_callback:
                    def retry_aware_callback(stream_progress: float, http_retry_info: Optional[Dict[str, Any]] = None):
                        # Enhanced retry info with more detail
                        retry_info = None
                        if attempt > 0 or http_retry_info:
                            retry_info = {
                                'generation_retry': {
                                    'current': attempt + 1 if attempt > 0 else 0,
                                    'total': max_attempts,
                                    'attempt_phase': 'generation',
                                    'last_error': str(last_error)[:50] + '...' if last_error and attempt > 0 else None
                                }
                            }
                            if http_retry_info:
                                retry_info['http_retry'] = http_retry_info
                        
                        # Use non-blocking progress update
                        try:
                            progress_callback(stream_progress, retry_info)
                        except Exception as e:
                            # Don't let progress callback errors break generation
                            self.logger.warning(f"Progress callback error: {e}")
                
                # Phase progress updates for better user feedback
                if progress_callback:
                    try:
                        phase_progress = 0.1 + (attempt * 0.1)  # Each retry starts from higher base
                        retry_aware_callback(phase_progress, None)  # Signal generation start
                    except Exception:
                        pass  # Ignore progress callback errors
                
                response = await self.llm_client.generate(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    progress_callback=retry_aware_callback
                )
                
                # Track token usage across retries
                self.logger.file_only(f"LLM response.usage: {response.usage}", level="DEBUG")
                if response.usage:
                    total_tokens_used += response.usage.get("total_tokens", 0)
                    self.logger.file_only(f"Added tokens, total now: {total_tokens_used}", level="DEBUG")
                
                # Validate response format early
                self._validate_response_format(response.content)
                
                # Parse and validate LLM response
                test_cases = self._parse_llm_response(response.content, endpoint)
                
                # Enhance test cases with response schemas and smart status codes
                test_cases = self._enhance_test_cases(test_cases, endpoint)
                
                # Generate concise Chinese description
                concise_description = self._generate_concise_chinese_description(endpoint)
                
                # Create test case collection with metadata
                collection = TestCaseCollection(
                    endpoint_id=endpoint.get_endpoint_id(),
                    method=endpoint.method,
                    path=endpoint.path,
                    summary=endpoint.summary,
                    description=concise_description,
                    test_cases=test_cases
                )
                
                # Set metadata at collection level
                collection.metadata.llm_model = response.model
                collection.metadata.api_version = self.api_version
                
                # Extract token usage from LLM response (use total from all attempts)
                token_usage = None
                self.logger.file_only(f"Response usage: {response.usage}, total_tokens_used: {total_tokens_used}", level="DEBUG")
                if response.usage or total_tokens_used > 0:
                    token_usage = TokenUsage(
                        prompt_tokens=response.usage.get("prompt_tokens", 0) if response.usage else 0,
                        completion_tokens=response.usage.get("completion_tokens", 0) if response.usage else 0,
                        total_tokens=response.usage.get("total_tokens", 0) if response.usage else 0,
                        model=response.model,
                        endpoint_id=endpoint.get_endpoint_id(),
                        retry_count=attempt  # Record actual attempts made
                    )
                    self.logger.file_only(f"Created TokenUsage: {token_usage}")
                
                # Success! Log generation details
                test_count = len(collection.test_cases)
                positive_count = sum(1 for tc in collection.test_cases if tc.test_type == "positive")
                negative_count = sum(1 for tc in collection.test_cases if tc.test_type == "negative")
                boundary_count = sum(1 for tc in collection.test_cases if tc.test_type == "boundary")
                
                if attempt > 0:
                    self.logger.file_only(f"✨ Successfully generated {test_count} test cases on attempt {attempt + 1} for {endpoint_id}")
                else:
                    self.logger.file_only(f"✨ Successfully generated {test_count} test cases for {endpoint_id}")
                
                self.logger.file_only(f"Test case breakdown: {positive_count} positive, {negative_count} negative, {boundary_count} boundary", level="DEBUG")
                
                return GenerationResult(
                    test_cases=collection,
                    retry_count=attempt,  # Add retry count to result
                    token_usage=token_usage
                )
                
            except (TestGeneratorError, ValidationError, json.JSONDecodeError) as e:
                last_error = str(e)
                self.logger.warning(f"Attempt {attempt + 1} failed for {endpoint.get_endpoint_id()}: {e}")
                
                # Check if we should retry
                if self._should_retry(e) and attempt < max_attempts - 1:
                    self.logger.info(f"Will retry with enhanced prompt for {endpoint.get_endpoint_id()}")
                    await asyncio.sleep(2)  # Brief delay before retry
                    continue
                else:
                    # Final failure - create error with retry statistics
                    error_msg = f"Failed to generate test cases for {endpoint.get_endpoint_id()} after {attempt + 1} attempts: {e}"
                    # Only log as error if it's the final failure after all retries
                    if attempt == max_attempts - 1:
                        self.logger.error(error_msg)
                    else:
                        self.logger.warning(error_msg)
                    
                    # Import here to avoid circular imports
                    from casecraft.core.providers.exceptions import ProviderError
                    
                    # Create error with detailed retry statistics
                    retry_error = ProviderError.create_with_retry_stats(
                        message=error_msg,
                        provider_name="TestGenerator",
                        generation_retries=attempt + 1,
                        generation_max_retries=max_attempts,
                        retry_reasons=[str(e) for e in [last_error] if e]
                    )
                    raise TestGeneratorError(retry_error.get_friendly_message())
            
            except Exception as e:
                # Unexpected error - don't retry, but still include basic retry info
                from casecraft.core.providers.exceptions import ProviderError
                
                retry_error = ProviderError.create_with_retry_stats(
                    message=f"Unexpected error generating test cases for {endpoint.get_endpoint_id()}: {e}",
                    provider_name="TestGenerator",
                    generation_retries=attempt + 1,
                    generation_max_retries=max_attempts,
                    retry_reasons=["Unexpected error"]
                )
                raise TestGeneratorError(retry_error.get_friendly_message())
    
    def _should_retry(self, error: Exception) -> bool:
        """Determine if error is worth retrying.
        
        Args:
            error: The exception that occurred
            
        Returns:
            True if should retry, False otherwise
        """
        error_str = str(error).lower()
        
        # Retry for format/validation errors
        retry_patterns = [
            "validation error",
            "required property",
            "invalid json",
            "failed to parse",
            "test case",
            "at least",
            "header",
            "instead of"
        ]
        
        # Don't retry for these errors
        no_retry_patterns = [
            "authentication",
            "unauthorized",
            "api key",
            "model not found",
            "rate limit",
            "quota"
        ]
        
        # Check if it's a no-retry error first
        for pattern in no_retry_patterns:
            if pattern in error_str:
                return False
        
        # Check if it's a retry-worthy error
        for pattern in retry_patterns:
            if pattern in error_str:
                return True
        
        # Default to retry for unknown errors
        return isinstance(error, (TestGeneratorError, ValidationError, json.JSONDecodeError))
    
    def _validate_response_format(self, content: str) -> None:
        """Validate response format early to catch common errors.
        
        Args:
            content: Response content from LLM
            
        Raises:
            TestGeneratorError: If response format is invalid
        """
        try:
            # Try to parse JSON first
            parsed = json.loads(content)
            
            # Check if it's a dict that looks like headers
            if isinstance(parsed, dict) and not isinstance(parsed, list):
                # Check for common header keys
                header_keys = ['content-type', 'accept', 'authorization', 'user-agent']
                if any(key.lower() in [k.lower() for k in parsed.keys()] for key in header_keys):
                    raise TestGeneratorError(
                        "LLM returned headers object instead of test cases array. "
                        "Expected format: [{test_case_1}, {test_case_2}, ...]"
                    )
                
                # If it's a single test case, we'll handle it in parsing
                if 'test_id' in parsed or 'name' in parsed:
                    self.logger.file_only("Response is a single test case object, will wrap in array", level="WARNING")
            
            # Check if it's an empty response
            if not parsed:
                raise TestGeneratorError("LLM returned empty response")
                
        except json.JSONDecodeError as e:
            # Let the main parser handle this
            self.logger.debug(f"JSON decode error in format validation: {e}")
    
    def _build_prompt_with_retry_hints(self, endpoint: APIEndpoint, last_error: str, attempt: int) -> str:
        """Build enhanced prompt with retry hints based on previous error.
        
        Args:
            endpoint: API endpoint
            last_error: Error message from last attempt
            attempt: Current attempt number
            
        Returns:
            Enhanced prompt string
        """
        base_prompt = self._build_prompt(endpoint)
        
        # Analyze error to provide specific hints
        error_hints = []
        
        if "required property" in last_error or "test_id" in last_error:
            error_hints.append("每个测试用例必须包含: test_id, name, description, method, path, status, test_type")
        
        if "headers" in last_error.lower() and "instead of" in last_error:
            error_hints.append("不要只返回headers，必须返回完整的测试用例数组")
        
        if "json" in last_error.lower():
            error_hints.append("确保返回有效的JSON数组格式")
        
        # Parse specific count requirements from error message
        if "at least" in last_error:
            import re
            # Try to extract specific numbers from error message
            # Pattern: "At least X positive/negative/boundary test cases required, got Y"
            pattern = r"At least (\d+) (\w+) test cases? (?:are )?required.*got (\d+)"
            match = re.search(pattern, last_error)
            if match:
                required_count = match.group(1)
                test_type = match.group(2)
                actual_count = match.group(3)
                error_hints.append(f"强烈建议生成 {required_count} 个或更多 {test_type} 类型的测试用例（当前只有 {actual_count} 个）以确保充分覆盖")
            else:
                # Fallback generic hint
                error_hints.append("建议生成推荐数量的测试用例以确保全面测试覆盖")
            
            # Also get the complexity requirements for this endpoint
            complexity = self._evaluate_endpoint_complexity(endpoint)
            error_hints.append(f"该 {complexity['complexity_level']} 复杂度端点需要：")
            error_hints.append(f"  • 正向测试: {complexity['recommended_counts']['positive'][0]}-{complexity['recommended_counts']['positive'][1]} 个")
            error_hints.append(f"  • 负向测试: {complexity['recommended_counts']['negative'][0]}-{complexity['recommended_counts']['negative'][1]} 个")
            error_hints.append(f"  • 边界测试: {complexity['recommended_counts']['boundary'][0]}-{complexity['recommended_counts']['boundary'][1]} 个")
            error_hints.append(f"  • 总计: {complexity['recommended_counts']['total'][0]}-{complexity['recommended_counts']['total'][1]} 个")
        
        # Build retry hint section
        # Get complexity info for better examples
        complexity = self._evaluate_endpoint_complexity(endpoint)
        min_positive = complexity['recommended_counts']['positive'][0]
        min_negative = complexity['recommended_counts']['negative'][0]
        
        retry_hint = f"""

⚠️ **重试 {attempt + 1}/3 - 上次生成失败**

错误信息: {last_error[:200]}

**特别注意事项:**
{chr(10).join(f"• {hint}" for hint in error_hints)}

**推荐的返回格式示例（建议生成 {min_positive} 个正向 + {min_negative} 个负向测试，全面覆盖更重要）:**
```json
[
  {{
    "test_id": 1,
    "name": "成功创建用户",
    "description": "测试正常的用户注册流程",
    "method": "{endpoint.method}",
    "path": "{endpoint.path}",
    "headers": {{"Content-Type": "application/json"}},
    "body": {{"username": "test", "password": "123456"}},
    "status": 200,
    "test_type": "positive"
  }},
  {{
    "test_id": 2,
    "name": "包含可选字段的成功请求",
    "description": "测试包含所有可选字段的情况",
    "method": "{endpoint.method}",
    "path": "{endpoint.path}",
    "headers": {{"Content-Type": "application/json"}},
    "body": {{"username": "test2", "password": "123456", "email": "test@example.com"}},
    "status": 200,
    "test_type": "positive"
  }},
  {{
    "test_id": 3,
    "name": "缺少必需字段",
    "description": "测试缺少username字段的情况",
    "method": "{endpoint.method}",
    "path": "{endpoint.path}",
    "headers": {{"Content-Type": "application/json"}},
    "body": {{"password": "123456"}},
    "status": 400,
    "test_type": "negative"
  }},
  {{
    "test_id": 4,
    "name": "无效的参数格式",
    "description": "测试参数格式错误的情况",
    "method": "{endpoint.method}",
    "path": "{endpoint.path}",
    "headers": {{"Content-Type": "application/json"}},
    "body": {{"username": 123, "password": "123456"}},
    "status": 400,
    "test_type": "negative"
  }}
]
```

请严格按照上述格式生成测试用例，确保返回JSON数组。
💡 **建议**：推荐生成充分的测试用例（{min_positive}+ 正向，{min_negative}+ 负向）以确保全面测试覆盖。质量和数量同样重要！
"""
        
        return base_prompt + retry_hint
    
    def _get_system_prompt_with_retry_emphasis(self) -> str:
        """Get enhanced system prompt for retry attempts."""
        return """你是一个专业的API用例设计工程师。

⚠️ 重要提醒（重试时必须注意）：
1. 必须返回JSON数组格式，即使只有一个测试用例也要用 [...] 包装
2. 每个测试用例都必须包含所有必需字段（test_id, name, description, method, path, status, test_type）
3. 不要只返回headers或其他部分内容，必须返回完整的测试用例对象
4. 严格遵守JSON语法，确保可以被正确解析
5. 推荐生成充分数量的测试用例来确保全面覆盖：
   - simple端点：建议3个positive + 3个negative（最少2个positive + 2个negative）
   - medium端点：建议4个positive + 4个negative（最少3个positive + 3个negative） 
   - complex端点：建议5个positive + 5个negative（最少4个positive + 4个negative）
6. 每个测试用例必须有明确的测试目的，覆盖不同场景
7. 全面的测试覆盖比节省token更重要

根据提供的API规范和复杂度要求生成测试用例。请生成推荐数量的测试用例，确保全面覆盖各种正向和负向场景！"""
    
    def _get_system_prompt(self) -> str:
        """Get system prompt for LLM."""
        return """你是一个专业的API用例设计工程师，负责设计全面、高质量的测试用例。

⚠️ **关键要求：必须生成充足数量的正向测试用例！**
- POST端点：至少7个正向测试用例
- GET端点：至少4个正向测试用例  
- PUT/PATCH端点：至少5个正向测试用例
- DELETE端点：至少4个正向测试用例

## 🎯 核心设计理念
"完善的测试设计是高质量API的基石" - 请设计充分的测试用例以确保接口的可靠性。

## 📊 测试数量指导原则

根据HTTP方法的重要性和风险等级，设计相应数量的测试用例：

### POST（创建操作）- 最重要
**目标数量：16-25个测试用例**
- 正向测试（35%）：6-9个
- 负向测试（45%）：7-11个
- 边界测试（20%）：3-5个
创建操作影响数据完整性，需要最全面的测试。

**POST必须包含的测试场景：**
□ 认证授权测试（未认证401、无权限403、token过期401）
□ 并发创建处理（同时创建相同资源、不同资源）
□ 业务规则验证（库存不足、商品下架、超出限制）
□ 唯一性约束（重复创建409、唯一字段冲突）
□ 数据完整性（外键约束、引用验证）
□ 事务处理（部分失败回滚、批量创建）
□ 资源限制（配额限制、速率限制429）

### DELETE（删除操作）- 第二重要
**目标数量：15-22个测试用例**
- 正向测试（25%）：4-6个
- 负向测试（55%）：8-12个
- 边界测试（20%）：3-4个
删除操作不可逆，必须充分测试权限、存在性、级联影响。

### PUT/PATCH（更新操作）
**目标数量：14-20个测试用例**
- 正向测试（35%）：5-7个
- 负向测试（45%）：6-9个
- 边界测试（20%）：3-4个

### GET（查询操作）
**目标数量：13-20个测试用例**
- 正向测试（40%）：5-8个
- 负向测试（40%）：5-8个
- 边界测试（20%）：3-4个

## 📝 DELETE操作特殊测试要求（重要）
必须包含以下测试场景：
□ 删除不存在的资源（404）
□ 重复删除同一资源（404或409）
□ 删除被引用的资源（409冲突）
□ 级联删除验证（验证关联数据处理）
□ 软删除vs硬删除（标记删除vs物理删除）
□ 删除权限验证（401未认证，403无权限）
□ 删除后的数据恢复（验证是否可恢复）
□ 批量删除场景（删除多个资源）
□ 并发删除处理（同时删除同一资源）
□ 删除锁定的资源（423锁定）

测试用例要求：
- 每个测试用例必须有test_id（从1开始的递增编号）
- 使用中文命名，name和description都用中文描述
- 选择合适的状态码：200(成功)、400(参数错误)、404(资源不存在)、422(验证失败)、401(未认证)、403(无权限)
- 测试数据要真实且简短
- 确保测试用例具有实际意义，避免重复或无效的测试

质量与数量并重：
- 生成高质量的测试用例，同时确保充分的数量
- 全面的测试比节省token更重要
- 目标是达到推荐数量，而不是最低要求
- 多样化的测试场景能发现更多潜在问题

Headers设置智能规则：
1. 基于HTTP方法的Headers（重要：必须完整，不要截断）：
   - GET: 添加 "Accept": "application/json" （完整的MIME类型）
   - POST/PUT/PATCH: 添加 "Content-Type": "application/json", "Accept": "application/json"
   - DELETE: 添加 "Accept": "application/json" （必须是完整的"application/json"）

2. 基于认证要求的Headers：
   - Bearer Token认证: 添加 "Authorization": "Bearer ${AUTH_TOKEN}"
   - API Key认证: 添加 "X-API-Key": "${API_KEY}" 或相应header
   - Basic Auth认证: 添加 "Authorization": "Basic ${BASIC_CREDENTIALS}"
   - 无认证要求: 只添加基本的Accept/Content-Type headers

3. 基于请求体类型的Headers：
   - JSON请求体: "Content-Type": "application/json"
   - 注意：body字段必须始终是JSON对象格式，不要生成URL编码字符串

4. 负向测试的Headers策略：
   - 缺失认证headers (返回401/403)
   - 错误的Content-Type (返回415)
   - 无效的Accept头 (返回406)
   - 其他情况可以为空

5. 参数生成智能规则：
   - 路径参数：如果API路径包含占位符(如{category_id})，path字段保持原样包含占位符，实际值放在path_params中
     示例：path: "/api/v1/categories/{category_id}", path_params: {"category_id": 123}
   - GET/DELETE: 如果路径包含占位符则需要path_params，可能有query_params
   - POST/PUT/PATCH: 通常有body，path_params仅在路径包含占位符时存在，query_params较少使用
   - 极其重要的规则：
     * 当端点有路径参数时，才包含path_params字段，值为具体参数对象
     * 当端点有查询参数时，才包含query_params字段，值为具体参数对象
     * 当端点没有对应参数时，绝对不要包含该字段（不要设为null、{}、""或任何空值）
     * 示例：POST /api/v1/auth/register 只需要 body，不要包含 path_params 或 query_params
     * 示例：GET /api/v1/categories/{id} 需要 path_params: {"id": 1}，不包含 query_params
     * 示例：GET /api/v1/products?limit=10 需要 query_params: {"limit": 10}，不包含 path_params

重要：
- 直接返回JSON数组，不要任何解释或markdown标记
- 确保JSON格式正确，不要包含注释
- 字符串使用双引号，避免特殊字符
- Headers必须基于上述规则智能生成，不要随意设置
- Tags必须基于上述规则智能生成，绝对不能为空数组[]
- body字段格式要求：
  * body必须是JSON对象格式，例如：{"username": "test", "password": "123456"}
  * 绝对不要生成URL编码字符串，如："username=test&password=123456"
  * 如果不需要body，则不包含body字段（不要设为null）
- 参数字段规则：
  * 有路径参数时才包含path_params字段（不要设为null）
  * 有查询参数时才包含query_params字段（不要设为null）
  * 没有参数时完全省略这些字段
- 每个测试用例必须包含完整的预期验证信息：
  * resp_headers: 响应头验证
  * resp_content: 响应内容断言
  * rules: 业务逻辑验证规则"""
    
    def _build_prompt(self, endpoint: APIEndpoint) -> str:
        """Build prompt for test case generation.
        
        Args:
            endpoint: API endpoint to generate prompt for
            
        Returns:
            Formatted prompt string
        """
        # Evaluate endpoint complexity
        complexity = self._evaluate_endpoint_complexity(endpoint)
        
        # Build endpoint description
        endpoint_info = {
            "method": endpoint.method,
            "path": endpoint.path,
            "summary": endpoint.summary,
            "description": endpoint.description
        }
        
        # Add parameters info
        if endpoint.parameters:
            params_info = []
            for param in endpoint.parameters:
                param_info = {
                    "name": param.name,
                    "location": param.location,
                    "type": param.type,
                    "required": param.required,
                    "description": param.description
                }
                if param.param_schema:
                    param_info["schema"] = param.param_schema
                params_info.append(param_info)
            endpoint_info["parameters"] = params_info
        
        # Add request body info
        if endpoint.request_body:
            endpoint_info["requestBody"] = endpoint.request_body
        
        # Add response info
        if endpoint.responses:
            endpoint_info["responses"] = endpoint.responses
        
        # Analyze headers recommendations
        headers_scenarios = self.headers_analyzer.analyze_headers(endpoint)
        
        # Build complexity guidance
        complexity_guidance = f"""
**接口复杂度分析:**
- 复杂度级别: {complexity['complexity_level']}
- 影响因素: {', '.join(complexity['factors']) if complexity['factors'] else '基础接口'}
- 推荐生成数量:
  - 总计: 建议生成{complexity['recommended_counts']['total'][1]}个测试用例（最少{complexity['recommended_counts']['total'][0]}个）
  - 正向测试: **建议{complexity['recommended_counts']['positive'][1]}个**（不少于{complexity['recommended_counts']['positive'][0]}个）
  - 负向测试: **建议{complexity['recommended_counts']['negative'][1]}个**（不少于{complexity['recommended_counts']['negative'][0]}个）
  - 边界测试: 建议{complexity['recommended_counts']['boundary'][1]}个（至少{complexity['recommended_counts']['boundary'][0]}个）

📌 **推荐要求**: 请生成推荐数量的测试用例以确保全面覆盖。全面的测试覆盖比节省token更重要！
"""

        # Build the prompt
        prompt = f"""Generate comprehensive test cases for the following API endpoint:

**Endpoint Definition:**
```json
{json.dumps(endpoint_info, indent=2)}
```

{complexity_guidance}

**Headers建议 (智能分析结果):**
- 正向测试建议headers: {json.dumps(headers_scenarios.get('positive', {}), indent=2)}
- 负向测试场景: {list(headers_scenarios.keys())}

**完整的测试用例验证要求:**
1. **状态码验证**: 准确的HTTP状态码期望
2. **响应头验证**: 包括Content-Type、Location、Cache-Control等
3. **响应体结构验证**: 基于OpenAPI schema的结构验证
4. **响应内容验证**: 具体字段值、格式、业务逻辑验证
5. **性能验证**: 响应时间期望
6. **业务规则验证**: 数据一致性、权限控制等

**Required Test Case JSON Schema:**
```json
{json.dumps(self._test_case_schema, indent=2)}
```

请根据接口复杂度生成相应数量的高质量测试用例。每个用例都应该有明确的测试目的，避免重复或无意义的测试。

⚠️ **关键提醒**:
1. **必须生成**足够的正向测试用例：至少{complexity['recommended_counts']['positive'][0]}个，推荐{complexity['recommended_counts']['positive'][1]}个
2. **必须生成**足够的负向测试用例：至少{complexity['recommended_counts']['negative'][0]}个，推荐{complexity['recommended_counts']['negative'][1]}个
3. 每个测试用例必须包含所有必需字段
4. 生成的测试用例应该包含完整的预期验证，不仅仅是状态码，还要包括响应头、响应内容、业务规则等全面的验证
5. 返回格式必须是JSON数组，即使只有一个测试用例也要用 [...] 包装

🔥 **最重要：确保正向测试用例数量达到要求！不要少于{complexity['recommended_counts']['positive'][0]}个！**

Return the test cases as a JSON array:"""
        
        return prompt
    
    def _parse_llm_response(self, response_content: str, endpoint: APIEndpoint) -> List[TestCase]:
        """Parse and validate LLM response.
        
        Args:
            response_content: Raw LLM response content
            endpoint: API endpoint for context
            
        Returns:
            List of validated test cases
            
        Raises:
            TestGeneratorError: If response is invalid
        """
        self.logger.file_only(f"🔄 Parsing LLM response ({len(response_content):,} characters)")
        self.logger.file_only("Extracting test cases from JSON structure", level="DEBUG")
        
        # Parse JSON response directly
        try:
            test_data = json.loads(response_content)
            self.logger.file_only(f"Successfully parsed JSON, type: {type(test_data).__name__}", level="DEBUG")
        except json.JSONDecodeError as e:
            # Log the problematic content for debugging
            self.logger.warning(f"Failed to parse JSON (will retry): {str(e)[:100]}")
            self.logger.debug(f"Raw content: {response_content[:500]}...")
            raise TestGeneratorError(f"Invalid JSON in LLM response: {e}")
        
        if not isinstance(test_data, list):
            # Special handling for non-array responses
            self.logger.file_only(f"Response is not an array, attempting to extract test cases from {type(test_data)}", level="WARNING")
            
            if isinstance(test_data, dict):
                # Try to find an array field in the response
                possible_keys = [
                    'response', 'data', 'result', 'test_cases', 'tests', 'items',
                    'testCases', 'test_case_list', 'cases', 'array', 'list',
                    'content', 'output', 'generated', 'testdata'
                ]
                
                extracted_array = None
                for key in possible_keys:
                    if key in test_data and isinstance(test_data[key], list):
                        extracted_array = test_data[key]
                        self.logger.file_only(f"Extracted test cases from '{key}' field: {len(extracted_array)} items", level="INFO")
                        break
                
                # Check for nested arrays
                if not extracted_array:
                    for key, value in test_data.items():
                        if isinstance(value, dict):
                            for nested_key in possible_keys:
                                if nested_key in value and isinstance(value[nested_key], list):
                                    extracted_array = value[nested_key]
                                    self.logger.file_only(f"Extracted test cases from nested '{key}.{nested_key}': {len(extracted_array)} items", level="INFO")
                                    break
                        if extracted_array:
                            break
                
                # Last resort: look for any array that might contain test case-like objects
                if not extracted_array:
                    for key, value in test_data.items():
                        if isinstance(value, list) and len(value) > 0:
                            # Check if first item looks like a test case
                            first_item = value[0]
                            if isinstance(first_item, dict):
                                test_indicators = ['test_id', 'id', 'method', 'path', 'name', 'description']
                                if any(indicator in first_item for indicator in test_indicators):
                                    extracted_array = value
                                    self.logger.file_only(f"Found test case-like array at '{key}': {len(value)} items", level="INFO")
                                    break
                
                if extracted_array:
                    test_data = extracted_array
                else:
                    # Check if the entire dict is a single test case
                    test_indicators = ['test_id', 'id', 'method', 'path', 'name', 'description', 'expected_status', 'status']
                    if any(indicator in test_data for indicator in test_indicators):
                        self.logger.file_only("Converting single test case object to array", level="INFO")
                        test_data = [test_data]
                    else:
                        # Log the structure for debugging
                        self.logger.error(f"Could not extract test cases from dict with keys: {list(test_data.keys())}")
                        if os.getenv("CASECRAFT_DEBUG_RESPONSE"):
                            import time
                            debug_file = f"failed_response_{int(time.time())}.json"
                            try:
                                with open(debug_file, 'w', encoding='utf-8') as f:
                                    json.dump(test_data, f, indent=2, ensure_ascii=False)
                                self.logger.file_only(f"Failed response saved to {debug_file}", level="INFO")
                            except Exception:
                                pass
                        raise TestGeneratorError(f"LLM response must be a JSON array of test cases. Got dict with keys: {list(test_data.keys())[:10]}")
            else:
                raise TestGeneratorError(f"LLM response must be a JSON array of test cases. Got {type(test_data).__name__}")
        
        # Validate and convert to TestCase objects
        test_cases = []
        for i, test_case_data in enumerate(test_data):
            try:
                # Fix body field if it's a URL-encoded string
                if 'body' in test_case_data and isinstance(test_case_data['body'], str):
                    body_str = test_case_data['body']
                    # Check if it looks like URL-encoded data
                    if '=' in body_str and '&' in body_str:
                        self.logger.file_only(f"Test case {i+1}: body is URL-encoded string, converting to JSON object", level="WARNING")
                        # Parse URL-encoded string
                        import urllib.parse
                        params = urllib.parse.parse_qs(body_str)
                        # Convert to simple dict (take first value for each key)
                        test_case_data['body'] = {k: v[0] if len(v) == 1 else v for k, v in params.items()}
                    else:
                        # Try to parse as JSON string
                        try:
                            test_case_data['body'] = json.loads(body_str)
                            self.logger.file_only(f"Test case {i+1}: body was JSON string, converted to object", level="WARNING")
                        except json.JSONDecodeError:
                            # If all else fails, wrap in an object
                            self.logger.file_only(f"Test case {i+1}: body is plain string, wrapping in object", level="WARNING")
                            test_case_data['body'] = {"data": body_str}
                
                # Validate against schema
                validate(test_case_data, self._test_case_schema)
                
                # Clean up null/empty parameters before creating TestCase
                # This ensures we don't have unnecessary null or empty dict fields
                params_to_check = ['path_params', 'query_params']
                for param_field in params_to_check:
                    if param_field in test_case_data:
                        value = test_case_data[param_field]
                        # Remove if None, empty dict, empty string, or string "null"
                        if value is None or value == {} or value == '' or value == 'null':
                            del test_case_data[param_field]
                
                # Convert to TestCase object
                test_case = TestCase(**test_case_data)
                test_cases.append(test_case)
                
            except ValidationError as e:
                raise TestGeneratorError(f"Test case {i} validation error: {e}")
            except PydanticValidationError as e:
                raise TestGeneratorError(f"Test case {i} model error: {e}")
        
        # Validate test case coverage
        self._validate_test_coverage(test_cases, endpoint)
        
        return test_cases
    
    def _validate_test_coverage(self, test_cases: List[TestCase], endpoint: APIEndpoint) -> None:
        """Validate that test cases meet coverage requirements based on endpoint complexity.
        
        Args:
            test_cases: Generated test cases
            endpoint: API endpoint
            
        Raises:
            TestGeneratorError: If coverage requirements not met
        """
        if not test_cases:
            raise TestGeneratorError("No test cases generated")
        
        # Evaluate endpoint complexity to get requirements
        complexity = self._evaluate_endpoint_complexity(endpoint)
        
        # Count test types
        positive_count = sum(1 for tc in test_cases if tc.test_type == TestType.POSITIVE)
        negative_count = sum(1 for tc in test_cases if tc.test_type == TestType.NEGATIVE)
        boundary_count = sum(1 for tc in test_cases if tc.test_type == TestType.BOUNDARY)
        total_count = len(test_cases)
        
        # Use 60% of minimum requirements as soft requirements (more lenient)
        min_positive = max(2, int(complexity['recommended_counts']['positive'][0] * 0.6))
        min_negative = max(3, int(complexity['recommended_counts']['negative'][0] * 0.6))
        min_total = max(8, int(complexity['recommended_counts']['total'][0] * 0.6))
        
        # Only error on severe deficiency
        if positive_count < min_positive:
            self.logger.warning(f"Positive test cases below recommended: {positive_count} < {complexity['recommended_counts']['positive'][0]}")
            if positive_count < 2:  # Only error if less than 2
                raise TestGeneratorError(f"At least 2 positive test cases required, got {positive_count}")
        
        if negative_count < min_negative:
            self.logger.warning(f"Negative test cases below recommended: {negative_count} < {complexity['recommended_counts']['negative'][0]}")
            if negative_count < 2:  # Only error if less than 2
                raise TestGeneratorError(f"At least 2 negative test cases required, got {negative_count}")
        
        if total_count < min_total:
            self.logger.warning(f"Total test cases below recommended: {total_count} < {complexity['recommended_counts']['total'][0]}")
            if total_count < 5:  # Only error if less than 5
                raise TestGeneratorError(f"At least 5 test cases required, got {total_count}")
        
        # Log test case distribution with complexity info
        # Note: This log is for validation only, actual generation success is logged in generate_test_cases method
        self.logger.file_only(f"Validated {total_count} test cases for {complexity['complexity_level']} endpoint ({endpoint.method} {endpoint.path}): {positive_count} positive, {negative_count} negative, {boundary_count} boundary", level="DEBUG")
        
        # Validate that each test case has required fields
        for i, test_case in enumerate(test_cases):
            if not test_case.name or not test_case.description:
                raise TestGeneratorError(f"Test case {i} missing name or description")
            
            if not test_case.status:
                raise TestGeneratorError(f"Test case {i} missing expected status code")
    
    def _get_test_case_schema(self) -> Dict[str, Any]:
        """Get JSON schema for test case validation."""
        return {
            "type": "object",
            "required": [
                "test_id",
                "name",
                "description", 
                "method",
                "path",
                "status",
                "test_type"
            ],
            "properties": {
                "test_id": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Test case ID/sequence number"
                },
                "name": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Test case name"
                },
                "description": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Test case description"
                },
                "method": {
                    "type": "string",
                    "pattern": "^(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)$",
                    "description": "HTTP method"
                },
                "path": {
                    "type": "string",
                    "minLength": 1,
                    "description": "API path"
                },
                "headers": {
                    "type": "object",
                    "description": "Request headers"
                },
                "path_params": {
                    "type": "object",
                    "description": "Path parameters"
                },
                "query_params": {
                    "type": "object",
                    "description": "Query parameters"
                },
                "body": {
                    "oneOf": [
                        {"type": "object"},
                        {"type": "null"}
                    ],
                    "description": "Request body"
                },
                "status": {
                    "type": "integer",
                    "minimum": 100,
                    "maximum": 599,
                    "description": "Expected HTTP status code"
                },
                "resp_schema": {
                    "type": "object",
                    "description": "Expected response schema"
                },
                "test_type": {
                    "type": "string",
                    "enum": ["positive", "negative", "boundary"],
                    "description": "Test case type"
                },
                "resp_headers": {
                    "type": "object",
                    "description": "Expected response headers"
                },
                "resp_content": {
                    "type": "object",
                    "description": "Expected response content assertions"
                },
                "rules": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Business logic validation rules"
                }
            },
            "additionalProperties": False
        }
    
    def _enhance_test_cases(self, test_cases: List[TestCase], endpoint: APIEndpoint) -> List[TestCase]:
        """Enhance test cases with response schemas and improved status codes.
        
        Args:
            test_cases: List of test cases to enhance
            endpoint: API endpoint for context
            
        Returns:
            Enhanced test cases
        """
        # Extract response schemas from endpoint
        response_schemas = self._extract_response_schemas(endpoint)
        
        # Ensure each test case has a proper test_id
        for i, test_case in enumerate(test_cases, 1):
            if not hasattr(test_case, 'test_id') or test_case.test_id is None:
                test_case.test_id = i
            
            status_str = str(test_case.status)
            
            # Add response schema for all cases with defined schemas
            if status_str in response_schemas:
                test_case.resp_schema = response_schemas[status_str]
            else:
                # Provide default schema based on status code
                test_case.resp_schema = self._get_default_response_schema(status_str)
            
            # Add expected response headers
            test_case.resp_headers = self._extract_response_headers(endpoint, status_str)
            
            # Add response content assertions
            content_assertions = self._extract_response_content_assertions(endpoint, status_str)
            if content_assertions:
                test_case.resp_content = content_assertions
            
            # Add business rules based on endpoint characteristics
            business_rules = self._generate_business_rules(test_case, endpoint)
            if business_rules:
                test_case.rules = business_rules
            
            # Improve status codes based on test type and error
            if test_case.test_type == TestType.NEGATIVE:
                test_case.status = self._infer_status_code(test_case, endpoint)
        
        return test_cases
    
    def _extract_response_schemas(self, endpoint: APIEndpoint) -> Dict[str, Dict[str, Any]]:
        """Extract response schemas from endpoint definition.
        
        Args:
            endpoint: API endpoint
            
        Returns:
            Map of status code to response schema
        """
        schemas = {}
        
        for status, response_def in endpoint.responses.items():
            if "content" in response_def:
                # Try to find JSON schema
                for content_type, content_def in response_def["content"].items():
                    if "json" in content_type.lower() and "schema" in content_def:
                        schema = content_def["schema"].copy()
                        # Simplify or remove long titles to save tokens
                        if "title" in schema and len(schema["title"]) > 20:
                            # Create a simple title based on status code
                            status_int = int(status) if status.isdigit() else 200
                            if 200 <= status_int < 300:
                                schema["title"] = "Success Response"
                            elif 400 <= status_int < 500:
                                schema["title"] = "Error Response"
                            else:
                                schema["title"] = f"Response {status}"
                        schemas[status] = schema
                        break
        
        return schemas
    
    def _get_default_response_schema(self, status_code: str) -> Dict[str, Any]:
        """Get default response schema based on status code.
        
        Args:
            status_code: HTTP status code as string
            
        Returns:
            Default response schema
        """
        status_int = int(status_code)
        
        # Success responses (2xx)
        if 200 <= status_int < 300:
            return {
                "type": "object",
                "additionalProperties": True
            }
        
        # Client error responses (4xx)
        elif 400 <= status_int < 500:
            return {
                "type": "object",
                "properties": {
                    "error": {"type": "string"},
                    "message": {"type": "string"},
                    "code": {"type": "string"}
                },
                "additionalProperties": True
            }
        
        # Server error responses (5xx)
        elif 500 <= status_int < 600:
            return {
                "type": "object",
                "properties": {
                    "error": {"type": "string"},
                    "message": {"type": "string"}
                },
                "additionalProperties": True
            }
        
        # Default fallback
        else:
            return {
                "type": "object",
                "additionalProperties": True
            }
    
    def _extract_response_headers(self, endpoint: APIEndpoint, status_code: str) -> Dict[str, Any]:
        """Extract expected response headers for a given status code.
        
        Args:
            endpoint: API endpoint
            status_code: HTTP status code (as string)
            
        Returns:
            Map of header name to expected value or pattern
        """
        headers = {}
        
        # Default headers for all responses
        headers["Content-Type"] = "application/json"
        
        # Extract from endpoint response definition
        if status_code in endpoint.responses:
            response_def = endpoint.responses[status_code]
            if "headers" in response_def:
                for header_name, header_def in response_def["headers"].items():
                    # Extract expected header value or pattern
                    if "schema" in header_def:
                        schema = header_def["schema"]
                        if "example" in schema:
                            headers[header_name] = schema["example"]
                        elif "default" in schema:
                            headers[header_name] = schema["default"]
                        else:
                            # Just indicate the header should be present
                            headers[header_name] = "<any>"
        
        # Add common response headers based on operation type
        if endpoint.method in ["POST", "PUT", "PATCH"] and status_code in ["200", "201"]:
            headers["Location"] = "<resource-url>"
        
        if status_code == "201":
            headers["Location"] = "<created-resource-url>"
        
        # Add cache-related headers for GET requests
        if endpoint.method == "GET" and status_code == "200":
            headers["Cache-Control"] = "max-age=300"
            headers["ETag"] = "<etag-value>"
        
        return headers
    
    def _extract_response_content_assertions(self, endpoint: APIEndpoint, status_code: str) -> Optional[Dict[str, Any]]:
        """Extract content validation assertions for response.
        
        Args:
            endpoint: API endpoint
            status_code: HTTP status code (as string)
            
        Returns:
            Content assertion rules or None
        """
        assertions = {}
        
        # Extract from response schema
        if status_code in endpoint.responses:
            response_def = endpoint.responses[status_code]
            if "content" in response_def:
                for content_type, content_def in response_def["content"].items():
                    if "json" in content_type.lower() and "schema" in content_def:
                        schema = content_def["schema"]
                        
                        # Add schema-based assertions
                        if "properties" in schema:
                            required_fields = schema.get("required", [])
                            if required_fields:
                                assertions["required_fields"] = required_fields
                        
                        # Add type assertions
                        if "type" in schema:
                            assertions["response_type"] = schema["type"]
                        
                        # Add example-based assertions
                        if "example" in schema:
                            assertions["example_match"] = schema["example"]
                        
                        # Add format assertions
                        if "format" in schema:
                            assertions["format"] = schema["format"]
                        
                        break
        
        # Add common assertions based on status code
        if status_code == "200":
            if endpoint.method == "GET":
                assertions["non_empty_response"] = True
        elif status_code == "201":
            assertions["created_resource_id"] = True
        elif status_code == "400":
            assertions["error_message"] = True
            assertions["error_code"] = True
        elif status_code == "404":
            assertions["error_message"] = "Resource not found"
        elif status_code == "422":
            assertions["validation_errors"] = True
        
        return assertions if assertions else None
    
    def _infer_status_code(self, test_case: TestCase, endpoint: APIEndpoint) -> int:
        """Infer appropriate status code based on test case details.
        
        Args:
            test_case: Test case to analyze
            endpoint: API endpoint for context
            
        Returns:
            Inferred status code
        """
        name_lower = test_case.name.lower()
        desc_lower = test_case.description.lower()
        combined = name_lower + desc_lower
        
        # Priority order for status code inference
        
        # 1. Authentication errors - 401
        if any(word in combined for word in ["未认证", "未授权", "unauthorized", "authentication", "无认证", "未登录"]):
            return 401  # Unauthorized
        
        # 2. Permission errors - 403  
        if any(word in combined for word in ["权限", "forbidden", "permission", "access denied", "不允许"]):
            return 403  # Forbidden
        
        # 3. Validation errors - 422
        if any(word in combined for word in ["验证", "validation", "constraint", "range", "格式错误", "类型错误"]):
            return 422  # Unprocessable Entity
        
        # 4. Missing required fields - 422 (not 400)
        if any(word in combined for word in ["missing", "required", "缺少", "必填", "必需"]):
            return 422  # Unprocessable Entity for missing required fields
        
        # 5. Invalid parameter type/format - 422
        if any(word in combined for word in ["invalid type", "string instead", "format", "非数字", "非整数"]):
            return 422  # Unprocessable Entity for type errors
        
        # 6. Resource not found - 404 (only for actual missing resources)
        if any(word in combined for word in ["not found", "nonexistent", "doesn't exist", "不存在的商品", "找不到"]):
            # But not for invalid IDs - those should be 422
            if any(word in combined for word in ["invalid", "格式", "负数", "零值"]):
                return 422
            return 404  # Not Found
        
        # 7. Bad request - 400 (general client errors)
        if any(word in combined for word in ["bad request", "malformed", "错误请求"]):
            return 400
        
        # For DELETE operations with path params, prefer 422 for invalid IDs
        if endpoint.method.upper() == "DELETE" and test_case.path_params:
            # If it's about invalid ID format, use 422
            if any(word in combined for word in ["invalid", "负数", "零值", "格式"]):
                return 422
            # If it's about non-existent resource, use 404
            if any(word in combined for word in ["不存在", "not found"]):
                return 404
        
        # Default to 422 for validation errors, 400 for others
        return test_case.status if test_case.status in [400, 401, 403, 404, 422] else 422
    
    def _evaluate_endpoint_complexity(self, endpoint: APIEndpoint) -> Dict[str, Any]:
        """Evaluate the complexity of an API endpoint.
        
        Args:
            endpoint: API endpoint to evaluate
            
        Returns:
            Dictionary with complexity metrics and recommended test case counts
        """
        complexity_score = 0
        factors = []
        
        # 1. Parameter complexity (adjusted weights)
        if endpoint.parameters:
            param_by_location = {"path": [], "query": [], "header": [], "cookie": []}
            
            for param in endpoint.parameters:
                location = param.location if hasattr(param, 'location') else param.get("in", "query")
                if location in param_by_location:
                    param_by_location[location].append(param)
            
            # Path parameters: 2 points each (more important)
            if param_by_location["path"]:
                complexity_score += len(param_by_location["path"]) * 2
                factors.append(f"{len(param_by_location['path'])} path params")
            
            # Query parameters: 1 point each (reduced from 2)
            if param_by_location["query"]:
                complexity_score += len(param_by_location["query"]) * 1
                factors.append(f"{len(param_by_location['query'])} query params")
            
            # Header parameters: 1 point each
            if param_by_location["header"]:
                complexity_score += len(param_by_location["header"]) * 1
                factors.append(f"{len(param_by_location['header'])} header params")
            
            # Cookie parameters: 0.5 points each
            if param_by_location["cookie"]:
                complexity_score += len(param_by_location["cookie"]) * 0.5
                factors.append(f"{len(param_by_location['cookie'])} cookie params")
            
            # Required parameters get extra points
            required_count = sum(1 for params in param_by_location.values() 
                                for p in params if (hasattr(p, 'required') and p.required) 
                                or (isinstance(p, dict) and p.get("required", False)))
            if required_count > 0:
                complexity_score += required_count * 0.5
        
        # 2. Request body complexity (increased weights)
        if endpoint.request_body:
            body_complexity = self._evaluate_schema_complexity(endpoint.request_body)
            
            # Dynamic grading with higher weights
            if body_complexity <= 3:
                score = 6  # Increased from ~3
                factors.append("simple request body")
            elif body_complexity <= 7:
                score = 10  # Increased from ~6
                factors.append("medium request body")
            elif body_complexity <= 15:
                score = 14  # Increased from ~9
                factors.append("complex request body")
            else:
                score = 18  # Very complex
                factors.append("very complex request body")
            
            complexity_score += score
        
        # 3. Operation type complexity (DELETE gets highest weight)
        method_upper = endpoint.method.upper()
        
        if method_upper == "DELETE":
            complexity_score += 7  # DELETE gets highest weight (2nd most tests)
            factors.append("DELETE operation (critical)")
        elif method_upper == "POST":
            complexity_score += 6  # POST is important
            factors.append("POST operation")
        elif method_upper in ["PUT", "PATCH"]:
            complexity_score += 5  # Update operations
            factors.append(f"{method_upper} operation")
        elif method_upper in ["HEAD", "OPTIONS"]:
            complexity_score += 1
            factors.append(f"{method_upper} operation")
        # GET gets 0 points
        
        # 4. Authentication requirements (enhanced detection)
        if self._requires_authentication(endpoint):
            complexity_score += 3  # Increased from 2
            factors.append("authentication required")
        
        # 5. Business criticality assessment
        business_score = self._evaluate_business_criticality(endpoint)
        if business_score > 0:
            complexity_score += business_score
            factors.append(f"business criticality (+{business_score})")
        
        # 6. Response complexity
        if endpoint.responses:
            response_count = len(endpoint.responses)
            if response_count > 5:
                complexity_score += 3
                factors.append(f"{response_count} response scenarios")
            elif response_count > 3:
                complexity_score += 2
                factors.append("multiple response types")
            elif response_count > 1:
                complexity_score += 1
        
        # 7. Data consistency requirements
        if method_upper in ["PUT", "PATCH", "DELETE"]:
            complexity_score += 1
            factors.append("data consistency check")
        
        # Calculate test counts using new enhanced logic
        return self._calculate_test_counts(complexity_score, method_upper, factors)
    
    def _requires_authentication(self, endpoint: APIEndpoint) -> bool:
        """
        Generic authentication requirement detection.
        Does not rely on specific implementations.
        """
        # 1. Check endpoint security field
        if hasattr(endpoint, 'security') and endpoint.security:
            return True
        
        # 2. Check for authentication-related parameters
        if endpoint.parameters:
            # Generic authentication parameter patterns
            auth_patterns = [
                "auth", "token", "key", "credential", "session",
                "jwt", "bearer", "oauth", "apikey", "api-key",
                "x-auth", "x-token", "x-api", "authorization"
            ]
            
            for param in endpoint.parameters:
                param_name = param.name if hasattr(param, 'name') else param.get("name", "")
                param_lower = param_name.lower().replace("-", "").replace("_", "")
                
                if any(pattern in param_lower for pattern in auth_patterns):
                    return True
        
        # 3. Check path for secured areas
        path_lower = endpoint.path.lower()
        secured_paths = ["admin", "private", "secure", "protected", "internal"]
        if any(word in path_lower for word in secured_paths):
            return True
        
        return False
    
    def _evaluate_business_criticality(self, endpoint: APIEndpoint) -> int:
        """
        Evaluate business criticality using smart analyzer.
        Replaces hardcoded patterns with intelligent inference.
        """
        # 使用智能关键性分析器替代硬编码
        return self.criticality_analyzer.analyze(endpoint)
    
    def _calculate_test_counts(self, complexity_score: int, method: str, factors: list) -> dict:
        """
        Calculate test counts based on complexity and method using constants.
        Ensures DELETE gets 2nd most test cases.
        """
        
        # 使用常量中的方法基准数量
        base = METHOD_BASE_COUNTS.get(method.upper(), 12)
        
        # 根据复杂度等级确定multiplier
        if complexity_score <= COMPLEXITY_THRESHOLDS['simple']:
            multiplier = 0.8
            level = "simple"
        elif complexity_score <= COMPLEXITY_THRESHOLDS['medium']:
            multiplier = 1.0
            level = "medium"
        else:
            multiplier = 1.3
            level = "complex"
        
        # 计算总数
        total = int(base * multiplier)
        
        # 获取测试类型比例
        ratios = TEST_TYPE_RATIOS[level]
        
        # 计算各类型数量
        positive = max(MIN_TEST_COUNTS['positive'], int(total * ratios['positive']))
        negative = max(MIN_TEST_COUNTS['negative'], int(total * ratios['negative']))
        boundary = max(MIN_TEST_COUNTS['boundary'], int(total * ratios['boundary']))
        
        # 确保总数匹配
        calculated_total = positive + negative + boundary
        if calculated_total != total:
            diff = total - calculated_total
            if diff > 0:
                # 增加负向测试数量
                negative += diff
            else:
                # 减少负向测试数量
                negative = max(MIN_TEST_COUNTS['negative'], negative + diff)
        
        # 应用最大值约束
        positive = min(positive, MAX_TEST_COUNTS['positive'])
        negative = min(negative, MAX_TEST_COUNTS['negative'])
        boundary = min(boundary, MAX_TEST_COUNTS['boundary'])
        total = min(positive + negative + boundary, MAX_TEST_COUNTS['total'])
        
        return {
            "complexity_score": complexity_score,
            "complexity_level": level,
            "factors": factors,
            "recommended_counts": {
                "total": (total, total),
                "positive": (positive, positive),
                "negative": (negative, negative),
                "boundary": (boundary, boundary)
            }
        }
    
    def _evaluate_schema_complexity(self, schema: Dict[str, Any]) -> int:
        """Evaluate the complexity of a JSON schema.
        
        Args:
            schema: JSON schema to evaluate
            
        Returns:
            Complexity score
        """
        score = 0
        
        if isinstance(schema, dict):
            # Check for content types
            if "content" in schema:
                for content_type, content_schema in schema.get("content", {}).items():
                    if "schema" in content_schema:
                        score += self._evaluate_schema_complexity(content_schema["schema"])
            
            # Check for object properties
            if schema.get("type") == "object":
                properties = schema.get("properties", {})
                score += len(properties)
                
                # Check for required fields
                required = schema.get("required", [])
                score += len(required)
                
                # Check for nested objects
                for prop_schema in properties.values():
                    if isinstance(prop_schema, dict) and prop_schema.get("type") == "object":
                        score += 2  # Nested objects add complexity
                    elif isinstance(prop_schema, dict) and prop_schema.get("type") == "array":
                        score += 1  # Arrays add some complexity
            
            # Check for arrays
            elif schema.get("type") == "array":
                score += 2
                if "items" in schema:
                    score += self._evaluate_schema_complexity(schema["items"])
        
        return score
    
    def _generate_business_rules(self, test_case: TestCase, endpoint: APIEndpoint) -> List[str]:
        """Generate business logic validation rules for a test case.
        
        Args:
            test_case: Test case to generate rules for
            endpoint: API endpoint context
            
        Returns:
            List of business rule descriptions
        """
        rules = []
        
        # Rules based on HTTP method
        if endpoint.method == "POST" and test_case.test_type == TestType.POSITIVE:
            rules.append("创建的资源应具有唯一ID")
            rules.append("响应应包含资源位置")
        
        elif endpoint.method == "PUT" and test_case.test_type == TestType.POSITIVE:
            rules.append("更新的资源应保持数据完整性")
            rules.append("版本号或时间戳应被更新")
        
        elif endpoint.method == "DELETE" and test_case.test_type == TestType.POSITIVE:
            rules.append("资源应被标记为已删除或移除")
            rules.append("后续的GET请求应返回404")
        
        elif endpoint.method == "GET" and test_case.test_type == TestType.POSITIVE:
            rules.append("响应数据应与数据库保持一致")
            if "list" in endpoint.path.lower() or "search" in endpoint.path.lower():
                rules.append("分页应被正确处理")
                rules.append("结果应匹配过滤条件")
        
        # Rules based on authentication
        has_auth = any(p.name.lower() in ["authorization", "api-key", "x-api-key"] 
                      for p in (endpoint.parameters or []))
        
        if has_auth and test_case.test_type == TestType.NEGATIVE:
            if "unauthorized" in test_case.description.lower():
                rules.append("无有效认证时应拒绝访问")
            elif "forbidden" in test_case.description.lower():
                rules.append("应验证用户权限")
        
        # Rules based on path parameters
        if test_case.path_params and "{id}" in endpoint.path:
            if test_case.test_type == TestType.NEGATIVE:
                rules.append("无效的ID格式应被拒绝")
                rules.append("不存在的ID应返回适当的错误")
            else:
                rules.append("ID应引用存在的资源")
        
        # Rules for validation scenarios
        if test_case.test_type == TestType.NEGATIVE and "validation" in test_case.description.lower():
            rules.append("输入验证错误应被清晰描述")
            rules.append("错误响应应包含字段级别的错误信息")
        
        # Rules for boundary cases
        if test_case.test_type == TestType.BOUNDARY:
            rules.append("边界值应被优雅地处理")
            rules.append("系统限制应被遵守")
        
        return rules
    
