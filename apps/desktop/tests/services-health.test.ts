/** Compose sağlık özeti ve Docker ipuçları. */

import { describe, expect, it } from 'vitest';

import {
  buildDockerHints,
  classifyComposeProgressLine,
  classifyDockerContext,
  classifyDockerDesktopStatus,
  classifyDockerEngineOutput,
  classifyHostDockerAccess,
  composeUpWaitArgs,
  dockerDesktopCandidates,
  dockerDesktopLaunchKind,
  DOCKER_DESKTOP_INSTALLER_URL,
  formatComposeConfigFailure,
  isComposeServiceReady,
  sanitizeComposeService,
  sanitizeLogSource,
  summarizeComposeHealth,
} from '../electron/services-health';
import { formatTrayTooltip } from '../electron/tray';

describe('tek servis up --wait', () => {
  it('allowlist servisi --wait ile üretir, kabuk yok', () => {
    expect(composeUpWaitArgs('LLM')).toEqual([
      'compose',
      '--project-name',
      'uryx',
      'up',
      '-d',
      '--wait',
      '--wait-timeout',
      '90',
      'llm',
    ]);
    expect(composeUpWaitArgs('rm -rf')).toBeNull();
  });
});

describe('Odysseus host docker access', () => {
  it('CLI var motor yok = cli_only; motor up = ok', () => {
    expect(classifyHostDockerAccess({ cliAvailable: true, engineState: 'down' })).toBe('cli_only');
    expect(classifyHostDockerAccess({ cliAvailable: true, engineState: 'starting' })).toBe(
      'cli_only',
    );
    expect(classifyHostDockerAccess({ cliAvailable: true, engineState: 'up' })).toBe('ok');
    expect(classifyHostDockerAccess({ cliAvailable: false, engineState: 'down' })).toBe('missing');
  });

  it('cli_only ipucunu CLI yetmez diye yazar', () => {
    const hints = buildDockerHints({
      dockerAvailable: false,
      composeAvailable: false,
      gpuAvailable: true,
      repoRoot: 'C:\\proj',
      apiReachable: false,
      dockerDesktopInstalled: true,
      apiHealthy: false,
      engineState: 'down',
      dockerCliAvailable: true,
      hostDockerAccess: 'cli_only',
    }, 'tr');
    expect(hints[0]).toMatch(/CLI yetmez/i);
  });
});

describe('Podman Desktop docker context', () => {
  it('desktop-linux + named pipe varsayılan sayılır, sapmaz', () => {
    expect(
      classifyDockerContext({
        contextName: 'desktop-linux',
        dockerHost: 'npipe:////./pipe/docker_engine',
        hostFromEnv: false,
      }),
    ).toMatchObject({ kind: 'default', redirected: false });
    expect(
      classifyDockerContext({
        contextName: 'default',
        dockerHost: 'npipe:////./pipe/dockerDesktopLinuxEngine',
        hostFromEnv: true,
      }),
    ).toMatchObject({ kind: 'default', redirected: false, hostSet: true });
  });

  it('podman / tcp / colima sapmasını ayırır', () => {
    expect(
      classifyDockerContext({
        contextName: 'podman-machine-default',
        dockerHost: 'unix:///run/podman/podman.sock',
      }),
    ).toMatchObject({ kind: 'podman', redirected: true });
    expect(
      classifyDockerContext({
        contextName: 'default',
        dockerHost: 'tcp://192.168.1.10:2375',
        hostFromEnv: true,
      }),
    ).toMatchObject({ kind: 'remote', redirected: true, hostSet: true });
    expect(
      classifyDockerContext({
        contextName: 'colima',
        dockerHost: 'unix:///Users/me/.colima/default/docker.sock',
      }),
    ).toMatchObject({ kind: 'custom', redirected: true, contextName: 'colima' });
  });

  it('sapmış context ipucunu Türkçe yazar', () => {
    const podman = buildDockerHints({
      dockerAvailable: true,
      composeAvailable: true,
      gpuAvailable: true,
      repoRoot: 'C:\\proj',
      apiReachable: true,
      dockerDesktopInstalled: true,
      apiHealthy: true,
      dockerContextKind: 'podman',
      dockerContextRedirected: true,
      dockerContextName: 'podman-machine-default',
    }, 'tr');
    expect(podman.some((hint) => /Podman/i.test(hint) && /DOCKER_HOST/i.test(hint))).toBe(true);

    const remote = buildDockerHints({
      dockerAvailable: true,
      composeAvailable: true,
      gpuAvailable: true,
      repoRoot: 'C:\\proj',
      apiReachable: true,
      dockerDesktopInstalled: true,
      apiHealthy: true,
      dockerContextKind: 'remote',
      dockerContextRedirected: true,
    }, 'tr');
    expect(remote.some((hint) => /uzak motor/i.test(hint))).toBe(true);
  });
});

describe('sanitizeComposeService', () => {
  it('yalnızca allowlist adlarını kabul eder', () => {
    expect(sanitizeComposeService('uryx-api')).toBe('uryx-api');
    expect(sanitizeComposeService('LLM')).toBe('llm');
    expect(sanitizeComposeService('postgres-debug-port')).toBeNull();
    expect(sanitizeComposeService('rm -rf')).toBeNull();
  });

  it('log kaynağına docker-desktop ekler, follow/kabuk yok', () => {
    expect(sanitizeLogSource('docker-desktop')).toBe('docker-desktop');
    expect(sanitizeLogSource('')).toBe('');
    expect(sanitizeLogSource('docker desktop logs --follow')).toBeNull();
    expect(sanitizeLogSource('llm; rm -rf')).toBeNull();
  });
});

describe('compose sağlık', () => {
  it('healthy API’yi hazır sayar', () => {
    expect(
      isComposeServiceReady({
        name: 'uryx-api',
        state: 'running',
        health: 'healthy',
        image: 'uryx/api',
      }),
    ).toBe(true);
    expect(
      isComposeServiceReady({
        name: 'uryx-api',
        state: 'exited',
        health: 'unhealthy',
        image: 'uryx/api',
      }),
    ).toBe(false);
  });

  it('özet çıkarır', () => {
    const summary = summarizeComposeHealth([
      { name: 'uryx-api', state: 'running', health: 'healthy', image: 'api' },
      { name: 'llm', state: 'exited (1)', health: null, image: 'llama.cpp' },
    ]);
    expect(summary.apiHealthy).toBe(true);
    expect(summary.running).toBe(1);
    expect(summary.unhealthy).toEqual(['llm']);
    expect(summary.missing).toEqual(expect.arrayContaining(['postgres', 'qdrant']));
  });
});

describe('Docker motor sınıflandırması', () => {
  it('başarılı info’yu up sayar', () => {
    expect(classifyDockerEngineOutput(0, '27.0.3', '')).toBe('up');
  });

  it('named pipe / starting hatalarını starting sayar', () => {
    expect(
      classifyDockerEngineOutput(
        1,
        '',
        'error during connect: open //./pipe/dockerDesktopLinuxEngine: The system cannot find the file specified.',
      ),
    ).toBe('starting');
  });
});

describe('Docker ipuçları', () => {
  it('Docker kapalıyken kurulum/çalıştırma ayrımı yapar', () => {
    const missing = buildDockerHints({
      dockerAvailable: false,
      composeAvailable: false,
      gpuAvailable: true,
      repoRoot: 'C:\\proj',
      apiReachable: false,
      dockerDesktopInstalled: false,
      apiHealthy: false,
    }, 'tr');
    expect(missing[0]).toMatch(/bulunamadı/i);
    expect(missing[0]).toMatch(/resmi kurucu|UAC|yönetici/i);

    const stopped = buildDockerHints({
      dockerAvailable: false,
      composeAvailable: true,
      gpuAvailable: true,
      repoRoot: 'C:\\proj',
      apiReachable: false,
      dockerDesktopInstalled: true,
      apiHealthy: false,
    }, 'tr');
    expect(stopped[0]).toMatch(/çalışmıyor/i);

    const starting = buildDockerHints({
      dockerAvailable: false,
      composeAvailable: true,
      gpuAvailable: true,
      repoRoot: 'C:\\proj',
      apiReachable: false,
      dockerDesktopInstalled: true,
      apiHealthy: false,
      engineState: 'starting',
    }, 'tr');
    expect(starting[0]).toMatch(/ayağa kalkıyor/i);
  });

  it('bilinen Docker Desktop yollarını üretir', () => {
    const paths = dockerDesktopCandidates({
      LOCALAPPDATA: 'C:\\Users\\test\\AppData\\Local',
      ProgramFiles: 'C:\\Program Files',
    });
    expect(paths.some((item) => item.includes('Docker Desktop.exe'))).toBe(true);
  });

  it('kurulu değilse resmi Windows amd64 kurucusunu işaretler', () => {
    expect(DOCKER_DESKTOP_INSTALLER_URL).toMatch(
      /^https:\/\/desktop\.docker\.com\/win\/main\/amd64\//,
    );
    expect(dockerDesktopLaunchKind(true)).toBe('launch');
    expect(dockerDesktopLaunchKind(false)).toBe('download-installer');
  });
});

describe('docker desktop status', () => {
  it('Running / Starting / Stopped ayrımı yapar', () => {
    expect(classifyDockerDesktopStatus(0, 'Docker Desktop is running', '')).toBe('up');
    expect(classifyDockerDesktopStatus(1, 'Docker Desktop is starting', '')).toBe('starting');
    expect(classifyDockerDesktopStatus(1, 'Docker Desktop is stopped', '')).toBe('down');
  });
});

describe('compose config --quiet', () => {
  it('sıfır çıkışta geçersiz saymaz', () => {
    expect(formatComposeConfigFailure(0, 'name: uryx\n', '')).toBeNull();
  });

  it('YAML hatasını Türkçe mesaja çevirir', () => {
    const message = formatComposeConfigFailure(1, '', 'yaml: line 12: did not find expected key', 'tr');
    expect(message).toMatch(/geçersiz/i);
    expect(message).toMatch(/did not find expected key/);
  });
});

describe('compose ilerleme satırı', () => {
  it('Compose v2 Container/Image satırını phase + varsayılan İngilizce mesaja çevirir', () => {
    expect(classifyComposeProgressLine(' Container uryx-postgres Creating')).toEqual({
      phase: 'creating',
      message: 'Creating: postgres',
    });
    expect(classifyComposeProgressLine('Container uryx-qdrant Waiting')).toEqual({
      phase: 'waiting',
      message: 'Waiting for health: qdrant',
    });
    expect(classifyComposeProgressLine('Container uryx-api Healthy')).toEqual({
      phase: 'healthy',
      message: 'Healthy: api',
    });
    expect(classifyComposeProgressLine('Image postgres:16 Pulling')).toMatchObject({
      phase: 'pulling',
    });
    expect(classifyComposeProgressLine(' Container uryx-postgres Creating', 'tr')).toEqual({
      phase: 'creating',
      message: 'Oluşturuluyor: postgres',
    });
  });

  it('Waiting for … healthy ve daemon hatasını yakalar, gürültüyü atar', () => {
    expect(classifyComposeProgressLine('Waiting for uryx-api to be healthy')).toEqual({
      phase: 'waiting',
      message: 'Waiting for health: api',
    });
    expect(classifyComposeProgressLine('Error response from daemon: port is already allocated')).toMatchObject({
      phase: 'error',
    });
    expect(classifyComposeProgressLine('  ')).toBeNull();
    expect(classifyComposeProgressLine('time="2026-08-16" level=info')).toBeNull();
  });
});

describe('tepsi ipucu', () => {
  it('motor starting iken kapalı demez', () => {
    expect(
      formatTrayTooltip({
        dockerAvailable: false,
        apiReachable: false,
        hostConnected: true,
        engineState: 'starting',
      }),
    ).toMatch(/is starting/);
    expect(
      formatTrayTooltip(
        {
          dockerAvailable: false,
          apiReachable: false,
          hostConnected: true,
          engineState: 'starting',
        },
        'tr',
      ),
    ).toMatch(/ayağa kalkıyor/);
  });

  it('İngilizce arayüzde tepsi ipucunu çevirir', () => {
    expect(
      formatTrayTooltip(
        {
          dockerAvailable: true,
          apiReachable: true,
          hostConnected: true,
          engineState: 'up',
        },
        'en',
      ),
    ).toBe('Uryx · Host bridge connected · API ready');
  });
});
