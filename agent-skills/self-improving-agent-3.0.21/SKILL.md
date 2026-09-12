---
name: self-improvement
description: "记录学习、错误和纠正，实现持续改进。触发场景：(1) 命令或操作意外失败 (2) 用户纠正你 (3) 用户请求不存在的功能 (4) 外部 API 或工具失败 (5) 发现更好的方法。在主要任务前也应检查已有学习记录。"
tools: [read_file, write_file, shell, search_files, write_memory]
---

# Self-Improvement Skill

将学习和错误记录到 markdown 文件中，实现持续改进。高价值的学习记录会被提升到项目记忆中。

## 初始化

首次使用前，确保 `.learnings/` 目录和文件存在：

```bash
mkdir -p .learnings
[ -f .learnings/LEARNINGS.md ] || printf "# Learnings\n\n开发过程中捕获的纠正、洞察和知识缺口。\n\n**类别**: correction | insight | knowledge_gap | best_practice\n\n---\n" > .learnings/LEARNINGS.md
[ -f .learnings/ERRORS.md ] || printf "# Errors\n\n命令失败和集成错误。\n\n---\n" > .learnings/ERRORS.md
[ -f .learnings/FEATURE_REQUESTS.md ] || printf "# Feature Requests\n\n用户请求的功能。\n\n---\n" > .learnings/FEATURE_REQUESTS.md
```

如果 `.learnings/` 已存在，不覆盖。

不要记录密钥、token、密码或完整配置文件。优先使用简短摘要或脱敏摘录。

## 快速参考

| 场景 | 操作 |
|------|------|
| 命令/操作失败 | 记录到 `.learnings/ERRORS.md` |
| 用户纠正你 | 记录到 `.learnings/LEARNINGS.md`，类别 `correction` |
| 用户想要缺失的功能 | 记录到 `.learnings/FEATURE_REQUESTS.md` |
| API/外部工具失败 | 记录到 `.learnings/ERRORS.md`，附集成细节 |
| 知识过时 | 记录到 `.learnings/LEARNINGS.md`，类别 `knowledge_gap` |
| 发现更好的方法 | 记录到 `.learnings/LEARNINGS.md`，类别 `best_practice` |
| 广泛适用的学习 | 提升到 `MEMORY.md`（使用 write_memory 工具） |

## 日志格式

### 学习条目

追加到 `.learnings/LEARNINGS.md`：

```markdown
## [LRN-YYYYMMDD-XXX] category

**时间**: ISO-8601 时间戳
**优先级**: low | medium | high | critical
**状态**: pending
**领域**: frontend | backend | infra | tests | docs | config

### 摘要
一行描述学到了什么

### 详情
完整上下文：发生了什么、哪里错了、正确的做法

### 建议操作
具体的修复或改进方案

### 元数据
- 来源: conversation | error | user_feedback
- 相关文件: path/to/file.ext
- 标签: tag1, tag2
```

### 错误条目

追加到 `.learnings/ERRORS.md`：

```markdown
## [ERR-YYYYMMDD-XXX] skill_or_command_name

**时间**: ISO-8601 时间戳
**优先级**: high
**状态**: pending

### 摘要
简要描述失败内容

### 错误信息
```
实际错误消息或输出
```

### 上下文
- 尝试的命令/操作
- 使用的输入或参数
- 相关环境细节

### 建议修复
如果可识别，可能的解决方案

### 元数据
- 可复现: yes | no | unknown
- 相关文件: path/to/file.ext
```

### 功能请求条目

追加到 `.learnings/FEATURE_REQUESTS.md`：

```markdown
## [FEAT-YYYYMMDD-XXX] capability_name

**时间**: ISO-8601 时间戳
**优先级**: medium
**状态**: pending

### 请求的功能
用户想做什么

### 用户上下文
为什么需要，解决什么问题

### 复杂度估计
simple | medium | complex

### 建议实现
如何构建
```

## ID 生成

格式：`TYPE-YYYYMMDD-XXX`
- TYPE: `LRN`（学习）、`ERR`（错误）、`FEAT`（功能）
- YYYYMMDD: 当前日期
- XXX: 顺序号或随机 3 字符

## 解决条目

问题修复后，更新条目：

1. `**状态**: pending` → `**状态**: resolved`
2. 在元数据后添加解决块：

```markdown
### 解决方案
- **解决时间**: 2025-01-16T09:00:00Z
- **备注**: 简要描述做了什么
```

## 提升到项目记忆

当学习广泛适用时（不是一次性修复），使用 `write_memory` 工具提升到项目记忆。

### 何时提升

- 学习适用于多个文件/功能
- 任何贡献者（人类或 AI）都应该知道
- 防止重复犯错
- 记录项目特定约定

### 提升方法

1. **提炼**学习为简洁的规则或事实
2. 使用 `write_memory` 工具保存到项目记忆
3. 更新原始条目状态为 `promoted`

## 检测触发器

自动记录以下情况：

**纠正**（→ learning，类别 `correction`）：
- "不对，应该是..."
- "你搞错了..."
- "这已经过时了..."

**功能请求**（→ feature request）：
- "能不能..."
- "我希望你能..."
- "有没有办法..."

**知识缺口**（→ learning，类别 `knowledge_gap`）：
- 用户提供了你不知道的信息
- 你引用的文档已过时
- API 行为与你的理解不同

**错误**（→ error entry）：
- 命令返回非零退出码
- 异常或堆栈跟踪
- 意外输出或行为
- 超时或连接失败

## 定期审查

在自然断点时审查 `.learnings/`：

### 何时审查
- 开始新的主要任务前
- 完成功能后
- 在有历史学习的领域工作时

### 审查操作
- 解决已修复的条目
- 提升适用的学习
- 链接相关条目
- 升级重复出现的问题

## 最佳实践

1. **立即记录** - 上下文在问题发生后最清晰
2. **具体明确** - 未来的 agent 需要快速理解
3. **包含复现步骤** - 尤其是错误
4. **链接相关文件** - 使修复更容易
5. **建议具体修复** - 不只是"调查一下"
6. **积极提升** - 如果有疑虑，使用 write_memory 保存到项目记忆
7. **定期审查** - 过时的学习失去价值
