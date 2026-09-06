/**
 * Docker servis yönetimi.
 *
 * Kullanıcı backend servislerini uygulama içinden başlatıp durdurabilir.
 * `docker compose` komutu **kabuk kullanılmadan** çalıştırılır ve yalnızca
 * sabit alt komutlara izin verilir.
 */

import { app, net, shell } from 'electron';
import { createWriteStream, existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { Readable } from 'node:stream';
import { pipeline } from 'node:stream/promises';
import { readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';

import { launchDetached, run } from './host-tools/process';
import { redactUrlsInText } from './host-tools/safe-url';
import {
  buildDockerHints,
  classifyComposeProgressLine,
  classifyDockerContext,
  classifyDockerDesktopStatus,
  classifyDockerEngineOutput,
  classifyHostDockerAccess,
  composeUpWaitArgs,
  COMPOSE_API_SERVICE,
  COMPOSE_PROJECT_NAME,
  dockerDesktopCandidates,
  dockerDesktopLaunchKind,
  DOCKER_DESKTOP_INSTALLER_URL,
  formatComposeConfigFailure,
  sanitizeComposeService,
  sanitizeLogSource,
  summarizeComposeHealth,
  type DockerContextKind,
  type DockerEngineState,
  type HostDockerAccess,
} from './services-health';
import { hostLang, hostT } from './host-i18n';
import {
  applyLlmComposeEnv,
  bindProcessModelsDir,
  migrateRepoGgufs,
  presetFromSettings,
} from './models-dir';
import { getSettings } from './store';

/** Compose dosyasının bulunduğu kök klasör (önbellekli). */
let cachedRoot: string | null | undefined;
const COMPOSE_PROJECT_ARGS = ['compose', '--project-name', COMPOSE_PROJECT_NAME];

export interface ServicesProgress {
  phase: string;
  message: string;
}

let progressSink: ((payload: ServicesProgress) => void) | null = null;

/** Compose ilerleme olaylarını UI'ya taşımak için. */
export function setServicesProgressSink(
  sink: ((payload: ServicesProgress) => void) | null,
): void {
  progressSink = sink;
}

function emitProgress(phase: string, message: string): void {
  progressSink?.({ phase, message });
}

function createLinePump(onLine: (line: string) => void): (chunk: string) => void {
  let buffer = '';
  return (chunk: string) => {
    buffer += chunk;
    const parts = buffer.split(/\r?\n/);
    buffer = parts.pop() ?? '';
    for (const line of parts) onLine(line);
  };
}

function composeChunkSink(): (stream: 'stdout' | 'stderr', chunk: string) => void {
  const pump = createLinePump((line) => {
    const parsed = classifyComposeProgressLine(line, getSettings().language);
    if (parsed) emitProgress(parsed.phase, parsed.message);
  });
  return (_stream, chunk) => pump(chunk);
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * `docker-compose.yml` içeren proje kökünü arar.
 *
 * Sırasıyla: `URYX_REPO_ROOT` ortam değişkeni → uygulama yolu → çalışma
 * dizini üzerinden yukarı doğru tarama.
 */
export function findRepoRoot(): string | null {
  if (cachedRoot !== undefined) return cachedRoot;

  const candidates: string[] = [];
  if (process.env.URYX_REPO_ROOT) candidates.push(process.env.URYX_REPO_ROOT);
  if (process.env.JARVIS_REPO_ROOT) candidates.push(process.env.JARVIS_REPO_ROOT);
  if (app.isPackaged) candidates.push(path.join(process.resourcesPath, 'project'));

  const starts = [app.getAppPath(), process.cwd(), path.dirname(app.getPath('exe'))];
  for (const start of starts) {
    let current = start;
    for (let depth = 0; depth < 6; depth += 1) {
      candidates.push(current);
      const parent = path.dirname(current);
      if (parent === current) break;
      current = parent;
    }
  }

  for (const candidate of candidates) {
    if (candidate && existsSync(path.join(candidate, 'docker-compose.yml'))) {
      cachedRoot = candidate;
      migrateRepoGgufs(cachedRoot);
      bindProcessModelsDir();
      return cachedRoot;
    }
  }

  cachedRoot = null;
  return null;
}

export interface DockerServiceInfo {
  name: string;
  state: string;
  health: string | null;
  image: string;
}

export interface ServicesStatus {
  dockerAvailable: boolean;
  composeAvailable: boolean;
  gpuAvailable: boolean;
  gpuName: string | null;
  services: DockerServiceInfo[];
  error: string | null;
  repoRoot: string | null;
  apiReachable: boolean;
  apiLatencyMs: number | null;
  dockerDesktopInstalled: boolean;
  engineState: DockerEngineState;
  dockerCliAvailable: boolean;
  hostDockerAccess: HostDockerAccess;
  dockerContext: string;
  dockerContextKind: DockerContextKind;
  dockerContextRedirected: boolean;
  dockerHostSet: boolean;
  hints: string[];
}

export interface ServicesActionResult {
  ok: boolean;
  message: string;
  output?: string;
}

function dockerDesktopInstalled(): boolean {
  return dockerDesktopCandidates().some((candidate) => existsSync(candidate));
}

function apiBaseUrl(): string {
  try {
    return getSettings().backendUrl.replace(/\/+$/, '') || 'http://127.0.0.1:8080';
  } catch {
    return 'http://127.0.0.1:8080';
  }
}

/** Host'tan API `/health` yoklaması. Whisper/TTS iç ağda kalır, dışarı açılmaz. */
export async function probeApiHealth(
  backendUrl = apiBaseUrl(),
  timeoutMs = 2500,
): Promise<{ ok: boolean; ms: number | null }> {
  const healthUrl = `${backendUrl.replace(/\/+$/, '')}/health`;
  const started = Date.now();
  try {
    const response = await net.fetch(healthUrl, { signal: AbortSignal.timeout(timeoutMs) });
    return { ok: response.ok, ms: Date.now() - started };
  } catch {
    return { ok: false, ms: null };
  }
}

/** Paket güncellemesi ve compose up sonrası API'nin HTTP kabul etmesini bekler. */
export async function waitForApiHealth(
  backendUrl = apiBaseUrl(),
  attempts = 45,
): Promise<boolean> {
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    const probe = await probeApiHealth(backendUrl, 2500);
    if (probe.ok) return true;
    await sleep(1000);
  }
  return false;
}

function decorateStatus(
  partial: Omit<
    ServicesStatus,
    | 'apiReachable'
    | 'apiLatencyMs'
    | 'dockerDesktopInstalled'
    | 'hints'
    | 'engineState'
    | 'dockerCliAvailable'
    | 'hostDockerAccess'
    | 'dockerContext'
    | 'dockerContextKind'
    | 'dockerContextRedirected'
    | 'dockerHostSet'
  > &
    Partial<
      Pick<
        ServicesStatus,
        | 'apiReachable'
        | 'apiLatencyMs'
        | 'engineState'
        | 'dockerCliAvailable'
        | 'hostDockerAccess'
        | 'dockerContext'
        | 'dockerContextKind'
        | 'dockerContextRedirected'
        | 'dockerHostSet'
      >
    >,
): ServicesStatus {
  const installed = dockerDesktopInstalled();
  const summary = summarizeComposeHealth(partial.services);
  const apiReachable = partial.apiReachable ?? false;
  const engineState = partial.engineState ?? (partial.dockerAvailable ? 'up' : 'down');
  const dockerCliAvailable = partial.dockerCliAvailable ?? partial.dockerAvailable;
  const hostDockerAccess =
    partial.hostDockerAccess ??
    classifyHostDockerAccess({ cliAvailable: dockerCliAvailable, engineState });
  const context = classifyDockerContext({
    contextName: partial.dockerContext,
    dockerHost: '',
    hostFromEnv: partial.dockerHostSet,
  });
  const dockerContext = partial.dockerContext ?? context.contextName;
  const dockerContextKind = partial.dockerContextKind ?? context.kind;
  const dockerContextRedirected = partial.dockerContextRedirected ?? context.redirected;
  const dockerHostSet = partial.dockerHostSet ?? context.hostSet;
  const hints = buildDockerHints({
    dockerAvailable: partial.dockerAvailable,
    composeAvailable: partial.composeAvailable,
    gpuAvailable: partial.gpuAvailable,
    repoRoot: partial.repoRoot,
    apiReachable,
    dockerDesktopInstalled: installed,
    apiHealthy: summary.apiHealthy,
    engineState,
    dockerCliAvailable,
    hostDockerAccess,
    dockerContextName: dockerContext,
    dockerContextKind,
    dockerContextRedirected,
    missing: summary.missing,
    unhealthy: summary.unhealthy,
  }, hostLang());
  return {
    ...partial,
    apiReachable,
    apiLatencyMs: partial.apiLatencyMs ?? null,
    dockerDesktopInstalled: installed,
    engineState,
    dockerCliAvailable,
    hostDockerAccess,
    dockerContext,
    dockerContextKind,
    dockerContextRedirected,
    dockerHostSet,
    hints,
  };
}

/** Docker Desktop motor durumu (Jan health-check / Desktop tepsi ayrımı). */
async function dockerEngine(): Promise<{ available: boolean; state: DockerEngineState }> {
  try {
    const result = await run('docker', ['info', '--format', '{{.ServerVersion}}'], {
      timeoutMs: 12_000,
    });
    const state = classifyDockerEngineOutput(result.code, result.stdout, result.stderr);
    if (state !== 'down') return { available: state === 'up', state };
  } catch {
  }
  try {
    const desktop = await run('docker', ['desktop', 'status'], { timeoutMs: 12_000 });
    const state = classifyDockerDesktopStatus(desktop.code, desktop.stdout, desktop.stderr);
    return { available: state === 'up', state };
  } catch {
    return { available: false, state: 'down' };
  }
}

/** Docker Desktop çalışıyor mu? */
async function dockerRunning(): Promise<boolean> {
  return (await dockerEngine()).available;
}

/** Podman Desktop: `DOCKER_HOST` / `DOCKER_CONTEXT` CLI’yı Desktop soketinden saptırır. */
async function probeDockerContext(env: NodeJS.ProcessEnv = process.env): Promise<{
  contextName: string;
  dockerHost: string;
  hostFromEnv: boolean;
}> {
  const envHost = String(env.DOCKER_HOST ?? '').trim();
  const envContext = String(env.DOCKER_CONTEXT ?? '').trim();
  let contextName = envContext;
  let dockerHost = envHost;
  try {
    if (!contextName) {
      const shown = await run('docker', ['context', 'show'], { timeoutMs: 5000 });
      if (shown.code === 0) {
        contextName = shown.stdout.trim().split(/\r?\n/)[0] ?? '';
      }
    }
    if (!dockerHost) {
      const inspect = await run(
        'docker',
        contextName
          ? ['context', 'inspect', contextName, '--format', '{{.Endpoints.docker.Host}}']
          : ['context', 'inspect', '--format', '{{.Endpoints.docker.Host}}'],
        { timeoutMs: 5000 },
      );
      if (inspect.code === 0) dockerHost = inspect.stdout.trim();
    }
  } catch {
  }
  return { contextName, dockerHost, hostFromEnv: envHost.length > 0 };
}

/** Odysseus: istemci CLI, daemon’dan ayrı yoklanır. */
async function dockerCliAvailable(): Promise<boolean> {
  try {
    const result = await run('docker', ['version', '--format', '{{.Client.Version}}'], {
      timeoutMs: 8000,
    });
    return result.code === 0 && result.stdout.trim().length > 0;
  } catch {
    return false;
  }
}

/** `docker compose` eklentisi mevcut mu? */
async function composeAvailable(): Promise<boolean> {
  try {
    const result = await run('docker', ['compose', 'version', '--short'], { timeoutMs: 12_000 });
    return result.code === 0;
  } catch {
    return false;
  }
}

/** NVIDIA GPU erişimi var mı? */
async function gpuInfo(): Promise<{ available: boolean; name: string | null }> {
  try {
    const result = await run('nvidia-smi', ['--query-gpu=name', '--format=csv,noheader'], {
      timeoutMs: 8000,
    });
    const name = result.stdout.trim().split('\n')[0]?.trim() ?? '';
    return { available: result.code === 0 && name.length > 0, name: name || null };
  } catch {
    return { available: false, name: null };
  }
}

/** Compose servislerinin durumunu okur. */
async function composePs(root: string): Promise<DockerServiceInfo[]> {
  const result = await run('docker', [...COMPOSE_PROJECT_ARGS, 'ps', '--format', 'json'], {
    cwd: root,
    timeoutMs: 30_000,
  });
  if (result.code !== 0) return [];

  const lines = result.stdout.trim().split('\n').filter(Boolean);
  const services: DockerServiceInfo[] = [];

  for (const line of lines) {
    try {
      const parsed = JSON.parse(line) as Record<string, unknown> | Record<string, unknown>[];
      const rows = Array.isArray(parsed) ? parsed : [parsed];
      for (const row of rows) {
        services.push({
          name: String(row.Service ?? row.Name ?? ''),
          state: String(row.State ?? row.Status ?? 'unknown'),
          health: (row.Health as string) || null,
          image: String(row.Image ?? ''),
        });
      }
    } catch {
    }
  }
  return services.filter((s) => s.name);
}

/** Tüm servis ve ortam durumunu toplar. */
export async function getServicesStatus(): Promise<ServicesStatus> {
  const root = findRepoRoot();
  const [engine, compose, gpu, apiProbe, cli, dockerCtx] = await Promise.all([
    dockerEngine(),
    composeAvailable(),
    gpuInfo(),
    probeApiHealth(),
    dockerCliAvailable(),
    probeDockerContext(),
  ]);
  const docker = engine.available;
  const hostDockerAccess = classifyHostDockerAccess({
    cliAvailable: cli,
    engineState: engine.state,
  });
  const context = classifyDockerContext(dockerCtx);

  if (!docker) {
    return decorateStatus({
      dockerAvailable: false,
      engineState: engine.state,
      dockerCliAvailable: cli,
      hostDockerAccess,
      dockerContext: context.contextName,
      dockerContextKind: context.kind,
      dockerContextRedirected: context.redirected,
      dockerHostSet: context.hostSet,
      composeAvailable: compose,
      gpuAvailable: gpu.available,
      gpuName: gpu.name,
      services: [],
      error:
        engine.state === 'starting'
          ? hostT('host.dockerStarting')
          : hostT('host.dockerNotRunning'),
      repoRoot: root,
      apiReachable: apiProbe.ok,
      apiLatencyMs: apiProbe.ms,
    });
  }

  if (!root) {
    return decorateStatus({
      dockerAvailable: true,
      engineState: 'up',
      dockerCliAvailable: cli,
      hostDockerAccess,
      dockerContext: context.contextName,
      dockerContextKind: context.kind,
      dockerContextRedirected: context.redirected,
      dockerHostSet: context.hostSet,
      composeAvailable: compose,
      gpuAvailable: gpu.available,
      gpuName: gpu.name,
      services: [],
      error: hostT('host.composeMissing'),
      repoRoot: null,
      apiReachable: apiProbe.ok,
      apiLatencyMs: apiProbe.ms,
    });
  }

  try {
    return decorateStatus({
      dockerAvailable: true,
      engineState: 'up',
      dockerCliAvailable: cli,
      hostDockerAccess,
      dockerContext: context.contextName,
      dockerContextKind: context.kind,
      dockerContextRedirected: context.redirected,
      dockerHostSet: context.hostSet,
      composeAvailable: compose,
      gpuAvailable: gpu.available,
      gpuName: gpu.name,
      services: await composePs(root),
      error: null,
      repoRoot: root,
      apiReachable: apiProbe.ok,
      apiLatencyMs: apiProbe.ms,
    });
  } catch (error) {
    return decorateStatus({
      dockerAvailable: true,
      engineState: 'up',
      dockerCliAvailable: cli,
      hostDockerAccess,
      dockerContext: context.contextName,
      dockerContextKind: context.kind,
      dockerContextRedirected: context.redirected,
      dockerHostSet: context.hostSet,
      composeAvailable: compose,
      gpuAvailable: gpu.available,
      gpuName: gpu.name,
      services: [],
      error: error instanceof Error ? error.message : String(error),
      repoRoot: root,
      apiReachable: apiProbe.ok,
      apiLatencyMs: apiProbe.ms,
    });
  }
}

/** Ortam tanısı — durum + ipuçları (UI "Tanı" düğmesi). */
export function diagnoseServices(): Promise<ServicesStatus> {
  return getServicesStatus();
}

/** İzin verilen compose alt komutları (allowlist). */
const COMPOSE_ACTIONS: Record<string, string[]> = {
  up: [...COMPOSE_PROJECT_ARGS, 'up', '-d'],
  update: [
    ...COMPOSE_PROJECT_ARGS,
    'up',
    '-d',
    '--build',
    '--no-deps',
    COMPOSE_API_SERVICE,
    'tts',
    'whisper',
  ],
  stop: [...COMPOSE_PROJECT_ARGS, 'stop'],
  restart: [...COMPOSE_PROJECT_ARGS, 'restart'],
};

/** Preset değişince llama-server GGUF'u yeniden yüklensin. */
export async function recreateLlmService(): Promise<ServicesActionResult> {
  const ready = await ensureComposeReady();
  if (isActionResult(ready)) return ready;
  const settings = getSettings();
  applyLlmComposeEnv(
    ready.root,
    presetFromSettings(settings.modelName, settings.llmPreset),
    settings.modelName,
  );
  emitProgress('llm', hostT('host.llmReloading'));
  const result = await run(
    'docker',
    [...COMPOSE_PROJECT_ARGS, 'up', '-d', '--force-recreate', 'llm'],
    { cwd: ready.root, timeoutMs: 180_000, onChunk: composeChunkSink() },
  );
  const output = `${result.stdout}\n${result.stderr}`.trim();
  emitProgress(result.code === 0 ? 'done' : 'error', result.code === 0 ? '' : hostT('host.llmRestartFail'));
  return {
    ok: result.code === 0,
    message:
      result.code === 0
        ? hostT('host.llmReloaded')
        : hostT('host.llmRestartCode', { code: result.code }),
    output: output.slice(-6000),
  };
}

async function ensureComposeReady(): Promise<{ root: string } | ServicesActionResult> {
  const root = findRepoRoot();
  if (!root) {
    return {
      ok: false,
      message: hostT('host.composeMissingRoot'),
    };
  }
  if (!(await dockerRunning())) {
    return { ok: false, message: hostT('host.startDockerFirst') };
  }
  return { root };
}

function isActionResult(
  value: { root: string } | ServicesActionResult,
): value is ServicesActionResult {
  return 'ok' in value;
}

/** Jan health-check: up/update öncesi YAML’i `config --quiet` ile doğrular. */
async function validateComposeConfig(root: string): Promise<ServicesActionResult | null> {
  emitProgress('config', hostT('host.configCheck'));
  try {
    const result = await run('docker', [...COMPOSE_PROJECT_ARGS, 'config', '--quiet'], {
      cwd: root,
      timeoutMs: 25_000,
    });
    const failure = formatComposeConfigFailure(
      result.code,
      result.stdout,
      result.stderr,
      hostLang(),
    );
    if (!failure) return null;
    emitProgress('error', failure);
    return { ok: false, message: failure, output: `${result.stderr}\n${result.stdout}`.trim() };
  } catch (error) {
    const message =
      error instanceof Error ? error.message.slice(0, 500) : hostT('host.configFail');
    emitProgress('error', message);
    return { ok: false, message };
  }
}

/** Compose komutunu çalıştırır. */
async function runCompose(action: keyof typeof COMPOSE_ACTIONS): Promise<ServicesActionResult> {
  const ready = await ensureComposeReady();
  if (isActionResult(ready)) return ready;

  const args = COMPOSE_ACTIONS[action];
  if (!args) return { ok: false, message: hostT('host.invalidAction') };

  const settings = getSettings();
  applyLlmComposeEnv(
    ready.root,
    presetFromSettings(settings.modelName, settings.llmPreset),
    settings.modelName,
  );

  if (action === 'up' || action === 'update') {
    const invalid = await validateComposeConfig(ready.root);
    if (invalid) return invalid;
  }

  emitProgress(action, hostT('host.composeRunning'));
  const result = await run('docker', args, {
    cwd: ready.root,
    timeoutMs: 300_000,
    onChunk: composeChunkSink(),
  });
  const output = `${result.stdout}\n${result.stderr}`.trim();
  emitProgress(result.code === 0 ? 'done' : 'error', result.code === 0 ? '' : hostT('host.composeFail'));

  const verbKey =
    action === 'up'
      ? 'host.verb.up'
      : action === 'stop'
        ? 'host.verb.stop'
        : action === 'restart'
          ? 'host.verb.restart'
          : 'host.verb.update';

  return {
    ok: result.code === 0,
    message:
      result.code === 0
        ? hostT('host.servicesDone', { verb: hostT(verbKey) })
        : hostT('host.failCode', { code: result.code }),
    output: output.slice(-6000),
  };
}

async function waitForDockerEngine(timeoutMs: number): Promise<boolean> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await dockerRunning()) return true;
    await sleep(2000);
  }
  return false;
}

/** Docker Desktop'ı host'ta başlatır; yoksa resmi kurucuyu indirir (UAC, sessiz kurulum yok). */
export async function openDockerDesktop(): Promise<ServicesActionResult> {
  if (await dockerRunning()) {
    return { ok: true, message: hostT('host.dockerAlready') };
  }
  const installed = dockerDesktopInstalled();
  if (dockerDesktopLaunchKind(installed) === 'download-installer') {
    emitProgress('docker_desktop', hostT('host.dockerDownloading'));
    try {
      const installer = await downloadOfficialDockerInstaller();
      launchDetached(installer, []);
      return {
        ok: true,
        message: hostT('host.dockerInstaller'),
      };
    } catch {
      try {
        await shell.openExternal(DOCKER_DESKTOP_INSTALLER_URL);
        return {
          ok: true,
          message: hostT('host.dockerBrowser'),
        };
      } catch {
        return {
          ok: false,
          message: hostT('host.dockerNotFound'),
        };
      }
    }
  }
  emitProgress('docker_desktop', hostT('host.dockerLaunching'));
  try {
    const cli = await run('docker', ['desktop', 'start'], { timeoutMs: 90_000 });
    if (cli.code === 0) {
      return {
        ok: true,
        message: hostT('host.dockerCliStarted'),
      };
    }
  } catch {
  }
  const exe = dockerDesktopCandidates().find((candidate) => existsSync(candidate));
  if (!exe) {
    return {
      ok: false,
      message: hostT('host.dockerExeMissing'),
    };
  }
  launchDetached(exe, []);
  return {
    ok: true,
    message: hostT('host.dockerStarted'),
  };
}

async function downloadOfficialDockerInstaller(): Promise<string> {
  const dest = path.join(tmpdir(), 'Uryx-DockerDesktopInstaller.exe');
  const response = await net.fetch(DOCKER_DESKTOP_INSTALLER_URL);
  if (!response.ok || !response.body) {
    throw new Error(hostT('host.dockerInstallerFail', { status: response.status }));
  }
  await pipeline(Readable.fromWeb(response.body as never), createWriteStream(dest));
  return dest;
}

/** Servisleri başlatır; Docker kapalıysa önce Desktop'ı açmayı dener. */
export async function startServices(): Promise<ServicesActionResult> {
  if (!(await dockerRunning())) {
    const launched = await openDockerDesktop();
    if (!launched.ok) return launched;
    emitProgress('docker_wait', hostT('host.dockerWait'));
    const engineReady = await waitForDockerEngine(90_000);
    if (!engineReady) {
      return {
        ok: false,
        message:
          hostT('host.dockerOpenedWait'),
      };
    }
  }

  const result = await runCompose('up');
  if (!result.ok) return result;

  const ready = await ensureComposeReady();
  if (!isActionResult(ready)) {
    emitProgress('waiting', hostT('host.coreWait'));
    await run(
      'docker',
      [
        ...COMPOSE_PROJECT_ARGS,
        'up',
        '-d',
        '--wait',
        '--wait-timeout',
        '90',
        'postgres',
        'qdrant',
        COMPOSE_API_SERVICE,
      ],
      { cwd: ready.root, timeoutMs: 120_000, onChunk: composeChunkSink() },
    );
  }

  emitProgress('waiting', hostT('host.apiWait'));
  const healthy = await waitForApiHealth(apiBaseUrl(), 45);
  emitProgress(healthy ? 'done' : 'error', healthy ? '' : hostT('host.apiNoHealth'));
  return {
    ok: healthy,
    message: healthy
      ? hostT('host.startedOk')
      : hostT('host.startedNoHealth'),
    output: result.output,
  };
}

/** Servisleri durdurur. */
export function stopServices(): Promise<ServicesActionResult> {
  return runCompose('stop');
}

/** Tüm servisleri veya allowlist'teki tek servisi yeniden başlatır. */
export async function restartServices(service?: string): Promise<ServicesActionResult> {
  if (service && String(service).trim()) {
    const name = sanitizeComposeService(service);
    if (!name) {
      return {
        ok: false,
        message: hostT('host.restartDenied', { name: String(service) }),
      };
    }
    const ready = await ensureComposeReady();
    if (isActionResult(ready)) return ready;
    const waitArgs = composeUpWaitArgs(name, 90);
    if (!waitArgs) {
      return { ok: false, message: hostT('host.restartDenied', { name }) };
    }
    emitProgress('waiting', hostT('host.svcWait', { name }));
    const result = await run('docker', waitArgs, {
      cwd: ready.root,
      timeoutMs: 180_000,
      onChunk: composeChunkSink(),
    });
    const output = `${result.stdout}\n${result.stderr}`.trim();
    const ok = result.code === 0;
    if (ok && name === COMPOSE_API_SERVICE) {
      emitProgress('waiting', hostT('host.apiWait'));
      const healthy = await waitForApiHealth(apiBaseUrl(), 30);
      emitProgress(healthy ? 'done' : 'error', healthy ? '' : hostT('host.apiNoHealth'));
      return {
        ok: healthy,
        message: healthy ? hostT('host.apiRestarted') : hostT('host.apiRestartedWait'),
        output: output.slice(-6000),
      };
    }
    emitProgress(ok ? 'done' : 'error', ok ? '' : hostT('host.notHealthy', { name }));
    return {
      ok,
      message: ok
        ? hostT('host.readyWait', { name })
        : hostT('host.failCode', { code: result.code }),
      output: output.slice(-6000),
    };
  }
  return runCompose('restart');
}

/** Yeni paket sürümünde backend imajlarını bir kez günceller. */
export async function syncPackagedServices(version: string): Promise<ServicesActionResult | null> {
  if (!app.isPackaged) return null;
  const marker = path.join(app.getPath('userData'), 'services-version');
  try {
    if ((await readFile(marker, 'utf8')).trim() === version) return null;
  } catch {
  }

  const result = await runCompose('update');
  if (result.ok) await writeFile(marker, version, 'utf8');
  return result;
}

/** Docker Desktop motor logu — yalnızca `docker desktop logs`, follow yok. */
export async function getDockerDesktopLogs(lines = 200): Promise<string> {
  const safeLines = Math.max(10, Math.min(Math.round(lines) || 200, 400));
  try {
    const result = await run('docker', ['desktop', 'logs'], { timeoutMs: 20_000 });
    const text = redactUrlsInText(`${result.stdout}\n${result.stderr}`.trim());
    if (!text) return hostT('host.desktopLogEmpty');
    return text.split(/\r?\n/).slice(-safeLines).join('\n').slice(-40_000);
  } catch (error) {
    return error instanceof Error ? error.message.slice(0, 500) : hostT('host.desktopLogFail');
  }
}

/** Servis loglarını getirir. */
export async function getServiceLogs(service = '', lines = 200): Promise<string> {
  const source = sanitizeLogSource(service);
  if (source === null) {
    return hostT('host.logDenied', { name: String(service) });
  }
  if (source === 'docker-desktop') {
    return getDockerDesktopLogs(lines);
  }

  const root = findRepoRoot();
  if (!root) return hostT('host.composeFileMissing');

  const safeLines = Math.max(10, Math.min(Math.round(lines) || 200, 1000));
  const args = [...COMPOSE_PROJECT_ARGS, 'logs', '--no-color', `--tail=${safeLines}`];
  if (source) args.push(source);

  const result = await run('docker', args, { cwd: root, timeoutMs: 45_000 });
  return redactUrlsInText(`${result.stdout}\n${result.stderr}`.trim()).slice(-60_000);
}
