/** REST API veri tipleri. */

export type MessageRole = 'system' | 'user' | 'assistant' | 'tool';

export type ServiceState = 'up' | 'down' | 'starting' | 'unknown' | 'degraded';

export type RiskLevel = 'low' | 'medium' | 'high';

export type ExecutionTarget = 'backend' | 'host';

export type MemoryCategory =
  | 'preference'
  | 'system_info'
  | 'project'
  | 'folder'
  | 'application'
  | 'contact'
  | 'fact'
  | 'other';

export type DocumentStatus = 'pending' | 'parsing' | 'embedding' | 'indexed' | 'failed';

export interface ConversationSummary {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
  archived: boolean;
}

export interface SourceRef {
  chunk_id: string;
  document_id: string;
  filename: string;
  score: number;
  snippet: string;
  page: number | null;
}

export interface MemoryRef {
  id: string;
  content: string;
  category: string;
  score: number;
}

export interface ToolCallSummary {
  tool_name: string;
  display_name?: string;
  arguments?: Record<string, unknown>;
  success: boolean;
  error?: string | null;
  duration_ms?: number;
  rejected?: boolean;
  result?: Record<string, unknown>;
}

export interface MessageMeta {
  sources?: SourceRef[];
  memories?: MemoryRef[];
  tool_calls?: ToolCallSummary[];
}

export interface ChatMessage {
  id: string;
  conversation_id: string;
  role: MessageRole;
  content: string;
  thinking: string | null;
  created_at: string;
  token_count: number;
  meta: MessageMeta;
}

export interface ConversationDetail extends ConversationSummary {
  summary: string | null;
  messages: ChatMessage[];
}

export interface ChatOptions {
  use_rag: boolean;
  use_memory: boolean;
  use_tools: boolean;
  thinking: boolean;
  concise: boolean;
  tts: boolean;
  tts_voice?: string | null;
  tts_speed?: number | null;
  temperature?: number | null;
  max_tokens?: number | null;
  rag_top_k?: number | null;
  require_confirmation?: boolean;
  language?: 'tr' | 'en' | null;
}

export interface MemoryRecord {
  id: string;
  content: string;
  category: MemoryCategory;
  importance: number;
  pinned: boolean;
  active: boolean;
  source: string;
  source_conversation_id: string | null;
  use_count: number;
  last_used_at: string | null;
  created_at: string;
  updated_at: string;
  tags: string[];
}

export interface MemoryStats {
  total: number;
  pinned: number;
  by_category: Record<string, number>;
}

export interface DocumentRecord {
  id: string;
  filename: string;
  source_path: string | null;
  mime_type: string;
  extension: string;
  size_bytes: number;
  collection: string;
  status: DocumentStatus;
  chunk_count: number;
  error: string | null;
  created_at: string;
  indexed_at: string | null;
}

export interface DocumentSearchHit {
  chunk_id: string;
  document_id: string;
  filename: string;
  content: string;
  score: number;
  page: number | null;
}

export interface DocumentStats {
  total: number;
  by_status: Record<string, number>;
  total_size_bytes: number;
  total_chunks: number;
  vectors?: Record<string, number>;
  embedding_model?: string;
  embedding_fallback?: boolean;
  vector_store_available?: boolean;
}

export interface ToolParameterDef {
  name: string;
  type: string;
  description: string;
  required: boolean;
  enum: string[] | null;
  default: unknown;
}

export interface ToolDefinition {
  name: string;
  display_name: string;
  description: string;
  category: string;
  risk: RiskLevel;
  execution: ExecutionTarget;
  parameters: ToolParameterDef[];
  impact: string;
  enabled: boolean;
}

export interface ToolListResponse {
  tools: ToolDefinition[];
  host_bridge_connected: boolean;
}

export interface ToolResult {
  call_id: string;
  tool_name: string;
  success: boolean;
  result: Record<string, unknown>;
  error: string | null;
  duration_ms: number;
  requires_confirmation: boolean;
}

export interface ServiceStatus {
  name: string;
  display_name: string;
  state: ServiceState;
  detail: string | null;
  latency_ms: number | null;
  container_status: string | null;
  url: string | null;
}

export interface GPUInfo {
  name: string;
  vram_total_mb: number;
  vram_used_mb: number;
  vram_percent: number;
  utilization_percent: number;
  temperature_c: number | null;
  driver_version: string | null;
  available: boolean;
}

export interface DiskInfo {
  mount: string;
  total_gb: number;
  used_gb: number;
  percent: number;
}

export interface SystemMetrics {
  cpu_percent: number;
  cpu_cores: number;
  ram_total_mb: number;
  ram_used_mb: number;
  ram_percent: number;
  gpu: GPUInfo;
  disks: DiskInfo[];
  source: 'host' | 'container';
  timestamp: string;
}

export interface ModelStatus {
  loaded: boolean;
  model_id: string | null;
  max_model_len: number | null;
  detail: string | null;
}

export interface SystemStatus {
  services: ServiceStatus[];
  metrics: SystemMetrics;
  model: ModelStatus;
  host_bridge_connected: boolean;
  last_error: string | null;
  timestamp: string;
}

export interface TranscriptionSegment {
  start: number;
  end: number;
  text: string;
}

export interface TranscriptionResult {
  text: string;
  language: string;
  duration: number;
  segments: TranscriptionSegment[];
  model: string;
  device: string;
}

export interface VoiceInfo {
  id: string;
  name: string;
  language: string;
  quality: string;
  installed: boolean;
}

export interface VoiceListResponse {
  voices: VoiceInfo[];
  active: string | null;
}

export interface STTStatus {
  available: boolean;
  model: string;
  device: string;
  language: string;
  detail: string | null;
}

export type LlmCredentialSource = 'env' | 'ui' | 'none';

export interface LlmCredentialsStatus {
  configured: boolean;
  hint: string;
  source: LlmCredentialSource;
  model: string;
  enabled: boolean;
  provider?: string;
  provider_label?: string;
}

export interface LlmCredentialsUpdate {
  api_key?: string | null;
  model?: string | null;
}

export interface LlmCredentialsReveal {
  api_key: string;
  source: LlmCredentialSource;
}

export interface ApiErrorBody {
  code: string;
  message: string;
  details: Record<string, unknown>;
}

export interface ApiErrorResponse {
  error: ApiErrorBody;
}
