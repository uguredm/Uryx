/** Host araç bekçisi: ad/argüman temizliği, zaman aşımı, eşzamanlılık. */

import { afterEach, describe, expect, it } from 'vitest';

import {
  MCP_HOST_TIMEOUT_MS,
  MCP_INIT_TIMEOUT_MS,
  MCP_RPC_TIMEOUT_MS,
} from '@shared/settings';

import {
  HOST_MAX_OUTPUT_CHARS,
  HOST_TOOL_TIMEOUT_MS,
  MAX_HOST_TOOLS_IN_FLIGHT,
  classifyHostToolPolicy,
  hostToolTimeoutMs,
  resetHostToolGuard,
  runHostToolGuarded,
  sanitizeToolArgs,
  sanitizeToolName,
  truncateHostOutput,
  truncateHostResult,
} from '../electron/host-tools/guard';
import { argvRequestsNewChat, jumpListTasks } from '../electron/windows-desktop';

afterEach(() => {
  resetHostToolGuard();
});

describe('sanitizeToolName', () => {
  it('güvenli adları kabul eder', () => {
    expect(sanitizeToolName('Open_Application')).toBe('open_application');
  });

  it('yol ve boş adları reddeder', () => {
    expect(sanitizeToolName('../rm')).toBeNull();
    expect(sanitizeToolName('')).toBeNull();
    expect(sanitizeToolName('run powershell')).toBeNull();
  });
});

describe('sanitizeToolArgs', () => {
  it('prototype kirliliğini atar', () => {
    const raw = JSON.parse('{"text":"ok","__proto__":{"admin":true},"constructor":"x"}') as Record<
      string,
      unknown
    >;
    const cleaned = sanitizeToolArgs(raw);
    expect(cleaned.text).toBe('ok');
    expect(Object.hasOwn(cleaned, '__proto__')).toBe(false);
    expect(Object.hasOwn(cleaned, 'constructor')).toBe(false);
    expect(Object.getPrototypeOf(cleaned)).toBe(Object.prototype);
  });

  it('dizi argümanı reddeder', () => {
    expect(() => sanitizeToolArgs(['x'])).toThrow(/nesne/i);
  });
});

describe('runHostToolGuarded', () => {
  it('zaman aşımında hata verir', async () => {
    await expect(
      runHostToolGuarded('take_screenshot', () => new Promise(() => undefined), {
        timeoutMs: 1500,
      }),
    ).rejects.toThrow(/zaman aşımı/i);
  });

  it('AbortSignal ile iptal eder', async () => {
    const controller = new AbortController();
    const pending = runHostToolGuarded(
      'get_ram_usage',
      () => new Promise(() => undefined),
      { signal: controller.signal },
    );
    controller.abort();
    await expect(pending).rejects.toThrow(/iptal/i);
  });

  it('eşzamanlılık tavanını uygular', async () => {
    const started = Array.from({ length: MAX_HOST_TOOLS_IN_FLIGHT }, () =>
      runHostToolGuarded(
        'get_ram_usage',
        () => new Promise((resolve) => setTimeout(() => resolve('ok'), 40)),
      ),
    );
    const overflow = runHostToolGuarded('get_cpu_usage', async () => 'late');
    await expect(overflow).rejects.toThrow(/en fazla/i);
    await Promise.all(started);
  });

  it('list+call kuyruğu inFlight slot yemez; salt okunur araç araya girer', async () => {
    let release!: (value: string) => void;
    const first = runHostToolGuarded(
      'mcp_call',
      () => new Promise<string>((resolve) => {
        release = resolve;
      }),
    );
    await new Promise((resolve) => setTimeout(resolve, 15));
    const queued = runHostToolGuarded('mcp_list_tools', async () => 'listed');
    const other = await runHostToolGuarded('get_cpu_usage', async () => 'cpu');
    expect(other).toBe('cpu');
    release('called');
    await expect(first).resolves.toBe('called');
    await expect(queued).resolves.toBe('listed');
  });
});

describe('MCP faz zaman aşımları', () => {
  it('init 40s, rpc 20s; host tavanı init+rpc ve backend 60s altında kalmaz', () => {
    expect(MCP_INIT_TIMEOUT_MS).toBe(40_000);
    expect(MCP_RPC_TIMEOUT_MS).toBe(20_000);
    expect(MCP_HOST_TIMEOUT_MS).toBeGreaterThanOrEqual(MCP_INIT_TIMEOUT_MS + MCP_RPC_TIMEOUT_MS);
    expect(HOST_TOOL_TIMEOUT_MS.mcp_call).toBe(MCP_HOST_TIMEOUT_MS);
    expect(HOST_TOOL_TIMEOUT_MS.mcp_list_tools).toBe(MCP_HOST_TIMEOUT_MS);
    expect(hostToolTimeoutMs('mcp_call')).toBeGreaterThanOrEqual(MCP_INIT_TIMEOUT_MS + MCP_RPC_TIMEOUT_MS);
    expect(hostToolTimeoutMs('mcp_call', 60_000)).toBeGreaterThanOrEqual(
      MCP_INIT_TIMEOUT_MS + MCP_RPC_TIMEOUT_MS,
    );
    expect(hostToolTimeoutMs('mcp_list_tools', 45_000)).toBe(MCP_HOST_TIMEOUT_MS);
  });
});

describe('execpolicy etiketleri', () => {
  it('salt okunuru safe, yan etkilileri unsafe sayar', () => {
    expect(classifyHostToolPolicy('clipboard_read')).toBe('safe');
    expect(classifyHostToolPolicy('list_directory')).toBe('safe');
    expect(classifyHostToolPolicy('get_volume')).toBe('safe');
    expect(classifyHostToolPolicy('copy_file')).toBe('unsafe');
    expect(classifyHostToolPolicy('move_file')).toBe('unsafe');
    expect(classifyHostToolPolicy('create_directory')).toBe('unsafe');
    expect(classifyHostToolPolicy('save_selected_text')).toBe('unsafe');
    expect(classifyHostToolPolicy('rename_file')).toBe('unsafe');
    expect(classifyHostToolPolicy('open_external_url')).toBe('unsafe');
    expect(classifyHostToolPolicy('get_battery_level')).toBe('safe');
    expect(classifyHostToolPolicy('get_file_hash')).toBe('safe');
    expect(classifyHostToolPolicy('duplicate_file')).toBe('unsafe');
    expect(classifyHostToolPolicy('list_printers')).toBe('safe');
    expect(classifyHostToolPolicy('file_exists')).toBe('safe');
    expect(classifyHostToolPolicy('count_file_lines')).toBe('safe');
    expect(classifyHostToolPolicy('is_process_running')).toBe('safe');
    expect(classifyHostToolPolicy('list_open_windows')).toBe('safe');
    expect(classifyHostToolPolicy('get_system_locale')).toBe('safe');
    expect(classifyHostToolPolicy('get_default_browser')).toBe('safe');
    expect(classifyHostToolPolicy('copy_file_path')).toBe('unsafe');
    expect(classifyHostToolPolicy('eject_removable_drive')).toBe('unsafe');
    expect(classifyHostToolPolicy('open_windows_settings')).toBe('unsafe');
    expect(classifyHostToolPolicy('get_system_time')).toBe('safe');
    expect(classifyHostToolPolicy('get_dark_mode')).toBe('safe');
    expect(classifyHostToolPolicy('get_internet_status')).toBe('safe');
    expect(classifyHostToolPolicy('list_startup_apps')).toBe('safe');
    expect(classifyHostToolPolicy('list_logical_drives')).toBe('safe');
    expect(classifyHostToolPolicy('get_recycle_bin_info')).toBe('safe');
    expect(classifyHostToolPolicy('get_special_folder_path')).toBe('safe');
    expect(classifyHostToolPolicy('get_folder_size')).toBe('safe');
    expect(classifyHostToolPolicy('resolve_application_path')).toBe('safe');
    expect(classifyHostToolPolicy('get_default_printer')).toBe('safe');
    expect(classifyHostToolPolicy('get_file_association')).toBe('safe');
    expect(classifyHostToolPolicy('get_power_plan')).toBe('safe');
    expect(classifyHostToolPolicy('get_user_profile_path')).toBe('safe');
    expect(classifyHostToolPolicy('list_nearby_wifi')).toBe('safe');
    expect(classifyHostToolPolicy('list_files_by_extension')).toBe('safe');
    expect(classifyHostToolPolicy('get_newest_file')).toBe('safe');
    expect(classifyHostToolPolicy('is_directory_empty')).toBe('safe');
    expect(classifyHostToolPolicy('get_largest_file')).toBe('safe');
    expect(classifyHostToolPolicy('count_files_by_extension')).toBe('safe');
    expect(classifyHostToolPolicy('list_subdirectories')).toBe('safe');
    expect(classifyHostToolPolicy('list_today_files')).toBe('safe');
    expect(classifyHostToolPolicy('get_last_boot_time')).toBe('safe');
    expect(classifyHostToolPolicy('get_system_model')).toBe('safe');
    expect(classifyHostToolPolicy('get_night_light')).toBe('safe');
    expect(classifyHostToolPolicy('get_bluetooth_status')).toBe('safe');
    expect(classifyHostToolPolicy('get_oldest_file')).toBe('safe');
    expect(classifyHostToolPolicy('count_subdirectories')).toBe('safe');
    expect(classifyHostToolPolicy('get_timezone')).toBe('safe');
    expect(classifyHostToolPolicy('get_temp_folder_path')).toBe('safe');
    expect(classifyHostToolPolicy('get_wallpaper_path')).toBe('safe');
    expect(classifyHostToolPolicy('get_wifi_radio')).toBe('safe');
    expect(classifyHostToolPolicy('get_default_playback_device')).toBe('safe');
    expect(classifyHostToolPolicy('get_drive_label')).toBe('safe');
    expect(classifyHostToolPolicy('get_smallest_file')).toBe('safe');
    expect(classifyHostToolPolicy('list_this_week_files')).toBe('safe');
    expect(classifyHostToolPolicy('get_onedrive_path')).toBe('safe');
    expect(classifyHostToolPolicy('get_cpu_name')).toBe('safe');
    expect(classifyHostToolPolicy('get_gpu_name')).toBe('safe');
    expect(classifyHostToolPolicy('get_ethernet_status')).toBe('safe');
    expect(classifyHostToolPolicy('get_default_recording_device')).toBe('safe');
    expect(classifyHostToolPolicy('get_refresh_rate')).toBe('safe');
    expect(classifyHostToolPolicy('list_yesterday_files')).toBe('safe');
    expect(classifyHostToolPolicy('count_today_files')).toBe('safe');
    expect(classifyHostToolPolicy('get_screen_scale')).toBe('safe');
    expect(classifyHostToolPolicy('get_ram_size')).toBe('safe');
    expect(classifyHostToolPolicy('get_cpu_count')).toBe('safe');
    expect(classifyHostToolPolicy('get_mute_status')).toBe('safe');
    expect(classifyHostToolPolicy('get_drive_filesystem')).toBe('safe');
    expect(classifyHostToolPolicy('get_airplane_mode')).toBe('safe');
    expect(classifyHostToolPolicy('list_this_month_files')).toBe('safe');
    expect(classifyHostToolPolicy('count_yesterday_files')).toBe('safe');
    expect(classifyHostToolPolicy('get_os_version')).toBe('safe');
    expect(classifyHostToolPolicy('get_username')).toBe('safe');
    expect(classifyHostToolPolicy('get_brightness')).toBe('safe');
    expect(classifyHostToolPolicy('get_vpn_status')).toBe('safe');
    expect(classifyHostToolPolicy('get_keyboard_layout')).toBe('safe');
    expect(classifyHostToolPolicy('get_battery_saver')).toBe('safe');
    expect(classifyHostToolPolicy('count_this_week_files')).toBe('safe');
    expect(classifyHostToolPolicy('count_this_month_files')).toBe('safe');
    expect(classifyHostToolPolicy('get_architecture')).toBe('safe');
    expect(classifyHostToolPolicy('get_focus_assist')).toBe('safe');
    expect(classifyHostToolPolicy('get_firewall_status')).toBe('safe');
    expect(classifyHostToolPolicy('get_default_mail_app')).toBe('safe');
    expect(classifyHostToolPolicy('get_screenshots_folder')).toBe('safe');
    expect(classifyHostToolPolicy('get_wifi_signal')).toBe('safe');
    expect(classifyHostToolPolicy('get_uptime')).toBe('safe');
    expect(classifyHostToolPolicy('get_wifi_status')).toBe('safe');
    expect(classifyHostToolPolicy('list_recent_files')).toBe('safe');
    expect(classifyHostToolPolicy('copy_selected_text')).toBe('unsafe');
    expect(classifyHostToolPolicy('lock_workstation')).toBe('unsafe');
    expect(classifyHostToolPolicy('get_selected_text')).toBe('safe');
    expect(classifyHostToolPolicy('get_display_info')).toBe('safe');
    expect(classifyHostToolPolicy('mcp_list_tools')).toBe('unsafe');
    expect(classifyHostToolPolicy('mcp_call')).toBe('unsafe');
    expect(classifyHostToolPolicy('run_powershell')).toBe('unsafe');
    expect(classifyHostToolPolicy('notify_user')).toBe('unsafe');
    expect(classifyHostToolPolicy('open_docker_desktop')).toBe('unsafe');
    expect(classifyHostToolPolicy('browser_open')).toBe('safe');
    expect(classifyHostToolPolicy('browser_list_controls')).toBe('safe');
    expect(classifyHostToolPolicy('browser_click')).toBe('unsafe');
    expect(classifyHostToolPolicy('browser_type')).toBe('unsafe');
    expect(classifyHostToolPolicy('browser_fill_form')).toBe('unsafe');
    expect(HOST_TOOL_TIMEOUT_MS.browser_click).toBe(45_000);
    expect(HOST_TOOL_TIMEOUT_MS.browser_type).toBe(45_000);
    expect(HOST_TOOL_TIMEOUT_MS.browser_fill_form).toBe(45_000);
    expect(HOST_TOOL_TIMEOUT_MS.browser_list_controls).toBe(45_000);
    expect(classifyHostToolPolicy('browser_capture')).toBe('safe');
    expect(classifyHostToolPolicy('list_calendar_events')).toBe('safe');
    expect(classifyHostToolPolicy('list_outlook_tasks')).toBe('safe');
    expect(HOST_TOOL_TIMEOUT_MS.list_calendar_events).toBe(15_000);
    expect(HOST_TOOL_TIMEOUT_MS.list_outlook_tasks).toBe(15_000);
    expect(classifyHostToolPolicy('delete_file')).toBe('unsafe');
  });
});

describe('OI max_output', () => {
  it('kısa metni değiştirmez', () => {
    expect(truncateHostOutput('ok')).toBe('ok');
  });

  it('uzun metni baş+son ve [...] ile keser', () => {
    const data = `${'A'.repeat(2000)}MID${'Z'.repeat(2000)}`;
    const out = truncateHostOutput(data);
    expect(out).toMatch(/kısaltıldı/i);
    expect(out).toContain('[...]');
    expect(out).toContain('AAA');
    expect(out).toContain('ZZZ');
    expect(out).not.toContain('MID');
    expect(out.length).toBeLessThan(data.length);
    expect(out.length).toBeGreaterThan(HOST_MAX_OUTPUT_CHARS);
  });

  it('görüntü alanını kesmez, log metnini keser', () => {
    const text = 'L'.repeat(4000);
    const image = 'iVBORw0KGgo'.repeat(400);
    const { result, truncated } = truncateHostResult({ text, image, path: 'C:\\a.png' });
    expect(truncated).toBe(true);
    expect(String(result.text)).toContain('[...]');
    expect(result.image).toBe(image);
    expect(result.path).toBe('C:\\a.png');
  });
});

describe('Windows argv', () => {
  it('--new-chat bayrağını tanır', () => {
    expect(argvRequestsNewChat(['electron', '--new-chat'])).toBe(true);
    expect(argvRequestsNewChat(['electron'])).toBe(false);
  });

  it('Jump List başlıklarını dile göre ayırır', () => {
    expect(jumpListTasks('tr')[0]?.title).toBe("Uryx'i göster");
    expect(jumpListTasks('en')[0]?.title).toBe('Show Uryx');
    expect(jumpListTasks('en')[1]?.title).toBe('New chat');
  });
});
