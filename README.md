# Astraship Agent OS

Astraship is a Python Agent OS platform that composes product capabilities around the Felix agent kernel.

## Development

Requirements: Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run astraship --help
uv run pytest
```

Astraship starts Felix as a separate process over newline-delimited JSON-RPC. Set `ASTRASHIP_FELIX_COMMAND` to the Felix server command, or configure `kernel.command` when embedding the client. The platform never downloads or bundles Felix.

```bash
ASTRASHIP_FELIX_COMMAND="felix-server --stdio" uv run astraship kernel check
ASTRASHIP_FELIX_COMMAND="felix-server --stdio" uv run astraship run --prompt "hello"
```

**下一代智能体操作系统**

Astraship 是一个面向 AI Agent 的操作系统级框架，为智能体提供完整的运行环境、工具生态和协作机制。

## 核心定位

- **Agent Runtime**: 提供标准化的智能体运行时环境
- **Tool Ecosystem**: 构建丰富的工具和能力生态
- **Multi-Agent Orchestration**: 支持多智能体协作和编排
- **Developer Platform**: 为开发者提供完整的 SDK 和工具链

## 快速开始

```bash
# 安装开发环境
uv sync

# 运行一个 prompt
ASTRASHIP_FELIX_COMMAND="felix-server --stdio" uv run astraship run --prompt "hello"
```

## 文档

- [产品架构](./docs/architecture.md)
- [生态组成](./docs/ecosystem.md)
- [开发指南](./docs/development.md)
- [API 文档](./docs/api.md)

## 核心特性

### 🚀 标准化运行时
- 统一的 Agent 生命周期管理
- 内存和状态持久化
- 资源调度和隔离

### 🛠️ 丰富的工具生态
- MCP (Model Context Protocol) 兼容
- 内置常用工具库
- 第三方工具市场

### 🤝 多智能体协作
- Agent 间通信协议
- 任务编排和调度
- 协作模式库

### 🔧 开发者友好
- TypeScript/Python SDK
- 可视化调试工具
- 完整的测试框架

## 架构概览

```
┌─────────────────────────────────────────────┐
│           Astraship Agent OS                │
├─────────────────────────────────────────────┤
│  Applications & Agents Layer                │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐   │
│  │  Agent   │ │  Agent   │ │  Agent   │   │
│  │    A     │ │    B     │ │    C     │   │
│  └──────────┘ └──────────┘ └──────────┘   │
├─────────────────────────────────────────────┤
│  Orchestration Layer                        │
│  • Multi-Agent Coordination                 │
│  • Workflow Engine                          │
│  • Task Scheduling                          │
├─────────────────────────────────────────────┤
│  Agent Runtime Layer                        │
│  • Lifecycle Management                     │
│  • Memory & State                           │
│  • Tool Execution                           │
├─────────────────────────────────────────────┤
│  Tool & Capability Layer                    │
│  • MCP Tools                                │
│  • Built-in Tools                           │
│  • Custom Tools                             │
├─────────────────────────────────────────────┤
│  Infrastructure Layer                       │
│  • Storage                                  │
│  • Networking                               │
│  • Security                                 │
└─────────────────────────────────────────────┘
```

## 许可证

MIT License
