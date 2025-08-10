# 📋 合并到 Master 分支的详细执行计划

> 生成时间：2025-08-10
> 版本：v0.2.0
> 功能：多 LLM 提供商支持

## 🎯 目标

安全地将 `feature/multi-llm-providers` 分支合并到 `master` 分支

## 📊 风险评估结果

- **风险等级**：中低风险 ⚠️
- **代码变更**：33个文件，约6400行代码
- **新增提交**：12个
- **测试状态**：全部通过（10/10）

## 🔄 执行计划（共30个任务）

### 阶段 1：准备和备份（6个任务）

#### 任务 1.1：检查当前分支状态
```bash
git status
git branch -a
```
- [ ] 执行状态：待执行
- [ ] 结果记录：

#### 任务 1.2：创建主分支备份
```bash
git checkout main
git pull origin main
git branch backup/main-before-multi-provider-$(date +%Y%m%d-%H%M%S)
```
- [ ] 执行状态：待执行
- [ ] 备份分支名：

#### 任务 1.3：创建功能分支备份
```bash
git checkout feature/multi-llm-providers
git branch backup/feature-multi-llm-providers-$(date +%Y%m%d-%H%M%S)
```
- [ ] 执行状态：待执行
- [ ] 备份分支名：

#### 任务 1.4：推送备份分支到远程
```bash
git push origin backup/main-before-multi-provider-[timestamp]
git push origin backup/feature-multi-llm-providers-[timestamp]
```
- [ ] 执行状态：待执行
- [ ] 推送结果：

#### 任务 1.5：记录当前提交哈希
```bash
echo "Main: $(git rev-parse main)" > merge_record.txt
echo "Feature: $(git rev-parse feature/multi-llm-providers)" >> merge_record.txt
```
- [ ] 执行状态：待执行
- [ ] Main哈希：
- [ ] Feature哈希：

#### 任务 1.6：清理工作区
```bash
git clean -fd
git stash list
```
- [ ] 执行状态：待执行
- [ ] 清理结果：

---

### 阶段 2：预合并验证（6个任务）

#### 任务 2.1：创建测试合并分支
```bash
git checkout -b test-merge-multi-provider main
```
- [ ] 执行状态：待执行
- [ ] 分支创建：

#### 任务 2.2：执行测试合并
```bash
git merge feature/multi-llm-providers --no-commit --no-ff
```
- [ ] 执行状态：待执行
- [ ] 合并结果：

#### 任务 2.3：检查合并冲突
```bash
git status
git diff --name-only --diff-filter=U
```
- [ ] 执行状态：待执行
- [ ] 冲突文件：

#### 任务 2.4：运行基础导入测试
```bash
python -c "import casecraft; print('Import test passed')"
```
- [ ] 执行状态：待执行
- [ ] 测试结果：

#### 任务 2.5：运行CLI测试
```bash
casecraft --version
casecraft generate --help
```
- [ ] 执行状态：待执行
- [ ] CLI状态：

#### 任务 2.6：运行单元测试
```bash
python -m pytest tests/test_multi_provider.py -v
```
- [ ] 执行状态：待执行
- [ ] 测试结果：

---

### 阶段 3：功能验证（6个任务）

#### 任务 3.1：测试单提供商模式
```bash
casecraft generate ecommerce_api_openapi.json --provider glm --include-path "/health" --dry-run
```
- [ ] 执行状态：待执行
- [ ] 功能状态：

#### 任务 3.2：测试多提供商模式
```bash
casecraft generate ecommerce_api_openapi.json --providers glm,qwen --dry-run
```
- [ ] 执行状态：待执行
- [ ] 功能状态：

#### 任务 3.3：验证配置加载
```bash
python -c "from casecraft.core.management.config_manager import ConfigManager; cm = ConfigManager(); print('Config OK')"
```
- [ ] 执行状态：待执行
- [ ] 配置状态：

#### 任务 3.4：验证状态管理
```bash
ls -la .casecraft_state.json .casecraft_provider_stats.json 2>/dev/null || echo "State files OK"
```
- [ ] 执行状态：待执行
- [ ] 状态文件：

#### 任务 3.5：验证日志系统
```bash
CASECRAFT_LOG_LEVEL=DEBUG casecraft generate ecommerce_api_openapi.json --provider glm --dry-run 2>&1 | head -5
```
- [ ] 执行状态：待执行
- [ ] 日志输出：

#### 任务 3.6：完成测试合并
```bash
git commit -m "Test merge: feature/multi-llm-providers into main"
git log --oneline -n 3
```
- [ ] 执行状态：待执行
- [ ] 提交记录：

---

### 阶段 4：正式合并（6个任务）

#### 任务 4.1：切换到主分支
```bash
git checkout main
git pull origin main --ff-only
```
- [ ] 执行状态：待执行
- [ ] 分支状态：

#### 任务 4.2：执行正式合并
```bash
git merge feature/multi-llm-providers --no-ff -m "feat: 合并多LLM提供商支持功能

- 支持 GLM、Qwen、Kimi、Local 多个提供商
- 实现智能故障转移和负载均衡
- 添加详细的使用统计和监控
- 完善的文档和示例"
```
- [ ] 执行状态：待执行
- [ ] 合并提交：

#### 任务 4.3：验证合并结果
```bash
git log --oneline -n 5
git diff HEAD~1 --stat
```
- [ ] 执行状态：待执行
- [ ] 验证结果：

#### 任务 4.4：打标签
```bash
git tag -a v0.2.0 -m "Release v0.2.0: Multi-LLM Provider Support

Features:
- Multi-provider support (GLM, Qwen, Kimi, Local)
- Automatic fallback mechanism
- Provider strategies (round-robin, random, complexity, manual)
- Enhanced statistics and monitoring"
```
- [ ] 执行状态：待执行
- [ ] 标签创建：

#### 任务 4.5：推送到远程仓库
```bash
git push origin main
git push origin v0.2.0
```
- [ ] 执行状态：待执行
- [ ] 推送结果：

#### 任务 4.6：验证远程更新
```bash
git fetch origin
git log origin/main --oneline -n 3
```
- [ ] 执行状态：待执行
- [ ] 远程状态：

---

### 阶段 5：部署后验证（6个任务）

#### 任务 5.1：创建新的工作目录测试
```bash
cd /tmp
git clone https://github.com/Devliang24/casecraft.git casecraft-test
cd casecraft-test
```
- [ ] 执行状态：待执行
- [ ] 克隆结果：

#### 任务 5.2：安装和测试
```bash
pip install -e .
casecraft --version
```
- [ ] 执行状态：待执行
- [ ] 安装状态：

#### 任务 5.3：运行示例命令
```bash
casecraft generate ecommerce_api_openapi.json --provider qwen --workers 1 --dry-run
```
- [ ] 执行状态：待执行
- [ ] 运行结果：

#### 任务 5.4：检查文档
```bash
grep "Multi-LLM Provider" README.md
ls docs/multi-llm-*.md
```
- [ ] 执行状态：待执行
- [ ] 文档状态：

#### 任务 5.5：清理测试分支
```bash
cd /opt/api
git branch -d test-merge-multi-provider
```
- [ ] 执行状态：待执行
- [ ] 清理结果：

#### 任务 5.6：生成合并报告
```bash
echo "=== Merge Report ===" > merge_report.md
echo "Date: $(date)" >> merge_report.md
echo "Version: v0.2.0" >> merge_report.md
echo "Features merged: Multi-LLM Provider Support" >> merge_report.md
echo "Files changed: 33" >> merge_report.md
echo "Lines added: ~6400" >> merge_report.md
echo "Status: SUCCESS" >> merge_report.md
```
- [ ] 执行状态：待执行
- [ ] 报告生成：

---

## 🔄 回滚计划

如果在任何阶段发现问题，执行以下回滚步骤：

### 回滚步骤
```bash
# 1. 切换到备份分支
git checkout backup/main-before-multi-provider-[timestamp]

# 2. 强制更新main
git branch -f main backup/main-before-multi-provider-[timestamp]

# 3. 推送回滚
git push origin main --force-with-lease

# 4. 删除问题标签（如果已创建）
git push origin :v0.2.0

# 5. 通知团队
echo "Rollback completed at $(date)"
```

### 回滚触发条件
- [ ] 合并冲突无法解决
- [ ] 测试失败率 > 10%
- [ ] CLI 命令无法正常工作
- [ ] 导入错误
- [ ] 严重的性能问题

---

## ✅ 成功标准

- [ ] 所有30个任务执行完成
- [ ] 所有测试通过
- [ ] CLI 命令正常工作
- [ ] 文档已更新
- [ ] 标签 v0.2.0 已创建
- [ ] 远程仓库已更新
- [ ] 可以从新clone的仓库正常使用

---

## 📝 执行记录

### 开始时间：
### 完成时间：
### 执行人：
### 最终状态：

---

## 📊 执行统计

- 总任务数：30
- 已完成：0
- 进行中：0
- 待执行：30
- 失败：0

---

## 🚨 问题记录

如果遇到问题，在此记录：

1. 问题描述：
   - 时间：
   - 任务编号：
   - 错误信息：
   - 解决方案：

---

## 📋 检查清单

### 合并前检查
- [ ] 确认没有未提交的更改
- [ ] 确认测试环境正常
- [ ] 确认有足够的磁盘空间
- [ ] 确认网络连接正常
- [ ] 确认有 GitHub 推送权限

### 合并后检查
- [ ] 主分支可以正常checkout
- [ ] 可以运行基本命令
- [ ] 远程仓库已更新
- [ ] 标签已创建
- [ ] 文档已更新

---

## 🔗 相关链接

- GitHub 仓库：https://github.com/Devliang24/casecraft
- 功能分支：feature/multi-llm-providers
- 相关 PR：（待创建）
- 相关 Issue：（如有）

---

*本文档由合并执行计划自动生成*