/** Sistem bilgisi ve donanım araçları. */

import { app, clipboard, desktopCapturer, powerMonitor, screen } from 'electron';
import { lookup } from 'node:dns/promises';
import { createSocket } from 'node:dgram';
import { existsSync } from 'node:fs';
import { writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';

import { dateLocale } from '../../src/lib/messages';
import { hostLang, hostText } from '../host-i18n';
import { sanitizeSingleLine } from '../security';
import { notifyDesktopImmediate } from '../windows-desktop';
import { classifyLanAddress, rankLanCandidates } from './lan';
import { run, runPowerShell } from './process';

let previousCpuInfo = os.cpus();
let previousSampleTime = Date.now();

/**
 * CPU kullanım yüzdesini iki örnekleme arasındaki farktan hesaplar.
 * İlk çağrıda önceki örnek yoksa kısa bir bekleme ile ikinci örnek alınır.
 */
export async function cpuPercent(): Promise<number> {
  const elapsed = Date.now() - previousSampleTime;
  if (elapsed < 200) {
    await new Promise((resolve) => setTimeout(resolve, 220 - elapsed));
  }

  const current = os.cpus();
  let idleDelta = 0;
  let totalDelta = 0;

  for (let i = 0; i < current.length; i += 1) {
    const now = current[i]!.times;
    const before = previousCpuInfo[i]?.times ?? now;
    const nowTotal = now.user + now.nice + now.sys + now.idle + now.irq;
    const beforeTotal = before.user + before.nice + before.sys + before.idle + before.irq;
    idleDelta += now.idle - before.idle;
    totalDelta += nowTotal - beforeTotal;
  }

  previousCpuInfo = current;
  previousSampleTime = Date.now();

  if (totalDelta <= 0) return 0;
  return Math.round((1 - idleDelta / totalDelta) * 1000) / 10;
}

/** `get_cpu_usage` aracı. */
export async function getCpuUsage(): Promise<Record<string, unknown>> {
  const cpus = os.cpus();
  return {
    percent: await cpuPercent(),
    cores: cpus.length,
    model: cpus[0]?.model?.trim() ?? hostText('Bilinmiyor', 'Unknown'),
    speed_mhz: cpus[0]?.speed ?? 0,
    load_average: os.loadavg(),
  };
}

/** `get_ram_usage` aracı. */
export function getRamUsage(): Record<string, unknown> {
  const total = os.totalmem();
  const free = os.freemem();
  const used = total - free;
  return {
    total_mb: Math.round(total / 1024 / 1024),
    used_mb: Math.round(used / 1024 / 1024),
    free_mb: Math.round(free / 1024 / 1024),
    percent: Math.round((used / total) * 1000) / 10,
  };
}

export interface GpuSnapshot {
  name: string;
  vram_total_mb: number;
  vram_used_mb: number;
  vram_percent: number;
  utilization_percent: number;
  temperature_c: number | null;
  driver_version: string | null;
  available: boolean;
}

/** `nvidia-smi` üzerinden GPU bilgisi okur. */
export async function getGpuUsage(): Promise<GpuSnapshot> {
  const empty: GpuSnapshot = {
    name: hostText('NVIDIA GPU bulunamadı', 'NVIDIA GPU not found'),
    vram_total_mb: 0,
    vram_used_mb: 0,
    vram_percent: 0,
    utilization_percent: 0,
    temperature_c: null,
    driver_version: null,
    available: false,
  };

  try {
    const result = await run(
      'nvidia-smi',
      [
        '--query-gpu=name,memory.total,memory.used,utilization.gpu,temperature.gpu,driver_version',
        '--format=csv,noheader,nounits',
      ],
      { timeoutMs: 8000 },
    );
    if (result.code !== 0 || !result.stdout.trim()) return empty;

    const [line] = result.stdout.trim().split('\n');
    const parts = line!.split(',').map((p) => p.trim());
    if (parts.length < 6) return empty;

    const total = Number(parts[1]) || 0;
    const used = Number(parts[2]) || 0;

    return {
      name: parts[0] || 'NVIDIA GPU',
      vram_total_mb: total,
      vram_used_mb: used,
      vram_percent: total ? Math.round((used / total) * 1000) / 10 : 0,
      utilization_percent: Number(parts[3]) || 0,
      temperature_c: Number(parts[4]) || null,
      driver_version: parts[5] || null,
      available: true,
    };
  } catch {
    return empty;
  }
}

export interface DiskSnapshot {
  mount: string;
  total_gb: number;
  used_gb: number;
  percent: number;
}

/** `get_disk_usage` aracı — WMIC yerine PowerShell CIM kullanır. */
export async function getDiskUsage(): Promise<{ disks: DiskSnapshot[] }> {
  try {
    const result = await runPowerShell(
      'Get-CimInstance Win32_LogicalDisk -Filter "DriveType=3" | ' +
        'Select-Object DeviceID,Size,FreeSpace | ConvertTo-Json -Compress',
      { timeoutMs: 15_000 },
    );
    const raw = result.stdout.trim();
    if (!raw) return { disks: [] };

    const parsed = JSON.parse(raw) as
      | { DeviceID: string; Size: number; FreeSpace: number }
      | { DeviceID: string; Size: number; FreeSpace: number }[];
    const rows = Array.isArray(parsed) ? parsed : [parsed];

    return {
      disks: rows
        .filter((r) => r && Number(r.Size) > 0)
        .map((r) => {
          const total = Number(r.Size);
          const free = Number(r.FreeSpace) || 0;
          const used = total - free;
          return {
            mount: r.DeviceID,
            total_gb: Math.round((total / 1e9) * 10) / 10,
            used_gb: Math.round((used / 1e9) * 10) / 10,
            percent: Math.round((used / total) * 1000) / 10,
          };
        }),
    };
  } catch {
    return { disks: [] };
  }
}

/** `list_processes` aracı. */
export async function listProcesses(args: Record<string, unknown>): Promise<
  Record<string, unknown>
> {
  const limit = Math.max(1, Math.min(Number(args.limit ?? 15) || 15, 50));
  const result = await runPowerShell(
    `Get-Process | Sort-Object -Property WorkingSet64 -Descending | Select-Object -First ${limit} ` +
      'Id,ProcessName,@{N="MemoryMB";E={[math]::Round($_.WorkingSet64/1MB,1)}},' +
      '@{N="CpuSeconds";E={if($_.CPU){[math]::Round($_.CPU,1)}else{0}}} | ConvertTo-Json -Compress',
    { timeoutMs: 20_000 },
  );

  const raw = result.stdout.trim();
  if (!raw) return { processes: [] };

  try {
    const parsed = JSON.parse(raw);
    const rows = Array.isArray(parsed) ? parsed : [parsed];
    return {
      count: rows.length,
      processes: rows.map((r: Record<string, unknown>) => ({
        pid: Number(r.Id),
        name: String(r.ProcessName ?? ''),
        memory_mb: Number(r.MemoryMB ?? 0),
        cpu_seconds: Number(r.CpuSeconds ?? 0),
      })),
    };
  } catch {
    return {
      processes: [],
      error: hostText('İşlem listesi ayrıştırılamadı.', 'Could not parse the process list.'),
    };
  }
}

/** `kill_process` aracı. */
export async function killProcess(args: Record<string, unknown>): Promise<
  Record<string, unknown>
> {
  const pid = Number(args.pid);
  if (!Number.isInteger(pid) || pid <= 0) {
    throw new Error(hostText('Geçerli bir PID gerekli.', 'A valid PID is required.'));
  }
  if (pid === process.pid || pid === process.ppid) {
    throw new Error(hostText('Uryx kendi sürecini sonlandıramaz.', 'Uryx cannot terminate its own process.'));
  }
  if (pid <= 4) {
    throw new Error(hostText('Sistem süreçleri sonlandırılamaz.', 'System processes cannot be terminated.'));
  }

  const result = await run('taskkill.exe', ['/PID', String(pid), '/F'], { timeoutMs: 15_000 });
  if (result.code !== 0) {
    throw new Error(
      hostText(
        `İşlem sonlandırılamadı: ${(result.stderr || result.stdout).trim().slice(0, 300)}`,
        `Could not terminate the process: ${(result.stderr || result.stdout).trim().slice(0, 300)}`,
      ),
    );
  }
  return { killed: true, pid };
}

/** Allowlist takma adı → Windows süreç adı (serbest kabuk yok). */
const PROCESS_QUERY_NAMES: Record<string, string[]> = {
  chrome: ['chrome'],
  edge: ['msedge'],
  firefox: ['firefox'],
  notepad: ['notepad'],
  calc: ['Calculator', 'CalculatorApp', 'calc'],
  vscode: ['Code'],
  code: ['Code'],
  spotify: ['Spotify'],
  terminal: ['WindowsTerminal', 'wt'],
  explorer: ['explorer'],
  paint: ['mspaint'],
  cmd: ['cmd'],
  powershell: ['powershell', 'pwsh'],
  task_manager: ['Taskmgr'],
  gorev_yoneticisi: ['Taskmgr'],
  snippingtool: ['SnippingTool', 'ScreenClippingHost'],
  wordpad: ['wordpad', 'write'],
  settings: ['SystemSettings'],
  ayarlar: ['SystemSettings'],
};

/** `is_process_running` — allowlist adı; liste/sonlandırma yok. */
export async function isProcessRunning(
  args: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  const alias = sanitizeSingleLine(args.name, 40).toLocaleLowerCase('tr-TR');
  const names = PROCESS_QUERY_NAMES[alias];
  if (!names?.length) {
    throw new Error(
      hostText(`'${alias}' için süreç sorgusu yok.`, `No process query for '${alias}'.`),
    );
  }
  const quoted = names.map((name) => `'${name.replace(/'/g, '')}'`).join(',');
  const result = await runPowerShell(
    `$names = @(${quoted}); ` +
      '$rows = @(Get-Process -Name $names -ErrorAction SilentlyContinue); ' +
      '[PSCustomObject]@{ count = $rows.Count; name = $rows[0].ProcessName } | ConvertTo-Json -Compress',
    { timeoutMs: 8_000 },
  );
  const raw = result.stdout.trim();
  try {
    const parsed = JSON.parse(raw) as { count?: number; name?: string };
    const count = Number(parsed.count) || 0;
    return {
      running: count > 0,
      name: sanitizeSingleLine(parsed.name || names[0] || alias, 80),
      alias,
      count,
    };
  } catch {
    return { running: false, name: names[0], alias, count: 0 };
  }
}

const AUDIO_CS = `
using System.Runtime.InteropServices;
[Guid("5CDF2C82-841E-4546-9722-0CF74078229A"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IAudioEndpointVolume {
  int _0(); int _1(); int _2(); int _3();
  int SetMasterVolumeLevelScalar(float fLevel, System.Guid pguidEventContext);
  int _5();
  int GetMasterVolumeLevelScalar(out float pfLevel);
}
[Guid("D666063F-1587-4E43-81F1-B948E807363F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IMMDevice { int Activate(ref System.Guid id, int ctx, System.IntPtr p, out IAudioEndpointVolume aev); }
[Guid("A95664D2-9614-4F35-A746-DE8DB63617E6"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IMMDeviceEnumerator { int _0(); int GetDefaultAudioEndpoint(int dataFlow, int role, out IMMDevice ep); }
[ComImport, Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")] class MMDeviceEnumeratorComObject { }
public class UryxAudio {
  public static void SetVolume(float level) {
    var enumerator = (IMMDeviceEnumerator)(new MMDeviceEnumeratorComObject());
    IMMDevice device; enumerator.GetDefaultAudioEndpoint(0, 1, out device);
    var guid = typeof(IAudioEndpointVolume).GUID;
    IAudioEndpointVolume volume; device.Activate(ref guid, 23, System.IntPtr.Zero, out volume);
    volume.SetMasterVolumeLevelScalar(level, System.Guid.Empty);
  }
  public static float GetVolume() {
    var enumerator = (IMMDeviceEnumerator)(new MMDeviceEnumeratorComObject());
    IMMDevice device; enumerator.GetDefaultAudioEndpoint(0, 1, out device);
    var guid = typeof(IAudioEndpointVolume).GUID;
    IAudioEndpointVolume volume; device.Activate(ref guid, 23, System.IntPtr.Zero, out volume);
    float level; volume.GetMasterVolumeLevelScalar(out level); return level;
  }
}
`;

async function readMasterVolume(): Promise<number> {
  const script = `
$src = @"
${AUDIO_CS}
"@
Add-Type -TypeDefinition $src -Language CSharp | Out-Null
[math]::Round([UryxAudio]::GetVolume() * 100)
`.trim();
  const result = await run(
    'powershell.exe',
    ['-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-Command', script],
    { timeoutMs: 30_000 },
  );
  if (result.code !== 0) {
    throw new Error(
      hostText(
        `Ses seviyesi okunamadı: ${result.stderr.trim().slice(0, 300)}`,
        `Could not read the volume level: ${result.stderr.trim().slice(0, 300)}`,
      ),
    );
  }
  const applied = Number(result.stdout.trim().split('\n').pop());
  if (!Number.isFinite(applied)) {
    throw new Error(hostText('Ses seviyesi okunamadı.', 'Could not read the volume level.'));
  }
  return applied;
}

export async function getVolume(): Promise<Record<string, unknown>> {
  const volume = await readMasterVolume();
  return { volume };
}

/**
 * `set_volume` aracı.
 *
 * Windows ana ses seviyesini IAudioEndpointVolume COM arayüzü üzerinden ayarlar.
 * Ek bağımlılık (nircmd vb.) gerektirmez.
 */
export async function setVolume(args: Record<string, unknown>): Promise<Record<string, unknown>> {
  const level = Number(args.level);
  if (!Number.isFinite(level) || level < 0 || level > 100) {
    throw new Error(
      hostText('Ses seviyesi 0 ile 100 arasında olmalı.', 'Volume level must be between 0 and 100.'),
    );
  }

  const script = `
$src = @"
${AUDIO_CS}
"@
Add-Type -TypeDefinition $src -Language CSharp | Out-Null
[UryxAudio]::SetVolume(${(level / 100).toFixed(4)})
[math]::Round([UryxAudio]::GetVolume() * 100)
`.trim();

  const result = await run(
    'powershell.exe',
    ['-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-Command', script],
    { timeoutMs: 30_000 },
  );

  if (result.code !== 0) {
    throw new Error(
      hostText(
        `Ses seviyesi ayarlanamadı: ${result.stderr.trim().slice(0, 300)}`,
        `Could not set the volume level: ${result.stderr.trim().slice(0, 300)}`,
      ),
    );
  }
  const applied = Number(result.stdout.trim().split('\n').pop());
  return { volume: Number.isFinite(applied) ? applied : level, requested: level };
}

/** `clipboard_read` aracı. */
export function clipboardRead(): Record<string, unknown> {
  const text = clipboard.readText();
  return {
    text: text.slice(0, 20_000),
    length: text.length,
    truncated: text.length > 20_000,
    empty: text.length === 0,
  };
}

/** `clipboard_write` aracı. */
export function clipboardWrite(args: Record<string, unknown>): Record<string, unknown> {
  const text = String(args.text ?? '');
  if (!text) throw new Error(hostText('Panoya yazılacak metin boş olamaz.', 'Clipboard text cannot be empty.'));
  if (text.length > 100_000) {
    throw new Error(
      hostText('Metin çok uzun (sınır: 100.000 karakter).', 'Text is too long (limit: 100,000 characters).'),
    );
  }
  clipboard.writeText(text);
  return { written: true, length: text.length };
}

/** `clipboard_clear` aracı — panoyu boşaltır, kabuk yok. */
export function clipboardClear(): Record<string, unknown> {
  clipboard.writeText('');
  return { cleared: true, empty: true };
}

/** `get_power_status` — Electron powerMonitor; fare/klavye yok. */
export function getPowerStatus(): Record<string, unknown> {
  const onBattery =
    typeof powerMonitor?.isOnBatteryPower === 'function' ? powerMonitor.isOnBatteryPower() : false;
  return { on_battery: onBattery, ac: !onBattery };
}

/** `get_uptime` — OS açık kalma süresi; kabuk yok. */
export function getUptime(): Record<string, unknown> {
  const seconds = Math.max(0, Math.floor(os.uptime()));
  return {
    uptime_seconds: seconds,
    uptime_hours: Math.round((seconds / 3600) * 10) / 10,
  };
}

/** `get_computer_info` — ad / kullanıcı / sürüm; kabuk yok. */
export function getComputerInfo(): Record<string, unknown> {
  const user = os.userInfo();
  return {
    hostname: sanitizeSingleLine(os.hostname(), 80),
    username: sanitizeSingleLine(user.username, 80),
    platform: os.platform(),
    release: sanitizeSingleLine(os.release(), 40),
    arch: os.arch(),
  };
}

/** `get_system_locale` — dil / yerel; kabuk yok. */
export function getSystemLocale(): Record<string, unknown> {
  const locale =
    typeof app?.getLocale === 'function' ? sanitizeSingleLine(app.getLocale(), 40) : '';
  const intl = sanitizeSingleLine(Intl.DateTimeFormat().resolvedOptions().locale, 40);
  return {
    locale: locale || intl || 'und',
    intl,
    language: sanitizeSingleLine((locale || intl).split('-')[0] || 'und', 12),
  };
}

/** `get_system_time` — yerel saat / tarih; ayar değiştirmez. */
export function getSystemTime(): Record<string, unknown> {
  const now = new Date();
  const locale = dateLocale(hostLang());
  return {
    iso: now.toISOString(),
    local: now.toLocaleString(locale),
    date: now.toLocaleDateString(locale),
    time: now.toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit' }),
    timezone: sanitizeSingleLine(Intl.DateTimeFormat().resolvedOptions().timeZone, 80),
    weekday: now.toLocaleDateString(locale, { weekday: 'long' }),
  };
}

/** `get_dark_mode` — tema; değiştirmez. */
export async function getDarkMode(): Promise<Record<string, unknown>> {
  const result = await runPowerShell(
    '(Get-ItemProperty -Path HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize ' +
      '-ErrorAction SilentlyContinue | Select-Object AppsUseLightTheme,SystemUsesLightTheme) | ConvertTo-Json -Compress',
    { timeoutMs: 8_000 },
  );
  const raw = result.stdout.trim();
  try {
    const parsed = JSON.parse(raw) as { AppsUseLightTheme?: number; SystemUsesLightTheme?: number };
    const appsLight = Number(parsed.AppsUseLightTheme) !== 0;
    return {
      dark: !appsLight,
      apps_light: appsLight,
      system_light: Number(parsed.SystemUsesLightTheme) !== 0,
    };
  } catch {
    return { dark: false, apps_light: true, system_light: true };
  }
}

/** `list_startup_apps` — HKCU Run adları; komut satırı yok. */
export async function listStartupApps(): Promise<Record<string, unknown>> {
  const result = await runPowerShell(
    '$item = Get-ItemProperty -Path HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Run -ErrorAction SilentlyContinue; ' +
      'if (-not $item) { "[]"; exit 0 }; ' +
      '$names = $item.PSObject.Properties | Where-Object { $_.Name -notlike "PS*" } | ForEach-Object { $_.Name }; ' +
      '@($names) | ConvertTo-Json -Compress',
    { timeoutMs: 8_000 },
  );
  const raw = result.stdout.trim();
  if (!raw) return { count: 0, apps: [] };
  try {
    const parsed = JSON.parse(raw) as string | string[];
    const names = (Array.isArray(parsed) ? parsed : [parsed])
      .map((name) => sanitizeSingleLine(name, 80))
      .filter(Boolean)
      .slice(0, 40);
    return { count: names.length, apps: names };
  } catch {
    return { count: 0, apps: [] };
  }
}

/** `get_internet_status` — DNS; parola/IP sızdırmaz. */
export async function getInternetStatus(): Promise<Record<string, unknown>> {
  try {
    await lookup('one.one.one.one');
    return { online: true, checked: 'one.one.one.one' };
  } catch {
    return { online: false, checked: 'one.one.one.one' };
  }
}

/** `get_default_browser` — HTTPS UserChoice; parola yok. */
export async function getDefaultBrowser(): Promise<Record<string, unknown>> {
  const result = await runPowerShell(
    `(Get-ItemProperty 'HKCU:\\Software\\Microsoft\\Windows\\Shell\\Associations\\UrlAssociations\\https\\UserChoice' ` +
      '-ErrorAction SilentlyContinue).ProgId',
    { timeoutMs: 8_000 },
  );
  const progId = sanitizeSingleLine(result.stdout, 80);
  const lower = progId.toLowerCase();
  let name = progId || hostText('bilinmiyor', 'unknown');
  if (lower.includes('chrome')) name = 'Google Chrome';
  else if (lower.includes('edge')) name = 'Microsoft Edge';
  else if (lower.includes('firefox')) name = 'Firefox';
  else if (lower.includes('ie.') || lower.includes('internetexplorer')) name = 'Internet Explorer';
  return { prog_id: progId, name, found: Boolean(progId) };
}

/** `get_battery_level` — yüzde; prize takılı bilgisi ayrı (`get_power_status`). */
export async function getBatteryLevel(): Promise<Record<string, unknown>> {
  const result = await runPowerShell(
    'Get-CimInstance Win32_Battery | Select-Object EstimatedChargeRemaining,BatteryStatus | ConvertTo-Json -Compress',
    { timeoutMs: 8_000 },
  );
  const raw = result.stdout.trim();
  if (!raw) {
    return { present: false, percent: null };
  }
  try {
    const parsed = JSON.parse(raw) as
      | { EstimatedChargeRemaining?: number; BatteryStatus?: number }
      | { EstimatedChargeRemaining?: number; BatteryStatus?: number }[];
    const row = Array.isArray(parsed) ? parsed[0] : parsed;
    const percent = Number(row?.EstimatedChargeRemaining);
    return {
      present: true,
      percent: Number.isFinite(percent) ? percent : null,
      status: Number(row?.BatteryStatus) || null,
    };
  } catch {
    return { present: false, percent: null };
  }
}

/** `list_removable_drives` — USB/SD; biçimlendirme yok. */
export async function listRemovableDrives(): Promise<Record<string, unknown>> {
  const result = await runPowerShell(
    'Get-CimInstance Win32_LogicalDisk -Filter "DriveType=2" | ' +
      'Select-Object DeviceID,VolumeName,Size,FreeSpace | ConvertTo-Json -Compress',
    { timeoutMs: 10_000 },
  );
  const raw = result.stdout.trim();
  if (!raw) return { count: 0, drives: [] };
  try {
    const parsed = JSON.parse(raw) as
      | { DeviceID?: string; VolumeName?: string; Size?: number; FreeSpace?: number }
      | { DeviceID?: string; VolumeName?: string; Size?: number; FreeSpace?: number }[];
    const rows = Array.isArray(parsed) ? parsed : [parsed];
    const drives = rows
      .filter((row) => row?.DeviceID)
      .map((row) => ({
        letter: sanitizeSingleLine(row.DeviceID, 8),
        name: sanitizeSingleLine(row.VolumeName ?? '', 80),
        total_gb: Number(row.Size) > 0 ? Math.round(Number(row.Size) / 1_000_000_000) : 0,
        free_gb: Number(row.FreeSpace) > 0 ? Math.round(Number(row.FreeSpace) / 1_000_000_000) : 0,
      }));
    return { count: drives.length, drives };
  } catch {
    return { count: 0, drives: [] };
  }
}

/** `eject_removable_drive` — yalnızca DriveType=2 harf; biçimlendirmez. */
export async function ejectRemovableDrive(
  args: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  const letter = sanitizeSingleLine(args.letter, 4).toUpperCase().replace(/[^A-Z]/g, '');
  if (!/^[A-Z]$/.test(letter)) {
    throw new Error(
      hostText('Geçerli bir sürücü harfi gerekli (A–Z).', 'A valid drive letter is required (A–Z).'),
    );
  }
  const notRemovable = hostText(
    'Cikarilabilir surucu degil veya takili degil.',
    'Not a removable drive, or it is not attached.',
  ).replace(/'/g, "''");
  const driveMissing = hostText('Surucu bulunamadi.', 'Drive was not found.').replace(/'/g, "''");
  const result = await runPowerShell(
    `$letter = '${letter}:'
$disk = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='$letter' AND DriveType=2" -ErrorAction SilentlyContinue
if (-not $disk) { throw '${notRemovable}' }
$shell = New-Object -ComObject Shell.Application
$item = $shell.NameSpace(17).ParseName($letter)
if (-not $item) { throw '${driveMissing}' }
$item.InvokeVerb('Eject')
[PSCustomObject]@{ letter = $letter; ejected = $true } | ConvertTo-Json -Compress`,
    { timeoutMs: 12_000 },
  );
  const raw = result.stdout.trim();
  try {
    const parsed = JSON.parse(raw) as { letter?: string; ejected?: boolean };
    return { ejected: Boolean(parsed.ejected), letter: sanitizeSingleLine(parsed.letter || `${letter}:`, 8) };
  } catch {
    throw new Error(
      result.stderr.trim().slice(0, 200) ||
        hostText('Sürücü çıkarılamadı.', 'Could not eject the drive.'),
    );
  }
}

const DRIVE_TYPE_LABELS: Record<number, string> = {
  2: 'removable',
  3: 'fixed',
  4: 'network',
  5: 'cdrom',
};

/** `list_logical_drives` — tüm harfler; USB listesi / biçim değil. */
export async function listLogicalDrives(): Promise<Record<string, unknown>> {
  const result = await runPowerShell(
    'Get-CimInstance Win32_LogicalDisk | Select-Object DeviceID,DriveType,VolumeName,Size,FreeSpace | ConvertTo-Json -Compress',
    { timeoutMs: 10_000 },
  );
  const raw = result.stdout.trim();
  if (!raw) return { count: 0, drives: [] };
  try {
    const parsed = JSON.parse(raw) as
      | { DeviceID?: string; DriveType?: number; VolumeName?: string; Size?: number; FreeSpace?: number }
      | { DeviceID?: string; DriveType?: number; VolumeName?: string; Size?: number; FreeSpace?: number }[];
    const rows = Array.isArray(parsed) ? parsed : [parsed];
    const drives = rows
      .filter((row) => row?.DeviceID)
      .map((row) => ({
        letter: sanitizeSingleLine(row.DeviceID, 8),
        kind: DRIVE_TYPE_LABELS[Number(row.DriveType)] || 'other',
        name: sanitizeSingleLine(row.VolumeName ?? '', 80),
        total_gb: Number(row.Size) > 0 ? Math.round(Number(row.Size) / 1_000_000_000) : 0,
        free_gb: Number(row.FreeSpace) > 0 ? Math.round(Number(row.FreeSpace) / 1_000_000_000) : 0,
      }));
    return { count: drives.length, drives };
  } catch {
    return { count: 0, drives: [] };
  }
}

/** `list_printers` — yazıcı adları; yazdırmaz. */
export async function listPrinters(): Promise<Record<string, unknown>> {
  const result = await runPowerShell(
    'Get-CimInstance Win32_Printer | Select-Object Name,Default,WorkOffline | ConvertTo-Json -Compress',
    { timeoutMs: 10_000 },
  );
  const raw = result.stdout.trim();
  if (!raw) return { count: 0, printers: [] };
  try {
    const parsed = JSON.parse(raw) as
      | { Name?: string; Default?: boolean; WorkOffline?: boolean }
      | { Name?: string; Default?: boolean; WorkOffline?: boolean }[];
    const rows = Array.isArray(parsed) ? parsed : [parsed];
    const printers = rows
      .filter((row) => row?.Name)
      .map((row) => ({
        name: sanitizeSingleLine(row.Name, 120),
        default: Boolean(row.Default),
        offline: Boolean(row.WorkOffline),
      }));
    return { count: printers.length, printers };
  } catch {
    return { count: 0, printers: [] };
  }
}

/** `get_default_printer` — varsayılan ad; yazdırmaz, listeyi ezmez. */
export async function getDefaultPrinter(): Promise<Record<string, unknown>> {
  const result = await runPowerShell(
    'Get-CimInstance Win32_Printer -Filter "Default=True" | Select-Object -First 1 Name,WorkOffline | ConvertTo-Json -Compress',
    { timeoutMs: 10_000 },
  );
  const raw = result.stdout.trim();
  if (!raw) return { found: false, name: '', offline: false };
  try {
    const parsed = JSON.parse(raw) as { Name?: string; WorkOffline?: boolean };
    const name = sanitizeSingleLine(parsed.Name ?? '', 120);
    return { found: Boolean(name), name, offline: Boolean(parsed.WorkOffline) };
  } catch {
    return { found: false, name: '', offline: false };
  }
}

const FILE_ASSOC_EXT = new Set([
  'pdf',
  'txt',
  'doc',
  'docx',
  'xls',
  'xlsx',
  'ppt',
  'pptx',
  'jpg',
  'jpeg',
  'png',
  'gif',
  'zip',
  'mp3',
  'mp4',
  'md',
  'csv',
  'json',
]);

/** `get_file_association` — uzantı → ProgId; açmaz. */
export async function getFileAssociation(
  args: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  const ext = sanitizeSingleLine(args.extension ?? args.ext ?? '', 8)
    .toLowerCase()
    .replace(/^\./, '');
  if (!FILE_ASSOC_EXT.has(ext)) {
    throw new Error(
      hostText(`'${ext}' izinli bir uzantı değil.`, `'${ext}' is not an allowed extension.`),
    );
  }
  const result = await run('cmd.exe', ['/d', '/s', '/c', `assoc .${ext}`], { timeoutMs: 8_000 });
  const line = sanitizeSingleLine(result.stdout, 200);
  const progId = line.includes('=') ? sanitizeSingleLine(line.split('=').slice(1).join('='), 120) : '';
  return { extension: `.${ext}`, prog_id: progId, found: Boolean(progId) };
}

/** `get_power_plan` — aktif plan adı; değiştirmez. */
export async function getPowerPlan(): Promise<Record<string, unknown>> {
  const result = await run('powercfg.exe', ['/GETACTIVESCHEME'], { timeoutMs: 8_000 });
  const text = result.stdout || '';
  const named = /\(([^)]+)\)/.exec(text);
  const guid = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i.exec(text);
  return {
    name: sanitizeSingleLine(named?.[1] ?? '', 80),
    guid: sanitizeSingleLine(guid?.[0] ?? '', 40),
    found: Boolean(named?.[1]),
  };
}

/** `get_user_profile_path` — ev klasörü; içerik yok. */
export function getUserProfilePath(): Record<string, unknown> {
  return { path: sanitizeSingleLine(os.homedir(), 500) };
}

/** `get_wifi_status` — bağlı SSID; parola yok, serbest kabuk yok. */
export async function getWifiStatus(): Promise<Record<string, unknown>> {
  const result = await run('netsh', ['wlan', 'show', 'interfaces'], { timeoutMs: 12_000 });
  const text = result.stdout || '';
  const ssid = /^\s*SSID\s*:\s*(.+)$/im.exec(text)?.[1]?.trim() ?? '';
  const state = /^\s*(?:State|Durum)\s*:\s*(.+)$/im.exec(text)?.[1]?.trim() ?? '';
  const connected = /connected|bağlı|bagli/i.test(state);
  return {
    connected,
    ssid: sanitizeSingleLine(ssid, 80),
    state: sanitizeSingleLine(state, 40),
  };
}

/** `list_nearby_wifi` — SSID listesi; parola/BSSID yok. */
export async function listNearbyWifi(): Promise<Record<string, unknown>> {
  const result = await run('netsh', ['wlan', 'show', 'networks'], { timeoutMs: 12_000 });
  const names = new Set<string>();
  for (const line of (result.stdout || '').split(/\r?\n/)) {
    const matched = /^\s*SSID\s+\d+\s*:\s*(.+)$/i.exec(line);
    const ssid = sanitizeSingleLine(matched?.[1] ?? '', 80);
    if (ssid) names.add(ssid);
  }
  const networks = [...names].slice(0, 30);
  return { count: networks.length, networks };
}

/** `get_last_boot_time` — son açılış; uptime süresini ezmez. */
export function getLastBootTime(): Record<string, unknown> {
  const boot = new Date(Date.now() - Math.max(0, os.uptime()) * 1000);
  return {
    boot_iso: boot.toISOString(),
    boot_local: boot.toLocaleString(dateLocale(hostLang())),
  };
}

/** `get_system_model` — marka/model; hostname değil. */
export async function getSystemModel(): Promise<Record<string, unknown>> {
  const result = await runPowerShell(
    'Get-CimInstance Win32_ComputerSystem | Select-Object Manufacturer,Model | ConvertTo-Json -Compress',
    { timeoutMs: 8_000 },
  );
  const raw = result.stdout.trim();
  try {
    const parsed = JSON.parse(raw) as { Manufacturer?: string; Model?: string };
    return {
      manufacturer: sanitizeSingleLine(parsed.Manufacturer ?? '', 80),
      model: sanitizeSingleLine(parsed.Model ?? '', 80),
    };
  } catch {
    return { manufacturer: '', model: '' };
  }
}

/** `get_night_light` — gece ışığı; karanlık temayı ezmez. */
export async function getNightLight(): Promise<Record<string, unknown>> {
  const result = await runPowerShell(
    `$p = 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\CloudStore\\Store\\DefaultAccount\\Current\\default$windows.data.bluelightreduction.bluelightreductionstate\\windows.data.bluelightreduction.bluelightreductionstate'
$item = Get-ItemProperty -Path $p -ErrorAction SilentlyContinue
if (-not $item -or -not $item.Data) { '{"found":false,"enabled":false}'; exit 0 }
$data = [byte[]]$item.Data
$on = $data.Length -gt 18 -and $data[18] -eq 0x15
[PSCustomObject]@{ found = $true; enabled = [bool]$on } | ConvertTo-Json -Compress`,
    { timeoutMs: 8_000 },
  );
  const raw = result.stdout.trim();
  try {
    const parsed = JSON.parse(raw) as { found?: boolean; enabled?: boolean };
    return { found: Boolean(parsed.found), enabled: Boolean(parsed.enabled) };
  } catch {
    return { found: false, enabled: false };
  }
}

/** `get_bluetooth_status` — radyo var/açık; eşleştirmez, ayar açmaz. */
export async function getBluetoothStatus(): Promise<Record<string, unknown>> {
  const result = await runPowerShell(
    '$devs = @(Get-PnpDevice -Class Bluetooth -ErrorAction SilentlyContinue); ' +
      '$ok = @($devs | Where-Object { $_.Status -eq "OK" }).Count; ' +
      '[PSCustomObject]@{ present = ($devs.Count -gt 0); enabled = ($ok -gt 0); count = $ok } | ConvertTo-Json -Compress',
    { timeoutMs: 10_000 },
  );
  const raw = result.stdout.trim();
  try {
    const parsed = JSON.parse(raw) as { present?: boolean; enabled?: boolean; count?: number };
    return {
      present: Boolean(parsed.present),
      enabled: Boolean(parsed.enabled),
      count: Number(parsed.count) || 0,
    };
  } catch {
    return { present: false, enabled: false, count: 0 };
  }
}

/** `get_timezone` — IANA dilimi; saati ezmez. */
export function getTimezone(): Record<string, unknown> {
  const zone = sanitizeSingleLine(Intl.DateTimeFormat().resolvedOptions().timeZone, 80);
  const offset = -new Date().getTimezoneOffset();
  return {
    timezone: zone || 'und',
    offset_minutes: offset,
  };
}

/** `get_temp_folder_path` — geçici klasör; ev/masaüstü yolu değil. */
export function getTempFolderPath(): Record<string, unknown> {
  return { path: sanitizeSingleLine(os.tmpdir(), 500) };
}

/** `get_wallpaper_path` — duvar kağıdı yolu; görüntü okumaz. */
export async function getWallpaperPath(): Promise<Record<string, unknown>> {
  const result = await runPowerShell(
    '$p = (Get-ItemProperty -Path "HKCU:\\Control Panel\\Desktop" -Name Wallpaper -ErrorAction SilentlyContinue).Wallpaper; ' +
      '[PSCustomObject]@{ path = [string]$p } | ConvertTo-Json -Compress',
    { timeoutMs: 8_000 },
  );
  const raw = result.stdout.trim();
  try {
    const parsed = JSON.parse(raw) as { path?: string };
    const wallpaper = sanitizeSingleLine(parsed.path ?? '', 500);
    return { found: Boolean(wallpaper), path: wallpaper };
  } catch {
    return { found: false, path: '' };
  }
}

/** `get_wifi_radio` — radyo açık/kapalı; SSID/yakın ağ değil. */
export async function getWifiRadio(): Promise<Record<string, unknown>> {
  const result = await runPowerShell(
    '$n = @(Get-NetAdapter -ErrorAction SilentlyContinue | Where-Object { $_.InterfaceDescription -match "Wireless|Wi-?Fi|802\\.11|WLAN" }); ' +
      '$up = @($n | Where-Object { $_.Status -eq "Up" }).Count; ' +
      '[PSCustomObject]@{ present = ($n.Count -gt 0); enabled = ($up -gt 0); count = $up } | ConvertTo-Json -Compress',
    { timeoutMs: 10_000 },
  );
  const raw = result.stdout.trim();
  try {
    const parsed = JSON.parse(raw) as { present?: boolean; enabled?: boolean; count?: number };
    return {
      present: Boolean(parsed.present),
      enabled: Boolean(parsed.enabled),
      count: Number(parsed.count) || 0,
    };
  } catch {
    return { present: false, enabled: false, count: 0 };
  }
}

/** `get_default_playback_device` — hoparlör adı; ses seviyesi değil. */
export async function getDefaultPlaybackDevice(): Promise<Record<string, unknown>> {
  const result = await runPowerShell(
    '$d = Get-CimInstance Win32_SoundDevice -ErrorAction SilentlyContinue | Where-Object { $_.Status -eq "OK" } | Select-Object -First 1 Name; ' +
      '[PSCustomObject]@{ name = [string]$d.Name } | ConvertTo-Json -Compress',
    { timeoutMs: 8_000 },
  );
  const raw = result.stdout.trim();
  try {
    const parsed = JSON.parse(raw) as { name?: string };
    const name = sanitizeSingleLine(parsed.name ?? '', 120);
    return { found: Boolean(name), name };
  } catch {
    return { found: false, name: '' };
  }
}

/** `get_drive_label` — sürücü etiketi; çıkarmaz, formatlamaz. */
export async function getDriveLabel(args: Record<string, unknown>): Promise<Record<string, unknown>> {
  const letter = sanitizeSingleLine(args.letter ?? args.drive ?? 'C', 2)
    .replace(/[^A-Za-z]/g, '')
    .toUpperCase()
    .slice(0, 1);
  if (!/^[A-Z]$/.test(letter)) {
    throw new Error(hostText('Sürücü harfi A–Z olmalı.', 'Drive letter must be A–Z.'));
  }
  const result = await runPowerShell(
    `$d = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='${letter}:'" -ErrorAction SilentlyContinue; ` +
      'if (-not $d) { \'{"found":false,"letter":"' +
      letter +
      '","label":""}\'; exit 0 }; ' +
      `[PSCustomObject]@{ found = $true; letter = '${letter}'; label = [string]$d.VolumeName } | ConvertTo-Json -Compress`,
    { timeoutMs: 8_000 },
  );
  const raw = result.stdout.trim();
  try {
    const parsed = JSON.parse(raw) as { found?: boolean; letter?: string; label?: string };
    return {
      found: Boolean(parsed.found),
      letter,
      label: sanitizeSingleLine(parsed.label ?? '', 80),
    };
  } catch {
    return { found: false, letter, label: '' };
  }
}

/** `get_onedrive_path` — OneDrive klasörü; ev/temp değil. */
export async function getOnedrivePath(): Promise<Record<string, unknown>> {
  const result = await runPowerShell(
    '$p = $null; foreach ($key in @("Personal","Business1")) { ' +
      '$item = Get-ItemProperty "HKCU:\\Software\\Microsoft\\OneDrive\\Accounts\\$key" -ErrorAction SilentlyContinue; ' +
      'if ($item.UserFolder) { $p = $item.UserFolder; break } }; ' +
      '[PSCustomObject]@{ path = [string]$p } | ConvertTo-Json -Compress',
    { timeoutMs: 8_000 },
  );
  let folder = '';
  try {
    folder = sanitizeSingleLine((JSON.parse(result.stdout.trim()) as { path?: string }).path ?? '', 500);
  } catch {
    folder = '';
  }
  if (!folder) {
    for (const name of ['OneDrive', 'OneDrive - Personal']) {
      const candidate = path.join(os.homedir(), name);
      if (existsSync(candidate)) {
        folder = sanitizeSingleLine(candidate, 500);
        break;
      }
    }
  }
  return { found: Boolean(folder), path: folder };
}

/** `get_cpu_name` — işlemci adı; kullanım yüzdesi değil. */
export function getCpuName(): Record<string, unknown> {
  const name = sanitizeSingleLine(os.cpus()[0]?.model ?? '', 120);
  return { found: Boolean(name), name, count: os.cpus().length };
}

/** `get_gpu_name` — ekran kartı adı; kullanım/sıcaklık değil. */
export async function getGpuName(): Promise<Record<string, unknown>> {
  const result = await runPowerShell(
    '$d = Get-CimInstance Win32_VideoController -ErrorAction SilentlyContinue | Select-Object -First 1 Name; ' +
      '[PSCustomObject]@{ name = [string]$d.Name } | ConvertTo-Json -Compress',
    { timeoutMs: 8_000 },
  );
  const raw = result.stdout.trim();
  try {
    const parsed = JSON.parse(raw) as { name?: string };
    const name = sanitizeSingleLine(parsed.name ?? '', 120);
    return { found: Boolean(name), name };
  } catch {
    return { found: false, name: '' };
  }
}

/** `get_ethernet_status` — kablolu bağ; wifi/IP değil. */
export async function getEthernetStatus(): Promise<Record<string, unknown>> {
  const result = await runPowerShell(
    '$n = @(Get-NetAdapter -ErrorAction SilentlyContinue | Where-Object { ' +
      '$_.InterfaceDescription -match "Ethernet|Gigabit" -and $_.InterfaceDescription -notmatch "Wireless|Wi-?Fi|802\\.11|WLAN|Bluetooth" }); ' +
      '$up = @($n | Where-Object { $_.Status -eq "Up" }).Count; ' +
      '[PSCustomObject]@{ present = ($n.Count -gt 0); connected = ($up -gt 0); count = $up } | ConvertTo-Json -Compress',
    { timeoutMs: 10_000 },
  );
  const raw = result.stdout.trim();
  try {
    const parsed = JSON.parse(raw) as { present?: boolean; connected?: boolean; count?: number };
    return {
      present: Boolean(parsed.present),
      connected: Boolean(parsed.connected),
      count: Number(parsed.count) || 0,
    };
  } catch {
    return { present: false, connected: false, count: 0 };
  }
}

/** `get_default_recording_device` — mikrofon adı; hoparlör değil. */
export async function getDefaultRecordingDevice(): Promise<Record<string, unknown>> {
  const result = await runPowerShell(
    '$d = Get-CimInstance Win32_SoundDevice -ErrorAction SilentlyContinue | ' +
      'Where-Object { $_.Name -match "Microphone|Mikrofon|Input" } | Select-Object -First 1 Name; ' +
      'if (-not $d) { $d = Get-CimInstance Win32_SoundDevice -ErrorAction SilentlyContinue | Select-Object -First 1 Name }; ' +
      '[PSCustomObject]@{ name = [string]$d.Name } | ConvertTo-Json -Compress',
    { timeoutMs: 8_000 },
  );
  const raw = result.stdout.trim();
  try {
    const parsed = JSON.parse(raw) as { name?: string };
    const name = sanitizeSingleLine(parsed.name ?? '', 120);
    return { found: Boolean(name), name };
  } catch {
    return { found: false, name: '' };
  }
}

/** `get_refresh_rate` — Hz; monitör sayısı/çözünürlük değil. */
export function getRefreshRate(): Record<string, unknown> {
  const primary = screen.getPrimaryDisplay();
  const hz = Number((primary as { displayFrequency?: number }).displayFrequency) || 0;
  return { hz, found: hz > 0 };
}

/** `get_screen_scale` — ölçek; Hz / monitör sayısı değil. */
export function getScreenScale(): Record<string, unknown> {
  const primary = screen.getPrimaryDisplay();
  const scale = Number(primary.scaleFactor) || 1;
  return { scale, percent: Math.round(scale * 100) };
}

/** `get_ram_size` — toplam RAM; kullanım yüzdesi değil. */
export function getRamSize(): Record<string, unknown> {
  const bytes = os.totalmem();
  return {
    total_gb: Math.round((bytes / 1024 / 1024 / 1024) * 10) / 10,
    total_mb: Math.round(bytes / 1024 / 1024),
  };
}

/** `get_cpu_count` — çekirdek sayısı; ad/kullanım değil. */
export function getCpuCount(): Record<string, unknown> {
  return { count: os.cpus().length };
}

/** `get_mute_status` — ses kapalı mı; seviyeyi ezmez, sessiz yapmaz. */
export async function getMuteStatus(): Promise<Record<string, unknown>> {
  const volume = await readMasterVolume();
  return { muted: volume <= 0, volume };
}

/** `get_drive_filesystem` — NTFS/FAT; etiket/doluluk değil. */
export async function getDriveFilesystem(
  args: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  const letter = sanitizeSingleLine(args.letter ?? args.drive ?? 'C', 2)
    .replace(/[^A-Za-z]/g, '')
    .toUpperCase()
    .slice(0, 1);
  if (!/^[A-Z]$/.test(letter)) {
    throw new Error(hostText('Sürücü harfi A–Z olmalı.', 'Drive letter must be A–Z.'));
  }
  const result = await runPowerShell(
    `$d = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='${letter}:'" -ErrorAction SilentlyContinue; ` +
      'if (-not $d) { \'{"found":false,"letter":"' +
      letter +
      '","filesystem":""}\'; exit 0 }; ' +
      `[PSCustomObject]@{ found = $true; letter = '${letter}'; filesystem = [string]$d.FileSystem } | ConvertTo-Json -Compress`,
    { timeoutMs: 8_000 },
  );
  const raw = result.stdout.trim();
  try {
    const parsed = JSON.parse(raw) as { found?: boolean; filesystem?: string };
    return {
      found: Boolean(parsed.found),
      letter,
      filesystem: sanitizeSingleLine(parsed.filesystem ?? '', 20),
    };
  } catch {
    return { found: false, letter, filesystem: '' };
  }
}

/** `get_airplane_mode` — uçak modu; wifi radyo/SSID değil. */
export async function getAirplaneMode(): Promise<Record<string, unknown>> {
  const result = await runPowerShell(
    '$p = "HKLM:\\SYSTEM\\CurrentControlSet\\Control\\RadioManagement\\SystemRadioState"; ' +
      'if (-not (Test-Path $p)) { \'{"found":false,"enabled":false}\'; exit 0 }; ' +
      '$item = Get-ItemProperty $p -ErrorAction SilentlyContinue; ' +
      '$raw = $item.\'(default)\'; if ($null -eq $raw) { $raw = $item.SystemRadioState }; ' +
      '$on = $false; try { $on = [int]$raw -eq 1 } catch {}; ' +
      '[PSCustomObject]@{ found = $true; enabled = [bool]$on } | ConvertTo-Json -Compress',
    { timeoutMs: 8_000 },
  );
  const raw = result.stdout.trim();
  try {
    const parsed = JSON.parse(raw) as { found?: boolean; enabled?: boolean };
    return { found: Boolean(parsed.found), enabled: Boolean(parsed.enabled) };
  } catch {
    return { found: false, enabled: false };
  }
}

/** `get_os_version` — Windows sürümü; model / hostname değil. */
export async function getOsVersion(): Promise<Record<string, unknown>> {
  const result = await runPowerShell(
    'Get-CimInstance Win32_OperatingSystem | Select-Object Caption,Version,BuildNumber | ConvertTo-Json -Compress',
    { timeoutMs: 8_000 },
  );
  const raw = result.stdout.trim();
  try {
    const parsed = JSON.parse(raw) as {
      Caption?: string;
      Version?: string;
      BuildNumber?: string;
    };
    return {
      caption: sanitizeSingleLine(parsed.Caption ?? '', 80),
      version: sanitizeSingleLine(parsed.Version ?? '', 40),
      build: sanitizeSingleLine(String(parsed.BuildNumber ?? ''), 20),
    };
  } catch {
    return { caption: '', version: sanitizeSingleLine(os.release(), 40), build: '' };
  }
}

/** `get_username` — oturum adı; ev klasörü değil. */
export function getUsername(): Record<string, unknown> {
  return { username: sanitizeSingleLine(os.userInfo().username, 80) };
}

/** `get_brightness` — parlaklık; ölçek / gece ışığı / ses değil. */
export async function getBrightness(): Promise<Record<string, unknown>> {
  const result = await runPowerShell(
    '$b = Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightness -ErrorAction SilentlyContinue | Select-Object -First 1; ' +
      'if (-not $b) { \'{"found":false,"percent":null}\'; exit 0 }; ' +
      '[PSCustomObject]@{ found = $true; percent = [int]$b.CurrentBrightness } | ConvertTo-Json -Compress',
    { timeoutMs: 8_000 },
  );
  const raw = result.stdout.trim();
  try {
    const parsed = JSON.parse(raw) as { found?: boolean; percent?: number | null };
    const percent = Number(parsed.percent);
    return {
      found: Boolean(parsed.found),
      percent: Number.isFinite(percent) ? percent : null,
    };
  } catch {
    return { found: false, percent: null };
  }
}

/** `get_vpn_status` — VPN; wifi / ethernet / internet değil. */
export async function getVpnStatus(): Promise<Record<string, unknown>> {
  const result = await runPowerShell(
    '$all = @(Get-VpnConnection -ErrorAction SilentlyContinue); ' +
      "$up = @($all | Where-Object { $_.ConnectionStatus -eq 'Connected' }); " +
      '$name = if ($up.Count) { [string]$up[0].Name } else { \'\' }; ' +
      '[PSCustomObject]@{ found = $true; connected = ($up.Count -gt 0); name = $name; count = $up.Count } | ConvertTo-Json -Compress',
    { timeoutMs: 8_000 },
  );
  const raw = result.stdout.trim();
  try {
    const parsed = JSON.parse(raw) as {
      found?: boolean;
      connected?: boolean;
      name?: string;
      count?: number;
    };
    return {
      found: Boolean(parsed.found),
      connected: Boolean(parsed.connected),
      name: sanitizeSingleLine(parsed.name ?? '', 80),
      count: Number(parsed.count) || 0,
    };
  } catch {
    return { found: false, connected: false, name: '', count: 0 };
  }
}

/** `get_keyboard_layout` — klavye dili; sistem locale değil. */
export async function getKeyboardLayout(): Promise<Record<string, unknown>> {
  const result = await runPowerShell(
    '$l = Get-WinUserLanguageList -ErrorAction SilentlyContinue | Select-Object -First 1; ' +
      'if (-not $l) { \'{"found":false,"tag":"","name":""}\'; exit 0 }; ' +
      '[PSCustomObject]@{ found = $true; tag = [string]$l.LanguageTag; name = [string]$l.LocalizedName } | ConvertTo-Json -Compress',
    { timeoutMs: 8_000 },
  );
  const raw = result.stdout.trim();
  try {
    const parsed = JSON.parse(raw) as { found?: boolean; tag?: string; name?: string };
    return {
      found: Boolean(parsed.found),
      tag: sanitizeSingleLine(parsed.tag ?? '', 20),
      name: sanitizeSingleLine(parsed.name ?? '', 80),
    };
  } catch {
    return { found: false, tag: '', name: '' };
  }
}

/** `get_battery_saver` — pil tasarrufu; yüzde / güç planı değil. */
export async function getBatterySaver(): Promise<Record<string, unknown>> {
  const result = await runPowerShell(
    "$guid = '961cc777-2547-4f9d-8174-7d86181b8a7a'; " +
      "$p = Get-ItemProperty 'HKLM:\\SYSTEM\\CurrentControlSet\\Control\\Power\\User\\PowerSchemes' -ErrorAction SilentlyContinue; " +
      'if (-not $p) { \'{"found":false,"enabled":false}\'; exit 0 }; ' +
      '$dc = [string]$p.ActiveOverlayDcPowerScheme; $ac = [string]$p.ActiveOverlayAcPowerScheme; ' +
      '$on = ($dc -ieq $guid) -or ($ac -ieq $guid); ' +
      '[PSCustomObject]@{ found = $true; enabled = [bool]$on } | ConvertTo-Json -Compress',
    { timeoutMs: 8_000 },
  );
  const raw = result.stdout.trim();
  try {
    const parsed = JSON.parse(raw) as { found?: boolean; enabled?: boolean };
    return { found: Boolean(parsed.found), enabled: Boolean(parsed.enabled) };
  } catch {
    return { found: false, enabled: false };
  }
}

/** `get_architecture` — 64/32 bit; Windows sürümü / işlemci adı değil. */
export function getArchitecture(): Record<string, unknown> {
  const arch = sanitizeSingleLine(os.arch(), 16);
  return { arch, bits: arch.includes('64') ? 64 : 32 };
}

/** `get_focus_assist` — odaklanma / rahatsız etme; sessiz / gece ışığı değil. */
export async function getFocusAssist(): Promise<Record<string, unknown>> {
  const result = await runPowerShell(
    "$p = 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Notifications\\Settings'; " +
      '$item = Get-ItemProperty $p -ErrorAction SilentlyContinue; ' +
      'if (-not $item) { \'{"found":false,"enabled":false}\'; exit 0 }; ' +
      '$raw = $item.NOC_GLOBAL_SETTING_TOASTS_ENABLED; ' +
      '$on = $false; if ($null -ne $raw) { try { $on = [int]$raw -eq 0 } catch {} }; ' +
      '[PSCustomObject]@{ found = $true; enabled = [bool]$on } | ConvertTo-Json -Compress',
    { timeoutMs: 8_000 },
  );
  const raw = result.stdout.trim();
  try {
    const parsed = JSON.parse(raw) as { found?: boolean; enabled?: boolean };
    return { found: Boolean(parsed.found), enabled: Boolean(parsed.enabled) };
  } catch {
    return { found: false, enabled: false };
  }
}

/** `get_firewall_status` — güvenlik duvarı; antivirüs değil. */
export async function getFirewallStatus(): Promise<Record<string, unknown>> {
  const result = await runPowerShell(
    '$p = @(Get-NetFirewallProfile -ErrorAction SilentlyContinue | Select-Object Name,Enabled); ' +
      'if (-not $p.Count) { \'{"found":false,"enabled":false,"profiles":[]}\'; exit 0 }; ' +
      '$on = @($p | Where-Object { $_.Enabled }).Count -gt 0; ' +
      '$names = @($p | ForEach-Object { [string]$_.Name }); ' +
      '[PSCustomObject]@{ found = $true; enabled = [bool]$on; profiles = $names } | ConvertTo-Json -Compress',
    { timeoutMs: 8_000 },
  );
  const raw = result.stdout.trim();
  try {
    const parsed = JSON.parse(raw) as {
      found?: boolean;
      enabled?: boolean;
      profiles?: string[];
    };
    const profiles = Array.isArray(parsed.profiles)
      ? parsed.profiles.map((name) => sanitizeSingleLine(name, 20)).filter(Boolean)
      : [];
    return { found: Boolean(parsed.found), enabled: Boolean(parsed.enabled), profiles };
  } catch {
    return { found: false, enabled: false, profiles: [] };
  }
}

/** `get_default_mail_app` — varsayılan e-posta; tarayıcı değil. */
export async function getDefaultMailApp(): Promise<Record<string, unknown>> {
  const result = await runPowerShell(
    "$p = Get-ItemProperty 'HKCU:\\Software\\Microsoft\\Windows\\Shell\\Associations\\UrlAssociations\\mailto\\UserChoice' -ErrorAction SilentlyContinue; " +
      'if (-not $p) { \'{"found":false,"progid":"","name":""}\'; exit 0 }; ' +
      '$id = [string]$p.ProgId; ' +
      '[PSCustomObject]@{ found = $true; progid = $id; name = $id } | ConvertTo-Json -Compress',
    { timeoutMs: 8_000 },
  );
  const raw = result.stdout.trim();
  try {
    const parsed = JSON.parse(raw) as { found?: boolean; progid?: string; name?: string };
    const progid = sanitizeSingleLine(parsed.progid ?? '', 80);
    return { found: Boolean(parsed.found), progid, name: progid };
  } catch {
    return { found: false, progid: '', name: '' };
  }
}

/** `get_screenshots_folder` — Ekran Görüntüleri yolu; ekran yakalamaz. */
export function getScreenshotsFolder(): Record<string, unknown> {
  const pictures =
    typeof app?.getPath === 'function' ? app.getPath('pictures') : path.join(os.homedir(), 'Pictures');
  const candidates = [
    path.join(pictures, 'Screenshots'),
    path.join(os.homedir(), 'Pictures', 'Screenshots'),
    path.join(os.homedir(), 'OneDrive', 'Pictures', 'Screenshots'),
  ];
  const found = candidates.find((item) => existsSync(item));
  const resolved = found ?? path.join(pictures, 'Screenshots');
  return { path: sanitizeSingleLine(resolved, 500), found: Boolean(found) };
}

/** `get_wifi_signal` — sinyal %; SSID / radyo açık mı değil. */
export async function getWifiSignal(): Promise<Record<string, unknown>> {
  const result = await run('netsh', ['wlan', 'show', 'interfaces'], { timeoutMs: 12_000 });
  const text = result.stdout || '';
  const signal = /^\s*(?:Signal|Sinyal)\s*:\s*(\d+)/im.exec(text);
  const percent = signal ? Number(signal[1]) : null;
  const state = /^\s*(?:State|Durum)\s*:\s*(.+)$/im.exec(text)?.[1]?.trim() ?? '';
  const connected = /connected|bağlı|bagli/i.test(state);
  return {
    found: percent != null && Number.isFinite(percent),
    percent: percent != null && Number.isFinite(percent) ? percent : null,
    connected,
  };
}

/** Seçili metni panoya yazar (Ctrl+C yok). */
export async function copySelectedText(): Promise<Record<string, unknown>> {
  const selected = await getSelectedText();
  const text = String(selected.text ?? '');
  if (!text) {
    return { copied: false, empty: true, text: '' };
  }
  clipboard.writeText(text);
  return { copied: true, empty: false, length: text.length, text: text.slice(0, 500) };
}

/** Windows oturumunu kilitler (Win+L). */
export async function lockWorkstation(): Promise<Record<string, unknown>> {
  const result = await run('rundll32.exe', ['user32.dll,LockWorkStation'], { timeoutMs: 8_000 });
  if (result.code !== 0) {
    throw new Error(
      hostText(
        `Oturum kilitlenemedi: ${(result.stderr || result.stdout).trim().slice(0, 300)}`,
        `Could not lock the session: ${(result.stderr || result.stdout).trim().slice(0, 300)}`,
      ),
    );
  }
  return { locked: true };
}

/** `take_screenshot` aracı — görüntüyü Resimler klasörüne kaydeder. */
export async function takeScreenshot(): Promise<Record<string, unknown>> {
  const display = screen.getPrimaryDisplay();
  const { width, height } = display.size;
  const scale = display.scaleFactor || 1;

  const sources = await desktopCapturer.getSources({
    types: ['screen'],
    thumbnailSize: { width: Math.round(width * scale), height: Math.round(height * scale) },
  });
  if (!sources.length) {
    throw new Error(hostText('Ekran kaynağı bulunamadı.', 'No screen source was found.'));
  }

  const image = sources[0]!.thumbnail;
  if (image.isEmpty()) {
    throw new Error(
      hostText('Ekran görüntüsü alınamadı (boş görüntü).', 'Could not capture the screenshot (empty image).'),
    );
  }

  const stamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
  const target = path.join(app.getPath('pictures'), `uryx-ekran-${stamp}.png`);
  await writeFile(target, image.toPNG());

  return {
    saved: true,
    path: target,
    width: image.getSize().width,
    height: image.getSize().height,
  };
}

/**
 * Open Interpreter ``computer.os.get_selected_text`` — odaklı kontrolün
 * UI Automation metnini okur; Ctrl+C ile panoyu ezmez.
 */
export async function getSelectedText(): Promise<Record<string, unknown>> {
  const script = `
Add-Type -AssemblyName UIAutomationClient
$el = [System.Windows.Automation.AutomationElement]::FocusedElement
if (-not $el) { Write-Output ''; exit 0 }
try {
  $pat = $el.GetCurrentPattern([System.Windows.Automation.TextPattern]::Pattern)
  $pat.DocumentRange.GetText(4000)
} catch {
  $el.Current.Name
}
`.trim();
  const result = await run(
    'powershell.exe',
    ['-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-Command', script],
    { timeoutMs: 12_000 },
  );
  const text = result.stdout.trim().slice(0, 4000);
  return { text, empty: text.length === 0 };
}

/** Odaktaki pencere başlığı ve PID (OI ``computer.os`` / Windows tepsi kalıbı). */
export async function getForegroundWindow(): Promise<Record<string, unknown>> {
  const script = `
Add-Type @"
using System;
using System.Runtime.InteropServices;
using System.Text;
public class UryxFg {
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
}
"@
$h = [UryxFg]::GetForegroundWindow()
if ($h -eq [IntPtr]::Zero) { Write-Output '|0'; exit 0 }
$sb = New-Object System.Text.StringBuilder 512
[void][UryxFg]::GetWindowText($h, $sb, $sb.Capacity)
$pid = [uint32]0
[void][UryxFg]::GetWindowThreadProcessId($h, [ref]$pid)
$title = ($sb.ToString() -replace '[|\\r\\n]', ' ')
Write-Output ("$title|$pid")
`.trim();
  const result = await run(
    'powershell.exe',
    ['-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-Command', script],
    { timeoutMs: 12_000 },
  );
  const line = result.stdout.trim();
  const sep = line.lastIndexOf('|');
  if (sep < 0) {
    return { title: sanitizeSingleLine(line, 240), pid: 0 };
  }
  return {
    title: sanitizeSingleLine(line.slice(0, sep), 240),
    pid: Number(line.slice(sep + 1)) || 0,
  };
}

/** `list_open_windows` — başlıklar; tıklama/HWND yok. */
export async function listOpenWindows(
  args: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  const limit = Math.max(1, Math.min(Number(args.limit ?? 20) || 20, 40));
  const result = await runPowerShell(
    `Get-Process | Where-Object { $_.MainWindowTitle } | Select-Object -First ${limit} ` +
      'Id,ProcessName,MainWindowTitle | ConvertTo-Json -Compress',
    { timeoutMs: 10_000 },
  );
  const raw = result.stdout.trim();
  if (!raw) return { count: 0, windows: [] };
  try {
    const parsed = JSON.parse(raw) as
      | { Id?: number; ProcessName?: string; MainWindowTitle?: string }
      | { Id?: number; ProcessName?: string; MainWindowTitle?: string }[];
    const rows = Array.isArray(parsed) ? parsed : [parsed];
    const windows = rows
      .filter((row) => row?.MainWindowTitle)
      .map((row) => ({
        title: sanitizeSingleLine(row.MainWindowTitle, 200),
        name: sanitizeSingleLine(row.ProcessName ?? '', 80),
        pid: Number(row.Id) || 0,
      }));
    return { count: windows.length, windows };
  } catch {
    return { count: 0, windows: [] };
  }
}

/**
 * Open Interpreter ``computer.display`` — ekran boyutu/ölçek.
 * Mouse/klavye yok; yalnızca salt okunur geometri.
 */
export function getDisplayInfo(): Record<string, unknown> {
  const primary = screen.getPrimaryDisplay();
  const all =
    typeof screen.getAllDisplays === 'function' ? screen.getAllDisplays() : [primary];
  return {
    count: all.length,
    primary: {
      id: 'id' in primary ? Number((primary as { id?: number }).id) || 0 : 0,
      width: primary.size.width,
      height: primary.size.height,
      scale: primary.scaleFactor,
    },
    displays: all.map((display) => ({
      id: 'id' in display ? Number((display as { id?: number }).id) || 0 : 0,
      width: display.size.width,
      height: display.size.height,
      scale: display.scaleFactor,
    })),
  };
}

/** Electron ``powerMonitor`` — kullanıcı kaç saniyedir boşta (OI os idle). */
export function getIdleTime(): Record<string, unknown> {
  const seconds =
    typeof powerMonitor?.getSystemIdleTime === 'function' ? powerMonitor.getSystemIdleTime() : 0;
  return { idle_seconds: seconds, idle: seconds >= 90 };
}

/** OI ``computer.os.notify`` — Action Center tostu; dakikada 3 ile sınırlı. */
export function notifyUser(args: Record<string, unknown>): Record<string, unknown> {
  const title = sanitizeSingleLine(String(args.title ?? 'Uryx'), 80) || 'Uryx';
  const body = sanitizeSingleLine(String(args.body ?? args.text ?? ''), 240);
  if (!body) {
    throw new Error(hostText('Bildirim metni boş olamaz.', 'Notification text cannot be empty.'));
  }
  const shown = notifyDesktopImmediate(title, body);
  return { shown, title, body };
}

/** Odysseus/HA: UDP connect paket göndermez; OS çıkış arayüzünü söyler. */
export function probeEgressIpv4(target = '8.8.8.8', timeoutMs = 400): Promise<string | null> {
  return new Promise((resolve) => {
    const socket = createSocket('udp4');
    let settled = false;
    const finish = (ip: string | null) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      try {
        socket.close();
      } catch {
      }
      resolve(ip);
    };
    const timer = setTimeout(() => finish(null), timeoutMs);
    socket.once('error', () => finish(null));
    try {
      socket.connect(80, target, () => {
        try {
          const info = socket.address();
          finish(typeof info === 'object' ? info.address : null);
        } catch {
          finish(null);
        }
      });
    } catch {
      finish(null);
    }
  });
}

/** Yerel IPv4/IPv6 (ChatRTX/Jan “API nerede dinliyor” tanısı). MAC yok. */
export async function getNetworkInterfaces(): Promise<Record<string, unknown>> {
  const addresses: Array<{ name: string; family: string; address: string; kind: string }> = [];
  for (const [name, list] of Object.entries(os.networkInterfaces())) {
    for (const item of list ?? []) {
      if (item.internal) continue;
      const address = sanitizeSingleLine(item.address, 80);
      const family = String(item.family);
      addresses.push({
        name: sanitizeSingleLine(name, 40),
        family,
        address,
        kind: family.includes('6') ? 'ipv6' : classifyLanAddress(address),
      });
    }
  }
  const egress = await probeEgressIpv4();
  const ranked = rankLanCandidates({
    egressIp: egress,
    addresses: addresses.filter((item) => !String(item.family).includes('6')).map((item) => item.address),
  });
  return {
    hostname: sanitizeSingleLine(os.hostname(), 80),
    preferred: ranked.preferred,
    lan_candidates: ranked.candidates,
    addresses: addresses.slice(0, 12),
  };
}

/** Backend'e push edilecek tam metrik anlık görüntüsü. */
export async function collectMetrics(): Promise<Record<string, unknown>> {
  const [cpu, gpu, disk] = await Promise.all([getCpuUsage(), getGpuUsage(), getDiskUsage()]);
  const ram = getRamUsage();

  return {
    cpu_percent: cpu.percent,
    cpu_cores: cpu.cores,
    ram_total_mb: ram.total_mb,
    ram_used_mb: ram.used_mb,
    ram_percent: ram.percent,
    gpu,
    disks: disk.disks,
    hostname: sanitizeSingleLine(os.hostname(), 80),
    platform: `${os.type()} ${os.release()}`,
  };
}
