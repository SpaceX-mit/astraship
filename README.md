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

## Tool Runtime

Astraship exposes a guarded Python tool registry independently of Felix. Tool schemas are validated before registration, calls are checked before dispatch, and results are normalized into stable success or error values. Built-in file tools are explicitly scoped to a workspace.

```python
import asyncio
from pathlib import Path

from astraship.tools import ToolCall, ToolContext, ToolRegistry, builtin_file_tools


async def main() -> None:
    registry = ToolRegistry()
    for tool in builtin_file_tools():
        registry.register(tool)
    result = await registry.execute(
        ToolCall("read-1", "read_file", {"path": "README.md"}),
        ToolContext(Path.cwd()),
    )
    print(result.output if not result.is_error else result.error)


asyncio.run(main())
```

The registry is the platform capability seam for future MCP integrations and
the Felix host-tool adapter below. Felix remains the agent kernel; Astraship
does not embed or implement that kernel.

When the Felix host-tool request API is enabled, the adapter wires the same
registry into the stdio client:

    from astraship.kernel.client import FelixClient
    from astraship.kernel.host_tools import HostToolAdapter

    adapter = HostToolAdapter(registry, ToolContext(Path.cwd()))
    client = FelixClient(
        config,
        capabilities=adapter.capability(),
        request_handlers=adapter.handlers(),
    )

The adapter is covered both by deterministic protocol tests and by a real-process
integration test. The latter builds `felix-server`, starts a local deterministic
OpenAI-compatible HTTP fixture, and executes an actual workspace `read_file` call.
It does not use an external service or API key:

```bash
ASTRASHIP_TEST_FELIX_REPO=../felix \
  PYTHONPATH=src uv run pytest tests/integration/test_real_felix_host_tools.py -v
```

`ASTRASHIP_TEST_FELIX_REPO` is optional when the Felix and Astraship repositories
are sibling directories.

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
