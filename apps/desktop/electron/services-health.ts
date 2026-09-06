/**
 * Compose / Docker sağlık yardımcıları (saf fonksiyonlar).
 *
 * Jan ve yerel ajan masaüstü kalıbı: host, konteyner durumunu
 * `docker compose ps` ile okur; API'nin HTTP `/health` yanıtını
 * ayrıca yoklar. llm/Whisper/TTS host'a port açmaz (llm 8000 hariç, 127.0.0.1).
 */

import type { UiLanguage } from '@shared/settings';

import { composePhaseLabel, translate } from '../src/lib/messages';
import { redactUrlsInText } from './host-tools/safe-url';

export const COMPOSE_PROJECT_NAME = 'uryx';
export const COMPOSE_API_SERVICE = 'uryx-api';

export const COMPOSE_SERVICE_ALLOWLIST = new Set([
  COMPOSE_API_SERVICE,
  'llm',
  'whisper',
  'tts',
  'postgres',
  'qdrant',
]);

export interface ComposeServiceSnapshot {
  name: string;
  state: string;
  health: string | null;
  image: string;
}

/** Compose servis adını allowlist'e indirger. */
export function sanitizeComposeService(raw: unknown): string | null {
  const name = String(raw ?? '')
    .trim()
    .toLowerCase();
  return COMPOSE_SERVICE_ALLOWLIST.has(name) ? name : null;
}

/**
 * Tek servis `up -d --wait` — `restart` healthy beklemez.
 * https://docs.docker.com/reference/cli/docker/compose/up/
 */
export function composeUpWaitArgs(service: unknown, waitTimeoutSec = 90): string[] | null {
  const name = sanitizeComposeService(service);
  if (!name) return null;
  const timeout = Math.max(10, Math.min(Math.floor(Number(waitTimeoutSec)) || 90, 180));
  return [
    'compose',
    '--project-name',
    COMPOSE_PROJECT_NAME,
    'up',
    '-d',
    '--wait',
    '--wait-timeout',
    String(timeout),
    name,
  ];
}

/** Log kaynağı: compose servisleri + Docker Desktop motor logu. */
export const LOG_SOURCE_ALLOWLIST = new Set([...COMPOSE_SERVICE_ALLOWLIST, 'docker-desktop']);

/** `docker compose config --quiet` çıkışını Jan health-check gibi sınıflandırır. */
export function formatComposeConfigFailure(
  code: number,
  stdout: string,
  stderr: string,
  language: UiLanguage = 'en',
): string | null {
  if (code === 0) return null;
  const detail = redactUrlsInText(`${stderr}\n${stdout}`.trim()).slice(0, 800);
  return translate(language, 'host.configInvalid', {
    detail: detail || translate(language, 'host.configExit', { code }),
  });
}

export function sanitizeLogSource(raw: unknown): string | null {
  const name = String(raw ?? '')
    .trim()
    .toLowerCase();
  if (!name) return '';
  return LOG_SOURCE_ALLOWLIST.has(name) ? name : null;
}

function norm(value: string | null | undefined): string {
  return String(value ?? '')
    .trim()
    .toLowerCase();
}

/** Konteyner çalışıyor ve (varsa) healthy mi? */
export function isComposeServiceReady(service: ComposeServiceSnapshot | undefined): boolean {
  if (!service) return false;
  const state = norm(service.state);
  const running = state === 'running' || state.includes('running');
  if (!running) return false;
  const health = norm(service.health);
  if (!health || health === 'unknown') return running;
  return health === 'healthy';
}

export const EXPECTED_COMPOSE_SERVICES = [
  COMPOSE_API_SERVICE,
  'postgres',
  'qdrant',
  'llm',
  'whisper',
  'tts',
] as const;

export interface ComposeHealthSummary {
  api: ComposeServiceSnapshot | undefined;
  apiHealthy: boolean;
  running: number;
  unhealthy: string[];
  missing: string[];
}

/** Compose anlık görüntüsünden özet çıkarır. */
export function summarizeComposeHealth(services: ComposeServiceSnapshot[]): ComposeHealthSummary {
  const api = services.find((item) => item.name === COMPOSE_API_SERVICE);
  const unhealthy = services
    .filter((item) => {
      const state = norm(item.state);
      const health = norm(item.health);
      return state.includes('exit') || health === 'unhealthy';
    })
    .map((item) => item.name);

  const present = new Set(services.map((item) => item.name));
  const missing = EXPECTED_COMPOSE_SERVICES.filter((name) => !present.has(name));

  return {
    api,
    apiHealthy: isComposeServiceReady(api),
    running: services.filter((item) => norm(item.state).includes('running')).length,
    unhealthy,
    missing: [...missing],
  };
}

export type DockerEngineState = 'up' | 'starting' | 'down';
export type HostDockerAccess = 'ok' | 'cli_only' | 'missing';
export type DockerContextKind = 'default' | 'podman' | 'remote' | 'custom';

export interface DockerContextClassification {
  kind: DockerContextKind;
  redirected: boolean;
  contextName: string;
  hostSet: boolean;
}

const LOCAL_DOCKER_CONTEXTS = new Set(['', 'default', 'desktop-linux', 'desktop-windows']);

function isLocalDockerHost(host: string): boolean {
  if (!host) return true;
  const value = host.toLowerCase();
  if (value.includes('podman')) return false;
  if (/^npipe:\/\/.*\/pipe\/docker(_engine|desktoplinuxengine|desktopwindowsengine)?$/i.test(value)) {
    return true;
  }
  return value === 'unix:///var/run/docker.sock' || value === 'unix://var/run/docker.sock';
}

/**
 * Podman Desktop: CLI context / DOCKER_HOST varsayılan Desktop soketinden sapabilir.
 * https://github.com/podman-desktop/podman-desktop/blob/main/extensions/docker/packages/extension/src/docker-context-handler.ts
 */
export function classifyDockerContext(input: {
  contextName?: string | null;
  dockerHost?: string | null;
  hostFromEnv?: boolean;
}): DockerContextClassification {
  const contextName = String(input.contextName ?? '').trim();
  const dockerHost = String(input.dockerHost ?? '').trim();
  const hostSet = Boolean(input.hostFromEnv);
  const blob = `${contextName}\n${dockerHost}`.toLowerCase();

  if (/\bpodman\b/.test(blob) || blob.includes('podman.sock') || blob.includes('podman-machine')) {
    return { kind: 'podman', redirected: true, contextName: contextName || 'podman', hostSet };
  }
  if (/^(tcp|ssh):\/\//i.test(dockerHost)) {
    return { kind: 'remote', redirected: true, contextName: contextName || 'remote', hostSet };
  }

  const localName = LOCAL_DOCKER_CONTEXTS.has(contextName.toLowerCase());
  const localHost = isLocalDockerHost(dockerHost);
  if (localName && localHost) {
    return {
      kind: 'default',
      redirected: false,
      contextName: contextName || 'default',
      hostSet,
    };
  }

  return {
    kind: 'custom',
    redirected: true,
    contextName: contextName || (dockerHost ? 'custom' : 'default'),
    hostSet,
  };
}

/**
 * Odysseus `local_docker_available`: CLI tek başına daemon değildir.
 * https://github.com/odysseus-dev/odysseus/blob/dev/src/host_docker_access.py
 */
export function classifyHostDockerAccess(input: {
  cliAvailable: boolean;
  engineState: DockerEngineState;
}): HostDockerAccess {
  if (input.engineState === 'up') return 'ok';
  if (input.cliAvailable) return 'cli_only';
  return 'missing';
}

/**
 * Docker Desktop tepsisi / named-pipe hatalarını ayırır.
 * "açık değil" ile "motor hâlâ ayağa kalkıyor" farklı ipucu ister.
 */
export function classifyDockerEngineOutput(code: number, stdout: string, stderr: string): DockerEngineState {
  if (code === 0 && stdout.trim().length > 0) return 'up';
  const text = `${stdout}\n${stderr}`.toLowerCase();
  if (
    /docker desktop is starting|error during connect|named pipe|npipe|dockerdesktoplinuxengine|cannot find the file specified|the system cannot find the file/i.test(
      text,
    )
  ) {
    return 'starting';
  }
  return 'down';
}

/**
 * Docker Desktop 4.37+ ``docker desktop status`` çıktısı.
 * Desktop tepsisi "Starting / Running / Stopped" ile aynı ayrım.
 */
export function classifyDockerDesktopStatus(code: number, stdout: string, stderr: string): DockerEngineState {
  const text = `${stdout}\n${stderr}`.toLowerCase();
  if (/is running|running\b/.test(text) && !/not running|stopped/.test(text)) return 'up';
  if (/starting|is starting/.test(text)) return 'starting';
  if (code === 0 && /running/.test(text)) return 'up';
  return 'down';
}

export interface DockerHintInput {
  dockerAvailable: boolean;
  composeAvailable: boolean;
  gpuAvailable: boolean;
  repoRoot: string | null;
  apiReachable: boolean;
  dockerDesktopInstalled: boolean;
  apiHealthy: boolean;
  engineState?: DockerEngineState;
  dockerCliAvailable?: boolean;
  hostDockerAccess?: HostDockerAccess;
  dockerContextName?: string;
  dockerContextKind?: DockerContextKind;
  dockerContextRedirected?: boolean;
  missing?: string[];
  unhealthy?: string[];
}

/** Kullanıcıya gösterilecek kısa ipuçları. */
export function buildDockerHints(
  input: DockerHintInput,
  language: UiLanguage = 'en',
): string[] {
  const hints: string[] = [];
  if (!input.dockerAvailable) {
    if (input.engineState === 'starting') {
      hints.push(translate(language, 'host.hint.starting'));
    } else if (input.hostDockerAccess === 'cli_only' || input.dockerCliAvailable) {
      hints.push(translate(language, 'host.hint.cliOnly'));
    } else {
      hints.push(
        translate(
          language,
          input.dockerDesktopInstalled ? 'host.hint.installedDown' : 'host.hint.missing',
        ),
      );
    }
  }
  if (input.dockerAvailable && !input.composeAvailable) {
    hints.push(translate(language, 'host.hint.noCompose'));
  }
  if (input.dockerAvailable && !input.repoRoot) {
    hints.push(translate(language, 'host.hint.noRepo'));
  }
  if (input.dockerAvailable && input.repoRoot && !input.apiHealthy && !input.apiReachable) {
    hints.push(translate(language, 'host.hint.apiWait'));
  }
  if (input.dockerAvailable && input.unhealthy && input.unhealthy.length > 0) {
    hints.push(translate(language, 'host.hint.unhealthy', { names: input.unhealthy.join(', ') }));
  }
  if (input.dockerAvailable && input.missing && input.missing.length > 0) {
    hints.push(translate(language, 'host.hint.missingSvcs', { names: input.missing.join(', ') }));
  }
  if (input.dockerAvailable && !input.gpuAvailable) {
    hints.push(translate(language, 'host.hint.noGpu'));
  }
  if (input.dockerContextRedirected) {
    if (input.dockerContextKind === 'podman') {
      hints.push(translate(language, 'host.hint.podman'));
    } else if (input.dockerContextKind === 'remote') {
      hints.push(translate(language, 'host.hint.remote'));
    } else {
      hints.push(
        translate(language, 'host.hint.context', { name: input.dockerContextName || 'custom' }),
      );
    }
  }
  return hints;
}

export interface ComposeProgressLine {
  phase: string;
  message: string;
}

function shortComposeName(name: string): string {
  return name
    .replace(/^uryx[-_]/i, '')
    .replace(/^uryx_v2[-_]/i, '')
    .replace(/-\d+$/, '')
    .slice(0, 48);
}

/**
 * Docker Compose v2 satırını phase + arayüz dili durum satırına çevirir.
 * Continue MCP progressToken yok; Jan health-check beklemesi satırda durur.
 */
export function classifyComposeProgressLine(
  line: string,
  language: UiLanguage = 'en',
): ComposeProgressLine | null {
  const trimmed = line.replace(/\r/g, '').trim();
  if (!trimmed) return null;

  const modern =
    /^(?:Container|Image|Volume|Network)\s+(\S+)\s+(Pulling|Pulled|Creating|Created|Starting|Started|Waiting|Healthy|Error|Exited|Stopping|Stopped|Building|Built)\b/i.exec(
      trimmed,
    );
  if (modern) {
    const action = modern[2]!.toLowerCase();
    const label = composePhaseLabel(language, action);
    return { phase: action, message: `${label}: ${shortComposeName(modern[1]!)}` };
  }

  const waiting = /Waiting for (\S+) to be (?:healthy|ready)/i.exec(trimmed);
  if (waiting) {
    return {
      phase: 'waiting',
      message: `${translate(language, 'compose.waiting')}: ${shortComposeName(waiting[1]!)}`,
    };
  }

  const legacy = /^(Pulling|Creating|Starting|Stopping|Building)\s+(\S+)/i.exec(trimmed);
  if (legacy) {
    const action = legacy[1]!.toLowerCase();
    return {
      phase: action,
      message: `${composePhaseLabel(language, action)}: ${shortComposeName(legacy[2]!)}`,
    };
  }

  if (/error response from daemon|cannot start service|failed to/i.test(trimmed)) {
    return {
      phase: 'error',
      message: translate(language, 'compose.errorLine', { msg: trimmed.slice(0, 160) }),
    };
  }

  return null;
}

/** Windows'ta bilinen Docker Desktop yolları. */
export const DOCKER_DESKTOP_INSTALLER_URL =
  'https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe';

export type DockerDesktopLaunchKind = 'launch' | 'download-installer';

export function dockerDesktopLaunchKind(installed: boolean): DockerDesktopLaunchKind {
  return installed ? 'launch' : 'download-installer';
}

export function dockerDesktopCandidates(env: NodeJS.ProcessEnv = process.env): string[] {
  const local = env.LOCALAPPDATA ?? '';
  const programFiles = env['ProgramFiles'] ?? 'C:\\Program Files';
  return [
    `${programFiles}\\Docker\\Docker\\Docker Desktop.exe`,
    local ? `${local}\\Docker\\Docker\\Docker Desktop.exe` : '',
  ].filter(Boolean);
}
