# CaseCraft

使用 BigModel LLM 解析 API 文档（OpenAPI/Swagger）并生成结构化测试用例的 CLI 工具。

## 🆕 最新更新 (2025-08-05)

- **智能动态生成**: 根据 API 接口复杂度自动调整测试用例数量（5-12个）
- **质量优先**: 强调生成有意义的测试用例，避免为凑数而生成冗余用例
- **复杂度评估**: 自动分析接口参数、请求体、认证等因素确定适合的用例数量

## 核心特性

- 🎯 **智能测试用例生成**: 利用 BigModel GLM-4.5-X 自动生成全面的测试场景
- 📊 **动态用例数量**: 根据接口复杂度智能调整生成数量（简单5-6个，复杂10-12个）
- 📚 **多格式支持**: 支持 OpenAPI 3.0 和 Swagger 2.0 (JSON/YAML)
- 🔄 **增量生成**: 只为变更的 API 生成新测试，节省时间和成本
- ⚡ **并发处理**: 支持多线程处理，可通过 `--workers` 参数调整（BigModel 目前限制为 1）
- 🎨 **灵活输出**: 支持 JSON 格式，未来支持 pytest、jest 等
- 🌏 **双语支持**: 完美支持中文和英文文档及测试用例

## 快速开始

### 安装

```bash
pip install casecraft
```

### 初始化配置

```bash
casecraft init
```

配置文件保存在 `~/.casecraft/config.yaml`，包含 BigModel API 密钥等设置。

> **提示**: 如需使用 BigModel API，可以在 [BigModel 开放平台](https://open.bigmodel.cn/) 申请 API 密钥。

### 生成测试用例

```bash
# 从 URL 生成
casecraft generate https://petstore.swagger.io/v2/swagger.json

# 从本地文件生成
casecraft generate ./api-docs.yaml

# 使用过滤器
casecraft generate ./openapi.json --include-tag users --exclude-tag admin

# 指定并发数（未来支持其他 LLM 时可用）
casecraft generate ./api.yaml --workers 4

# 预览模式（不调用 LLM）
casecraft generate ./api.yaml --dry-run
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
- `--include-tag`: 只包含指定标签的端点
- `--exclude-tag`: 排除指定标签的端点
- `--include-path`: 只包含匹配模式的路径
- `--workers, -w`: 并发工作线程数（默认：1，BigModel 只支持 1）
- `--force`: 强制重新生成所有测试用例
- `--dry-run`: 预览模式，不调用 LLM
- `--organize-by`: 按标签组织输出文件

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

支持通过环境变量配置 API 密钥：

```bash
# BigModel API
export BIGMODEL_API_KEY="your-api-key"

# 或使用通用环境变量
export CASECRAFT_LLM_API_KEY="your-api-key"
```

## 输出格式

每个生成的测试用例遵循以下 JSON 结构：

```json
{
  "name": "创建用户成功",
  "description": "使用所有必填字段测试用户创建成功的场景",
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

## 路线图

- [x] ~~智能动态测试用例生成（已完成）~~
- [x] ~~接口复杂度自动评估（已完成）~~
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