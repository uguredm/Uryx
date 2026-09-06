/**
 * Continue / OI: onay cevabı bool değil — bilet + parmak izi + hatırla.
 * HIGH ve geri alınamaz işlemlerde remember asla gitmez.
 */

import type { WSToolConfirmRequest, WSToolConfirmResponse } from '@shared/ws';

import type { MessageKey } from '@/lib/messages';
import { tNow } from '@/lib/tNow';

/** Odysseus `PendingToolApproval.public_payload` digest[:16] — mühür, yetki değil. */
export function sealDigest(fingerprint?: string): string {
  const raw = (fingerprint ?? '').replace(/\s+/g, '');
  return raw.length >= 8 ? raw.slice(0, 16) : '';
}

/** Yeni sohbet / geçmiş — onay modalı veya üretim varken turu kes. */
export function chatTurnIsActive(
  generating: boolean,
  pendingConfirmation: unknown,
): boolean {
  return Boolean(generating || pendingConfirmation);
}

/** Soket koptu / 4401 — modal kalmasın, geç onay gitmesin. */
export function chatSocketLost(status: string): boolean {
  return status === 'closed' || status === 'error';
}

/** tool_result bu onaya aitse (timeout/red) modalı kapat. */
export function confirmMatchesCall(
  pendingRequestId: string | undefined,
  callId: string,
): boolean {
  return Boolean(pendingRequestId && callId && pendingRequestId === callId);
}

/** Onay red / iptal / süre — kartı “başarısız” değil “reddedildi” yapsın. */
export function toolResultIsRejected(error: string | null | undefined): boolean {
  return /reddetti|iptal|zaman aşımına uğradı|rejected|cancelled|canceled|timed out/i.test(
    String(error ?? ''),
  );
}

export function canRememberConfirm(pending: WSToolConfirmRequest): boolean {
  return (
    pending.risk_level === 'medium' &&
    pending.remember_allowed !== false &&
    pending.irreversible !== true
  );
}

function mcpCallParts(pending: WSToolConfirmRequest): { server: string; tool: string } {
  const args = pending.arguments ?? {};
  return {
    server: String(args.server ?? '').trim(),
    tool: String(args.tool ?? '').trim(),
  };
}

/** mcp_call onayında sunucu/araç; HIGH oturum izni yok. */
export function mcpConfirmImpact(pending: WSToolConfirmRequest): string {
  if (pending.tool_name !== 'mcp_call') {
    return pending.impact || tNow('confirm.impactDefault');
  }
  const { server, tool } = mcpCallParts(pending);
  if (server && tool) {
    return tNow('confirm.mcpImpact', { server, tool });
  }
  return pending.impact || tNow('confirm.mcpDefault');
}

export function mcpConfirmToolLabel(pending: WSToolConfirmRequest): string {
  return toolCardLabel(pending.tool_name, pending.display_name, pending.arguments);
}

function mcpServerId(
  args: Record<string, unknown> | undefined,
  result?: Record<string, unknown>,
): string {
  return String(args?.server ?? result?.server ?? '').trim();
}

function mcpToolId(
  args: Record<string, unknown> | undefined,
  result?: Record<string, unknown>,
): string {
  return String(args?.tool ?? result?.tool ?? '').trim();
}

/** mcp_call kartı: sunucu → araç. Arg yoksa sonuçtaki sunucu/araç. */
export function toolCardLabel(
  toolName: string,
  displayName: string,
  args: Record<string, unknown> | undefined,
  result?: Record<string, unknown>,
): string {
  if (toolName === 'mcp_list_tools') {
    const server = mcpServerId(args, result);
    return server ? `${displayName} · ${server}` : displayName;
  }
  if (toolName !== 'mcp_call') return displayName;
  const server = mcpServerId(args, result);
  const tool = mcpToolId(args, result);
  if (server && tool) return `${displayName} · ${server} → ${tool}`;
  return displayName;
}

/** HUD satırı dar — “MCP aracı çağır ·” önekini düşür. */
export function hudToolLabel(
  toolName: string,
  displayName: string,
  args: Record<string, unknown> | undefined,
  result?: Record<string, unknown>,
): string {
  if (toolName === 'mcp_list_tools') return mcpServerId(args, result) || displayName;
  if (toolName !== 'mcp_call') return displayName;
  const server = mcpServerId(args, result);
  const tool = mcpToolId(args, result);
  if (server && tool) return `${server} → ${tool}`;
  return displayName;
}

const HOST_DISPLAY_KEYS = new Set(['execution_policy', 'output_truncated', '_meta']);

/** MCP text parçası JSON ise kartta okunaklı yaz. */
export function prettyDisplayText(text: string): string {
  const trimmed = text.trim();
  if (!trimmed) return '';
  if (
    !(
      (trimmed.startsWith('{') && trimmed.endsWith('}')) ||
      (trimmed.startsWith('[') && trimmed.endsWith(']'))
    )
  ) {
    return trimmed;
  }
  try {
    return JSON.stringify(JSON.parse(trimmed) as unknown, null, 2).slice(0, 4000);
  } catch {
    return trimmed;
  }
}

function redactDisplayValue(value: unknown): unknown {
  if (typeof value === 'string' && value.length > 240 && !value.includes(' ')) {
    return tNow('confirm.chars', { n: value.length });
  }
  if (Array.isArray(value)) return value.map(redactDisplayValue);
  if (value && typeof value === 'object') {
    const out: Record<string, unknown> = {};
    for (const [key, inner] of Object.entries(value as Record<string, unknown>)) {
      out[key] = redactDisplayValue(inner);
    }
    return out;
  }
  return value;
}

/** Host köprü alanlarını kart JSON’undan düşür. */
export function stripHostDisplayMeta(
  result: Record<string, unknown> | undefined,
): Record<string, unknown> | undefined {
  if (!result) return undefined;
  const cleaned: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(result)) {
    if (HOST_DISPLAY_KEYS.has(key)) continue;
    cleaned[key] = redactDisplayValue(value);
  }
  return cleaned;
}

function asArgRecord(value: unknown): Record<string, unknown> | null {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  if (typeof value !== 'string') return null;
  const trimmed = value.trim();
  if (!trimmed.startsWith('{') || !trimmed.endsWith('}')) return null;
  try {
    const parsed: unknown = JSON.parse(trimmed);
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      return parsed as Record<string, unknown>;
    }
  } catch {
    return null;
  }
  return null;
}

/** Host sarmalayıcısını soy, iç MCP sonucunu göster. */
export function toolCardResult(
  toolName: string,
  result: Record<string, unknown> | undefined,
): Record<string, unknown> | undefined {
  if (!result) return undefined;
  if (toolName !== 'mcp_call') return stripHostDisplayMeta(result);
  const inner = result.result;
  if (inner && typeof inner === 'object' && !Array.isArray(inner)) {
    return stripHostDisplayMeta(inner as Record<string, unknown>);
  }
  if (typeof inner === 'string') {
    const text = inner.trim();
    return {
      text: text.length > 240 && !text.includes(' ') ? tNow('confirm.chars', { n: text.length }) : text,
    };
  }
  if (Array.isArray(inner)) return stripHostDisplayMeta({ content: inner });
  return stripHostDisplayMeta(result);
}

export function mcpResultIsError(
  toolName: string,
  result: Record<string, unknown> | undefined,
): boolean {
  if (toolName !== 'mcp_call' || !result) return false;
  const inner = toolCardResult(toolName, result) ?? result;
  return inner.isError === true;
}

export type ToolDisplayStatus = 'running' | 'success' | 'failed' | 'rejected';

export const HUD_TOOL_STATUS_KEYS: Record<ToolDisplayStatus, MessageKey> = {
  running: 'hud.tool.running',
  success: 'hud.tool.success',
  failed: 'hud.tool.failed',
  rejected: 'hud.tool.rejected',
};

export function hudToolStatusLabel(status: ToolDisplayStatus): string {
  return tNow(HUD_TOOL_STATUS_KEYS[status]);
}

/** Host success + MCP isError → kart/HUD başarısız. */
export function toolDisplayStatus(
  toolName: string,
  status: ToolDisplayStatus,
  result: Record<string, unknown> | undefined,
): ToolDisplayStatus {
  return status === 'success' && mcpResultIsError(toolName, result) ? 'failed' : status;
}

/** Geçmiş meta `rejected` yazmasa da red metnini kart/HUD’da reddedildi say. */
export function summarizedToolStatus(
  toolName: string,
  call: {
    status?: ToolDisplayStatus;
    success?: boolean;
    rejected?: boolean;
    error?: string | null;
    result?: Record<string, unknown>;
  },
): ToolDisplayStatus {
  if (call.rejected || toolResultIsRejected(call.error)) return 'rejected';
  if (call.status) return toolDisplayStatus(toolName, call.status, call.result);
  return toolDisplayStatus(toolName, call.success ? 'success' : 'failed', call.result);
}

export function hudToolLineText(
  toolName: string,
  displayName: string,
  args: Record<string, unknown> | undefined,
  status: ToolDisplayStatus,
  result?: Record<string, unknown>,
): string {
  return `${hudToolLabel(toolName, displayName, args, result)} · ${hudToolStatusLabel(status)}`;
}

type ToolCallPlain = {
  tool_name: string;
  display_name?: string;
  arguments?: Record<string, unknown>;
  success?: boolean;
  rejected?: boolean;
  error?: string | null;
  result?: Record<string, unknown>;
};

export function hudMessagePlainText(content: string, toolCalls?: ToolCallPlain[]): string {
  const tools = (toolCalls ?? []).flatMap((call) => {
    const line = hudToolLineText(
      call.tool_name,
      call.display_name ?? call.tool_name,
      call.arguments,
      summarizedToolStatus(call.tool_name, call),
      call.result,
    );
    const body = mcpResultText(call.tool_name, call.result);
    return body ? [line, body] : [line];
  });
  return [...tools, content.trim()].filter(Boolean).join('\n');
}

/** Alıntı: cevap metni; yoksa MCP sonuç gövdesi (etiket/SUCCESS değil). */
export function quoteMessageText(content: string, toolCalls?: ToolCallPlain[]): string {
  const cleaned = content.trim();
  if (cleaned) return cleaned;
  return (toolCalls ?? [])
    .map((call) => mcpResultText(call.tool_name, call.result))
    .filter(Boolean)
    .join('\n\n');
}

const RESULT_ENVELOPE_KEYS = new Set(['content', 'isError', '_meta']);

/** Kart JSON yedek — protokol zarfını dökme. */
export function displayResultFallback(result: Record<string, unknown> | undefined): string {
  if (!result) return '';
  const cleaned: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(result)) {
    if (RESULT_ENVELOPE_KEYS.has(key)) continue;
    cleaned[key] = value;
  }
  if (Object.keys(cleaned).length === 0) return '';
  return JSON.stringify(cleaned, null, 2).slice(0, 4000);
}

function mcpContentText(content: unknown): string {
  if (typeof content === 'string') return prettyDisplayText(content);
  if (!Array.isArray(content)) return '';
  const texts: string[] = [];
  let media = 0;
  for (const item of content) {
    if (typeof item === 'string') {
      const text = prettyDisplayText(item);
      if (text) texts.push(text);
      continue;
    }
    if (!item || typeof item !== 'object') continue;
    const row = item as { type?: unknown; text?: unknown };
    const type = row.type == null ? 'text' : String(row.type);
    if (type === 'text') {
      const text = prettyDisplayText(String(row.text ?? ''));
      if (text) texts.push(text);
      continue;
    }
    if (type === 'image' || type === 'audio' || type === 'resource' || type === 'resource_link') {
      media += 1;
    }
  }
  if (texts.length) return texts.join('\n\n');
  if (media === 1) return tNow('mcp.mediaOne');
  if (media > 1) return tNow('mcp.mediaMany', { n: media });
  return '';
}

function mcpListDescriptionLines(result: Record<string, unknown>): string[] {
  if (!Array.isArray(result.descriptions)) return [];
  return result.descriptions.flatMap((item) => {
    if (!item || typeof item !== 'object') return [];
    const row = item as { name?: unknown; description?: unknown };
    const name = String(row.name ?? '').trim();
    const description = String(row.description ?? '').trim();
    if (name && description) return [`${name} — ${description}`];
    return name ? [name] : [];
  });
}

/** MCP text/content veya list özeti — ham JSON yerine. */
export function mcpResultText(
  toolName: string,
  result: Record<string, unknown> | undefined,
): string {
  if (!result) return '';
  if (toolName === 'mcp_list_tools') {
    const allowed = Array.isArray(result.allowed) ? result.allowed.map(String) : [];
    const advertised = Array.isArray(result.advertised) ? result.advertised.map(String) : [];
    const lines: string[] = [];
    if (result.server) lines.push(`${tNow('mcp.server')}: ${result.server}`);
    const descriptions = mcpListDescriptionLines(result);
    if (descriptions.length) lines.push(...descriptions);
    else if (allowed.length) lines.push(tNow('mcp.callable', { list: allowed.join(', ') }));
    else lines.push(tNow('mcp.callableNone'));
    if (advertised.length && advertised.join(',') !== allowed.join(',')) {
      lines.push(tNow('mcp.advertised', { list: advertised.join(', ') }));
    }
    return lines.join('\n');
  }
  if (toolName !== 'mcp_call') return '';
  const inner = toolCardResult(toolName, result) ?? result;
  const fromContent = mcpContentText(inner.content);
  if (fromContent) return fromContent;
  if (typeof inner.text === 'string' && inner.text.trim()) {
    return prettyDisplayText(inner.text);
  }
  if (inner.structuredContent != null) {
    return typeof inner.structuredContent === 'string'
      ? prettyDisplayText(inner.structuredContent)
      : JSON.stringify(inner.structuredContent, null, 2).slice(0, 4000);
  }
  return inner.isError === true ? tNow('mcp.toolError') : '';
}

function pushArgRows(rows: [string, unknown][], key: string, value: unknown): void {
  const nested = asArgRecord(value);
  if (nested && Object.keys(nested).length > 0) {
    for (const [innerKey, innerValue] of Object.entries(nested)) {
      rows.push([`${key}.${innerKey}`, innerValue]);
    }
    return;
  }
  rows.push([key, value]);
}

/** mcp_call gömülü arguments nesnesini düz satırlara aç. */
export function flattenToolArgs(
  toolName: string,
  args: Record<string, unknown> | undefined,
  result?: Record<string, unknown>,
): [string, unknown][] {
  const raw = args ?? {};
  if (toolName === 'mcp_list_tools') {
    const server = mcpServerId(raw, result);
    return server ? [[tNow('mcp.server'), server]] : [];
  }
  if (toolName !== 'mcp_call') return Object.entries(raw);
  const rows: [string, unknown][] = [];
  const server = mcpServerId(raw, result);
  const tool = mcpToolId(raw, result);
  if (server) rows.push([tNow('mcp.server'), server]);
  if (tool) rows.push([tNow('mcp.arg.tool'), tool]);
  const toolArgs = asArgRecord(raw.arguments);
  if (toolArgs) {
    for (const [key, value] of Object.entries(toolArgs)) {
      pushArgRows(rows, key, value);
    }
  } else if (raw.arguments != null) {
    rows.push([tNow('mcp.arg.args'), raw.arguments]);
  }
  return rows;
}

export function confirmArgumentEntries(pending: WSToolConfirmRequest): [string, unknown][] {
  return flattenToolArgs(pending.tool_name, pending.arguments);
}

/** Onay beklerken boş akan balon gösterme. */
export function shouldShowStreamingBubble(content: string, thinking?: string): boolean {
  return Boolean(content.trim() || thinking?.trim());
}

/** İkinci onay birincinin üstüne binmesin — eskisini reddet. */
export function pendingConfirmToReplace(
  current: WSToolConfirmRequest | null | undefined,
  incoming: WSToolConfirmRequest,
): WSToolConfirmRequest | null {
  if (!current) return null;
  if (current.request_id === incoming.request_id) return null;
  return current;
}

export function buildToolConfirmResponse(
  pending: WSToolConfirmRequest,
  approved: boolean,
  remember = false,
): WSToolConfirmResponse {
  return {
    type: 'tool_confirm_response',
    request_id: pending.request_id,
    approved,
    remember: approved && remember && canRememberConfirm(pending),
    fingerprint: pending.fingerprint || undefined,
    confirmation_ticket: pending.confirmation_ticket || undefined,
  };
}
