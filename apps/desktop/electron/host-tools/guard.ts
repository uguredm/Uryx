/**
 * Host araç güvenlik bekçisi (Open Interpreter / Continue kalıbı).
 *
 * Backend allowlist'ine ek ikinci katman:
 *  - araç adı ve argüman temizliği (prototype pollution yok),
 *  - eşzamanlılık tavanı (serbest paralel kabuk yok),
 *  - yazan/yıkıcı araçlar sıraya alınır,
 *  - araç başına zaman aşımı + AbortSignal iptali,
 *  - son çağrıların denetim halkası.
 *
 * Model serbest kabuk alamaz; bu katman o kuralı host tarafında tutar.
 */

import { MCP_HOST_TIMEOUT_MS } from '@shared/settings';

import { hostText } from '../host-i18n';
import { redactHostText } from './safe-url';

export const MAX_HOST_TOOLS_IN_FLIGHT = 2;
export const DEFAULT_HOST_TOOL_TIMEOUT_MS = 60_000;
/** Open Interpreter `max_output` — LLM'e giden host çıktısı tavanı. */
export const HOST_MAX_OUTPUT_CHARS = 2800;
const BINARY_RESULT_KEYS = new Set([
  'image',
  'png',
  'jpeg',
  'jpg',
  'base64',
  'data_url',
  'thumbnail',
]);
const MAX_AUDIT = 24;
const MAX_ARG_KEYS = 30;
const MAX_ARG_DEPTH = 4;

/** Aynı anda paralel çalışması istenmeyen (yan etkili) araçlar. */
export const MUTATING_HOST_TOOLS = new Set([
  'delete_file',
  'create_file',
  'edit_file',
  'kill_process',
  'close_application',
  'set_volume',
  'clipboard_write',
  'clipboard_clear',
  'copy_selected_text',
  'copy_file',
  'move_file',
  'rename_file',
  'duplicate_file',
  'create_directory',
  'save_selected_text',
  'copy_file_path',
  'eject_removable_drive',
  'open_windows_settings',
  'lock_workstation',
  'run_powershell',
  'run_cmd',
  'git_commit',
  'git_push',
  'mcp_call',
  'mcp_list_tools',
  'open_application',
  'open_external_url',
  'open_media_application',
  'control_media_playback',
  'notify_user',
  'open_docker_desktop',
  'browser_click',
  'browser_type',
  'browser_fill_form',
]);

/** Araç başına üst süre (ms). Tanımsız olanlar varsayılanı kullanır. */
export const HOST_TOOL_TIMEOUT_MS: Record<string, number> = {
  take_screenshot: 20_000,
  kill_process: 15_000,
  run_powershell: 50_000,
  run_cmd: 35_000,
  git_push: 120_000,
  git_commit: 40_000,
  browser_open: 45_000,
  browser_read_page: 45_000,
  browser_list_controls: 45_000,
  browser_click: 45_000,
  browser_type: 45_000,
  browser_fill_form: 45_000,
  browser_capture: 30_000,
  search_files: 40_000,
  list_directory: 15_000,
  copy_file: 20_000,
  move_file: 20_000,
  rename_file: 12_000,
  duplicate_file: 20_000,
  list_printers: 10_000,
  get_file_hash: 20_000,
  get_battery_level: 8_000,
  list_removable_drives: 10_000,
  eject_removable_drive: 12_000,
  is_process_running: 8_000,
  list_open_windows: 10_000,
  get_default_browser: 8_000,
  get_system_locale: 5_000,
  file_exists: 8_000,
  copy_file_path: 8_000,
  count_file_lines: 12_000,
  open_windows_settings: 8_000,
  get_recycle_bin_info: 12_000,
  get_folder_size: 20_000,
  get_special_folder_path: 5_000,
  list_logical_drives: 10_000,
  get_internet_status: 8_000,
  get_system_time: 5_000,
  get_dark_mode: 8_000,
  list_startup_apps: 8_000,
  resolve_application_path: 8_000,
  get_default_printer: 10_000,
  get_file_association: 8_000,
  get_power_plan: 8_000,
  get_user_profile_path: 5_000,
  list_nearby_wifi: 12_000,
  list_files_by_extension: 12_000,
  get_newest_file: 12_000,
  is_directory_empty: 8_000,
  get_largest_file: 12_000,
  count_files_by_extension: 12_000,
  list_subdirectories: 8_000,
  list_today_files: 12_000,
  get_last_boot_time: 5_000,
  get_system_model: 8_000,
  get_night_light: 8_000,
  get_bluetooth_status: 10_000,
  get_oldest_file: 12_000,
  count_subdirectories: 8_000,
  get_timezone: 5_000,
  get_temp_folder_path: 5_000,
  get_wallpaper_path: 8_000,
  get_wifi_radio: 10_000,
  get_default_playback_device: 8_000,
  get_drive_label: 8_000,
  get_smallest_file: 12_000,
  list_this_week_files: 12_000,
  get_onedrive_path: 8_000,
  get_cpu_name: 5_000,
  get_gpu_name: 8_000,
  get_ethernet_status: 10_000,
  get_default_recording_device: 8_000,
  get_refresh_rate: 5_000,
  list_yesterday_files: 12_000,
  count_today_files: 12_000,
  get_screen_scale: 5_000,
  get_ram_size: 5_000,
  get_cpu_count: 5_000,
  get_mute_status: 8_000,
  get_drive_filesystem: 8_000,
  get_airplane_mode: 8_000,
  list_calendar_events: 15_000,
  list_outlook_tasks: 15_000,
  list_this_month_files: 12_000,
  count_yesterday_files: 12_000,
  get_os_version: 8_000,
  get_username: 5_000,
  get_brightness: 8_000,
  get_vpn_status: 8_000,
  get_keyboard_layout: 8_000,
  get_battery_saver: 8_000,
  count_this_week_files: 12_000,
  count_this_month_files: 12_000,
  get_architecture: 5_000,
  get_focus_assist: 8_000,
  get_firewall_status: 8_000,
  get_default_mail_app: 8_000,
  get_screenshots_folder: 5_000,
  get_wifi_signal: 12_000,
  open_external_url: 8_000,
  create_directory: 8_000,
  get_file_info: 8_000,
  list_recent_files: 15_000,
  show_in_folder: 8_000,
  get_wifi_status: 12_000,
  get_uptime: 5_000,
  get_volume: 20_000,
  get_power_status: 5_000,
  clipboard_clear: 5_000,
  open_recycle_bin: 8_000,
  copy_selected_text: 15_000,
  save_selected_text: 15_000,
  lock_workstation: 8_000,
  mcp_call: MCP_HOST_TIMEOUT_MS,
  mcp_list_tools: MCP_HOST_TIMEOUT_MS,
  get_docker_engine_status: 25_000,
  get_docker_desktop_logs: 25_000,
  open_docker_desktop: 90_000,
  notify_user: 8_000,
};

export type HostExecPolicy = 'safe' | 'unsafe';

export interface HostToolAuditEntry {
  name: string;
  success: boolean;
  ms: number;
  at: number;
  error: string | null;
  policy: HostExecPolicy;
}

export interface HostToolGuardOptions {
  timeoutMs?: number;
  signal?: AbortSignal;
}

const audit: HostToolAuditEntry[] = [];
let inFlight = 0;
let mutatingTail: Promise<unknown> = Promise.resolve();

/** Testler arasında bekçi durumunu sıfırlar. */
export function resetHostToolGuard(): void {
  inFlight = 0;
  mutatingTail = Promise.resolve();
  audit.length = 0;
}

/** Kayıtlı son host araç çağrıları (yeniden eskiye). */
export function recentHostToolAudit(): HostToolAuditEntry[] {
  return [...audit];
}

/**
 * Backend `timeout_ms` ile yerel tavanın küçüğünü seçer.
 * Electron, backend'den 500 ms önce bitsin ki anlamlı araç hatası dönsün.
 */
export function hostToolTimeoutMs(name: string, requestedMs?: number): number {
  const local = HOST_TOOL_TIMEOUT_MS[name] ?? DEFAULT_HOST_TOOL_TIMEOUT_MS;
  if (name === 'mcp_call' || name === 'mcp_list_tools') {
    return local;
  }
  if (typeof requestedMs !== 'number' || !Number.isFinite(requestedMs) || requestedMs <= 0) {
    return local;
  }
  const requested = Math.max(1_000, Math.floor(requestedMs) - 500);
  return Math.min(local, requested);
}

/** Yalnızca `open_application` biçimindeki güvenli araç adlarını kabul eder. */
export function sanitizeToolName(raw: unknown): string | null {
  const name = String(raw ?? '')
    .trim()
    .toLowerCase();
  if (!/^[a-z][a-z0-9_]{0,63}$/.test(name)) return null;
  return name;
}

export const sanitizeHostToolName = sanitizeToolName;

function sanitizeValue(value: unknown, depth: number): unknown {
  if (depth <= 0) return null;
  if (value === null) return null;
  const kind = typeof value;
  if (kind === 'string') return (value as string).slice(0, 20_000);
  if (kind === 'number' || kind === 'boolean') return value;
  if (Array.isArray(value)) {
    return value.slice(0, 50).map((item) => sanitizeValue(item, depth - 1));
  }
  if (kind === 'object') {
    const out: Record<string, unknown> = {};
    for (const [key, nested] of Object.entries(value as Record<string, unknown>).slice(
      0,
      MAX_ARG_KEYS,
    )) {
      if (key === '__proto__' || key === 'constructor' || key === 'prototype') continue;
      if (!/^[A-Za-z_][A-Za-z0-9_-]{0,63}$/.test(key)) continue;
      out[key] = sanitizeValue(nested, depth - 1);
    }
    return out;
  }
  return String(value).slice(0, 500);
}

/** Host araç argümanlarını düz nesneye indirger. */
export function sanitizeToolArgs(raw: unknown): Record<string, unknown> {
  if (raw === null || raw === undefined) return {};
  if (typeof raw !== 'object' || Array.isArray(raw)) {
    throw new Error(hostText('Araç argümanları bir nesne olmalı.', 'Tool arguments must be an object.'));
  }
  return sanitizeValue(raw, MAX_ARG_DEPTH) as Record<string, unknown>;
}

export const sanitizeHostToolArgs = sanitizeToolArgs;

/**
 * OI `truncate_output`: baş + son, ortada `[...]`.
 * https://github.com/endolith/open-interpreter/blob/main/interpreter/core/utils/truncate_output.py
 */
export function truncateHostOutput(
  data: string,
  maxOutputChars: number = HOST_MAX_OUTPUT_CHARS,
): string {
  if (maxOutputChars <= 0) {
    throw new Error(hostText('max_output pozitif olmalı.', 'max_output must be positive.'));
  }
  data = redactHostText(data);
  if (data.length <= maxOutputChars) return data;
  const charsPerEnd = Math.floor(maxOutputChars / 2);
  const notice = hostText(
    `Çıktı kısaltıldı (${data.length} karakter). ` +
      `Baştan/sondan ${charsPerEnd} karakter gösteriliyor.\n\n`,
    `Output truncated (${data.length} characters). ` +
      `Showing ${charsPerEnd} characters from the start and end.\n\n`,
  );
  return `${notice}${data.slice(0, charsPerEnd)}\n[...]\n${data.slice(-charsPerEnd)}`;
}

/** Host araç sonucundaki uzun metinleri OI tavanına indirger (görüntü alanları durur). */
export function truncateHostResult(
  result: Record<string, unknown>,
  maxOutputChars: number = HOST_MAX_OUTPUT_CHARS,
): { result: Record<string, unknown>; truncated: boolean } {
  let truncated = false;

  const walk = (value: unknown, key?: string): unknown => {
    if (typeof value === 'string') {
      if (key && BINARY_RESULT_KEYS.has(key)) return value;
      const clean = redactHostText(value);
      if (clean.length <= maxOutputChars) return clean;
      truncated = true;
      return truncateHostOutput(clean, maxOutputChars);
    }
    if (Array.isArray(value)) {
      return value.slice(0, 50).map((item) => walk(item, key));
    }
    if (value && typeof value === 'object') {
      const out: Record<string, unknown> = {};
      for (const [nestedKey, nested] of Object.entries(value as Record<string, unknown>)) {
        out[nestedKey] = walk(nested, nestedKey);
      }
      return out;
    }
    return value;
  };

  return { result: walk(result) as Record<string, unknown>, truncated };
}

/** Open Interpreter execpolicy: salt okunur = safe, yan etkili = unsafe. */
export function classifyHostToolPolicy(name: string): HostExecPolicy {
  return MUTATING_HOST_TOOLS.has(name) ? 'unsafe' : 'safe';
}

function withTimeout<T>(
  work: Promise<T>,
  ms: number,
  name: string,
  signal?: AbortSignal,
): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const fail = (error: Error): void => {
      clearTimeout(timer);
      signal?.removeEventListener('abort', onAbort);
      reject(error);
    };
    const onAbort = (): void => {
      fail(new Error(hostText(`'${name}' iptal edildi.`, `'${name}' was cancelled.`)));
    };
    if (signal?.aborted) {
      reject(new Error(hostText(`'${name}' iptal edildi.`, `'${name}' was cancelled.`)));
      return;
    }
    const timer = setTimeout(() => {
      fail(
        new Error(
          hostText(`'${name}' zaman aşımına uğradı (${ms} ms).`, `'${name}' timed out (${ms} ms).`),
        ),
      );
    }, ms);
    signal?.addEventListener('abort', onAbort, { once: true });
    work.then(
      (value) => {
        clearTimeout(timer);
        signal?.removeEventListener('abort', onAbort);
        resolve(value);
      },
      (error: unknown) => {
        clearTimeout(timer);
        signal?.removeEventListener('abort', onAbort);
        reject(error);
      },
    );
  });
}

function enqueueMutating<T>(fn: () => Promise<T>): Promise<T> {
  const run = mutatingTail.then(fn, fn);
  mutatingTail = run.then(
    () => undefined,
    () => undefined,
  );
  return run;
}

function recordAudit(entry: HostToolAuditEntry): void {
  audit.unshift(entry);
  if (audit.length > MAX_AUDIT) audit.length = MAX_AUDIT;
}

/**
 * Host aracını eşzamanlılık, sıra, zaman aşımı ve iptal kurallarıyla çalıştırır.
 */
export async function runHostToolGuarded<T>(
  name: string,
  fn: () => Promise<T>,
  options: HostToolGuardOptions = {},
): Promise<T> {
  if (options.signal?.aborted) {
    throw new Error(hostText(`'${name}' iptal edildi.`, `'${name}' was cancelled.`));
  }

  const started = Date.now();
  const timeoutMs = hostToolTimeoutMs(name, options.timeoutMs);
  const exec = (): Promise<T> =>
    withTimeout(Promise.resolve().then(fn), timeoutMs, name, options.signal);

  const run = async (): Promise<T> => {
    if (options.signal?.aborted) {
      throw new Error(hostText(`'${name}' iptal edildi.`, `'${name}' was cancelled.`));
    }
    if (inFlight >= MAX_HOST_TOOLS_IN_FLIGHT) {
      throw new Error(
        hostText(
          `Aynı anda en fazla ${MAX_HOST_TOOLS_IN_FLIGHT} host aracı çalışabilir. Lütfen tekrar deneyin.`,
          `At most ${MAX_HOST_TOOLS_IN_FLIGHT} host tools can run at once. Please try again.`,
        ),
      );
    }

    inFlight += 1;
    let success = false;
    let error: string | null = null;
    try {
      const result = await exec();
      success = true;
      return result;
    } catch (caught) {
      error = caught instanceof Error ? caught.message : String(caught);
      throw caught;
    } finally {
      inFlight -= 1;
      recordAudit({
        name,
        success,
        ms: Date.now() - started,
        at: Date.now(),
        error: error ? error.slice(0, 240) : null,
        policy: classifyHostToolPolicy(name),
      });
    }
  };

  return MUTATING_HOST_TOOLS.has(name) ? enqueueMutating(run) : run();
}
