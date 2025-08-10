# 多 LLM 提供商支持设计方案

## 1. 项目背景

CaseCraft 是一个 API 测试用例生成工具，目前仅支持智谱 GLM 单一 LLM 提供商。为了提高系统的灵活性、可靠性和性能，需要支持多个 LLM 提供商，包括：
- 智谱 GLM（已支持）
- 阿里通义千问 (Qwen)
- Moonshot Kimi
- 本地部署模型（Ollama、vLLM 等）

## 2. 设计目标

### 2.1 核心目标
- **灵活性**：支持任意数量的 LLM 提供商，易于添加新提供商
- **可靠性**：提供故障转移和降级机制
- **性能**：充分利用不同提供商的并发能力
- **简单性**：所有配置通过 .env 文件管理，无需额外配置文件
- **兼容性**：需要用户更新配置指定提供商（移除默认值以提高明确性）

### 2.2 功能需求
- 支持单端点指定 LLM 提供商
- 支持多端点使用多个 LLM 并发执行
- 支持多种分配策略（轮询、随机、基于复杂度、手动映射）
- 支持自动故障转移和降级
- 记录每个端点使用的提供商和 token 使用情况

## 3. 系统架构

### 3.1 整体架构图

```
┌─────────────────────────────────────────────────────────┐
│                       CLI Interface                      │
│         casecraft generate --providers glm,qwen,kimi     │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│                  Multi-Provider Engine                   │
│  ┌──────────────────────────────────────────────────┐  │
│  │          Provider Assignment Strategy             │  │
│  │  (Round Robin / Random / Complexity / Manual)    │  │
│  └──────────────────────────────────────────────────┘  │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│                   Provider Registry                      │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐      │
│  │   GLM   │ │  Qwen   │ │  Kimi   │ │  Local  │      │
│  │Provider │ │Provider │ │Provider │ │Provider │      │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘      │
└──────────────────────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│                    Configuration                         │
│                     (.env file)                          │
└──────────────────────────────────────────────────────────┘
```

### 3.2 模块设计

#### 3.2.1 Provider 抽象层
```python
# casecraft/core/providers/base.py
class LLMProvider(ABC):
    """LLM 提供商抽象基类"""
    
    def __init__(self, config: ProviderConfig):
        self.config = config
        self.logger = get_logger(f"provider.{self.name}")
    
    @property
    @abstractmethod
    def name(self) -> str:
        """提供商名称"""
        pass
    
    @abstractmethod
    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        progress_callback: Optional[callable] = None,
        **kwargs
    ) -> LLMResponse:
        """生成响应"""
        pass
    
    @abstractmethod
    def get_max_workers(self) -> int:
        """获取最大并发数"""
        pass
    
    @abstractmethod
    def validate_config(self) -> bool:
        """验证配置是否有效"""
        pass
    
    @abstractmethod
    async def health_check(self) -> bool:
        """健康检查"""
        pass
```

#### 3.2.2 Provider Registry
```python
# casecraft/core/providers/registry.py
class ProviderRegistry:
    """提供商注册器"""
    
    _providers: Dict[str, Type[LLMProvider]] = {}
    _instances: Dict[str, LLMProvider] = {}
    
    @classmethod
    def register(cls, name: str, provider_class: Type[LLMProvider]):
        """注册提供商类"""
        cls._providers[name] = provider_class
    
    @classmethod
    def get_provider(cls, name: str, config: Dict) -> LLMProvider:
        """获取提供商实例（单例）"""
        if name not in cls._instances:
            if name not in cls._providers:
                raise ValueError(f"Unknown provider: {name}")
            cls._instances[name] = cls._providers[name](config)
        return cls._instances[name]
    
    @classmethod
    def list_available(cls) -> List[str]:
        """列出所有可用提供商"""
        return list(cls._providers.keys())
```

### 3.3 配置管理

#### 3.3.1 环境变量配置格式
```env
# 提供商列表（注意：没有默认值，必须显式配置）
CASECRAFT_PROVIDERS=glm,qwen,kimi,local

# 每个提供商的配置（统一格式）
CASECRAFT_{PROVIDER}_MODEL=model_name
CASECRAFT_{PROVIDER}_API_KEY=api_key
CASECRAFT_{PROVIDER}_BASE_URL=base_url
CASECRAFT_{PROVIDER}_TIMEOUT=timeout_seconds
CASECRAFT_{PROVIDER}_MAX_RETRIES=max_retries
CASECRAFT_{PROVIDER}_TEMPERATURE=temperature
CASECRAFT_{PROVIDER}_STREAM=true/false
CASECRAFT_{PROVIDER}_WORKERS=max_workers

# 策略配置
CASECRAFT_PROVIDER_STRATEGY=round_robin
# 注意：没有默认提供商，必须显式指定
CASECRAFT_FALLBACK_ENABLED=true
CASECRAFT_FALLBACK_CHAIN=glm,qwen,kimi,local
```

#### 3.3.2 配置模型
```python
# casecraft/models/provider_config.py
class ProviderConfig(BaseModel):
    """提供商配置"""
    name: str
    model: str
    api_key: Optional[str] = None
    base_url: str
    timeout: int = 60
    max_retries: int = 3
    temperature: float = 0.7
    stream: bool = False
    workers: int = 1
    
class MultiProviderConfig(BaseModel):
    """多提供商配置"""
    providers: List[str]
    configs: Dict[str, ProviderConfig]
    strategy: str = "round_robin"
    selected_provider: Optional[str] = None  # 用户指定的提供商
    fallback_enabled: bool = True
    fallback_chain: List[str] = []
```

## 4. 核心功能实现

### 4.1 提供商分配策略

#### 4.1.1 轮询分配 (Round Robin)
```python
class RoundRobinStrategy:
    def __init__(self, providers: List[str]):
        self.providers = providers
        self.current = 0
    
    def get_next_provider(self, endpoint: APIEndpoint) -> str:
        provider = self.providers[self.current]
        self.current = (self.current + 1) % len(self.providers)
        return provider
```

#### 4.1.2 基于复杂度分配
```python
class ComplexityBasedStrategy:
    def __init__(self, providers: List[str], thresholds: Dict[str, int]):
        self.providers = providers
        self.thresholds = thresholds
    
    def get_provider(self, endpoint: APIEndpoint) -> str:
        complexity = self.calculate_complexity(endpoint)
        
        if complexity > 10:
            # 高复杂度：使用能力强的模型
            return self._select_powerful_provider()
        elif complexity > 5:
            # 中等复杂度：使用平衡的模型
            return self._select_balanced_provider()
        else:
            # 低复杂度：使用快速/便宜的模型
            return self._select_fast_provider()
    
    def calculate_complexity(self, endpoint: APIEndpoint) -> int:
        """计算端点复杂度"""
        score = 0
        score += len(endpoint.path_params) * 2
        score += len(endpoint.query_params)
        if endpoint.request_body:
            score += self._calculate_schema_complexity(endpoint.request_body)
        score += len(endpoint.responses)
        if endpoint.requires_auth:
            score += 3
        return score
```

### 4.2 多提供商执行引擎

```python
# casecraft/core/multi_provider_engine.py
class MultiProviderEngine:
    """多提供商并发执行引擎"""
    
    def __init__(self, config: MultiProviderConfig):
        self.config = config
        self.registry = ProviderRegistry()
        self.strategy = self._create_strategy()
        self.fallback_handler = FallbackHandler(config)
    
    async def generate_with_providers(
        self,
        endpoints: List[APIEndpoint],
        provider_assignments: Optional[Dict[str, str]] = None
    ) -> GenerationResult:
        """使用多个提供商并发生成测试用例"""
        
        # 分配提供商
        if not provider_assignments:
            provider_assignments = self._assign_providers(endpoints)
        
        # 按提供商分组
        provider_groups = self._group_by_provider(endpoints, provider_assignments)
        
        # 创建并发任务
        tasks = []
        for provider_name, provider_endpoints in provider_groups.items():
            provider = self.registry.get_provider(provider_name, self.config.configs[provider_name])
            max_workers = provider.get_max_workers()
            
            # 创建该提供商的生成任务
            task = self._generate_batch(provider, provider_endpoints, max_workers)
            tasks.append(task)
        
        # 并发执行
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 处理结果
        return self._merge_results(results)
    
    async def _generate_batch(
        self,
        provider: LLMProvider,
        endpoints: List[APIEndpoint],
        max_workers: int
    ) -> List[GenerationResult]:
        """使用单个提供商批量生成"""
        semaphore = asyncio.Semaphore(max_workers)
        
        async def generate_with_semaphore(endpoint):
            async with semaphore:
                if self.config.fallback_enabled:
                    return await self.fallback_handler.generate_with_fallback(
                        endpoint, provider, self.config.fallback_chain
                    )
                else:
                    return await provider.generate(endpoint)
        
        tasks = [generate_with_semaphore(endpoint) for endpoint in endpoints]
        return await asyncio.gather(*tasks, return_exceptions=True)
```

### 4.3 故障转移和降级

```python
# casecraft/core/providers/fallback.py
class FallbackHandler:
    """处理提供商故障转移"""
    
    def __init__(self, config: MultiProviderConfig):
        self.config = config
        self.registry = ProviderRegistry()
        self.logger = get_logger("fallback")
    
    async def generate_with_fallback(
        self,
        endpoint: APIEndpoint,
        primary_provider: LLMProvider,
        fallback_chain: List[str]
    ) -> GenerationResult:
        """带降级机制的生成"""
        
        providers_tried = []
        last_error = None
        
        # 构建完整的提供商链
        provider_chain = [primary_provider.name] + [
            p for p in fallback_chain if p != primary_provider.name
        ]
        
        for provider_name in provider_chain:
            providers_tried.append(provider_name)
            
            try:
                # 获取提供商
                if provider_name == primary_provider.name:
                    provider = primary_provider
                else:
                    provider_config = self.config.configs.get(provider_name)
                    if not provider_config:
                        self.logger.warning(f"Provider {provider_name} not configured, skipping")
                        continue
                    provider = self.registry.get_provider(provider_name, provider_config)
                
                # 尝试生成
                self.logger.info(f"Trying provider {provider_name} for {endpoint.path}")
                result = await provider.generate(endpoint)
                
                # 记录降级信息
                if provider_name != primary_provider.name:
                    result.metadata["fallback_from"] = primary_provider.name
                    result.metadata["providers_tried"] = providers_tried
                    self.logger.info(
                        f"Successfully used fallback provider {provider_name} "
                        f"for {endpoint.path}"
                    )
                
                return result
                
            except Exception as e:
                last_error = e
                self.logger.warning(
                    f"Provider {provider_name} failed for {endpoint.path}: {e}"
                )
                
                # 如果是速率限制错误，等待一段时间
                if isinstance(e, RateLimitError):
                    await asyncio.sleep(5)
                
                continue
        
        # 所有提供商都失败
        error_msg = (
            f"All providers failed for {endpoint.path}. "
            f"Tried: {providers_tried}. Last error: {last_error}"
        )
        self.logger.error(error_msg)
        raise GeneratorError(error_msg)
```

## 5. 命令行接口设计

### 5.1 新增命令行参数

```python
# casecraft/cli/main.py 更新
@cli.command()
@click.option(
    "--provider",
    help="Use specific LLM provider for all endpoints"
)
@click.option(
    "--providers",
    help="Comma-separated list of providers for concurrent execution"
)
@click.option(
    "--provider-map",
    help="Manual provider mapping (format: path1:provider1,path2:provider2)"
)
@click.option(
    "--strategy",
    type=click.Choice(["round_robin", "random", "complexity_based", "manual"]),
    help="Provider assignment strategy (required when using multiple providers)"
)
```

### 5.2 参数验证

```python
def validate_provider_args(provider, providers, provider_map):
    """验证提供商参数"""
    if not any([provider, providers, provider_map]):
        raise click.ClickException(
            "必须指定 LLM 提供商。请使用以下选项之一：\n"
            "  --provider <name>：指定单个提供商\n"
            "  --providers <list>：指定多个提供商列表\n"
            "  --provider-map <mapping>：指定端点到提供商的映射\n"
            "\n示例：\n"
            "  casecraft generate api.json --provider glm\n"
            "  casecraft generate api.json --providers glm,qwen,kimi"
        )
```

### 5.3 使用示例

```bash
# 未指定提供商时的错误提示
$ casecraft generate api.json
Error: 必须指定 LLM 提供商。请使用以下选项之一：
  --provider <name>：指定单个提供商
  --providers <list>：指定多个提供商列表
  --provider-map <mapping>：指定端点到提供商的映射

# 单提供商
casecraft generate api.json --provider qwen

# 多提供商轮询
casecraft generate api.json --providers glm,qwen,kimi --strategy round_robin

# 手动映射
casecraft generate api.json --provider-map "/users:qwen,/products:glm"

# 基于复杂度
casecraft generate api.json --providers glm,qwen,local --strategy complexity_based
```

## 6. 状态管理

### 6.1 状态文件格式

```json
{
  "version": "2.0",
  "generated_at": "2025-08-07T10:00:00Z",
  "endpoints": {
    "/api/v1/users": {
      "hash": "abc123",
      "provider": {
        "name": "qwen",
        "model": "qwen-max",
        "version": "1.0"
      },
      "generation": {
        "generated_at": "2025-08-07T10:00:00Z",
        "retry_count": 0,
        "fallback_from": null
      },
      "usage": {
        "prompt_tokens": 1500,
        "completion_tokens": 2000,
        "total_tokens": 3500,
        "estimated_cost": 0.035
      }
    }
  },
  "statistics": {
    "total_endpoints": 25,
    "total_test_cases": 150,
    "by_provider": {
      "qwen": {
        "endpoints_count": 10,
        "test_cases_count": 60,
        "total_tokens": 35000,
        "success_rate": 0.95,
        "average_retry_count": 0.2
      }
    }
  }
}
```

## 7. 具体提供商实现

### 7.1 GLM Provider（重构现有）

```python
# casecraft/core/providers/glm_provider.py
class GLMProvider(LLMProvider):
    """智谱 GLM 提供商"""
    
    name = "glm"
    
    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self.client = httpx.AsyncClient(
            base_url=config.base_url,
            timeout=config.timeout,
            headers={
                "Authorization": f"Bearer {config.api_key}",
                "Content-Type": "application/json"
            }
        )
    
    async def generate(self, prompt: str, **kwargs) -> LLMResponse:
        # 实现 GLM 特定的 API 调用
        pass
    
    def get_max_workers(self) -> int:
        return 1  # GLM 只支持单并发
```

### 7.2 Qwen Provider

```python
# casecraft/core/providers/qwen_provider.py
class QwenProvider(LLMProvider):
    """阿里通义千问提供商"""
    
    name = "qwen"
    
    async def generate(self, prompt: str, **kwargs) -> LLMResponse:
        # 实现千问 API 调用
        # 使用 DashScope SDK 或 HTTP API
        pass
    
    def get_max_workers(self) -> int:
        return 3  # 千问支持 3 并发
```

### 7.3 Kimi Provider

```python
# casecraft/core/providers/kimi_provider.py
class KimiProvider(LLMProvider):
    """Moonshot Kimi 提供商"""
    
    name = "kimi"
    
    async def generate(self, prompt: str, **kwargs) -> LLMResponse:
        # 实现 Kimi API 调用
        # Kimi 使用 OpenAI 兼容接口
        pass
    
    def get_max_workers(self) -> int:
        return 2  # Kimi 支持 2 并发
```

### 7.4 Local Provider

```python
# casecraft/core/providers/local_provider.py
class LocalProvider(LLMProvider):
    """本地部署模型提供商"""
    
    name = "local"
    
    async def generate(self, prompt: str, **kwargs) -> LLMResponse:
        # 实现本地模型调用
        # 支持 Ollama、vLLM 等
        pass
    
    def get_max_workers(self) -> int:
        return self.config.workers  # 可配置
```

## 8. 测试策略

### 8.1 单元测试

- 每个提供商的独立测试
- 分配策略测试
- 故障转移机制测试
- 配置解析测试

### 8.2 集成测试

- 多提供商并发执行测试
- 端到端生成测试
- 性能基准测试
- 故障场景测试

### 8.3 测试用例示例

```python
# tests/test_multi_provider.py
@pytest.mark.asyncio
async def test_round_robin_strategy():
    """测试轮询分配策略"""
    strategy = RoundRobinStrategy(["glm", "qwen", "kimi"])
    endpoints = [create_mock_endpoint() for _ in range(6)]
    
    assignments = [strategy.get_next_provider(e) for e in endpoints]
    
    assert assignments == ["glm", "qwen", "kimi", "glm", "qwen", "kimi"]

@pytest.mark.asyncio
async def test_fallback_mechanism():
    """测试故障转移机制"""
    handler = FallbackHandler(config)
    
    # 模拟主提供商失败
    with patch.object(primary_provider, 'generate', side_effect=Exception("Failed")):
        result = await handler.generate_with_fallback(
            endpoint, primary_provider, ["qwen", "kimi"]
        )
    
    assert result.metadata["fallback_from"] == "glm"
    assert "qwen" in result.metadata["providers_tried"]
```

## 9. 性能优化

### 9.1 并发优化

- 利用不同提供商的并发能力
- 异步 I/O 最大化吞吐量
- 连接池复用

### 9.2 缓存策略

- 提供商实例缓存（单例模式）
- HTTP 客户端连接池
- 配置缓存

### 9.3 资源管理

- 自动关闭空闲连接
- 内存使用优化
- 日志级别控制

## 10. 向后兼容性

### 10.1 兼容性说明

- 保留原有的单提供商模式架构
- **重要变更**：必须显式指定提供商，不再有默认值
- 配置格式保持兼容，仅需添加 `--provider` 参数

### 10.2 迁移路径

```bash
# 旧版本（需要更新）
casecraft generate api.json  # 将提示用户指定提供商

# 新版本（必须指定）
casecraft generate api.json --provider glm  # 显式指定提供商
casecraft generate api.json --providers glm,qwen  # 新功能
```

## 11. 未来扩展

### 11.1 可能的扩展点

- 支持更多提供商（OpenAI、Anthropic、Cohere 等）
- 动态提供商加载（插件机制）
- 基于成本的智能路由
- A/B 测试支持
- 质量评分和自动选择

### 11.2 插件化架构

```python
# 未来：动态加载提供商
class ProviderLoader:
    @staticmethod
    def load_provider(module_path: str) -> Type[LLMProvider]:
        """动态加载提供商模块"""
        module = importlib.import_module(module_path)
        return module.Provider
```

## 12. 风险和缓解措施

### 12.1 潜在风险

1. **配置复杂度增加**
   - 缓解：提供清晰的错误提示和配置模板

2. **不同提供商的响应质量差异**
   - 缓解：添加质量验证和重试机制

3. **成本控制**
   - 缓解：添加成本追踪和预算限制

4. **提供商 API 变更**
   - 缓解：抽象层隔离，版本化管理

### 12.2 监控和告警

- 提供商可用性监控
- 成功率追踪
- 响应时间监控
- 成本追踪

## 13. 实施计划

### 阶段 1：基础架构（第 1 周）
- 创建提供商抽象层
- 实现注册器和工厂
- 配置系统扩展

### 阶段 2：提供商实现（第 2 周）
- GLM 提供商重构
- Qwen 提供商实现
- Kimi 提供商实现
- Local 提供商实现

### 阶段 3：核心功能（第 3 周）
- 多提供商执行引擎
- 分配策略实现
- 故障转移机制

### 阶段 4：CLI 和测试（第 4 周）
- CLI 命令扩展
- 单元测试
- 集成测试
- 文档更新

## 14. 总结

本方案提供了一个全面的多 LLM 提供商支持系统，具有以下优势：

1. **灵活性**：易于添加新提供商，支持多种分配策略
2. **可靠性**：完善的故障转移和降级机制
3. **性能**：充分利用并发能力，优化吞吐量
4. **简单性**：配置简单，使用方便
5. **可维护性**：模块化设计，职责清晰
6. **可扩展性**：为未来扩展预留接口

通过实施此方案，CaseCraft 将成为一个更加强大和灵活的 API 测试用例生成工具。