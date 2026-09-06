/** Uygulama açma/kapatma araçları. */

import { shell } from 'electron';
import { existsSync } from 'node:fs';
import path from 'node:path';

import { hostText } from '../host-i18n';
import { APPLICATION_ALLOWLIST, CLOSABLE_APPS, ensurePathAllowed, resolveSpecialFolder, sanitizeSingleLine } from '../security';
import { launchDetached, launchViaExplorer, run, runPowerShell } from './process';

export interface InstalledApplication {
  name: string;
  appId: string;
}

/** Kurulu medya uygulamasında güvenli arama/deep-link açar. */
export async function openMediaApplication(
  args: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  const appName = sanitizeSingleLine(args.app, 50).toLocaleLowerCase('tr-TR');
  const query = sanitizeSingleLine(args.query, 300);
  const url = sanitizeSingleLine(args.url ?? '', 1000);
  const kind = sanitizeSingleLine(args.kind ?? '', 30).toLocaleLowerCase('tr-TR');
  const autoplay = args.autoplay !== false;
  if (!query) throw new Error(hostText('Medya arama metni gerekli.', 'Media search text is required.'));
  if (appName !== 'spotify') {
    throw new Error(
      hostText(
        `'${appName}' için güvenli uygulama içi arama desteği yok.`,
        `'${appName}' has no safe in-app search support.`,
      ),
    );
  }

  const installed = rankInstalledApplications('Spotify', await listInstalledApplications());
  if (!installed[0] || installed[0].score < 60) {
    throw new Error(
      hostText(
        'Spotify bilgisayarda kurulu değil; web yedeği kullanılmalı.',
        'Spotify is not installed on this computer; the web fallback should be used.',
      ),
    );
  }

  const target = spotifyDeepLink(query, url, kind);
  launchViaExplorer(target);
  const playback =
    autoplay && !target.startsWith('spotify:search:')
      ? await verifySpotifyPlayback()
      : {
          playback_requested: autoplay,
          playback_verified: false,
          playback_state: target.startsWith('spotify:search:') ? 'search-opened' : 'not-requested',
          playback_method: 'none',
        };
  return {
    opened: true,
    app: installed[0].app.name,
    target,
    method: target.startsWith('spotify:search:') ? 'native-search' : 'native-deep-link',
    ...playback,
  };
}

/** Spotify oynatmasını değiştirir ve gözlenen son durumu döndürür. */
export async function controlMediaPlayback(
  args: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  const appName = sanitizeSingleLine(args.app, 50).toLocaleLowerCase('tr-TR');
  const action = sanitizeSingleLine(args.action, 30).toLocaleLowerCase('tr-TR');
  const allowed = new Set(['play', 'pause', 'next', 'previous', 'close']);
  if (appName !== 'spotify') {
    throw new Error(
      hostText(
        `'${appName}' için medya kontrolü desteklenmiyor.`,
        `'${appName}' does not support media control.`,
      ),
    );
  }
  if (!allowed.has(action)) {
    throw new Error(
      hostText(`'${action}' geçerli bir medya kontrolü değil.`, `'${action}' is not a valid media control.`),
    );
  }

  if (action === 'close') {
    const closeResult = await closeApplication({ name: 'spotify' });
    const verification = await runPowerShell(
      `
$deadline = (Get-Date).AddSeconds(6)
do {
  $running = @(Get-Process -Name Spotify -ErrorAction SilentlyContinue).Count -gt 0
  if (-not $running) { break }
  Start-Sleep -Milliseconds 300
} while ((Get-Date) -lt $deadline)
[PSCustomObject]@{ running = $running } | ConvertTo-Json -Compress
`,
      { timeoutMs: 10_000, maxBuffer: 64 * 1024 },
    );
    let running = true;
    try {
      running = Boolean((JSON.parse(verification.stdout.trim()) as { running?: unknown }).running);
    } catch {
      running = true;
    }
    return {
      app: 'Spotify',
      action,
      closed: !running,
      playback_verified: !running,
      playback_state: running ? 'close-unverified' : 'closed',
      close_result: closeResult,
    };
  }

  const script = spotifyControlScript(action);
  const result = await runPowerShell(script, { timeoutMs: 15_000, maxBuffer: 1024 * 1024 });
  if (result.code !== 0 || !result.stdout.trim()) {
    throw new Error(
      result.stderr.trim() ||
        hostText('Spotify oynatma durumu denetlenemedi.', 'Could not inspect Spotify playback state.'),
    );
  }
  try {
    return { app: 'Spotify', action, ...(JSON.parse(result.stdout.trim()) as object) };
  } catch {
    throw new Error(
      hostText(
        'Spotify oynatma denetimi geçersiz sonuç döndürdü.',
        'Spotify playback check returned an invalid result.',
      ),
    );
  }
}

function spotifyControlScript(action: string): string {
  return `
Add-Type -AssemblyName UIAutomationClient

function Get-SpotifyWindow {
  $spotifyPids = @(Get-Process -Name Spotify -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id)
  if ($spotifyPids.Count -eq 0) { return $null }
  $root = [System.Windows.Automation.AutomationElement]::RootElement
  $windows = $root.FindAll([System.Windows.Automation.TreeScope]::Children, [System.Windows.Automation.Condition]::TrueCondition)
  foreach ($window in $windows) {
    if ($spotifyPids -contains $window.Current.ProcessId) { return $window }
  }
  return $null
}

function Find-PlayerButton($window, $names) {
  $elements = $window.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Automation]::ControlViewCondition)
  foreach ($element in $elements) {
    $current = $element.Current
    if ($current.ControlType -eq [System.Windows.Automation.ControlType]::Button -and
        $current.IsEnabled -and -not $current.IsOffscreen -and $names -contains $current.Name) {
      return $element
    }
  }
  return $null
}

function Invoke-Button($button) {
  if ($null -eq $button) { return $false }
  $pattern = $null
  if ($button.TryGetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern, [ref]$pattern)) {
    ([System.Windows.Automation.InvokePattern]$pattern).Invoke()
    return $true
  }
  return $false
}

function Get-NowPlaying($window) {
  $elements = $window.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Automation]::ControlViewCondition)
  foreach ($element in $elements) {
    if ($element.Current.Name -like 'Now playing:*') { return $element.Current.Name }
  }
  return $window.Current.Name
}

$action = '${action}'
$window = Get-SpotifyWindow
if ($null -eq $window) {
  [PSCustomObject]@{ playback_verified = $false; playback_state = 'window-not-found'; playback_method = 'uia'; now_playing = '' } | ConvertTo-Json -Compress
  return
}

$playNames = @('Play', 'Oynat')
$pauseNames = @('Pause', 'Duraklat')
$target = $null
if ($action -eq 'play') {
  if ($null -ne (Find-PlayerButton $window $pauseNames)) {
    [PSCustomObject]@{ playback_verified = $true; playback_state = 'playing'; playback_method = 'uia-observed'; now_playing = Get-NowPlaying $window } | ConvertTo-Json -Compress
    return
  }
  $target = Find-PlayerButton $window $playNames
} elseif ($action -eq 'pause') {
  if ($null -ne (Find-PlayerButton $window $playNames)) {
    [PSCustomObject]@{ playback_verified = $true; playback_state = 'paused'; playback_method = 'uia-observed'; now_playing = Get-NowPlaying $window } | ConvertTo-Json -Compress
    return
  }
  $target = Find-PlayerButton $window $pauseNames
} elseif ($action -eq 'next') {
  $target = Find-PlayerButton $window @('Next', 'Next track', 'Sonraki', 'Sonraki parça')
} elseif ($action -eq 'previous') {
  $target = Find-PlayerButton $window @('Previous', 'Previous track', 'Önceki', 'Önceki parça')
}

$invoked = Invoke-Button $target
Start-Sleep -Milliseconds 800
$window = Get-SpotifyWindow
if ($null -eq $window) {
  [PSCustomObject]@{ playback_verified = $false; playback_state = 'window-lost'; playback_method = 'uia'; now_playing = '' } | ConvertTo-Json -Compress
  return
}

$verified = $false
$state = 'unverified'
if ($action -eq 'pause') {
  $verified = $null -ne (Find-PlayerButton $window $playNames)
  if ($verified) { $state = 'paused' }
} elseif ($action -eq 'play') {
  $verified = $null -ne (Find-PlayerButton $window $pauseNames)
  if ($verified) { $state = 'playing' }
} else {
  $verified = $invoked
  if ($verified) { $state = 'playing' }
}
[PSCustomObject]@{ playback_verified = $verified; playback_state = $state; playback_method = 'uia-invoke'; now_playing = Get-NowPlaying $window } | ConvertTo-Json -Compress
`;
}

/** Yalnızca doğrulanabilir Spotify içerik URL'lerini yerel URI'ye dönüştürür. */
export function spotifyDeepLink(query: string, url = '', kind = ''): string {
  if (kind === 'liked' || /beğenilen|begenilen|beğendikler|begendikler|liked songs|\bliked\b/i.test(query)) {
    return 'spotify:collection:tracks';
  }
  try {
    const parsed = new URL(url);
    if (parsed.hostname === 'open.spotify.com' || parsed.hostname === 'www.open.spotify.com') {
      if (/^\/collection\/tracks\/?$/.test(parsed.pathname)) {
        return 'spotify:collection:tracks';
      }
      const match = parsed.pathname.match(
        /^\/(track|album|playlist|artist)\/([A-Za-z0-9]{22})\/?$/,
      );
      if (match) return `spotify:${match[1]}:${match[2]}`;
    }
  } catch {
  }
  return `spotify:search:${encodeURIComponent(query.slice(0, 300))}`;
}

/** Spotify'da hedef açıldıktan sonra gerçek oynatma durumunu UI Automation ile doğrular. */
async function verifySpotifyPlayback(): Promise<Record<string, unknown>> {
  const script = `
Start-Sleep -Milliseconds 2500
Add-Type -AssemblyName UIAutomationClient

function Get-SpotifyWindow {
  $spotifyPids = @(Get-Process -Name Spotify -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id)
  if ($spotifyPids.Count -eq 0) { return $null }
  $root = [System.Windows.Automation.AutomationElement]::RootElement
  $windows = $root.FindAll([System.Windows.Automation.TreeScope]::Children, [System.Windows.Automation.Condition]::TrueCondition)
  foreach ($window in $windows) {
    if ($spotifyPids -contains $window.Current.ProcessId) { return $window }
  }
  return $null
}

function Find-PlayerButton($window, $names) {
  $elements = $window.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Automation]::ControlViewCondition)
  foreach ($element in $elements) {
    $current = $element.Current
    if ($current.ControlType -eq [System.Windows.Automation.ControlType]::Button -and
        $current.IsEnabled -and -not $current.IsOffscreen -and $names -contains $current.Name) {
      return $element
    }
  }
  return $null
}

function Get-NowPlaying($window) {
  $elements = $window.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Automation]::ControlViewCondition)
  foreach ($element in $elements) {
    if ($element.Current.Name -like 'Now playing:*') { return $element.Current.Name }
  }
  return $window.Current.Name
}

$window = Get-SpotifyWindow
if ($null -eq $window) {
  [PSCustomObject]@{ playback_requested = $true; playback_verified = $false; playback_state = 'window-not-found'; playback_method = 'uia'; now_playing = '' } | ConvertTo-Json -Compress
  return
}

$pause = Find-PlayerButton $window @('Pause', 'Duraklat')
if ($null -ne $pause) {
  [PSCustomObject]@{ playback_requested = $true; playback_verified = $true; playback_state = 'playing'; playback_method = 'uia-observed'; now_playing = Get-NowPlaying $window } | ConvertTo-Json -Compress
  return
}

$play = Find-PlayerButton $window @('Play', 'Oynat')
if ($null -ne $play) {
  $pattern = $null
  if ($play.TryGetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern, [ref]$pattern)) {
    ([System.Windows.Automation.InvokePattern]$pattern).Invoke()
    Start-Sleep -Milliseconds 700
    $window = Get-SpotifyWindow
    if ($null -ne $window -and $null -ne (Find-PlayerButton $window @('Pause', 'Duraklat'))) {
      [PSCustomObject]@{ playback_requested = $true; playback_verified = $true; playback_state = 'playing'; playback_method = 'uia-invoke'; now_playing = Get-NowPlaying $window } | ConvertTo-Json -Compress
      return
    }
  }
}

[PSCustomObject]@{ playback_requested = $true; playback_verified = $false; playback_state = 'unverified'; playback_method = 'uia'; now_playing = Get-NowPlaying $window } | ConvertTo-Json -Compress
`;
  const result = await runPowerShell(script, { timeoutMs: 15_000, maxBuffer: 1024 * 1024 });
  if (result.code !== 0 || !result.stdout.trim()) {
    return {
      playback_requested: true,
      playback_verified: false,
      playback_state: 'verification-failed',
      playback_method: 'uia',
    };
  }
  try {
    return JSON.parse(result.stdout.trim()) as Record<string, unknown>;
  } catch {
    return {
      playback_requested: true,
      playback_verified: false,
      playback_state: 'invalid-verification-result',
      playback_method: 'uia',
    };
  }
}

let installedAppsCache: { expiresAt: number; apps: InstalledApplication[] } | null = null;

/** Modelin uygulama adını tahmin etmesi yerine Windows'un gerçek listesini döndürür. */
export async function listInstalledApplicationsTool(
  args: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  const query = sanitizeSingleLine(args.query ?? '', 200);
  const apps = await listInstalledApplications();
  const selected = query
    ? rankInstalledApplications(query, apps).map((match) => match.app)
    : apps.sort((left, right) => left.name.localeCompare(right.name, 'tr')).slice(0, 300);
  return { count: selected.length, applications: selected };
}

/** Açık uygulamanın salt-okunur Windows UI Automation kontrol ağacını tarar. */
export async function inspectApplication(
  args: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  const name = sanitizeSingleLine(args.name, 200);
  const limit = Math.max(1, Math.min(Number(args.limit ?? 160) || 160, 300));
  if (!name) {
    throw new Error(
      hostText(
        'Taranacak açık uygulamanın adı gerekli.',
        'The name of the open application to inspect is required.',
      ),
    );
  }
  const literal = name.replace(/'/g, "''");
  const missingWindow = hostText(
    'Açık uygulama penceresi bulunamadı.',
    'No open application window was found.',
  ).replace(/'/g, "''");
  const script = `
Add-Type -AssemblyName UIAutomationClient
$root = [System.Windows.Automation.AutomationElement]::RootElement
$windows = $root.FindAll([System.Windows.Automation.TreeScope]::Children, [System.Windows.Automation.Condition]::TrueCondition)
$target = $null
foreach ($window in $windows) {
  if ($window.Current.Name -like '*${literal}*') { $target = $window; break }
}
if ($null -eq $target) { throw '${missingWindow}' }
$elements = $target.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Automation]::ControlViewCondition)
$controls = @()
for ($index = 0; $index -lt [Math]::Min($elements.Count, ${limit}); $index++) {
  $item = $elements.Item($index).Current
  $rect = $item.BoundingRectangle
  $controls += [PSCustomObject]@{
    name = $item.Name
    automation_id = $item.AutomationId
    class_name = $item.ClassName
    control_type = $item.ControlType.ProgrammaticName.Replace('ControlType.', '')
    enabled = $item.IsEnabled
    offscreen = $item.IsOffscreen
    bounds = [PSCustomObject]@{ x = [int]$rect.X; y = [int]$rect.Y; width = [int]$rect.Width; height = [int]$rect.Height }
  }
}
[PSCustomObject]@{ window = $target.Current.Name; total = $elements.Count; controls = $controls } | ConvertTo-Json -Depth 5 -Compress
`;
  const result = await runPowerShell(script, { timeoutMs: 20_000, maxBuffer: 4 * 1024 * 1024 });
  if (result.code !== 0) {
    throw new Error(
      result.stderr.trim() ||
        hostText(`'${name}' arayüzü taranamadı.`, `'${name}' interface could not be inspected.`),
    );
  }
  try {
    return JSON.parse(result.stdout.trim()) as Record<string, unknown>;
  } catch {
    throw new Error(
      hostText(
        `'${name}' arayüz tarama sonucu çözümlenemedi.`,
        `'${name}' interface scan result could not be parsed.`,
      ),
    );
  }
}

/** `open_application` aracı. */
export async function openApplication(
  args: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  const rawName = sanitizeSingleLine(args.name, 260);
  const extraArgs = sanitizeSingleLine(args.args ?? '', 300);
  if (!rawName) throw new Error(hostText('Uygulama adı gerekli.', 'An application name is required.'));

  const alias = rawName.toLowerCase().replace(/\s+/g, '_');
  const entry = APPLICATION_ALLOWLIST[alias];

  if (entry) {
    if (!entry.command) {
      throw new Error(
        hostText(
          `'${rawName}' güvenlik nedeniyle açılamaz.`,
          `'${rawName}' cannot be opened for security reasons.`,
        ),
      );
    }
    if (entry.command.endsWith(':')) {
      launchViaExplorer(entry.command);
      return { opened: true, target: entry.command, method: 'protocol' };
    }
    const argv = [...entry.args, ...(extraArgs ? extraArgs.split(/\s+/) : [])];
    const located = await run('where.exe', [entry.command], { timeoutMs: 5000 });
    if (located.code === 0) {
      const pid = launchDetached(entry.command, argv);
      return { opened: true, target: entry.command, pid: pid ?? null, method: 'direct' };
    }
  }

  const extension = path.extname(rawName).toLowerCase();
  if (['.exe', '.lnk', '.bat', '.cmd'].includes(extension)) {
    const resolved = ensurePathAllowed(rawName);
    if (!existsSync(resolved)) {
      throw new Error(hostText(`'${rawName}' bulunamadı.`, `'${rawName}' was not found.`));
    }
    if (['.bat', '.cmd'].includes(extension)) {
      throw new Error(
        hostText(
          'Toplu iş dosyaları (.bat/.cmd) güvenlik nedeniyle çalıştırılamaz.',
          'Batch files (.bat/.cmd) cannot be run for security reasons.',
        ),
      );
    }
    const error = await shell.openPath(resolved);
    if (error) throw new Error(error);
    return { opened: true, target: resolved, method: 'shell' };
  }

  const matches = rankInstalledApplications(rawName, await listInstalledApplications());
  if (matches.length === 1 || (matches[0] && matches[0].score > (matches[1]?.score ?? 0))) {
    const selected = matches[0]!.app;
    if (path.isAbsolute(selected.appId) && existsSync(selected.appId)) {
      const error = await shell.openPath(selected.appId);
      if (error) throw new Error(error);
      return {
        opened: true,
        target: selected.name,
        app_id: selected.appId,
        method: 'start-app-path',
      };
    }
    launchViaExplorer(`shell:AppsFolder\\${selected.appId}`);
    return { opened: true, target: selected.name, app_id: selected.appId, method: 'start-app-id' };
  }
  if (matches.length > 1) {
    throw new Error(
      hostText(
        `'${rawName}' birden fazla uygulamayla eşleşiyor: ${matches
          .slice(0, 5)
          .map((match) => match.app.name)
          .join(', ')}. Daha açık bir ad söyleyin.`,
        `'${rawName}' matches more than one application: ${matches
          .slice(0, 5)
          .map((match) => match.app.name)
          .join(', ')}. Use a more specific name.`,
      ),
    );
  }

  throw new Error(
    hostText(
      `'${rawName}' Windows Başlat menüsündeki kurulu uygulamalarda bulunamadı.`,
      `'${rawName}' was not found among installed Start menu applications.`,
    ),
  );
}

/** Windows'un güvenilir Başlat menüsü uygulama listesini kısa süreli önbelleğe alır. */
async function listInstalledApplications(): Promise<InstalledApplication[]> {
  if (installedAppsCache && installedAppsCache.expiresAt > Date.now()) {
    return installedAppsCache.apps;
  }
  const result = await runPowerShell(
    'Get-StartApps | Select-Object Name,AppID | ConvertTo-Json -Compress',
    { timeoutMs: 15_000, maxBuffer: 2 * 1024 * 1024 },
  );
  if (result.code !== 0 || !result.stdout.trim()) return [];

  try {
    const parsed = JSON.parse(result.stdout.trim()) as
      { Name?: unknown; AppID?: unknown } | Array<{ Name?: unknown; AppID?: unknown }>;
    const rows = Array.isArray(parsed) ? parsed : [parsed];
    const apps = rows.flatMap((row) => {
      const name = sanitizeSingleLine(row.Name, 200);
      const appId = sanitizeSingleLine(row.AppID, 1000);
      return name && appId ? [{ name, appId }] : [];
    });
    installedAppsCache = { expiresAt: Date.now() + 5 * 60_000, apps };
    return apps;
  } catch {
    return [];
  }
}

/** Kullanıcının söylediği görünen adı kurulu uygulama listesiyle eşleştirir. */
export function rankInstalledApplications(
  query: string,
  apps: InstalledApplication[],
): Array<{ app: InstalledApplication; score: number }> {
  const wanted = normalizeAppName(query);
  if (!wanted) return [];
  const words = wanted.split(' ').filter(Boolean);

  return apps
    .map((app) => {
      const name = normalizeAppName(app.name);
      let score = 0;
      if (name === wanted) score = 100;
      else if (name.startsWith(`${wanted} `)) score = 90;
      else if (words.every((word) => name.split(' ').includes(word))) score = 82;
      else if (name.includes(wanted)) score = 72;
      else if (editDistance(name, wanted) <= Math.max(1, Math.floor(wanted.length / 5))) score = 60;
      return { app, score };
    })
    .filter((match) => match.score > 0)
    .sort((a, b) => b.score - a.score || a.app.name.localeCompare(b.app.name, 'tr'))
    .slice(0, 8);
}

function normalizeAppName(value: string): string {
  return value
    .toLocaleLowerCase('tr-TR')
    .replace(/[çÇ]/g, 'c')
    .replace(/[ğĞ]/g, 'g')
    .replace(/[ıİ]/g, 'i')
    .replace(/[öÖ]/g, 'o')
    .replace(/[şŞ]/g, 's')
    .replace(/[üÜ]/g, 'u')
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/\b(uygulamasi|uygulama|programi|program)\b/g, ' ')
    .replace(/[^a-z0-9]+/g, ' ')
    .trim();
}

function editDistance(left: string, right: string): number {
  const previous = Array.from({ length: right.length + 1 }, (_, index) => index);
  for (let i = 1; i <= left.length; i += 1) {
    const current = [i];
    for (let j = 1; j <= right.length; j += 1) {
      current[j] = Math.min(
        current[j - 1]! + 1,
        previous[j]! + 1,
        previous[j - 1]! + (left[i - 1] === right[j - 1] ? 0 : 1),
      );
    }
    previous.splice(0, previous.length, ...current);
  }
  return previous[right.length]!;
}

/** `close_application` aracı — nazik kapatma (WM_CLOSE). */
export async function closeApplication(
  args: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  const raw = sanitizeSingleLine(args.name, 100).toLowerCase();
  if (!raw) throw new Error(hostText('Program adı gerekli.', 'A program name is required.'));

  const base = raw.replace(/\.exe$/i, '');
  if (!CLOSABLE_APPS.has(base)) {
    throw new Error(
      hostText(
        `'${raw}' kapatılabilir program listesinde değil. İzinliler: ${[...CLOSABLE_APPS].join(', ')}`,
        `'${raw}' is not on the closable program list. Allowed: ${[...CLOSABLE_APPS].join(', ')}`,
      ),
    );
  }

  const result = await run('taskkill.exe', ['/IM', `${base}.exe`], { timeoutMs: 15_000 });
  const output = `${result.stdout}${result.stderr}`.trim();

  if (result.code !== 0 && /not found|bulunamadı/i.test(output)) {
    return {
      closed: false,
      name: base,
      detail: hostText('Program zaten çalışmıyor.', 'The program is not running.'),
    };
  }
  return { closed: result.code === 0, name: base, output: output.slice(0, 500) };
}

/** `open_vscode` aracı. */
export async function openVSCode(args: Record<string, unknown>): Promise<Record<string, unknown>> {
  const rawPath = sanitizeSingleLine(args.path ?? '', 1000);
  const argv: string[] = [];

  if (rawPath) {
    const resolved = ensurePathAllowed(rawPath);
    if (!existsSync(resolved)) throw new Error(hostText(`'${rawPath}' bulunamadı.`, `'${rawPath}' was not found.`));
    argv.push(resolved);
  }

  for (const candidate of ['code.cmd', 'code']) {
    try {
      launchDetached(candidate, argv);
      return { opened: true, path: argv[0] ?? null, via: candidate };
    } catch {
      continue;
    }
  }
  throw new Error(
    hostText(
      "VS Code bulunamadı. 'code' komutunun PATH'e eklendiğinden emin olun " +
        '(VS Code → Ctrl+Shift+P → "Shell Command: Install \'code\' command in PATH").',
      "VS Code was not found. Make sure the 'code' command is on PATH " +
        '(VS Code → Ctrl+Shift+P → "Shell Command: Install \'code\' command in PATH").',
    ),
  );
}

/** `open_folder` aracı. */
export async function openFolder(args: Record<string, unknown>): Promise<Record<string, unknown>> {
  const raw = sanitizeSingleLine(args.path, 1000);
  if (!raw) throw new Error(hostText('Klasör yolu gerekli.', 'A folder path is required.'));
  const target = resolveSpecialFolder(raw) ?? raw;
  const resolved = ensurePathAllowed(target);
  if (!existsSync(resolved)) throw new Error(hostText(`'${raw}' bulunamadı.`, `'${raw}' was not found.`));

  const error = await shell.openPath(resolved);
  if (error) throw new Error(error);
  return { opened: true, path: resolved };
}

/** Geri Dönüşüm Kutusu — sabit explorer hedefi, serbest kabuk yok. */
export async function openRecycleBin(): Promise<Record<string, unknown>> {
  const result = await run('explorer.exe', ['shell:RecycleBinFolder'], { timeoutMs: 8_000 });
  if (result.code !== 0 && result.stderr.trim()) {
    throw new Error(
      hostText(
        `Geri Dönüşüm Kutusu açılamadı: ${result.stderr.trim().slice(0, 200)}`,
        `Could not open Recycle Bin: ${result.stderr.trim().slice(0, 200)}`,
      ),
    );
  }
  return { opened: true, target: 'recycle_bin' };
}

/** `get_recycle_bin_info` — sayı/boyut; boşaltmaz. */
export async function getRecycleBinInfo(): Promise<Record<string, unknown>> {
  const result = await runPowerShell(
    `$shell = New-Object -ComObject Shell.Application
$bin = $shell.NameSpace(10)
if (-not $bin) { '{"count":0,"bytes":0}'; exit 0 }
$items = @($bin.Items())
$sum = 0
foreach ($item in $items) { $sum += [int64]$item.Size }
[PSCustomObject]@{ count = $items.Count; bytes = $sum } | ConvertTo-Json -Compress`,
    { timeoutMs: 12_000 },
  );
  const raw = result.stdout.trim();
  try {
    const parsed = JSON.parse(raw) as { count?: number; bytes?: number };
    const count = Number(parsed.count) || 0;
    const bytes = Number(parsed.bytes) || 0;
    return { count, bytes, mb: Math.round((bytes / 1_000_000) * 10) / 10, emptied: false };
  } catch {
    return { count: 0, bytes: 0, mb: 0, emptied: false };
  }
}

/** `resolve_application_path` — allowlist komut yolu; açmaz. */
export async function resolveApplicationPath(
  args: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  const alias = sanitizeSingleLine(args.name, 40).toLocaleLowerCase('tr-TR');
  const entry = APPLICATION_ALLOWLIST[alias];
  if (!entry?.command) {
    throw new Error(hostText(`'${alias}' için yol sorgusu yok.`, `'${alias}' has no path lookup.`));
  }
  if (entry.command.endsWith(':')) {
    return { name: alias, path: entry.command, method: 'protocol', found: true };
  }
  const located = await run('where.exe', [entry.command], { timeoutMs: 5_000 });
  const first = located.stdout
    .split(/\r?\n/)
    .map((line) => line.trim())
    .find(Boolean);
  if (!first) return { name: alias, path: '', found: false };
  return { name: alias, path: sanitizeSingleLine(first, 500), found: true };
}

const WINDOWS_SETTINGS_PAGES: Record<string, string> = {
  bluetooth: 'ms-settings:bluetooth',
  wifi: 'ms-settings:network-wifi',
  display: 'ms-settings:display',
  sound: 'ms-settings:sound',
  update: 'ms-settings:windowsupdate',
  about: 'ms-settings:about',
  datetime: 'ms-settings:dateandtime',
  apps: 'ms-settings:appsfeatures',
};

/** `open_windows_settings` — allowlist `ms-settings:` sayfası; serbest kabuk yok. */
export async function openWindowsSettings(
  args: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  const page = sanitizeSingleLine(args.page, 40).toLocaleLowerCase('tr-TR');
  const uri = WINDOWS_SETTINGS_PAGES[page];
  if (!uri) {
    throw new Error(
      hostText(`'${page}' izinli bir Ayarlar sayfası değil.`, `'${page}' is not an allowed Settings page.`),
    );
  }
  await shell.openExternal(uri);
  return { opened: true, page, uri };
}
