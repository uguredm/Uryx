/**
 * MCP spawn öncesi allowlist — komut, argüman, araç adı, JSON-RPC tampon.
 * Store ve istemci aynı kuralları kullanır; docker/cmd yok.
 */

import path from 'node:path';

import { mcpCommandPathAllowed, type AppSettings, type McpServerConfig } from '@shared/settings';
import { hostText } from '../host-i18n';

export const MCP_COMMAND_ALLOWLIST = new Set([
  'npx',
  'npx.cmd',
  'npx.bat',
  'npm',
  'npm.cmd',
  'npm.bat',
  'pnpm',
  'pnpm.exe',
  'pnpm.cmd',
  'pnpm.bat',
  'pnpx',
  'pnpx.exe',
  'pnpx.cmd',
  'pnpx.bat',
  'yarn',
  'yarn.exe',
  'yarn.cmd',
  'yarn.bat',
  'node',
  'node.exe',
  'node.cmd',
  'node.bat',
  'bun',
  'bun.exe',
  'bun.cmd',
  'bun.bat',
  'bunx',
  'bunx.exe',
  'bunx.cmd',
  'bunx.bat',
  'uvx',
  'uvx.exe',
  'uvx.cmd',
  'uvx.bat',
  'uv',
  'uv.exe',
  'uv.cmd',
  'uv.bat',
  'python',
  'python.exe',
  'python.cmd',
  'python.bat',
  'pythonw',
  'pythonw.exe',
  'python3',
  'python3.exe',
  'py',
  'py.exe',
  'py.cmd',
  'py.bat',
]);

export const MCP_ID_PATTERN = /^[a-z0-9][a-z0-9_-]{0,39}$/;
export const MCP_TOOL_PATTERN = /^(?!.*\.\.)[A-Za-z0-9._-]{1,64}(?:\/[A-Za-z0-9._-]{1,64})?$/;
export const MCP_DANGEROUS_ARG = /[\0\t\v\f\r\n;&|`$<>%!"']/;
export const MCP_STDOUT_BUFFER_CAP = 1_048_576;
export const MCP_STDERR_CAP = 4_000;
export const MCP_TOOL_ARGS_MAX_BYTES = 32_768;

/** npx -c / node -e / python -c / node --run / --env-file — serbest kabuk, eval veya stdin. */
const FORBIDDEN_FLAG =
  /^(?:-c|--call|--eval|-e|-p|--print|--command|--node-options|--inspect|--inspect-brk|--inspect-port|-r|--require|--import|--loader|--experimental-loader|--preload|--run|--env-file|--script-shell|--userconfig|--globalconfig|--init-module)$/i;
const FORBIDDEN_FLAG_PREFIX =
  /^--(?:node-options|inspect|inspect-brk|inspect-port|eval|print|call|command|require|import|loader|experimental-loader|preload|run|env-file|script-shell|userconfig|globalconfig|init-module)=/i;

export type McpAdvertisement = { advertised: string[]; allowed: string[] };

const NPX_PACKAGE_STEMS = new Set(['npx', 'bunx', 'uvx', 'bun', 'uv', 'pnpm', 'pnpx']);
const NPM_SCRIPT_STEMS = new Set(['npm', 'yarn', 'pnpm']);
const INTERPRETER_STEMS = new Set(['node', 'python', 'pythonw', 'python3', 'py', 'bun']);
const FORBIDDEN_NPM_SCRIPT = /^(?:run|start|test|stop|restart|publish)$/i;

export function mcpCommandStem(command: string): string {
  return path.basename(command.trim()).toLocaleLowerCase('en-US').replace(/\.(cmd|bat|exe)$/i, '');
}

export function mcpCommandAllowed(command: string): boolean {
  const trimmed = command.trim();
  if (!mcpCommandPathAllowed(trimmed)) return false;
  const base = path.basename(trimmed).toLocaleLowerCase('en-US');
  return MCP_COMMAND_ALLOWLIST.has(base);
}

export function isForbiddenMcpArg(arg: string, command = ''): boolean {
  const trimmed = arg.trim();
  if (!trimmed || trimmed === '-' || MCP_DANGEROUS_ARG.test(trimmed)) return true;
  if (/(^|[\\/])\.\.([\\/]|$)/.test(trimmed)) return true;
  if (trimmed === '-p' && NPX_PACKAGE_STEMS.has(mcpCommandStem(command))) return false;
  if (NPM_SCRIPT_STEMS.has(mcpCommandStem(command)) && FORBIDDEN_NPM_SCRIPT.test(trimmed)) return true;
  if (
    INTERPRETER_STEMS.has(mcpCommandStem(command)) &&
    (trimmed === '-i' || /^--interactive$/i.test(trimmed))
  ) {
    return true;
  }
  if (FORBIDDEN_FLAG.test(trimmed) || FORBIDDEN_FLAG_PREFIX.test(trimmed)) return true;
  return false;
}

/** `-c calc` gibi bayrak+değer çiftini düşürür. */
export function filterSafeMcpArgs(args: readonly string[], command = ''): string[] {
  const out: string[] = [];
  for (let i = 0; i < args.length; i += 1) {
    const arg = args[i].trim();
    if (isForbiddenMcpArg(arg, command)) {
      if (FORBIDDEN_FLAG.test(arg) && !(arg === '-p' && NPX_PACKAGE_STEMS.has(mcpCommandStem(command)))) {
        i += 1;
      } else if (NPM_SCRIPT_STEMS.has(mcpCommandStem(command)) && /^run$/i.test(arg)) {
        i += 1;
      }
      continue;
    }
    out.push(arg);
  }
  return out;
}

export function assertSafeMcpArgs(args: readonly string[], command = ''): void {
  if (args.some((arg) => isForbiddenMcpArg(arg, command))) {
    throw new Error(
      hostText(
        'MCP argümanlarında kabuk veya yorumlayıcı bayrağı yok.',
        'MCP arguments cannot include shell or interpreter flags.',
      ),
    );
  }
}

export function sanitizeMcpServerId(value: string): string {
  const serverId = value.trim().toLocaleLowerCase('en-US');
  if (!MCP_ID_PATTERN.test(serverId)) {
    throw new Error(hostText('MCP sunucu kimliği geçersiz.', 'MCP server id is invalid.'));
  }
  return serverId;
}

export function sanitizeMcpToolName(value: string): string {
  const name = value.trim();
  if (!MCP_TOOL_PATTERN.test(name)) {
    throw new Error(hostText('MCP araç adı geçersiz.', 'MCP tool name is invalid.'));
  }
  return name;
}

export function sanitizeMcpToolArgs(value: unknown): Record<string, unknown> {
  if (typeof value === 'string') {
    const trimmed = value.trim();
    if (!trimmed.startsWith('{') || !trimmed.endsWith('}')) return {};
    try {
      const parsed: unknown = JSON.parse(trimmed);
      return sanitizeMcpToolArgs(parsed);
    } catch {
      return {};
    }
  }
  if (!value || typeof value !== 'object' || Array.isArray(value)) return {};
  let json: string;
  try {
    json = JSON.stringify(value);
  } catch {
    throw new Error(hostText('MCP araç argümanları geçersiz.', 'MCP tool arguments are invalid.'));
  }
  if (json.length > MCP_TOOL_ARGS_MAX_BYTES) {
    throw new Error(hostText('MCP araç argümanları çok büyük.', 'MCP tool arguments are too large.'));
  }
  return JSON.parse(json) as Record<string, unknown>;
}

export function prepareMcpServer(
  settings: Pick<AppSettings, 'mcpEnabled' | 'mcpServers'>,
  args: Record<string, unknown>,
): McpServerConfig {
  if (!settings.mcpEnabled) {
    throw new Error(
      hostText('MCP kapalı. Ayarlardan allowlist ile açın.', 'MCP is off. Enable it from Settings with an allowlist.'),
    );
  }
  const serverId = sanitizeMcpServerId(String(args.server ?? ''));
  const server = settings.mcpServers.find((item) => item.id === serverId);
  if (!server) {
    throw new Error(
      hostText(
        `'${serverId}' adlı MCP sunucusu ayarlarda yok.`,
        `'${serverId}' MCP server is not in Settings.`,
      ),
    );
  }
  const command = server.command.trim();
  if (!mcpCommandAllowed(command)) {
    throw new Error(
      hostText(
        `'${path.basename(command)}' MCP komut allowlist'inde değil.`,
        `'${path.basename(command)}' is not on the MCP command allowlist.`,
      ),
    );
  }
  assertSafeMcpArgs(server.args, command);
  const trimmedArgs = server.args.map((arg) => arg.trim()).filter((arg) => arg.length > 0);
  return { ...server, command, args: trimmedArgs };
}

export function prepareMcpCall(
  settings: Pick<AppSettings, 'mcpEnabled' | 'mcpServers'>,
  args: Record<string, unknown>,
  advertised?: McpAdvertisement,
): { server: McpServerConfig; tool: string; toolArgs: Record<string, unknown> } {
  const server = prepareMcpServer(settings, args);
  const tool = sanitizeMcpToolName(String(args.tool ?? ''));
  if (server.allowedTools.length === 0) {
    throw new Error(
      hostText('Bu sunucunun izinli araç listesi boş.', 'This server has an empty allowed-tools list.'),
    );
  }
  if (!server.allowedTools.includes(tool)) {
    throw new Error(
      hostText(
        `'${tool}' bu sunucu için izin listesinde değil.`,
        `'${tool}' is not on this server's allowlist.`,
      ),
    );
  }
  if (advertised && !advertised.allowed.includes(tool)) {
    throw new Error(
      hostText(
        `'${tool}' sunucunun ilan ettiği allowlist kesişiminde yok.`,
        `'${tool}' is not in the advertised allowlist intersection.`,
      ),
    );
  }
  return { server, tool, toolArgs: sanitizeMcpToolArgs(args.arguments) };
}

function takeUtf8Bytes(text: string, byteCount: number): { part: string; rest: string } | null {
  const raw = Buffer.from(text, 'utf8');
  if (raw.length < byteCount) return null;
  return {
    part: raw.subarray(0, byteCount).toString('utf8'),
    rest: raw.subarray(byteCount).toString('utf8'),
  };
}

function looksLikeContentLengthPrefix(text: string): boolean {
  const head = text.trimStart().slice(0, 20).toLocaleLowerCase('en-US');
  if (!head) return false;
  if (head.startsWith('content-length')) return true;
  return 'content-length'.startsWith(head);
}

/** Stdio yazımı: çerçeve + satır okuyucu için sondaki \\n gövdeye dahil değil. */
export function encodeMcpStdioFrame(message: object): string {
  const body = JSON.stringify(message);
  return `Content-Length: ${Buffer.byteLength(body, 'utf8')}\r\n\r\n${body}\n`;
}

export function mcpRecordGet(result: object, keys: readonly string[]): unknown {
  const row = result as Record<string, unknown>;
  for (const key of keys) {
    if (Object.prototype.hasOwnProperty.call(row, key) && row[key] !== undefined) return row[key];
  }
  return undefined;
}

export function mcpNormalizeListedTool(raw: unknown): { name?: unknown; description?: unknown } | null {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null;
  const name = mcpRecordGet(raw, ['name', 'Name']);
  const description = mcpRecordGet(raw, ['description', 'Description']);
  if (name === undefined && description === undefined) return null;
  const tool: { name?: unknown; description?: unknown } = {};
  if (typeof name === 'string') {
    const trimmed = name.trim();
    if (trimmed) tool.name = trimmed;
  } else if (name !== undefined) {
    tool.name = name;
  }
  if (typeof description === 'string') {
    const trimmed = description.trim();
    if (trimmed) tool.description = trimmed;
  } else if (description !== undefined) {
    tool.description = description;
  }
  if (tool.name === undefined && tool.description === undefined) return null;
  return tool;
}

function mcpNormalizeListedTools(list: unknown[]): Array<{ name?: unknown; description?: unknown }> {
  const out: Array<{ name?: unknown; description?: unknown }> = [];
  for (const item of list) {
    const tool = mcpNormalizeListedTool(item);
    if (tool) out.push(tool);
  }
  return out;
}

export function mcpToolsFromListResult(result: unknown): Array<{ name?: unknown; description?: unknown }> {
  if (Array.isArray(result)) return mcpNormalizeListedTools(result);
  if (!result || typeof result !== 'object') return [];
  const tools = mcpRecordGet(result, ['tools', 'Tools']);
  if (Array.isArray(tools)) return mcpNormalizeListedTools(tools);
  const single = mcpNormalizeListedTool(tools);
  return single ? [single] : [];
}

export function mcpUniqueToolNames(names: string[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const name of names) {
    if (seen.has(name)) continue;
    seen.add(name);
    out.push(name);
  }
  return out;
}

export function mcpListNextCursor(result: unknown): string | undefined {
  if (!result || typeof result !== 'object' || Array.isArray(result)) return undefined;
  let cursor = mcpRecordGet(result, ['nextCursor', 'NextCursor', 'next_cursor', 'cursor']);
  if (typeof cursor === 'number' && Number.isFinite(cursor) && cursor >= 0) {
    cursor = String(cursor);
  }
  if (typeof cursor !== 'string') return undefined;
  const trimmed = cursor.trim();
  return trimmed && trimmed.length <= 500 ? trimmed : undefined;
}

/** Aynı nextCursor tekrarı sayfa döngüsüne girmesin. */
export function mcpListAdvanceCursor(result: unknown, previous?: string): string | undefined {
  const next = mcpListNextCursor(result);
  if (!next || next === previous) return undefined;
  return next;
}

/** Sunucu sayı cursor verdiyse string gönderme — schema integer reddetmesin. */
export function mcpListCursorParam(cursor: string): string | number {
  if (cursor === '0' || /^[1-9]\d{0,8}$/.test(cursor)) {
    const value = Number(cursor);
    if (Number.isSafeInteger(value)) return value;
  }
  return cursor;
}

export function mcpLineBreakIndex(text: string): number {
  const lf = text.indexOf('\n');
  const cr = text.indexOf('\r');
  if (lf < 0) return cr;
  if (cr < 0) return lf;
  return Math.min(lf, cr);
}

export function mcpConsumeLine(text: string, at: number): { line: string; rest: string } {
  const width = text.startsWith('\r\n', at) ? 2 : 1;
  return { line: text.slice(0, at).trim(), rest: text.slice(at + width) };
}

/** SDK stdio: ``Content-Length`` çerçevesi veya satır JSON. */
export function appendMcpStdout(
  buffer: string,
  chunk: string,
): { buffer: string; lines: string[] } {
  if (buffer.length + chunk.length > MCP_STDOUT_BUFFER_CAP) {
    throw new Error(hostText('MCP çıktı tavanı aşıldı.', 'MCP output limit exceeded.'));
  }
  let next = buffer + chunk;
  const lines: string[] = [];

  while (next.length > 0) {
    const trimmedStart = next.trimStart();
    if (looksLikeContentLengthPrefix(trimmedStart)) {
      const headerEnd = /\r?\n\r?\n/.exec(trimmedStart);
      if (!headerEnd) break;
      const headers = trimmedStart.slice(0, headerEnd.index);
      const lengthMatch = /^content-length\s*:\s*(\d+)\s*$/im.exec(headers);
      if (!lengthMatch) {
        throw new Error(hostText('MCP çerçevesi geçersiz.', 'MCP frame is invalid.'));
      }
      const size = Number(lengthMatch[1]);
      if (!Number.isInteger(size) || size < 0 || size > MCP_STDOUT_BUFFER_CAP) {
        throw new Error(hostText('MCP çıktı tavanı aşıldı.', 'MCP output limit exceeded.'));
      }
      const afterHeaders = trimmedStart.slice(headerEnd.index + headerEnd[0].length);
      const taken = takeUtf8Bytes(afterHeaders, size);
      if (!taken) break;
      const body = taken.part.trim();
      if (body) lines.push(body);
      next = taken.rest;
      continue;
    }

    const breakAt = mcpLineBreakIndex(next);
    if (breakAt < 0) break;
    const consumed = mcpConsumeLine(next, breakAt);
    next = consumed.rest;
    if (consumed.line) lines.push(consumed.line);
  }

  return { buffer: next, lines };
}

/** npx hata satırı sonda durur — başı değil kuyruğu tut. ANSI tavanı yemesin. */
export function stripMcpAnsi(text: string): string {
  return text.replace(/\x1B\[[0-9;]*[A-Za-z]/g, '').replace(/\x1B\][^\x07]*(?:\x07|\x1B\\)/g, '');
}

export function appendMcpStderr(buffer: string, chunk: string, cap = MCP_STDERR_CAP): string {
  if (!chunk) return buffer.length > cap ? buffer.slice(-cap) : buffer;
  const next = buffer + stripMcpAnsi(chunk);
  return next.length <= cap ? next : next.slice(-cap);
}

/** Sunucu→istemci istekleri (ping/roots) cevapsız kalmasın. */
export function mcpNormalizeRpcMethod(method: unknown): string {
  return String(method ?? '')
    .trim()
    .toLocaleLowerCase('en-US');
}

export function mcpServerRequestReply(message: {
  id?: unknown;
  method?: unknown;
  result?: unknown;
  error?: unknown;
}): object | null {
  if (message.method == null || message.method === '') return null;
  if (message.id === undefined || message.id === null) return null;
  if ('result' in message || 'error' in message) return null;
  const method = mcpNormalizeRpcMethod(message.method);
  if (!method) return null;
  if (method.startsWith('notifications/')) return null;
  if (method === 'ping') return { jsonrpc: '2.0', id: message.id, result: {} };
  if (method === 'roots/list') return { jsonrpc: '2.0', id: message.id, result: { roots: [] } };
  if (method === 'resources/list') return { jsonrpc: '2.0', id: message.id, result: { resources: [] } };
  if (method === 'resources/templates/list') {
    return { jsonrpc: '2.0', id: message.id, result: { resourceTemplates: [] } };
  }
  if (method === 'prompts/list') return { jsonrpc: '2.0', id: message.id, result: { prompts: [] } };
  if (method === 'logging/setlevel') return { jsonrpc: '2.0', id: message.id, result: {} };
  if (method === 'elicitation/create') {
    return { jsonrpc: '2.0', id: message.id, result: { action: 'cancel' } };
  }
  return {
    jsonrpc: '2.0',
    id: message.id,
    error: { code: -32601, message: 'Method not found' },
  };
}

export function mcpRpcErrorMessage(error: unknown, fallback: string): string {
  if (typeof error === 'string') {
    const text = error.trim();
    return text || fallback;
  }
  if (!error || typeof error !== 'object') return fallback;
  const row = error as { message?: unknown; code?: unknown; data?: unknown };
  let message = '';
  if (typeof row.message === 'string') message = row.message.trim();
  else if (typeof row.message === 'number' && Number.isFinite(row.message)) message = String(row.message);
  else if (row.message && typeof row.message === 'object') {
    message = mcpRpcErrorDataText(row.message);
  }
  const data = mcpRpcErrorDataText(row.data);
  if (message && message !== '[object Object]') return message;
  if (data) return data.slice(0, 200);
  if (row.code != null && String(row.code).trim()) return `${fallback} (${row.code})`;
  return fallback;
}

export function mcpRpcErrorDataText(data: unknown, depth = 0): string {
  if (depth > 3) return '';
  if (typeof data === 'string') return data.trim();
  if (typeof data === 'number' && Number.isFinite(data)) return String(data);
  if (Array.isArray(data)) {
    for (const item of data.slice(0, 4)) {
      const text = mcpRpcErrorDataText(item, depth + 1);
      if (text) return text.slice(0, 200);
    }
    return '';
  }
  if (!data || typeof data !== 'object') return '';
  const row = data as {
    message?: unknown;
    reason?: unknown;
    error?: unknown;
    msg?: unknown;
    detail?: unknown;
    errors?: unknown;
    issues?: unknown;
  };
  for (const key of ['message', 'reason', 'error', 'msg', 'detail'] as const) {
    const value = row[key];
    if (typeof value === 'string' && value.trim()) return value.trim();
  }
  if (row.errors !== undefined) return mcpRpcErrorDataText(row.errors, depth + 1);
  if (row.issues !== undefined) return mcpRpcErrorDataText(row.issues, depth + 1);
  return '';
}

/** Satırda bitişik `{}{}` — JSON.parse tek nesne sanıp initialize'ı düşürmesin. */
export function mcpParseConcatenatedJson(text: string): object[] {
  const out: object[] = [];
  let start = 0;
  while (start < text.length) {
    while (start < text.length && /\s/.test(text[start] ?? '')) start += 1;
    if (start >= text.length) break;
    const open = text[start];
    if (open !== '{' && open !== '[') break;
    let depth = 0;
    let inStr = false;
    let escape = false;
    let end = -1;
    for (let i = start; i < text.length; i += 1) {
      const ch = text[i];
      if (inStr) {
        if (escape) escape = false;
        else if (ch === '\\') escape = true;
        else if (ch === '"') inStr = false;
        continue;
      }
      if (ch === '"') {
        inStr = true;
        continue;
      }
      if (ch === '{' || ch === '[') depth += 1;
      else if (ch === '}' || ch === ']') {
        depth -= 1;
        if (depth === 0) {
          end = i;
          break;
        }
      }
    }
    if (end < 0) break;
    try {
      const parsed: unknown = JSON.parse(text.slice(start, end + 1));
      if (Array.isArray(parsed)) {
        out.push(
          ...parsed.filter(
            (item): item is object => Boolean(item) && typeof item === 'object' && !Array.isArray(item),
          ),
        );
      } else if (parsed && typeof parsed === 'object') {
        out.push(parsed);
      }
    } catch {
      break;
    }
    start = end + 1;
  }
  return out;
}

/** Tek mesaj, JSON-RPC batch veya bitişik nesneler. */
export function mcpParseRpcMessages(line: string): object[] {
  const trimmed = line.trim();
  if (!trimmed) return [];
  try {
    const parsed: unknown = JSON.parse(trimmed);
    if (Array.isArray(parsed)) {
      return parsed.filter(
        (item): item is object => Boolean(item) && typeof item === 'object' && !Array.isArray(item),
      );
    }
    if (parsed && typeof parsed === 'object') return [parsed];
    return [];
  } catch {
    return mcpParseConcatenatedJson(trimmed);
  }
}

/** Sunucu id'yi string yazarsa bekleyen RPC asılı kalmasın. */
export function resolveMcpRpcId(raw: unknown): number | undefined {
  if (typeof raw === 'number' && Number.isInteger(raw) && raw > 0 && raw < 1_000_000) {
    return raw;
  }
  const text = typeof raw === 'string' ? raw.trim() : '';
  if (text && /^[1-9]\d{0,5}(?:\.0+)?$/.test(text)) {
    return Number.parseInt(text, 10);
  }
  return undefined;
}
