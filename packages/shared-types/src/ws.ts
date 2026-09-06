/**
 * WebSocket protokolü.
 *
 * Python karşılığı: `apps/api/app/schemas/chat.py` ve `.../system.py`.
 */

import type { ChatOptions, MemoryRef, SourceRef, SystemStatus } from './api';

export interface WSUserMessage {
  type: 'user_message';
  conversation_id?: string | null;
  content: string;
  options: ChatOptions;
}

export interface WSToolConfirmResponse {
  type: 'tool_confirm_response';
  request_id: string;
  approved: boolean;
  remember?: boolean;
  fingerprint?: string;
  confirmation_ticket?: string;
}

export interface WSCancel {
  type: 'cancel';
}

export interface WSPing {
  type: 'ping';
}

export type WSClientEvent = WSUserMessage | WSToolConfirmResponse | WSCancel | WSPing;

export interface WSStart {
  type: 'start';
  conversation_id: string;
  message_id: string;
}

export interface WSToken {
  type: 'token';
  content: string;
}

export interface WSThinking {
  type: 'thinking';
  content: string;
}

export interface WSToolCall {
  type: 'tool_call';
  call_id: string;
  tool_name: string;
  display_name: string;
  arguments: Record<string, unknown>;
}

export interface WSToolResult {
  type: 'tool_result';
  call_id: string;
  tool_name: string;
  success: boolean;
  result: Record<string, unknown>;
  error: string | null;
  duration_ms: number;
}

export interface WSToolConfirmRequest {
  type: 'tool_confirm_request';
  request_id: string;
  tool_name: string;
  display_name: string;
  description: string;
  arguments: Record<string, unknown>;
  risk_level: 'low' | 'medium' | 'high';
  impact: string;
  fingerprint?: string;
  remember_allowed?: boolean;
  irreversible?: boolean;
  confirmation_ticket?: string;
}

export interface WSSources {
  type: 'sources';
  sources: SourceRef[];
}

export interface WSMemoryUsed {
  type: 'memory_used';
  memories: MemoryRef[];
}

export interface WSMemoryCreated {
  type: 'memory_created';
  id: string;
  content: string;
  category: string;
  importance: number;
}

export interface WSTTSChunk {
  type: 'tts_chunk';
  index: number;
  audio_base64: string;
  mime_type: string;
  text: string;
  voice?: string | null;
  speed?: number | null;
}

export interface WSTTSStatus {
  type: 'tts_status';
  state: 'started' | 'finished' | 'error' | 'disabled';
  detail: string | null;
}

export interface WSDone {
  type: 'done';
  conversation_id: string;
  message_id: string;
  content: string;
  finish_reason: string;
  elapsed_ms: number;
}

export interface WSError {
  type: 'error';
  code: string;
  message: string;
  details: Record<string, unknown>;
}

export interface WSPong {
  type: 'pong';
}

export type WSServerEvent =
  | WSStart
  | WSToken
  | WSThinking
  | WSToolCall
  | WSToolResult
  | WSToolConfirmRequest
  | WSSources
  | WSMemoryUsed
  | WSMemoryCreated
  | WSTTSChunk
  | WSTTSStatus
  | WSDone
  | WSError
  | WSPong;

export interface WSSystemUpdate {
  type: 'system_update';
  payload: SystemStatus;
}

export interface HostToolRequest {
  type: 'host_tool_request';
  request_id: string;
  tool_name: string;
  arguments: Record<string, unknown>;
  timeout_ms: number;
}

export interface HostToolResponse {
  type: 'host_tool_response';
  request_id: string;
  success: boolean;
  result: Record<string, unknown>;
  error: string | null;
  cancelled?: boolean;
}

export interface HostMetricsPush {
  type: 'host_metrics';
  payload: Record<string, unknown>;
}

export interface HostCapabilities {
  type: 'host_capabilities';
  tools: string[];
  platform: string;
  arch: string;
  version: string;
  features: Record<string, unknown>;
}

export interface HostToolCancel {
  type: 'host_tool_cancel';
  request_id: string;
}

export type HostBridgeOutbound =
  | HostToolResponse
  | HostMetricsPush
  | HostCapabilities
  | { type: 'ping' };
