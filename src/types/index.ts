/**
 * Agent 配置接口
 */
export interface AgentConfig {
  id: string;
  name: string;
  description?: string;
  model?: string;
  temperature?: number;
  maxTokens?: number;
  tools?: string[];
  memory?: MemoryConfig;
  metadata?: Record<string, unknown>;
}

/**
 * 内存配置
 */
export interface MemoryConfig {
  type: 'ephemeral' | 'persistent';
  storage?: 'memory' | 'file' | 'vector';
  maxSize?: number;
  ttl?: number;
}

/**
 * Agent 生命周期状态
 */
export enum AgentStatus {
  CREATED = 'created',
  INITIALIZED = 'initialized',
  RUNNING = 'running',
  PAUSED = 'paused',
  STOPPED = 'stopped',
  ERROR = 'error',
  TERMINATED = 'terminated',
}

/**
 * Agent 上下文
 */
export interface AgentContext {
  agentId: string;
  conversationId: string;
  sessionId: string;
  variables: Record<string, unknown>;
  metadata: Record<string, unknown>;
}

/**
 * 工具定义
 */
export interface Tool {
  name: string;
  description: string;
  inputSchema: Record<string, unknown>;
  outputSchema?: Record<string, unknown>;
  execute: (input: unknown, context: AgentContext) => Promise<unknown>;
}

/**
 * 工具调用结果
 */
export interface ToolResult {
  toolName: string;
  success: boolean;
  result?: unknown;
  error?: Error;
  duration: number;
  timestamp: Date;
}

/**
 * 消息类型
 */
export enum MessageRole {
  USER = 'user',
  ASSISTANT = 'assistant',
  SYSTEM = 'system',
  TOOL = 'tool',
}

/**
 * 消息接口
 */
export interface Message {
  id: string;
  role: MessageRole;
  content: string;
  timestamp: Date;
  metadata?: Record<string, unknown>;
}

/**
 * Agent 执行结果
 */
export interface AgentExecutionResult {
  agentId: string;
  success: boolean;
  output?: unknown;
  error?: Error;
  messages: Message[];
  toolCalls: ToolResult[];
  duration: number;
  timestamp: Date;
}

/**
 * 工作流定义
 */
export interface Workflow {
  id: string;
  name: string;
  description?: string;
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
  metadata?: Record<string, unknown>;
}

/**
 * 工作流节点
 */
export interface WorkflowNode {
  id: string;
  type: 'agent' | 'tool' | 'condition' | 'parallel' | 'merge';
  config: Record<string, unknown>;
}

/**
 * 工作流边
 */
export interface WorkflowEdge {
  id: string;
  source: string;
  target: string;
  condition?: string;
}

/**
 * 事件类型
 */
export enum EventType {
  AGENT_CREATED = 'agent:created',
  AGENT_STARTED = 'agent:started',
  AGENT_STOPPED = 'agent:stopped',
  AGENT_ERROR = 'agent:error',
  TOOL_CALLED = 'tool:called',
  TOOL_COMPLETED = 'tool:completed',
  TOOL_FAILED = 'tool:failed',
  MESSAGE_RECEIVED = 'message:received',
  MESSAGE_SENT = 'message:sent',
}

/**
 * 事件接口
 */
export interface Event {
  id: string;
  type: EventType;
  agentId?: string;
  payload: Record<string, unknown>;
  timestamp: Date;
}
