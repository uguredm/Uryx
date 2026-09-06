/** Allowlist'li MCP istemcisi (stdio JSON-RPC). */

import { spawn, type ChildProcess } from 'node:child_process';

import { MCP_INIT_TIMEOUT_MS, MCP_RPC_TIMEOUT_MS } from '@shared/settings';
import { hostText } from '../host-i18n';
import { getSettings } from '../store';
import { mcpChildEnv } from './mcp-env';
import { formatMcpFailure, formatMcpSpawnError } from './mcp-error';
import {
  MCP_TOOL_PATTERN,
  appendMcpStderr,
  appendMcpStdout,
  encodeMcpStdioFrame,
  mcpListAdvanceCursor,
  mcpListCursorParam,
  mcpParseRpcMessages,
  mcpRpcErrorMessage,
  mcpServerRequestReply,
  mcpToolsFromListResult,
  mcpUniqueToolNames,
  prepareMcpCall,
  prepareMcpServer,
  resolveMcpRpcId,
} from './mcp-guard';
import {
  mcpChildStdioReady,
  mcpSpawnCwd,
  mcpWindowsVerbatimArguments,
  resolveMcpSpawn,
  writeMcpStdin,
} from './mcp-spawn';
import { currentHostAbortSignal, killProcessTree } from './process';

const mcpAdvertised = new Map<string, { advertised: string[]; allowed: string[] }>();
const liveMcpChildren = new Set<ChildProcess>();
const liveMcpFail = new Map<ChildProcess, (error: Error) => void>();
let mcpSlots = 0;
let mcpStopped = false;
/** Aynı anda bir stdio MCP süreci — ikinci npx bekler veya reddedilir. */
export const MAX_MCP_CHILDREN = 1;

export function mcpInFlightCount(): number {
  return liveMcpChildren.size;
}

export function acquireMcpSlot(): void {
  if (mcpStopped) {
    throw new Error(hostText('MCP durduruldu.', 'MCP was stopped.'));
  }
  if (mcpSlots >= MAX_MCP_CHILDREN) {
    throw new Error(
      hostText(
        'Aynı anda bir MCP süreci çalışabilir. Lütfen tekrar deneyin.',
        'Only one MCP process can run at a time. Please try again.',
      ),
    );
  }
  mcpSlots += 1;
}

export function releaseMcpSlot(): void {
  mcpSlots = Math.max(0, mcpSlots - 1);
}

export function watchMcpChild(child: ChildProcess, fail: (error: Error) => void): void {
  liveMcpChildren.add(child);
  liveMcpFail.set(child, fail);
}

export function abortInFlightMcp(reason?: string): number {
  const text = reason ?? hostText('MCP kapatıldı.', 'MCP was closed.');
  const error = new Error(text);
  const children = [...liveMcpChildren];
  for (const child of children) {
    liveMcpFail.get(child)?.(error);
    killProcessTree(child);
    liveMcpChildren.delete(child);
    liveMcpFail.delete(child);
  }
  mcpSlots = 0;
  return children.length;
}

function assertMcpStillEnabled(): void {
  if (mcpStopped || !getSettings().mcpEnabled) {
    throw new Error(hostText('MCP kapatıldı.', 'MCP was closed.'));
  }
}

export function peekMcpAdvertisement(
  serverId: string,
): { advertised: string[]; allowed: string[] } | undefined {
  return mcpAdvertised.get(serverId);
}

function mcpServerFingerprint(
  servers: Array<{
    id: string;
    command?: string;
    args?: unknown;
    allowedTools?: unknown;
    env?: unknown;
  }>,
): string {
  return servers
    .map((server) =>
      [
        server.id,
        server.command ?? '',
        JSON.stringify(server.args ?? []),
        JSON.stringify(server.allowedTools ?? []),
        JSON.stringify(server.env ?? {}),
      ].join('\x1f'),
    )
    .join('\0');
}

export function mcpSettingsRequireAbort(
  prev: {
    mcpEnabled: boolean;
    mcpServers: Array<{
      id: string;
      command?: string;
      args?: unknown;
      allowedTools?: unknown;
      env?: unknown;
    }>;
  },
  next: {
    mcpEnabled: boolean;
    mcpServers: Array<{
      id: string;
      command?: string;
      args?: unknown;
      allowedTools?: unknown;
      env?: unknown;
    }>;
  },
): boolean {
  if (!next.mcpEnabled) return prev.mcpEnabled || liveMcpChildren.size > 0;
  return mcpServerFingerprint(prev.mcpServers) !== mcpServerFingerprint(next.mcpServers);
}

/** Kapalı/açık veya sunucu parmak izi değişince backend snapshot yenilensin. */
export function mcpSettingsNeedCapabilityRefresh(
  prev: Parameters<typeof mcpSettingsRequireAbort>[0],
  next: Parameters<typeof mcpSettingsRequireAbort>[1],
): boolean {
  if (prev.mcpEnabled !== next.mcpEnabled) return true;
  return mcpServerFingerprint(prev.mcpServers) !== mcpServerFingerprint(next.mcpServers);
}

/** Ayar kaydı / sıfırlama — in-flight kes, ilan önbelleğini at. */
export function onMcpSettingsChanged(
  prev: Parameters<typeof mcpSettingsRequireAbort>[0],
  next: Parameters<typeof mcpSettingsRequireAbort>[1],
): number {
  mcpStopped = !next.mcpEnabled;
  if (!mcpSettingsRequireAbort(prev, next)) return 0;
  resetMcpAdvertisement();
  return abortInFlightMcp(
    next.mcpEnabled
      ? hostText('MCP sunucu listesi değişti.', 'The MCP server list changed.')
      : hostText('MCP kapatıldı.', 'MCP was closed.'),
  );
}

/** before-quit / will-quit — kuyruktaki spawn da durur. */
export function shutdownMcpRuntime(): number {
  mcpStopped = true;
  resetMcpAdvertisement();
  return abortInFlightMcp(hostText('Uygulama kapanıyor.', 'The application is closing.'));
}

export function isMcpRuntimeStopped(): boolean {
  return mcpStopped;
}

export function resumeMcpRuntime(): void {
  mcpStopped = false;
}

/** Jan: son ``tools/list`` kesişimi — ``host_capabilities.mcp``. */
export function mcpCapabilitySnapshot(): Record<string, unknown> {
  const settings = getSettings();
  return {
    enabled: Boolean(settings.mcpEnabled),
    servers: settings.mcpServers.map((server) => {
      const listed = mcpAdvertised.get(server.id);
      return {
        id: server.id,
        allowed: [...server.allowedTools],
        advertised: listed?.advertised ?? [],
        callable: listed?.allowed ?? [],
      };
    }),
  };
}

export function recordMcpAdvertisement(
  serverId: string,
  advertised: string[],
  allowed: string[],
): void {
  mcpAdvertised.set(serverId, { advertised: advertised.slice(0, 80), allowed: allowed.slice(0, 80) });
}

export function resetMcpAdvertisement(): void {
  mcpAdvertised.clear();
}

export { mcpCommandAllowed, sanitizeMcpToolName } from './mcp-guard';

/** Kullanıcının kaydettiği sunuculardan birine allowlist'li araç çağrısı yapar. */
export async function callMcpTool(args: Record<string, unknown>): Promise<Record<string, unknown>> {
  const settings = getSettings();
  const prepared = prepareMcpCall(settings, args, mcpAdvertised.get(String(args.server ?? '').trim().toLocaleLowerCase('en-US')));
  const result = await invokeMcp(prepared.server.command, prepared.server.args, {
    mode: 'call',
    tool: prepared.tool,
    toolArgs: prepared.toolArgs,
    extraEnv: prepared.server.env,
  });
  return { server: prepared.server.id, tool: prepared.tool, result };
}

/**
 * Jan MCP ``tools/list`` — initialize sonrası ilan edilen araçlar.
 * Model yalnızca allowlist kesişimini çağırabilir.
 */
export async function listMcpTools(args: Record<string, unknown>): Promise<Record<string, unknown>> {
  const settings = getSettings();
  const server = prepareMcpServer(settings, args);
  const listed = await invokeMcp(server.command, server.args, {
    mode: 'list',
    extraEnv: server.env,
  });
  const rawTools =
    listed && typeof listed === 'object' && Array.isArray((listed as { tools?: unknown }).tools)
      ? ((listed as { tools: Array<{ name?: unknown; description?: unknown }> }).tools)
      : [];
  const advertised = mcpUniqueToolNames(
    rawTools
      .map((item) => String(item.name ?? '').trim())
      .filter((name) => MCP_TOOL_PATTERN.test(name)),
  );
  const allowed = advertised.filter((name) => server.allowedTools.includes(name));
  recordMcpAdvertisement(server.id, advertised, allowed);
  return {
    server: server.id,
    advertised,
    allowed,
    descriptions: rawTools
      .filter((item) => allowed.includes(String(item.name ?? '')))
      .map((item) => ({
        name: String(item.name ?? ''),
        description: String(item.description ?? '').slice(0, 240),
      })),
  };
}

interface JsonRpcMessage {
  jsonrpc?: string;
  id?: number | string;
  method?: string;
  params?: unknown;
  result?: unknown;
  error?: { message?: string };
}

type McpInvoke =
  | {
      mode: 'call';
      tool: string;
      toolArgs: Record<string, unknown>;
      extraEnv?: Record<string, string>;
    }
  | { mode: 'list'; extraEnv?: Record<string, string> };

async function invokeMcp(command: string, args: string[], invoke: McpInvoke): Promise<unknown> {
  assertMcpStillEnabled();
  acquireMcpSlot();
  let child: ChildProcess | undefined;
  try {
    return await runMcpChild(command, args, invoke, (spawned) => {
      child = spawned;
    });
  } finally {
    if (child) {
      liveMcpChildren.delete(child);
      liveMcpFail.delete(child);
      killProcessTree(child);
    }
    releaseMcpSlot();
  }
}

async function runMcpChild(
  command: string,
  args: string[],
  invoke: McpInvoke,
  onSpawn: (child: ChildProcess) => void,
): Promise<unknown> {
  const resolved = resolveMcpSpawn(command, args);
  const child = spawn(resolved.command, resolved.args, {
    stdio: ['pipe', 'pipe', 'pipe'],
    windowsHide: true,
    windowsVerbatimArguments: mcpWindowsVerbatimArguments(resolved.command),
    cwd: mcpSpawnCwd(),
    env: mcpChildEnv(process.env, process.platform, invoke.extraEnv ?? {}),
  });
  onSpawn(child);
  if (!mcpChildStdioReady(child)) {
    throw new Error(hostText('MCP stdin/stdout yok.', 'MCP stdin/stdout is missing.'));
  }

  let buffer = '';
  let stderr = '';
  let dead: Error | null = null;
  const pending = new Map<number, { resolve: (value: JsonRpcMessage) => void; reject: (error: Error) => void }>();
  let nextId = 1;

  const failPending = (error: Error): void => {
    dead ??= error;
    for (const waiter of pending.values()) waiter.reject(error);
    pending.clear();
  };

  watchMcpChild(child, failPending);

  const send = (message: object): void => {
    if (!writeMcpStdin(child.stdin, encodeMcpStdioFrame(message))) {
      failPending(
        new Error(formatMcpFailure(hostText('MCP stdin kapandı.', 'MCP stdin closed.'), stderr)),
      );
    }
  };

  const request = (method: string, params: unknown): Promise<JsonRpcMessage> => {
    if (dead) return Promise.reject(dead);
    const id = nextId;
    nextId += 1;
    return new Promise((resolve, reject) => {
      pending.set(id, { resolve, reject });
      send({ jsonrpc: '2.0', id, method, params });
    });
  };

  child.stdout.setEncoding('utf8');
  child.stdin?.on('error', () => {
    failPending(
      new Error(formatMcpFailure(hostText('MCP stdin kapandı.', 'MCP stdin closed.'), stderr)),
    );
  });
  child.stdout.on('error', () => {
    failPending(
      new Error(formatMcpFailure(hostText('MCP stdout kapandı.', 'MCP stdout closed.'), stderr)),
    );
  });
  child.stdout.on('end', () => {
    if (pending.size === 0) return;
    failPending(
      new Error(formatMcpFailure(hostText('MCP stdout kapandı.', 'MCP stdout closed.'), stderr)),
    );
  });
  child.stdout.on('data', (chunk: string) => {
    try {
      const parsed = appendMcpStdout(buffer, chunk);
      buffer = parsed.buffer;
      for (const line of parsed.lines) {
        try {
          for (const message of mcpParseRpcMessages(line) as JsonRpcMessage[]) {
            const reply = mcpServerRequestReply(message);
            if (reply) {
              send(reply);
              continue;
            }
            const rpcId = resolveMcpRpcId(message.id);
            if (rpcId !== undefined) {
              pending.get(rpcId)?.resolve(message);
              pending.delete(rpcId);
            }
          }
        } catch {
        }
      }
    } catch (error) {
      failPending(
        error instanceof Error
          ? error
          : new Error(hostText('MCP çıktı tavanı aşıldı.', 'MCP output limit exceeded.')),
      );
      killProcessTree(child);
    }
  });

  child.stderr?.setEncoding('utf8');
  child.stderr?.on('error', () => {
  });
  child.stderr?.on('data', (chunk: string) => {
    stderr = appendMcpStderr(stderr, chunk);
  });

  child.on('error', (error) => {
    failPending(new Error(formatMcpSpawnError(error, command)));
  });

  child.on('exit', (code) => {
    if (pending.size === 0) return;
    failPending(
      new Error(
        formatMcpFailure(
          hostText(`MCP süreç çıktı (${code ?? '?'}).`, `MCP process exited (${code ?? '?'}).`),
          stderr,
        ),
      ),
    );
  });

  const failOnTimeout = (label: string): void => {
    killProcessTree(child);
    failPending(new Error(formatMcpFailure(label, stderr)));
  };

  let phaseTimer = setTimeout(
    () => failOnTimeout(hostText('MCP initialize zaman aşımı.', 'MCP initialize timed out.')),
    MCP_INIT_TIMEOUT_MS,
  );

  const signal = currentHostAbortSignal();
  const onAbort = (): void => {
    killProcessTree(child);
    failPending(new Error(hostText('Komut iptal edildi.', 'The command was cancelled.')));
  };
  if (signal?.aborted) {
    onAbort();
    throw new Error(hostText('Komut iptal edildi.', 'The command was cancelled.'));
  }
  signal?.addEventListener('abort', onAbort, { once: true });

  try {
    const init = await request('initialize', {
      protocolVersion: '2024-11-05',
      capabilities: {},
      clientInfo: { name: 'uryx', version: '1.0.0' },
    });
    if (init.error) {
      throw new Error(
        formatMcpFailure(
          mcpRpcErrorMessage(init.error, hostText('MCP initialize başarısız.', 'MCP initialize failed.')),
          stderr,
        ),
      );
    }
    assertMcpStillEnabled();
    send({ jsonrpc: '2.0', method: 'notifications/initialized', params: {} });
    const armRpcTimer = (): void => {
      clearTimeout(phaseTimer);
      phaseTimer = setTimeout(
        () => failOnTimeout(hostText('MCP RPC zaman aşımı.', 'MCP RPC timed out.')),
        MCP_RPC_TIMEOUT_MS,
      );
    };
    armRpcTimer();
    if (invoke.mode === 'list') {
      const tools: Array<{ name?: unknown; description?: unknown }> = [];
      let cursor: string | undefined;
      for (let page = 0; page < 4; page += 1) {
        armRpcTimer();
        const listed = await request('tools/list', cursor ? { cursor: mcpListCursorParam(cursor) } : {});
        if (listed.error) {
          throw new Error(
            formatMcpFailure(
              mcpRpcErrorMessage(listed.error, hostText('MCP tools/list başarısız.', 'MCP tools/list failed.')),
              stderr,
            ),
          );
        }
        tools.push(...mcpToolsFromListResult(listed.result));
        cursor = mcpListAdvanceCursor(listed.result, cursor);
        if (!cursor || tools.length >= 80) break;
      }
      return { tools: tools.slice(0, 80) };
    }
    const call = await request('tools/call', {
      name: invoke.tool,
      arguments: invoke.toolArgs,
    });
    if (call.error) {
      throw new Error(
        formatMcpFailure(
          mcpRpcErrorMessage(call.error, hostText('MCP tools/call başarısız.', 'MCP tools/call failed.')),
          stderr,
        ),
      );
    }
    return call.result ?? {};
  } finally {
    clearTimeout(phaseTimer);
    signal?.removeEventListener('abort', onAbort);
    liveMcpChildren.delete(child);
    liveMcpFail.delete(child);
    killProcessTree(child);
  }
}
