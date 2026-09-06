/** IPC whitelist ve host araç yönlendirici testleri. */

import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

import { IPC_EVENT_CHANNELS, IPC_INVOKE_CHANNELS } from '@shared/ipc';
import { rankInstalledApplications, spotifyDeepLink } from '../electron/host-tools/apps';
import { isBrowserLoginWall, normalizePublicWebUrl } from '../electron/host-tools/browser';
import {
  executeHostTool,
  hostCapabilityPayload,
  hostToolNames,
  HOST_TOOLS,
  recentHostToolAudit,
  resetHostToolGuard,
} from '../electron/host-tools';
import { getForegroundWindow, getSelectedText, getVolume, lockWorkstation, copySelectedText } from '../electron/host-tools/system';
import { APPLICATION_ALLOWLIST } from '../electron/security';

describe('IPC kanal whitelist', () => {
  it('invoke kanalları benzersiz', () => {
    expect(new Set(IPC_INVOKE_CHANNELS).size).toBe(IPC_INVOKE_CHANNELS.length);
  });

  it('olay kanalları benzersiz', () => {
    expect(new Set(IPC_EVENT_CHANNELS).size).toBe(IPC_EVENT_CHANNELS.length);
  });

  it('invoke ve olay kanalları çakışmıyor', () => {
    const overlap = IPC_INVOKE_CHANNELS.filter((channel) =>
      (IPC_EVENT_CHANNELS as readonly string[]).includes(channel),
    );
    expect(overlap).toEqual([]);
  });

  it('servis tanı ve Docker kanalları whitelist’te', () => {
    expect(IPC_INVOKE_CHANNELS).toContain('services:diagnose');
    expect(IPC_INVOKE_CHANNELS).toContain('services:openDocker');
    expect(IPC_INVOKE_CHANNELS).toContain('wake:status');
    expect(IPC_INVOKE_CHANNELS).toContain('wake:pushPcm');
  });

  it('tüm kanallar "alan:eylem" biçiminde', () => {
    for (const channel of [...IPC_INVOKE_CHANNELS, ...IPC_EVENT_CHANNELS]) {
      expect(channel).toMatch(/^[a-z]+:[a-zA-Z]+$/);
    }
  });

  it('dosya sistemi veya kabuk erişimi doğrudan açılmamış', () => {
    const forbidden = ['fs:', 'exec:', 'child_process', 'eval', 'require'];
    for (const channel of IPC_INVOKE_CHANNELS) {
      for (const pattern of forbidden) {
        expect(channel.startsWith(pattern)).toBe(false);
      }
    }
  });
});

describe('host araç yönlendirici', () => {
  it('geçersiz araç adını reddeder', async () => {
    resetHostToolGuard();
    const result = await executeHostTool('../rm_rf', {});
    expect(result.success).toBe(false);
    expect(result.error).toMatch(/geçersiz/i);
  });

  it('beklenen araçları içerir', () => {
    const names = hostToolNames();
    expect(names).toContain('mcp_call');
    for (const expected of [
      'open_application',
      'open_media_application',
      'control_media_playback',
      'list_installed_applications',
      'inspect_application',
      'browser_open',
      'browser_read_page',
      'browser_list_controls',
      'browser_click',
      'browser_type',
      'browser_fill_form',
      'browser_capture',
      'browser_save_images',
      'search_files',
      'read_file',
      'get_gpu_usage',
      'clipboard_read',
      'get_selected_text',
      'get_foreground_window',
      'get_display_info',
      'get_idle_time',
      'get_network_interfaces',
      'notify_user',
      'get_docker_engine_status',
      'open_docker_desktop',
      'get_docker_desktop_logs',
      'mcp_list_tools',
      'list_directory',
      'copy_file',
      'get_volume',
      'get_power_status',
      'clipboard_clear',
      'open_recycle_bin',
      'get_uptime',
      'get_wifi_status',
      'move_file',
      'create_directory',
      'get_file_info',
      'list_recent_files',
      'show_in_folder',
      'save_selected_text',
      'get_battery_level',
      'get_computer_info',
      'list_removable_drives',
      'rename_file',
      'get_file_hash',
      'open_external_url',
      'list_printers',
      'duplicate_file',
      'file_exists',
      'copy_file_path',
      'count_file_lines',
      'is_process_running',
      'list_open_windows',
      'get_system_locale',
      'get_default_browser',
      'eject_removable_drive',
      'open_windows_settings',
      'get_system_time',
      'get_dark_mode',
      'get_internet_status',
      'list_startup_apps',
      'list_logical_drives',
      'get_recycle_bin_info',
      'get_special_folder_path',
      'get_folder_size',
      'resolve_application_path',
      'get_default_printer',
      'get_file_association',
      'get_power_plan',
      'get_user_profile_path',
      'list_nearby_wifi',
      'list_files_by_extension',
      'get_newest_file',
      'is_directory_empty',
      'get_largest_file',
      'count_files_by_extension',
      'list_subdirectories',
      'list_today_files',
      'get_last_boot_time',
      'get_system_model',
      'get_night_light',
      'get_bluetooth_status',
      'get_oldest_file',
      'count_subdirectories',
      'get_timezone',
      'get_temp_folder_path',
      'get_wallpaper_path',
      'get_wifi_radio',
      'get_default_playback_device',
      'get_drive_label',
      'get_smallest_file',
      'list_this_week_files',
      'get_onedrive_path',
      'get_cpu_name',
      'get_gpu_name',
      'get_ethernet_status',
      'get_default_recording_device',
      'get_refresh_rate',
      'list_yesterday_files',
      'count_today_files',
      'get_screen_scale',
      'get_ram_size',
      'get_cpu_count',
      'get_mute_status',
      'get_drive_filesystem',
      'get_airplane_mode',
      'list_calendar_events',
      'list_outlook_tasks',
      'list_this_month_files',
      'count_yesterday_files',
      'get_os_version',
      'get_username',
      'get_brightness',
      'get_vpn_status',
      'get_keyboard_layout',
      'get_battery_saver',
      'count_this_week_files',
      'count_this_month_files',
      'get_architecture',
      'get_focus_assist',
      'get_firewall_status',
      'get_default_mail_app',
      'get_screenshots_folder',
      'get_wifi_signal',
      'copy_selected_text',
      'lock_workstation',
      'git_status',
      'run_powershell',
    ]) {
      expect(names).toContain(expected);
    }
  });

  it('bilinmeyen aracı reddeder', async () => {
    const result = await executeHostTool('rm_rf', {});
    expect(result.success).toBe(false);
    expect(result.error).toMatch(/tanımlı bir araç değil/i);
  });

  it('hataları yakalar ve sızdırmaz', async () => {
    const result = await executeHostTool('read_file', {});
    expect(result.success).toBe(false);
    expect(typeof result.error).toBe('string');
    expect(result.error!.length).toBeGreaterThan(0);
  });

  it('izin verilmeyen yolu reddeder', async () => {
    const result = await executeHostTool('read_file', { path: 'C:\\Windows\\win.ini' });
    expect(result.success).toBe(false);
    expect(result.error).toMatch(/izin verilen/i);
  });

  it('host yetenek ilanı araç listesini taşır', () => {
    const payload = hostCapabilityPayload('0.7.1');
    expect(payload.type).toBe('host_capabilities');
    expect(Array.isArray(payload.tools)).toBe(true);
    expect((payload.tools as string[]).includes('run_powershell')).toBe(true);
    expect((payload.features as { cancel?: boolean }).cancel).toBe(true);
    expect((payload.features as { mcp_list?: boolean }).mcp_list).toBe(true);
    expect((payload.features as { max_output?: boolean }).max_output).toBe(true);
    expect((payload.features as { docker_context?: boolean }).docker_context).toBe(true);
    expect((payload.features as { lan_preferred?: boolean }).lan_preferred).toBe(true);
    expect((payload.features as { safe_url?: boolean }).safe_url).toBe(true);
    expect((payload.features as { host_error_class?: boolean }).host_error_class).toBe(true);
    expect((payload.features as { power_resume?: boolean }).power_resume).toBe(true);
    expect((payload.features as { ws_liveness?: boolean }).ws_liveness).toBe(true);
    expect((payload.features as { auth_close?: boolean }).auth_close).toBe(true);
    expect((payload.features as { mcp_win_cmd?: boolean }).mcp_win_cmd).toBe(true);
    expect((payload.features as { reconnect_jitter?: boolean }).reconnect_jitter).toBe(true);
    expect((payload.features as { reconnect_grace?: boolean }).reconnect_grace).toBe(true);
    expect((payload.features as { mcp_stderr?: boolean }).mcp_stderr).toBe(true);
    expect((payload.features as { mcp_env?: boolean }).mcp_env).toBe(true);
    expect((payload.features as { mcp_catalog?: boolean }).mcp_catalog).toBe(true);
  });

  it('her araç bir fonksiyon', () => {
    for (const [name, handler] of Object.entries(HOST_TOOLS)) {
      expect(typeof handler, name).toBe('function');
    }
  });

  it('get_selected_text ve get_foreground_window hayalet değil', async () => {
    expect(HOST_TOOLS.get_selected_text).toBe(getSelectedText);
    expect(HOST_TOOLS.get_foreground_window).toBe(getForegroundWindow);
    expect(getSelectedText.name).toBe('getSelectedText');
    expect(getForegroundWindow.name).toBe('getForegroundWindow');

    resetHostToolGuard();
    const selected = await executeHostTool('get_selected_text', {});
    expect(selected.error ?? '').not.toMatch(/tanımlı bir araç değil|is not a function/i);
    expect(selected.success).toBe(true);
    expect(selected.result).toHaveProperty('text');
    expect(selected.result).toHaveProperty('empty');

    const foreground = await executeHostTool('get_foreground_window', {});
    expect(foreground.error ?? '').not.toMatch(/tanımlı bir araç değil|is not a function/i);
    expect(foreground.success).toBe(true);
    expect(foreground.result).toHaveProperty('title');
    expect(foreground.result).toHaveProperty('pid');
  });

  it('pano araçları çalışır', async () => {
    resetHostToolGuard();
    const write = await executeHostTool('clipboard_write', { text: 'Uryx testi' });
    expect(write.success).toBe(true);

    const read = await executeHostTool('clipboard_read', {});
    expect(read.success).toBe(true);
    expect(read.result.text).toBe('Uryx testi');
    expect(recentHostToolAudit()[0]?.name).toBe('clipboard_read');
  });

  it('list_directory ve copy_file izinli kökte çalışır', async () => {
    resetHostToolGuard();
    const listed = await executeHostTool('list_directory', { path: 'documents' });
    expect(listed.success).toBe(true);
    expect(listed.result.path).toMatch(/Documents/i);
    expect(Array.isArray(listed.result.entries)).toBe(true);

    const source = join(process.env.URYX_TEST_ROOT!, 'Documents', 'kopya-kaynak.txt');
    const destination = join(process.env.URYX_TEST_ROOT!, 'Documents', 'kopya-hedef.txt');
    writeFileSync(source, 'uryx', 'utf8');
    const copied = await executeHostTool('copy_file', { source, destination });
    expect(copied.success).toBe(true);
    expect(copied.result.copied).toBe(true);

    const again = await executeHostTool('copy_file', { source, destination });
    expect(again.success).toBe(false);
    expect(again.error ?? '').toMatch(/zaten var/i);

    const blocked = await executeHostTool('list_directory', { path: 'C:\\Windows' });
    expect(blocked.success).toBe(false);

    const desktop = await executeHostTool('list_directory', { path: 'masaüstü' });
    expect(desktop.success).toBe(true);
    expect(desktop.result.path).toMatch(/Desktop/i);
  });

  it('uptime, wifi ve günlük dosya araçları çalışır', async () => {
    resetHostToolGuard();
    const uptime = await executeHostTool('get_uptime', {});
    expect(uptime.success).toBe(true);
    expect(Number(uptime.result.uptime_seconds)).toBeGreaterThanOrEqual(0);
    expect(typeof uptime.result.uptime_hours).toBe('number');

    const wifi = await executeHostTool('get_wifi_status', {});
    expect(wifi.error ?? '').not.toMatch(/tanımlı bir araç değil|is not a function/i);
    expect(wifi.success).toBe(true);
    expect(typeof wifi.result.connected).toBe('boolean');
    expect(typeof wifi.result.ssid).toBe('string');

    const created = await executeHostTool('create_directory', { path: 'documents/uryx-wave-dir' });
    expect(created.success).toBe(true);
    expect(created.result.created).toBe(true);

    const source = join(process.env.URYX_TEST_ROOT!, 'Documents', 'tasi-kaynak.txt');
    const destination = join(process.env.URYX_TEST_ROOT!, 'Documents', 'tasi-hedef.txt');
    writeFileSync(source, 'tasi', 'utf8');
    const moved = await executeHostTool('move_file', { source, destination });
    expect(moved.success).toBe(true);
    expect(moved.result.moved).toBe(true);
    const again = await executeHostTool('move_file', { source: destination, destination });
    expect(again.success).toBe(false);
    expect(again.error ?? '').toMatch(/zaten var/i);

    const info = await executeHostTool('get_file_info', { path: destination });
    expect(info.success).toBe(true);
    expect(Number(info.result.size)).toBeGreaterThan(0);

    const recent = await executeHostTool('list_recent_files', { path: 'documents', limit: 5 });
    expect(recent.success).toBe(true);
    expect(Array.isArray(recent.result.files)).toBe(true);

    const shown = await executeHostTool('show_in_folder', { path: destination });
    expect(shown.success).toBe(true);
    expect(shown.result.shown).toBe(true);

    const blocked = await executeHostTool('create_directory', { path: 'C:\\Windows\\uryx-nope' });
    expect(blocked.success).toBe(false);
  });

  it('seçim/pano kaydı izinli köke yazar, üzerine yazmaz', async () => {
    resetHostToolGuard();
    const wrote = await executeHostTool('clipboard_write', { text: 'uryx kayit testi' });
    expect(wrote.success).toBe(true);
    const saved = await executeHostTool('save_selected_text', {
      source: 'clipboard',
      path: 'documents/uryx-secim-test.txt',
    });
    expect(saved.success).toBe(true);
    expect(saved.result.saved).toBe(true);
    expect(String(saved.result.path)).toMatch(/Documents/i);
    expect(existsSync(String(saved.result.path))).toBe(true);
    expect(readFileSync(String(saved.result.path), 'utf8')).toContain('uryx kayit testi');

    const again = await executeHostTool('save_selected_text', {
      source: 'clipboard',
      path: 'documents/uryx-secim-test.txt',
    });
    expect(again.success).toBe(false);
    expect(again.error ?? '').toMatch(/zaten var/i);

    const appended = await executeHostTool('save_selected_text', {
      source: 'clipboard',
      path: 'documents/uryx-secim-test.txt',
      mode: 'append',
    });
    expect(appended.success).toBe(true);
    expect(appended.result.appended).toBe(true);

    const blocked = await executeHostTool('save_selected_text', {
      source: 'clipboard',
      path: 'C:\\Windows\\uryx-nope.txt',
    });
    expect(blocked.success).toBe(false);
  });

  it('get_volume, copy_selected_text ve lock_workstation hayalet değil', async () => {
    expect(HOST_TOOLS.lock_workstation).toBe(lockWorkstation);
    expect(HOST_TOOLS.copy_selected_text).toBe(copySelectedText);
    expect(typeof getVolume).toBe('function');
    expect(typeof HOST_TOOLS.get_volume).toBe('function');
    resetHostToolGuard();
    const copied = await executeHostTool('copy_selected_text', {});
    expect(copied.error ?? '').not.toMatch(/tanımlı bir araç değil|is not a function/i);
    expect(copied.success).toBe(true);
    expect(copied.result).toHaveProperty('copied');
    expect(copied.result).toHaveProperty('empty');
  });

  it('boş pano yazımını reddeder', async () => {
    const result = await executeHostTool('clipboard_write', { text: '' });
    expect(result.success).toBe(false);
  });

  it('pano temizleme ve güç durumu çalışır', async () => {
    const cleared = await executeHostTool('clipboard_clear', {});
    expect(cleared.success).toBe(true);
    expect(cleared.result.cleared).toBe(true);
    const power = await executeHostTool('get_power_status', {});
    expect(power.success).toBe(true);
    expect(typeof power.result.on_battery).toBe('boolean');
    expect(typeof power.result.ac).toBe('boolean');
  });

  it('bilgisayar, pil, usb, ad, hash ve dış URL çalışır', async () => {
    resetHostToolGuard();
    const info = await executeHostTool('get_computer_info', {});
    expect(info.success).toBe(true);
    expect(String(info.result.hostname).length).toBeGreaterThan(0);
    expect(String(info.result.username).length).toBeGreaterThan(0);

    const battery = await executeHostTool('get_battery_level', {});
    expect(battery.success).toBe(true);
    expect(typeof battery.result.present).toBe('boolean');

    const usb = await executeHostTool('list_removable_drives', {});
    expect(usb.success).toBe(true);
    expect(Array.isArray(usb.result.drives)).toBe(true);

    const source = join(process.env.URYX_TEST_ROOT!, 'Documents', 'ad-kaynak.txt');
    writeFileSync(source, 'hash-me', 'utf8');
    const hashed = await executeHostTool('get_file_hash', { path: source });
    expect(hashed.success).toBe(true);
    expect(String(hashed.result.hash)).toMatch(/^[a-f0-9]{64}$/);

    const renamed = await executeHostTool('rename_file', { source, name: 'ad-hedef.txt' });
    expect(renamed.success).toBe(true);
    expect(renamed.result.renamed).toBe(true);
    const again = await executeHostTool('rename_file', {
      source: String(renamed.result.destination),
      name: 'ad-hedef.txt',
    });
    expect(again.success).toBe(false);

    const opened = await executeHostTool('open_external_url', { url: 'https://example.com' });
    expect(opened.success).toBe(true);
    expect(String(opened.result.url)).toMatch(/^https:\/\/example\.com/);
    const blocked = await executeHostTool('open_external_url', { url: 'http://127.0.0.1/' });
    expect(blocked.success).toBe(false);

    const printers = await executeHostTool('list_printers', {});
    expect(printers.success).toBe(true);
    expect(Array.isArray(printers.result.printers)).toBe(true);

    const toCopy = join(process.env.URYX_TEST_ROOT!, 'Documents', 'cogalt.txt');
    writeFileSync(toCopy, 'kopya', 'utf8');
    const dup = await executeHostTool('duplicate_file', { path: toCopy });
    expect(dup.success).toBe(true);
    expect(dup.result.duplicated).toBe(true);
    expect(String(dup.result.destination)).toMatch(/-kopya/);
  });

  it('varlık, yol, satır, locale, süreç ve ayar sayfası çalışır', async () => {
    resetHostToolGuard();
    const locale = await executeHostTool('get_system_locale', {});
    expect(locale.success).toBe(true);
    expect(String(locale.result.locale).length).toBeGreaterThan(0);

    const browser = await executeHostTool('get_default_browser', {});
    expect(browser.success).toBe(true);
    expect(typeof browser.result.found).toBe('boolean');

    const target = join(process.env.URYX_TEST_ROOT!, 'Documents', 'satirlar.txt');
    writeFileSync(target, 'a\nb\nc\n', 'utf8');
    const existed = await executeHostTool('file_exists', { path: target });
    expect(existed.success).toBe(true);
    expect(existed.result.exists).toBe(true);
    const missing = await executeHostTool('file_exists', {
      path: join(process.env.URYX_TEST_ROOT!, 'Documents', 'yok-dosya.txt'),
    });
    expect(missing.success).toBe(true);
    expect(missing.result.exists).toBe(false);

    const lined = await executeHostTool('count_file_lines', { path: target });
    expect(lined.success).toBe(true);
    expect(lined.result.lines).toBe(4);

    const copied = await executeHostTool('copy_file_path', { path: target });
    expect(copied.success).toBe(true);
    expect(copied.result.copied).toBe(true);

    const running = await executeHostTool('is_process_running', { name: 'notepad' });
    expect(running.success).toBe(true);
    expect(typeof running.result.running).toBe('boolean');
    const unknown = await executeHostTool('is_process_running', { name: 'rm_rf' });
    expect(unknown.success).toBe(false);

    const windows = await executeHostTool('list_open_windows', {});
    expect(windows.success).toBe(true);
    expect(Array.isArray(windows.result.windows)).toBe(true);

    const badPage = await executeHostTool('open_windows_settings', { page: 'regedit' });
    expect(badPage.success).toBe(false);
    const badLetter = await executeHostTool('eject_removable_drive', { letter: '12' });
    expect(badLetter.success).toBe(false);
  });

  it('saat, internet, çöp bilgisi, klasör ve sürücü çalışır', async () => {
    resetHostToolGuard();
    const clock = await executeHostTool('get_system_time', {});
    expect(clock.success).toBe(true);
    expect(String(clock.result.local).length).toBeGreaterThan(0);
    expect(String(clock.result.timezone).length).toBeGreaterThan(0);

    const dark = await executeHostTool('get_dark_mode', {});
    expect(dark.success).toBe(true);
    expect(typeof dark.result.dark).toBe('boolean');

    const net = await executeHostTool('get_internet_status', {});
    expect(net.success).toBe(true);
    expect(typeof net.result.online).toBe('boolean');

    const startup = await executeHostTool('list_startup_apps', {});
    expect(startup.success).toBe(true);
    expect(Array.isArray(startup.result.apps)).toBe(true);

    const drives = await executeHostTool('list_logical_drives', {});
    expect(drives.success).toBe(true);
    expect(Array.isArray(drives.result.drives)).toBe(true);

    const recycle = await executeHostTool('get_recycle_bin_info', {});
    expect(recycle.success).toBe(true);
    expect(recycle.result.emptied).toBe(false);
    expect(typeof recycle.result.count).toBe('number');

    const folder = await executeHostTool('get_special_folder_path', { folder: 'desktop' });
    expect(folder.success).toBe(true);
    expect(String(folder.result.path).length).toBeGreaterThan(0);

    const sized = await executeHostTool('get_folder_size', {
      path: join(process.env.URYX_TEST_ROOT!, 'Documents'),
    });
    expect(sized.success).toBe(true);
    expect(typeof sized.result.bytes).toBe('number');

    const chrome = await executeHostTool('resolve_application_path', { name: 'notepad' });
    expect(chrome.success).toBe(true);
    const unknown = await executeHostTool('resolve_application_path', { name: 'rm_rf' });
    expect(unknown.success).toBe(false);
  });

  it('yazıcı, uzantı, yeni dosya ve wifi taraması çalışır', async () => {
    resetHostToolGuard();
    const printer = await executeHostTool('get_default_printer', {});
    expect(printer.success).toBe(true);
    expect(typeof printer.result.found).toBe('boolean');

    const assoc = await executeHostTool('get_file_association', { extension: 'txt' });
    expect(assoc.success).toBe(true);
    expect(assoc.result.extension).toBe('.txt');
    const badExt = await executeHostTool('get_file_association', { extension: 'exe' });
    expect(badExt.success).toBe(false);

    const plan = await executeHostTool('get_power_plan', {});
    expect(plan.success).toBe(true);

    const profile = await executeHostTool('get_user_profile_path', {});
    expect(profile.success).toBe(true);
    expect(String(profile.result.path).length).toBeGreaterThan(0);

    const docs = join(process.env.URYX_TEST_ROOT!, 'Documents');
    writeFileSync(join(docs, 'uzanti-ornek.txt'), 'x', 'utf8');
    const listed = await executeHostTool('list_files_by_extension', {
      path: docs,
      extension: 'txt',
    });
    expect(listed.success).toBe(true);
    expect(Number(listed.result.count)).toBeGreaterThan(0);

    const newest = await executeHostTool('get_newest_file', { path: docs });
    expect(newest.success).toBe(true);
    expect(typeof newest.result.found).toBe('boolean');

    const empty = await executeHostTool('is_directory_empty', { path: docs });
    expect(empty.success).toBe(true);
    expect(empty.result.empty).toBe(false);

    const nearby = await executeHostTool('list_nearby_wifi', {});
    expect(nearby.success).toBe(true);
    expect(Array.isArray(nearby.result.networks)).toBe(true);
  });

  it('en büyük, uzantı sayısı, klasör, boot ve model çalışır', async () => {
    resetHostToolGuard();
    const docs = join(process.env.URYX_TEST_ROOT!, 'Documents');
    writeFileSync(join(docs, 'buyuk-ornek.txt'), 'xxxxxxxx', 'utf8');
    const largest = await executeHostTool('get_largest_file', { path: docs });
    expect(largest.success).toBe(true);
    expect(typeof largest.result.found).toBe('boolean');

    const counted = await executeHostTool('count_files_by_extension', {
      path: docs,
      extension: 'txt',
    });
    expect(counted.success).toBe(true);
    expect(Number(counted.result.count)).toBeGreaterThan(0);

    const folders = await executeHostTool('list_subdirectories', { path: docs });
    expect(folders.success).toBe(true);
    expect(Array.isArray(folders.result.folders)).toBe(true);

    const today = await executeHostTool('list_today_files', { path: docs });
    expect(today.success).toBe(true);
    expect(Array.isArray(today.result.files)).toBe(true);

    const boot = await executeHostTool('get_last_boot_time', {});
    expect(boot.success).toBe(true);
    expect(String(boot.result.boot_iso).length).toBeGreaterThan(0);

    const model = await executeHostTool('get_system_model', {});
    expect(model.success).toBe(true);

    const night = await executeHostTool('get_night_light', {});
    expect(night.success).toBe(true);
    expect(typeof night.result.enabled).toBe('boolean');

    const bluetooth = await executeHostTool('get_bluetooth_status', {});
    expect(bluetooth.success).toBe(true);
    expect(typeof bluetooth.result.present).toBe('boolean');
  });

  it('eski dosya, klasör sayısı, dilim ve radyo çalışır', async () => {
    resetHostToolGuard();
    const docs = join(process.env.URYX_TEST_ROOT!, 'Documents');
    writeFileSync(join(docs, 'eski-ornek.txt'), 'y', 'utf8');
    const oldest = await executeHostTool('get_oldest_file', { path: docs });
    expect(oldest.success).toBe(true);
    expect(typeof oldest.result.found).toBe('boolean');

    const folders = await executeHostTool('count_subdirectories', { path: docs });
    expect(folders.success).toBe(true);
    expect(typeof folders.result.count).toBe('number');

    const zone = await executeHostTool('get_timezone', {});
    expect(zone.success).toBe(true);
    expect(String(zone.result.timezone).length).toBeGreaterThan(0);

    const temp = await executeHostTool('get_temp_folder_path', {});
    expect(temp.success).toBe(true);
    expect(String(temp.result.path).length).toBeGreaterThan(0);

    const wallpaper = await executeHostTool('get_wallpaper_path', {});
    expect(wallpaper.success).toBe(true);
    expect(typeof wallpaper.result.found).toBe('boolean');

    const radio = await executeHostTool('get_wifi_radio', {});
    expect(radio.success).toBe(true);
    expect(typeof radio.result.present).toBe('boolean');

    const playback = await executeHostTool('get_default_playback_device', {});
    expect(playback.success).toBe(true);

    const label = await executeHostTool('get_drive_label', { letter: 'C' });
    expect(label.success).toBe(true);
    expect(label.result.letter).toBe('C');
  }, 15_000);

  it('küçük dosya, hafta, işlemci ve mikrofon çalışır', async () => {
    resetHostToolGuard();
    const docs = join(process.env.URYX_TEST_ROOT!, 'Documents');
    writeFileSync(join(docs, 'kucuk-ornek.txt'), 'z', 'utf8');
    const smallest = await executeHostTool('get_smallest_file', { path: docs });
    expect(smallest.success).toBe(true);
    expect(typeof smallest.result.found).toBe('boolean');

    const week = await executeHostTool('list_this_week_files', { path: docs });
    expect(week.success).toBe(true);
    expect(Array.isArray(week.result.files)).toBe(true);

    const onedrive = await executeHostTool('get_onedrive_path', {});
    expect(onedrive.success).toBe(true);
    expect(typeof onedrive.result.found).toBe('boolean');

    const cpu = await executeHostTool('get_cpu_name', {});
    expect(cpu.success).toBe(true);
    expect(String(cpu.result.name).length).toBeGreaterThan(0);

    const gpu = await executeHostTool('get_gpu_name', {});
    expect(gpu.success).toBe(true);

    const ethernet = await executeHostTool('get_ethernet_status', {});
    expect(ethernet.success).toBe(true);
    expect(typeof ethernet.result.present).toBe('boolean');

    const mic = await executeHostTool('get_default_recording_device', {});
    expect(mic.success).toBe(true);

    const hz = await executeHostTool('get_refresh_rate', {});
    expect(hz.success).toBe(true);
    expect(typeof hz.result.hz).toBe('number');
  });

  it('dün, ölçek, çekirdek ve uçak modu çalışır', async () => {
    resetHostToolGuard();
    const docs = join(process.env.URYX_TEST_ROOT!, 'Documents');
    writeFileSync(join(docs, 'dun-ornek.txt'), 'y', 'utf8');
    const yesterday = await executeHostTool('list_yesterday_files', { path: docs });
    expect(yesterday.success).toBe(true);
    expect(Array.isArray(yesterday.result.files)).toBe(true);

    const counted = await executeHostTool('count_today_files', { path: docs });
    expect(counted.success).toBe(true);
    expect(typeof counted.result.count).toBe('number');

    const scale = await executeHostTool('get_screen_scale', {});
    expect(scale.success).toBe(true);
    expect(typeof scale.result.percent).toBe('number');

    const ram = await executeHostTool('get_ram_size', {});
    expect(ram.success).toBe(true);
    expect(Number(ram.result.total_mb)).toBeGreaterThan(0);

    const cores = await executeHostTool('get_cpu_count', {});
    expect(cores.success).toBe(true);
    expect(Number(cores.result.count)).toBeGreaterThan(0);

    const mute = await executeHostTool('get_mute_status', {});
    expect(mute.success).toBe(true);
    expect(typeof mute.result.muted).toBe('boolean');

    const filesystem = await executeHostTool('get_drive_filesystem', { letter: 'C' });
    expect(filesystem.success).toBe(true);
    expect(filesystem.result.letter).toBe('C');

    const airplane = await executeHostTool('get_airplane_mode', {});
    expect(airplane.success).toBe(true);
    expect(typeof airplane.result.found).toBe('boolean');

    const calendar = await executeHostTool('list_calendar_events', {});
    expect(calendar.success).toBe(true);
    expect(typeof calendar.result.found).toBe('boolean');
    if (calendar.result.found) {
      expect(calendar.result.provider).toBe('outlook');
      expect(Array.isArray(calendar.result.items)).toBe(true);
      for (const item of calendar.result.items as Array<Record<string, unknown>>) {
        expect(item).not.toHaveProperty('body');
      }
    } else {
      expect(calendar.result.provider).toBeNull();
    }

    const tasks = await executeHostTool('list_outlook_tasks', {});
    expect(tasks.success).toBe(true);
    expect(typeof tasks.result.found).toBe('boolean');
    if (!tasks.result.found) expect(tasks.result.provider).toBeNull();
  });

  it('ay, vpn, parlaklık ve klavye çalışır', async () => {
    resetHostToolGuard();
    const docs = join(process.env.URYX_TEST_ROOT!, 'Documents');
    writeFileSync(join(docs, 'ay-ornek.txt'), 'm', 'utf8');
    const month = await executeHostTool('list_this_month_files', { path: docs });
    expect(month.success).toBe(true);
    expect(Array.isArray(month.result.files)).toBe(true);

    const counted = await executeHostTool('count_yesterday_files', { path: docs });
    expect(counted.success).toBe(true);
    expect(typeof counted.result.count).toBe('number');

    const osver = await executeHostTool('get_os_version', {});
    expect(osver.success).toBe(true);
    expect(String(osver.result.caption || osver.result.version).length).toBeGreaterThan(0);

    const user = await executeHostTool('get_username', {});
    expect(user.success).toBe(true);
    expect(String(user.result.username).length).toBeGreaterThan(0);

    const bright = await executeHostTool('get_brightness', {});
    expect(bright.success).toBe(true);
    expect(typeof bright.result.found).toBe('boolean');

    const vpn = await executeHostTool('get_vpn_status', {});
    expect(vpn.success).toBe(true);
    expect(typeof vpn.result.connected).toBe('boolean');

    const keyboard = await executeHostTool('get_keyboard_layout', {});
    expect(keyboard.success).toBe(true);

    const saver = await executeHostTool('get_battery_saver', {});
    expect(saver.success).toBe(true);
    expect(typeof saver.result.enabled).toBe('boolean');
  });

  it('hafta sayı, sinyal, güvenlik ve posta çalışır', async () => {
    resetHostToolGuard();
    const docs = join(process.env.URYX_TEST_ROOT!, 'Documents');
    writeFileSync(join(docs, 'hafta-ornek.txt'), 'w', 'utf8');
    const week = await executeHostTool('count_this_week_files', { path: docs });
    expect(week.success).toBe(true);
    expect(typeof week.result.count).toBe('number');

    const month = await executeHostTool('count_this_month_files', { path: docs });
    expect(month.success).toBe(true);
    expect(typeof month.result.count).toBe('number');

    const arch = await executeHostTool('get_architecture', {});
    expect(arch.success).toBe(true);
    expect(Number(arch.result.bits)).toBeGreaterThan(0);

    const focus = await executeHostTool('get_focus_assist', {});
    expect(focus.success).toBe(true);
    expect(typeof focus.result.enabled).toBe('boolean');

    const firewall = await executeHostTool('get_firewall_status', {});
    expect(firewall.success).toBe(true);
    expect(typeof firewall.result.enabled).toBe('boolean');

    const mail = await executeHostTool('get_default_mail_app', {});
    expect(mail.success).toBe(true);

    const shots = await executeHostTool('get_screenshots_folder', {});
    expect(shots.success).toBe(true);
    expect(String(shots.result.path).length).toBeGreaterThan(0);

    const signal = await executeHostTool('get_wifi_signal', {});
    expect(signal.success).toBe(true);
    expect(typeof signal.result.found).toBe('boolean');
  });

  it('ekran ve boşta kalma araçları çalışır', async () => {
    const display = await executeHostTool('get_display_info', {});
    expect(display.success).toBe(true);
    expect(display.result.count).toBeGreaterThan(0);

    const idle = await executeHostTool('get_idle_time', {});
    expect(idle.success).toBe(true);
    expect(typeof idle.result.idle_seconds).toBe('number');
  });

  it('boş bildirimi reddeder', async () => {
    const result = await executeHostTool('notify_user', { title: 'x', body: '' });
    expect(result.success).toBe(false);
  });

  it('RAM bilgisi döndürür', async () => {
    const result = await executeHostTool('get_ram_usage', {});
    expect(result.success).toBe(true);
    expect(Number(result.result.total_mb)).toBeGreaterThan(0);
    expect(Number(result.result.percent)).toBeGreaterThanOrEqual(0);
  });

  it('kendi sürecini sonlandırmayı reddeder', async () => {
    const result = await executeHostTool('kill_process', { pid: process.pid });
    expect(result.success).toBe(false);
    expect(result.error).toMatch(/kendi sürecini/i);
  });

  it('sistem süreçlerini korur', async () => {
    const result = await executeHostTool('kill_process', { pid: 4 });
    expect(result.success).toBe(false);
  });

  it('Spotify protokolünü allowlist üzerinden seçer (gerçek uygulamayı açmaz)', async () => {
    expect(APPLICATION_ALLOWLIST.spotify?.command).toBe('spotify:');
    const result = await executeHostTool('open_application', { name: 'spotify' });
    expect(result.success).toBe(true);
    expect(result.result.method).toBe('protocol');
    expect(result.result.target).toBe('spotify:');
  });

  it('Spotify için doğrulanmış deep-link veya güvenli arama üretir', () => {
    expect(
      spotifyDeepLink(
        'Daft Punk Get Lucky',
        'https://open.spotify.com/track/2Foc5Q5nqNiosCNqttzHof',
      ),
    ).toBe('spotify:track:2Foc5Q5nqNiosCNqttzHof');
    expect(
      spotifyDeepLink('Beğendiklerim', '', 'liked'),
    ).toBe('spotify:collection:tracks');
  });

  it('MCP kapalıyken çağrıyı reddeder', async () => {
    const result = await executeHostTool('mcp_call', {
      server: 'spotify',
      tool: 'search',
      arguments: {},
    });
    expect(result.success).toBe(false);
    expect(result.error).toMatch(/MCP kapalı|MCP is off/i);
  });

  it('geçersiz Spotify medya kontrolünü reddeder', async () => {
    const result = await executeHostTool('control_media_playback', {
      app: 'spotify',
      action: 'delete-library',
    });
    expect(result.success).toBe(false);
    expect(result.error).toMatch(/geçerli bir medya kontrolü/i);
  });

  it('kurulu uygulamaları görünen ad ve küçük yazım hatasıyla eşleştirir', () => {
    const apps = [
      { name: 'Visual Studio Code', appId: 'Microsoft.VisualStudioCode' },
      { name: 'Spotify', appId: 'spotify.exe' },
    ];
    expect(rankInstalledApplications('Spotify uygulaması', apps)[0]?.app.name).toBe('Spotify');
    expect(rankInstalledApplications('Spotfy', apps)[0]?.app.name).toBe('Spotify');
  });

  it('tarayıcıda yalnızca genel HTTP(S) adreslerine izin verir', () => {
    expect(normalizePublicWebUrl('instagram.com/meganfox/')).toBe(
      'https://instagram.com/meganfox/',
    );
    expect(() => normalizePublicWebUrl('file:///C:/Windows/win.ini')).toThrow(/HTTP/i);
    expect(() => normalizePublicWebUrl('http://127.0.0.1:8080')).toThrow(/özel ağ/i);
    expect(() => normalizePublicWebUrl('http://192.168.1.10')).toThrow(/özel ağ/i);
  });

  it('tıklama/yazma açık sayfa yokken reddeder; özel ağ tıklamada da yasak', async () => {
    resetHostToolGuard();
    const click = await executeHostTool('browser_click', { index: 0 });
    expect(click.success).toBe(false);
    const typed = await executeHostTool('browser_type', { index: 0, text: 'deneme' });
    expect(typed.success).toBe(false);
    expect(() => normalizePublicWebUrl('http://127.0.0.1/login')).toThrow(/özel ağ/i);
    expect(() => normalizePublicWebUrl('file:///C:/secret.html')).toThrow(/HTTP/i);
  });

  it('Instagram giriş duvarını tanır', () => {
    expect(
      isBrowserLoginWall('https://www.instagram.com/accounts/login/?next=/p/abc/', 'Instagram'),
    ).toBe(true);
    expect(isBrowserLoginWall('https://www.instagram.com/p/abc/', 'Login • Instagram')).toBe(true);
    expect(
      isBrowserLoginWall('https://www.instagram.com/p/abc/', 'Megan Fox', 'Beğeni ve yorumlar'),
    ).toBe(false);
    expect(isBrowserLoginWall('https://example.com/login', 'Giriş yap')).toBe(false);
  });
});
