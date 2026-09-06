/**
 * Host tarafı Docker Desktop / compose tanısı (Jan health-check kalıbı).
 * Konteyner içinden ``docker`` görmek yetmez; motor named-pipe host'tadır.
 * CLI context / DOCKER_HOST Podman veya uzak motora sapabilir.
 */

import { getDockerDesktopLogs, getServicesStatus, openDockerDesktop } from '../services';

/** Compose + motor + ipuçları — modelin kendi tanısını yapması için. */
export async function getDockerEngineStatus(): Promise<Record<string, unknown>> {
  const status = await getServicesStatus();
  return {
    engine: status.engineState,
    docker_cli: status.dockerCliAvailable,
    host_docker_access: status.hostDockerAccess,
    docker_context: status.dockerContext,
    docker_context_kind: status.dockerContextKind,
    docker_context_redirected: status.dockerContextRedirected,
    docker_host_set: status.dockerHostSet,
    docker_available: status.dockerAvailable,
    compose_available: status.composeAvailable,
    api_reachable: status.apiReachable,
    api_latency_ms: status.apiLatencyMs,
    gpu: status.gpuName,
    docker_desktop_installed: status.dockerDesktopInstalled,
    services: status.services,
    hints: status.hints,
    error: status.error,
    repo_root: status.repoRoot,
  };
}

/** Docker Desktop'ı host'ta açar (CLI veya exe). */
export async function openDockerDesktopTool(): Promise<Record<string, unknown>> {
  const result = await openDockerDesktop();
  return { ok: result.ok, message: result.message };
}

/** Allowlist'li Desktop motor logu (follow yok). */
export async function getDockerDesktopLogsTool(
  args: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  const lines = Number(args.lines);
  const text = await getDockerDesktopLogs(Number.isFinite(lines) ? lines : 200);
  return { source: 'docker-desktop', text };
}
