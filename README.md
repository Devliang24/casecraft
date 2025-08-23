# CaseCraft

使用多个 LLM 提供商解析 API 文档（OpenAPI/Swagger）并生成结构化测试用例的 CLI 工具。

## 🆕 最新更新 (2025-08-23)

- **智能优先级分配**: 自动为每个测试用例分配 P0/P1/P2 优先级，无需硬编码关键词
- **按重要性排序**: LLM 现在按测试重要性排序生成用例，确保关键场景优先
- **动态分配算法**: 每种测试类型（正向/负向/边界）都有完整的 P0/P1/P2 覆盖（30%/40%/30%）

## 📅 之前更新 (2025-08-22)

- **零配置模块检测**: 自动检测和分组 API 模块，无需任何配置文件
- **通用化改进**: 移除所有行业特定的硬编码，支持任何行业的 API
- **多语言支持**: 新增 `--lang` 参数，支持模块名称的中英文自动翻译
- **智能前缀生成**: 自动为每个模块生成唯一的前缀标识符
- **配置文件精简**: 优化 `default_templates.yaml`，移除已过时的模块映射配置
- **Excel 格式增强**: 完善 Excel 输出支持，支持自定义模板和合并输出

## 📅 之前更新 (2025-08-18)

- **配置管理优化**: 重构 max_tokens 配置管理，各 Provider 配置更加清晰
- **Provider 配置集中化**: 每个 Provider 的所有配置（包括 max_tokens）在 .env 文件中统一管理
- **简化代码架构**: 移除 Provider 类中的环境变量回退逻辑，职责更加单一

## 📅 历史更新 (2025-08-17)

- **HTTP方法筛选**: 新增 `--include-method` 和 `--exclude-method` 参数，支持按HTTP方法筛选接口
- **智能推断系统**: 实现基于OpenAPI规范的智能推断，完全移除硬编码路径映射
- **通用性大幅提升**: 支持任何RESTful API，不再局限于电商领域
- **轻量级依赖**: 仅增加inflect库用于英文处理，保持系统轻量
- **智能描述生成**: 基于路径语义和OpenAPI信息自动生成准确的中文描述
- **动态关键性评估**: 智能识别金融、认证、用户等不同业务领域的风险等级
- **DELETE操作优化**: 确保DELETE操作获得第二多的测试用例数量（仅次于POST）

## 🎉 之前更新 (2025-08-15)

- **新增 DeepSeek 提供商**: 支持 DeepSeek Chat 模型，提供高质量的测试用例生成
- **增强重试机制**: 完整的重试机制和进度条回滚功能，提升生成成功率
- **日志系统优化**: 优化日志格式显示，提升终端显示体验
- **时间戳功能**: 增强时间戳显示和追踪功能

## 🎉 之前更新 (2025-08-08)

- **多 LLM 提供商支持**: 支持 GLM（智谱）、Qwen（通义千问）和本地模型
- **灵活的提供商策略**: 支持轮询、随机、复杂度和手动映射等多种分配策略
- **自动故障转移**: 当一个提供商失败时自动切换到备用提供商
- **并发执行优化**: 不同提供商并发处理，显著提升生成速度
- **统一配置管理**: 通过环境变量或命令行参数灵活配置多个提供商

## 📈 历史更新 (2025-08-05)

- **智能动态生成**: 根据 API 接口复杂度自动调整测试用例数量（5-12个）
- **质量优先**: 强调生成有意义的测试用例，避免为凑数而生成冗余用例
- **复杂度评估**: 自动分析接口参数、请求体、认证等因素确定适合的用例数量

## 核心特性

- 🧠 **智能推断引擎**: 基于OpenAPI规范的智能分析，支持任何RESTful API（不限于电商）
- 🔧 **零配置模块检测**: 自动检测和分组 API 模块，无需任何配置文件
- 🌐 **多语言模块名称**: 支持中英文自动翻译模块名称（--lang 参数）
- 🎯 **智能测试用例生成**: 支持多个 LLM 提供商（GLM、Qwen、DeepSeek等）自动生成全面的测试场景
- 🎖️ **智能优先级分配**: 自动为每个测试用例分配 P0/P1/P2 优先级，无硬编码依赖
- 🤖 **多提供商支持**: 灵活切换和组合使用不同的 LLM 提供商
- 📊 **动态用例数量**: 根据接口复杂度智能调整生成数量（简单5-6个，复杂10-12个）
- 🔍 **语义分析**: 智能路径分析器，自动识别资源类型和操作意图
- 🎭 **智能描述**: 基于路径语义自动生成准确的中文接口描述
- ⚖️ **风险评估**: 动态评估业务关键性（金融、认证、用户数据等）
- 📚 **多格式支持**: 支持 OpenAPI 3.0 和 Swagger 2.0 (JSON/YAML)
- 🔄 **增量生成**: 只为变更的 API 生成新测试，节省时间和成本
- ⚡ **并发处理**: 支持多提供商并发执行，显著提升生成速度
- 🎨 **灵活输出**: 支持 JSON 格式，未来支持 pytest、jest 等
- 🌏 **双语支持**: 完美支持中文和英文文档及测试用例
- 🔀 **智能故障转移**: 自动切换失败的提供商，确保生成成功率
- 🪶 **轻量级设计**: 最小依赖，仅新增inflect库（35KB）

## 快速开始

### 安装

```bash
pip install casecraft
```

### 配置 API 密钥

```bash
# 1. 复制配置模板
cp .env.example .env

# 2. 编辑 .env 文件，填写您的 API 密钥
vim .env
```

> **注意**: 必须通过 `--provider` 参数指定要使用的 LLM 提供商（glm/qwen/deepseek/local）

### 生成测试用例

#### 基础示例

```bash
# 使用单个提供商
casecraft generate api.json --provider glm

# 使用多个提供商并发
casecraft generate api.json --providers glm,qwen,deepseek

# 手动映射提供商到特定端点
casecraft generate api.json --provider-map "/users:qwen,/products:glm,/analytics:deepseek"

# 从 URL 生成
casecraft generate https://petstore.swagger.io/v2/swagger.json --provider glm

# 使用过滤器
casecraft generate ./openapi.json --include-tag users --exclude-tag admin --provider qwen

# 预览模式（不调用 LLM）
casecraft generate ./api.yaml --dry-run
```

#### 完整实战示例

```bash
# 1. 基础用法 - 生成所有接口的测试用例
casecraft generate api.json --provider glm --workers 1

# 2. 只生成 POST 接口的测试用例
casecraft generate api.json --provider glm --include-method POST --workers 1

# 3. 生成 GET 和 POST 接口
casecraft generate api.json --provider qwen --include-method GET,POST --workers 3

# 4. 排除 DELETE 和 PATCH 操作
casecraft generate api.json --provider deepseek --exclude-method DELETE,PATCH --workers 2

# 5. 生成认证模块的 POST 接口
casecraft generate api.json --provider glm --include-path "/api/v1/auth" --include-method POST --workers 1

# 6. 生成订单模块的 GET 和 POST 接口
casecraft generate api.json --provider qwen --include-path "/api/v1/orders" --include-method GET,POST --workers 3

# 7. 生成用户模块，排除 DELETE 操作
casecraft generate api.json --provider glm --include-tag users --exclude-method DELETE --workers 1

# 8. 多提供商并发处理 POST 接口
casecraft generate api.json --providers glm,qwen,deepseek --include-method POST --strategy round_robin

# 9. 强制重新生成所有 PUT 和 PATCH 接口
casecraft generate api.json --provider qwen --include-method PUT,PATCH --workers 3 --force

# 10. 生成产品模块的非查询接口（排除 GET）
casecraft generate api.json --provider deepseek --include-path "/api/v1/products" --exclude-method GET --workers 2

# 11. 组合多个标签和方法
casecraft generate api.json --provider qwen --include-tag auth,users --include-method POST,PUT --workers 3

# 12. 使用特定模型版本生成
casecraft generate api.json --provider qwen --model qwen-max --include-method POST --workers 3

# 13. 预览模式 - 查看将生成的 POST 接口数量
casecraft generate api.json --provider glm --include-method POST --dry-run

# 14. 指定输出目录并按标签组织
casecraft generate api.json --provider qwen --output test_output --organize-by tag --workers 3

# 15. 从 URL 生成测试用例
casecraft generate https://petstore.swagger.io/v2/swagger.json --provider glm --include-method GET,POST --workers 1

# 16. 强制清理所有日志和测试用例
casecraft cleanup --all --force

# 17. 预览清理操作
casecraft cleanup --all --force --dry-run

# 18. 只清理日志文件
casecraft cleanup --logs --force

# 19. 清理重复的测试用例
casecraft cleanup --test-cases

# 20. 使用本地模型生成测试用例
casecraft generate api.json --provider local --model llama2 --include-method POST --workers 4

# 21. 使用中文显示模块名称
casecraft generate api.json --provider glm --lang zh --workers 1

# 22. 禁用自动模块检测
casecraft generate api.json --provider glm --no-auto-detect --workers 1

# 23. 生成认证模块测试用例（中文显示）
casecraft generate api.json --provider qwen --include-tag auth --lang zh --workers 3

# 24. 生成Excel格式测试用例
casecraft generate api.json --provider glm --format excel --workers 1

# 25. 使用自定义Excel模板
casecraft generate api.json --provider glm --format excel --config my_excel_template.yaml --workers 1

# 26. 合并所有端点到一个Excel文件
casecraft generate api.json --provider qwen --format excel --merge-excel --workers 3

# 27. 生成特定优先级的测试用例
casecraft generate api.json --provider glm --priority P0 --workers 1

# 28. 零配置快速开始（最简单）
casecraft generate api.json --provider glm --workers 1

# 29. 保存LLM提示词用于调试
casecraft generate api.json --provider glm --save-prompts --prompts-dir debug_prompts --workers 1

# 30. 同时保存提示词和响应
casecraft generate api.json --provider glm --save-prompts --save-responses --workers 1
```

#### Workers 参数使用指南

**根据端点数量选择合适的 workers 数：**

| 场景 | 推荐配置 | 说明 |
|------|----------|------|
| **单个端点** | `--workers 1` | 单个端点无法并行，使用1个worker即可 |
| **多个端点 + GLM** | `--workers 1` | GLM只支持单并发 |
| **多个端点 + Qwen** | `--workers 3` | 千问支持最多3个并发 |
| **多个端点 + DeepSeek** | `--workers 3` | DeepSeek支持最多3个并发 |
| **多个端点 + Local** | `--workers 4` | 本地模型根据硬件配置调整 |

**示例对比：**

```bash
# ✅ 正确：单端点使用1个worker
casecraft generate api.json --provider qwen --include-path "/api/v1/auth/register" --workers 1

# ❌ 不推荐：单端点使用多个workers（浪费资源）
casecraft generate api.json --provider qwen --include-path "/api/v1/auth/register" --workers 3

# ✅ 正确：多端点使用提供商支持的最大并发数
casecraft generate api.json --provider qwen --include-tag "auth" --workers 3
```

## 命令参考

### `casecraft init`

初始化 CaseCraft 配置，设置 BigModel API 密钥和默认参数。

### `casecraft generate <source>`

从 API 文档生成测试用例。

**参数:**
- `source`: OpenAPI/Swagger 文档的 URL 或文件路径

**选项:**
- `--output, -o`: 输出目录（默认：`test_cases`）
- `--provider`: 使用单个 LLM 提供商 (glm/qwen/deepseek/local)
- `--providers`: 使用多个提供商，逗号分隔
- `--provider-map`: 手动映射端点到提供商
- `--strategy`: 提供商分配策略 (round_robin/random/complexity/manual)
- `--model`: 指定具体模型（如 glm-4.5-airx, qwen-max, deepseek-chat）
- `--include-tag`: 只包含指定标签的端点
- `--exclude-tag`: 排除指定标签的端点
- `--include-path`: 只包含匹配模式的路径
- `--include-method`: 只包含指定HTTP方法的端点（如 POST, GET）
- `--exclude-method`: 排除指定HTTP方法的端点
- `--format`: 输出格式 (json/excel/compact/pretty)，默认 json
- `--config`: 自定义模板配置文件（主要用于Excel格式）
- `--merge-excel`: 合并所有端点到一个Excel文件的多个工作表
- `--priority`: 只生成特定优先级的测试用例 (P0/P1/P2/all)
- `--lang`: 选择语言 (zh/en)，用于模块名称的本地化显示
- `--auto-detect/--no-auto-detect`: 启用或禁用自动模块检测（默认启用）
- `--save-prompts`: 保存LLM提示词到文件（用于调试）
- `--prompts-dir`: 提示词保存目录（默认：`prompts`）
- `--save-responses`: 同时保存LLM响应（与--save-prompts配合使用）
- `--workers, -w`: 并发工作线程数（根据提供商和端点数量调整）
- `--force`: 强制重新生成所有测试用例
- `--dry-run`: 预览模式，不调用 LLM
- `--organize-by`: 按标签组织输出文件
- `--quiet, -q`: 静默模式（仅显示警告和错误）
- `--verbose, -v`: 详细模式（显示调试信息）

## 零配置使用

CaseCraft 现已支持**零配置**即可使用，系统会自动：
- 🔧 检测和分组 API 模块
- 🏷️ 生成唯一的模块前缀
- 📊 分配合理的测试优先级
- 🌐 识别常见资源并翻译

### Excel 格式输出

生成 Excel 格式的测试用例文档：

```bash
# 基础 Excel 输出
casecraft generate api.json --provider glm --format excel

# 合并到单个 Excel 文件
casecraft generate api.json --provider glm --format excel --merge-excel

# 使用自定义 Excel 模板
cat > my_excel.yaml << EOF
excel:
  columns:
    - header: '编号'
      field: 'case_id'
      width: 15
    - header: '名称'
      field: 'name'
      width: 40
  styles:
    header_bg_color: '0066CC'
EOF

casecraft generate api.json --provider glm --format excel --config my_excel.yaml
```

## 配置

配置文件 (`~/.casecraft/config.yaml`) 示例：

```yaml
llm:
  model: glm-4.5-x
  api_key: your-bigmodel-api-key
  base_url: https://open.bigmodel.cn/api/paas/v4
  timeout: 60
  max_retries: 3
  temperature: 0.7

output:
  directory: test_cases
  organize_by_tag: false
  filename_template: "{method}_{path_slug}.json"

processing:
  workers: 1  # BigModel 只支持单并发
```

### 环境变量配置

支持通过环境变量配置多个提供商：

```bash
# 指定要使用的提供商
export CASECRAFT_PROVIDER=glm  # 单个提供商
export CASECRAFT_PROVIDERS=glm,qwen,deepseek  # 多个提供商

# GLM (智谱) 配置
export CASECRAFT_GLM_MODEL=glm-4.5-airx
export CASECRAFT_GLM_API_KEY="your-glm-api-key"
export CASECRAFT_GLM_BASE_URL="https://open.bigmodel.cn/api/paas/v4"
export CASECRAFT_GLM_MAX_TOKENS=16384  # GLM 支持大输出

# Qwen (通义千问) 配置
export CASECRAFT_QWEN_MODEL=qwen-max
export CASECRAFT_QWEN_API_KEY="your-qwen-api-key"
export CASECRAFT_QWEN_BASE_URL="https://dashscope.aliyuncs.com/compatible-mode/v1"
export CASECRAFT_QWEN_MAX_TOKENS=16384  # qwen-plus/turbo/flash 支持 16384 (qwen-max 仅 8192)

# DeepSeek 配置
export CASECRAFT_DEEPSEEK_MODEL=deepseek-chat
export CASECRAFT_DEEPSEEK_API_KEY="your-deepseek-api-key"
export CASECRAFT_DEEPSEEK_BASE_URL="https://api.deepseek.com/v1"
export CASECRAFT_DEEPSEEK_MAX_TOKENS=8192  # DeepSeek 最大限制

# 或使用 .env 文件（推荐）
cp .env.example .env
# 编辑 .env 文件填写您的 API 密钥
```

## 输出格式

每个生成的测试用例遵循以下 JSON 结构：

```json
{
  "name": "创建用户成功",
  "description": "使用所有必填字段测试用户创建成功的场景",
  "priority": "P0",
  "method": "POST",
  "path": "/users",
  "headers": {"Content-Type": "application/json"},
  "query_params": {},
  "body": {"name": "张三", "email": "zhangsan@example.com"},
  "expected_status": 201,
  "expected_response_schema": {...},
  "test_type": "positive",
  "tags": ["users", "crud"],
  "metadata": {
    "generated_at": "2024-01-01T12:00:00Z",
    "api_version": "1.0.0",
    "llm_model": "glm-4.5-x"
  }
}
```

## 测试用例覆盖

### 动态用例生成（智能调整）

CaseCraft 会根据接口复杂度自动调整生成的测试用例数量：

#### 🟢 简单接口（5-6个用例）
- **特征**: 无参数或少量参数的 GET 请求
- **正向测试**: 2个
- **负向测试**: 2-3个
- **边界测试**: 1个
- **示例**: `GET /health`, `GET /version`

#### 🟡 中等复杂度（7-9个用例）
- **特征**: 带查询参数的 GET 请求，简单的 POST 操作
- **正向测试**: 2-3个
- **负向测试**: 3-4个
- **边界测试**: 1-2个
- **示例**: `GET /users?page=1&limit=10`, `POST /login`

#### 🔴 复杂接口（10-12个用例）
- **特征**: 嵌套请求体的 POST/PUT，多个必填参数，认证要求
- **正向测试**: 3-4个
- **负向测试**: 4-5个
- **边界测试**: 2-3个
- **示例**: `POST /orders`, `PUT /users/{id}/profile`

### 智能优先级分配

每个测试用例都会自动分配优先级（P0/P1/P2），确保测试执行的层次性：

#### 📊 优先级分配策略
- **P0（核心测试）**: 每种测试类型的前 30% 用例
- **P1（重要测试）**: 每种测试类型的中间 40% 用例
- **P2（补充测试）**: 每种测试类型的后 30% 用例

#### 🎯 分配示例
对于一个包含 10 个负向测试的接口：
- **3 个 P0 用例**: 最关键的错误场景（如：必填字段缺失）
- **4 个 P1 用例**: 重要的错误场景（如：格式验证失败）
- **3 个 P2 用例**: 边缘错误场景（如：特殊字符处理）

#### ✨ 优势
- **无硬编码**: 不依赖预定义的关键词列表
- **动态适应**: 根据测试用例数量自动调整
- **完整覆盖**: 每种测试类型都有 P0/P1/P2 分布
- **灵活执行**: 可按优先级选择性执行测试

### 复杂度评估因素

系统会自动评估以下因素来确定接口复杂度：
- 参数数量（路径、查询、头部）
- 请求体结构（嵌套对象、数组）
- HTTP 方法类型
- 认证要求
- 响应类型数量

## 开发

### 环境设置

```bash
git clone https://github.com/yourusername/casecraft.git
cd casecraft
pip install -e ".[dev]"
```

### 运行测试

```bash
# 运行所有测试
pytest

# 运行测试并生成覆盖率报告
pytest --cov=casecraft

# 运行特定类型的测试
pytest tests/unit/
pytest tests/integration/
```

### 代码质量

```bash
# 格式化代码
black casecraft tests

# 代码检查
ruff casecraft tests

# 类型检查
mypy casecraft
```

## 最佳实践

1. **API 文档准备**
   - 确保 API 文档完整且准确
   - 包含详细的参数描述和示例
   - 明确标注认证要求

2. **批量生成优化**
   - 使用批处理脚本处理大型 API
   - 利用增量生成功能避免重复
   - 合理设置重试和超时参数

3. **质量保证**
   - 系统会自动根据接口复杂度生成适量的测试用例
   - 每个测试用例都有明确的测试目的
   - 避免生成重复或无意义的测试

4. **性能优化**
   - BigModel API 支持单并发，系统已自动优化
   - 使用增量生成模式减少 API 调用
   - 合理使用 `--dry-run` 预览模式

## 许可证

MIT License - 详见 [LICENSE](LICENSE) 文件。

## 支持的 LLM 提供商

| 提供商 | 模型示例 | 并发数 | 最大Tokens | 特点 |
|--------|----------|--------|------------|------|
| **GLM** (智谱) | glm-4.5-x, glm-4.5-airx | 1 | 16384 | 高质量生成，支持思考模式 |
| **Qwen** (通义千问) | qwen-plus, qwen-turbo, qwen-flash | 3 | 16384* | 快速响应，成本较低 |
| **DeepSeek** | deepseek-chat, deepseek-coder | 3 | 8192 | 代码理解能力强，推理准确 |
| **Local** (Ollama/vLLM) | llama2, mistral | 可配置 | 8192 | 本地部署，无成本 |

> **注意**: Qwen 系列中，qwen-plus/turbo/flash 支持 16384 tokens，但 qwen-max 仅支持 8192 tokens

## 🧠 智能推断系统

CaseCraft v1.1 引入了革命性的智能推断系统，让工具具备了支持任何RESTful API的强大能力。

### 核心组件

#### 🔍 智能路径分析器 (PathAnalyzer)
- **语义分析**: 使用轻量级正则表达式和inflect库分析API路径
- **资源识别**: 自动识别路径中的资源名词（user, product, order等）
- **操作分类**: 智能判断操作类型（collection, single, create, update, delete）
- **特征检测**: 识别集合操作、路径参数、嵌套资源等特征

```python
# 示例：智能分析路径
/api/v1/users/{id} + GET → {
    'resources': ['user'],
    'operation_type': 'single',
    'has_path_params': True,
    'is_collection': False
}
```

#### 🎭 智能描述生成器 (SmartDescriptionGenerator)
- **优先级策略**: OpenAPI summary > description > 智能推断
- **中文本地化**: 自动翻译常见资源名词和操作动词
- **上下文感知**: 根据HTTP方法和路径特征生成精确描述

```python
# 示例：智能生成描述
GET /api/v1/users/{id} → "获取用户详情"
POST /api/v1/orders → "创建订单"
DELETE /api/v1/cart/items/{id} → "删除商品"
```

#### ⚖️ 业务关键性分析器 (CriticalityAnalyzer)
- **领域识别**: 智能识别金融、认证、用户数据等不同业务领域
- **风险评估**: 基于关键词模式和HTTP方法评估风险等级
- **评分系统**: 0-10分评分，自动调整测试数量

```python
# 示例：关键性评分
/api/v1/payments/charge → 6分（极高风险）
/api/v1/auth/login → 5分（高风险）
/api/v1/products → 0分（低风险）
```

### 技术优势

1. **零配置设计**: 自动检测模块结构，无需配置文件
2. **通用兼容**: 支持任何RESTful API设计规范
3. **轻量级**: 仅增加inflect一个依赖（35KB）
4. **高性能**: 推断速度<50ms，几乎无性能影响
5. **向后兼容**: 保持所有现有功能不变

### 应用场景

- **电商API**: 用户、商品、订单、购物车等
- **金融API**: 支付、转账、账户、交易等
- **社交API**: 用户、帖子、评论、关注等
- **企业API**: 员工、部门、权限、报表等
- **任何标准RESTful API**: 自动适配各种业务领域

## 路线图

- [x] ~~智能动态测试用例生成（已完成）~~
- [x] ~~接口复杂度自动评估（已完成）~~
- [x] ~~支持多个 LLM 提供商（GLM、Qwen、DeepSeek）（已完成）~~
- [x] ~~自动故障转移和负载均衡（已完成）~~
- [x] ~~增强重试机制和进度跟踪（已完成）~~
- [x] ~~智能推断系统（v1.1已完成）~~
- [x] ~~日志系统优化（已完成）~~
- [ ] 直接生成可执行测试代码（pytest、jest）
- [ ] 支持 Postman Collection 导出
- [ ] 交互式 TUI 界面
- [ ] 测试用例智能去重
- [ ] 插件系统支持自定义格式化器
- [ ] 支持更多 LLM 提供商（OpenAI、Anthropic 等）
- [ ] 测试用例执行和结果验证
- [ ] API 变更影响分析

## 贡献指南

欢迎提交 Issue 和 Pull Request！详见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 相关文档

- [需求文档](docs/需求文档.md) - 详细的产品需求说明
- [CLAUDE.md](CLAUDE.md) - Claude AI 开发指导文档