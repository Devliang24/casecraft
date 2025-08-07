# CaseCraft - 多 LLM 提供商支持

使用多个 LLM 提供商（GLM、Qwen、Kimi、本地模型）解析 API 文档并生成结构化测试用例的 CLI 工具。

## 🎉 新功能：多提供商支持

### 支持的 LLM 提供商

| 提供商 | 模型示例 | 并发数 | 特点 |
|--------|----------|--------|------|
| **GLM** (智谱) | glm-4.5-airx | 1 | 高质量生成，支持思考模式 |
| **Qwen** (通义千问) | qwen-max, qwen-plus | 3 | 快速响应，成本较低 |
| **Kimi** (Moonshot) | moonshot-v1-8k/32k/128k | 2 | 长上下文支持 |
| **Local** (Ollama/vLLM) | llama2, mistral | 可配置 | 本地部署，无成本 |

## 🚀 快速开始

### 1. 配置环境变量

复制示例配置文件并填写 API 密钥：

```bash
cp .env.example .env
```

编辑 `.env` 文件：

```env
# 必须指定提供商（无默认值）
CASECRAFT_PROVIDERS=glm,qwen,kimi

# GLM 配置
CASECRAFT_GLM_MODEL=glm-4.5-airx
CASECRAFT_GLM_API_KEY=your_glm_api_key_here

# Qwen 配置
CASECRAFT_QWEN_MODEL=qwen-max
CASECRAFT_QWEN_API_KEY=your_qwen_api_key_here

# Kimi 配置
CASECRAFT_KIMI_MODEL=moonshot-v1-8k
CASECRAFT_KIMI_API_KEY=your_kimi_api_key_here

# 本地模型配置（Ollama）
CASECRAFT_LOCAL_MODEL=llama2
CASECRAFT_LOCAL_BASE_URL=http://localhost:11434
CASECRAFT_LOCAL_SERVER_TYPE=ollama
```

### 2. 使用命令行

#### 单提供商模式

使用特定提供商生成所有测试用例：

```bash
# 使用 GLM 生成
casecraft generate api.json --provider glm

# 使用 Qwen 生成
casecraft generate api.json --provider qwen

# 使用本地模型
casecraft generate api.json --provider local
```

#### 多提供商并发模式

使用多个提供商并发生成，自动分配端点：

```bash
# 轮询分配（默认）
casecraft generate api.json --providers glm,qwen,kimi --strategy round_robin

# 随机分配
casecraft generate api.json --providers glm,qwen,kimi --strategy random

# 基于复杂度分配
casecraft generate api.json --providers glm,qwen,kimi --strategy complexity_based
```

#### 手动映射模式

精确控制哪些端点使用哪个提供商：

```bash
# 基本映射
casecraft generate api.json --provider-map "/users:qwen,/products:glm,/orders:kimi"

# 使用通配符
casecraft generate api.json --provider-map "/api/v1/*:glm,/api/v2/*:qwen"

# 方法级别映射
casecraft generate api.json --provider-map "GET:/users:glm,POST:/users:qwen"
```

## 📊 高级功能

### 故障转移和降级

系统自动处理提供商故障，支持配置降级链：

```env
# 启用故障转移
CASECRAFT_FALLBACK_ENABLED=true

# 降级链顺序
CASECRAFT_FALLBACK_CHAIN=glm,qwen,kimi,local
```

当主提供商失败时，系统会自动尝试降级链中的下一个提供商。

### 提供商性能统计

系统会自动跟踪每个提供商的性能指标：

- **成功率**: 成功/总请求数
- **平均响应时间**: 处理时间统计
- **Token 使用量**: 消耗的 token 数量
- **成本估算**: 基于 token 使用量的成本

查看统计报告：

```bash
# 生成后会自动显示统计报告
casecraft generate api.json --providers glm,qwen --verbose
```

统计数据保存在 `.casecraft_provider_stats.json` 文件中。

### 分配策略详解

#### 1. 轮询策略 (round_robin)
- 按顺序循环分配端点给各个提供商
- 确保负载均衡
- 适合提供商能力相近的场景

#### 2. 随机策略 (random)
- 随机选择提供商
- 避免固定模式
- 适合测试不同提供商的表现

#### 3. 复杂度策略 (complexity_based)
- 根据端点复杂度智能分配
- 简单端点 → 快速/便宜的提供商
- 复杂端点 → 高质量的提供商
- 自动优化成本和质量

#### 4. 手动映射 (manual)
- 完全控制分配逻辑
- 支持路径模式匹配
- 适合有特定需求的项目

## 🔧 配置说明

### 环境变量配置

所有配置通过环境变量管理，支持以下格式：

```env
# 提供商配置格式
CASECRAFT_{PROVIDER}_MODEL=model_name
CASECRAFT_{PROVIDER}_API_KEY=api_key
CASECRAFT_{PROVIDER}_BASE_URL=base_url
CASECRAFT_{PROVIDER}_TIMEOUT=60
CASECRAFT_{PROVIDER}_MAX_RETRIES=3
CASECRAFT_{PROVIDER}_TEMPERATURE=0.7
CASECRAFT_{PROVIDER}_STREAM=false
CASECRAFT_{PROVIDER}_WORKERS=1

# 策略配置
CASECRAFT_PROVIDER_STRATEGY=round_robin
CASECRAFT_FALLBACK_ENABLED=true
CASECRAFT_FALLBACK_CHAIN=glm,qwen,kimi
```

### 本地模型配置

支持 Ollama 和 vLLM 等本地部署：

```env
# Ollama 配置
CASECRAFT_LOCAL_MODEL=llama2
CASECRAFT_LOCAL_BASE_URL=http://localhost:11434
CASECRAFT_LOCAL_SERVER_TYPE=ollama

# vLLM 配置
CASECRAFT_LOCAL_MODEL=mistral-7b
CASECRAFT_LOCAL_BASE_URL=http://localhost:8000
CASECRAFT_LOCAL_SERVER_TYPE=vllm
```

## 📈 性能优化建议

1. **合理设置并发数**
   - GLM: 1 (API 限制)
   - Qwen: 3 (推荐)
   - Kimi: 2 (推荐)
   - Local: 根据硬件配置

2. **选择合适的策略**
   - 批量生成: 使用 `round_robin` 或 `random`
   - 成本优化: 使用 `complexity_based`
   - 精确控制: 使用 `manual` 映射

3. **配置故障转移**
   - 始终配置降级链
   - 将稳定的提供商放在链首
   - 本地模型作为最后备选

## 🐛 故障排查

### 常见问题

1. **"必须指定 LLM 提供商"错误**
   ```bash
   # 解决方案：指定提供商
   casecraft generate api.json --provider glm
   # 或设置环境变量
   export CASECRAFT_PROVIDER=glm
   ```

2. **提供商连接失败**
   ```bash
   # 检查 API 密钥
   echo $CASECRAFT_GLM_API_KEY
   
   # 测试连接
   casecraft generate api.json --provider glm --dry-run
   ```

3. **速率限制错误**
   - 减少并发数: `--workers 1`
   - 配置重试: `CASECRAFT_GLM_MAX_RETRIES=5`
   - 启用故障转移

## 📊 成本对比

| 提供商 | 输入价格 | 输出价格 | 适用场景 |
|--------|----------|----------|----------|
| GLM-4.5 | ¥0.001/1K | ¥0.002/1K | 高质量要求 |
| Qwen-Max | ¥0.0008/1K | ¥0.0016/1K | 平衡性价比 |
| Kimi-8K | ¥0.003/1K | ¥0.006/1K | 长上下文 |
| Local | 免费 | 免费 | 大批量生成 |

## 🔗 相关资源

- [GLM API 文档](https://open.bigmodel.cn/dev/api)
- [Qwen API 文档](https://help.aliyun.com/zh/dashscope/)
- [Kimi API 文档](https://platform.moonshot.cn/docs)
- [Ollama 文档](https://ollama.ai/docs)

## 📝 更新日志

### v0.6.0 (2025-08-08)
- ✨ 添加多 LLM 提供商支持
- 🚀 支持并发执行和智能分配
- 🔄 实现故障转移机制
- 📊 添加性能统计和成本追踪
- 🎯 必须显式指定提供商（无默认值）

## 许可证

MIT License - 详见 [LICENSE](LICENSE) 文件