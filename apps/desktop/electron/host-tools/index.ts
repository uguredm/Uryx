/**
 * Host araç yönlendiricisi.
 *
 * Backend'in `/ws/host` üzerinden gönderdiği `host_tool_request` mesajları
 * buraya düşer. Bu tablo **ikinci bir allowlist** katmanıdır: backend'de
 * tanımlı olsa bile burada karşılığı olmayan bir araç çalıştırılamaz.
 */

import { hostT } from '../host-i18n';
import {
  classifyHostToolPolicy,
  runHostToolGuarded,
  sanitizeToolArgs,
  sanitizeToolName,
  truncateHostResult,
} from './guard';
import { listCalendarEvents, listOutlookTasks } from './outlook';
import { formatHostError } from './host-error';
import { bindHostAbortSignal, runWithHostAbort } from './process';
import { getDockerDesktopLogsTool, getDockerEngineStatus, openDockerDesktopTool } from './compose';
import { callMcpTool, listMcpTools, mcpCapabilitySnapshot } from './mcp';
import {
  closeApplication,
  controlMediaPlayback,
  inspectApplication,
  listInstalledApplicationsTool,
  openApplication,
  openFolder,
  openMediaApplication,
  openRecycleBin,
  openVSCode,
  openWindowsSettings,
  getRecycleBinInfo,
  resolveApplicationPath,
} from './apps';
import {
  captureBrowserPage,
  clickBrowserControl,
  fillBrowserForm,
  listBrowserControls,
  openBrowserPage,
  openExternalUrl,
  readBrowserPage,
  saveBrowserImages,
  scrollBrowserPage,
  typeBrowserControl,
} from './browser';
import {
  copyFilePath,
  copyFileTool,
  countFileLines,
  duplicateFileTool,
  createDirectoryTool,
  createFile,
  deleteFile,
  editFile,
  fileExists,
  getFileHash,
  getFileInfo,
  getFolderSize,
  getNewestFile,
  getLargestFile,
  getOldestFile,
  getSmallestFile,
  getSpecialFolderPath,
  isDirectoryEmpty,
  countFilesByExtension,
  countSubdirectories,
  listDirectory,
  listFilesByExtension,
  listSubdirectories,
  listTodayFiles,
  listThisWeekFiles,
  listYesterdayFiles,
  countTodayFiles,
  listThisMonthFiles,
  countYesterdayFiles,
  countThisWeekFiles,
  countThisMonthFiles,
  listRecentFiles,
  moveFileTool,
  renameFileTool,
  readTextFile,
  saveSelectedText,
  searchFiles,
  showInFolder,
} from './files';
import { gitCommit, gitPush, gitStatus } from './shell';
import { runCmdTool, runPowerShellTool } from './shell';
import {
  clipboardClear,
  clipboardRead,
  clipboardWrite,
  copySelectedText,
  ejectRemovableDrive,
  getBatteryLevel,
  getComputerInfo,
  getDefaultBrowser,
  getDefaultPrinter,
  getFileAssociation,
  getLastBootTime,
  getNightLight,
  getBluetoothStatus,
  getTimezone,
  getTempFolderPath,
  getWallpaperPath,
  getWifiRadio,
  getDefaultPlaybackDevice,
  getDriveLabel,
  getOnedrivePath,
  getCpuName,
  getGpuName,
  getEthernetStatus,
  getDefaultRecordingDevice,
  getRefreshRate,
  getScreenScale,
  getRamSize,
  getCpuCount,
  getMuteStatus,
  getDriveFilesystem,
  getAirplaneMode,
  getOsVersion,
  getUsername,
  getBrightness,
  getVpnStatus,
  getKeyboardLayout,
  getBatterySaver,
  getArchitecture,
  getFocusAssist,
  getFirewallStatus,
  getDefaultMailApp,
  getScreenshotsFolder,
  getWifiSignal,
  getSystemModel,
  getPowerPlan,
  getPowerStatus,
  getUserProfilePath,
  listNearbyWifi,
  getSystemLocale,
  getSystemTime,
  getDarkMode,
  getInternetStatus,
  getUptime,
  listLogicalDrives,
  listStartupApps,
  getWifiStatus,
  listPrinters,
  listRemovableDrives,
  getCpuUsage,
  getDiskUsage,
  getDisplayInfo,
  getForegroundWindow,
  isProcessRunning,
  listOpenWindows,
  getGpuUsage,
  getIdleTime,
  getNetworkInterfaces,
  getRamUsage,
  getSelectedText,
  getVolume,
  killProcess,
  listProcesses,
  lockWorkstation,
  notifyUser,
  setVolume,
  takeScreenshot,
} from './system';

export type HostToolHandler = (
  args: Record<string, unknown>,
) => Promise<Record<string, unknown>> | Record<string, unknown>;

/** Çalıştırılmasına izin verilen host araçları. */
export const HOST_TOOLS: Record<string, HostToolHandler> = {
  open_application: openApplication,
  open_media_application: openMediaApplication,
  control_media_playback: controlMediaPlayback,
  list_installed_applications: listInstalledApplicationsTool,
  inspect_application: inspectApplication,
  close_application: closeApplication,
  open_vscode: openVSCode,
  open_folder: openFolder,
  open_recycle_bin: openRecycleBin,
  get_recycle_bin_info: getRecycleBinInfo,
  open_windows_settings: openWindowsSettings,
  resolve_application_path: resolveApplicationPath,

  browser_open: openBrowserPage,
  open_external_url: openExternalUrl,
  browser_read_page: readBrowserPage,
  browser_list_controls: listBrowserControls,
  browser_click: clickBrowserControl,
  browser_type: typeBrowserControl,
  browser_fill_form: fillBrowserForm,
  browser_scroll: scrollBrowserPage,
  browser_capture: captureBrowserPage,
  browser_save_images: saveBrowserImages,

  search_files: searchFiles,
  read_file: readTextFile,
  create_file: createFile,
  edit_file: editFile,
  delete_file: deleteFile,
  list_directory: listDirectory,
  copy_file: copyFileTool,
  move_file: moveFileTool,
  rename_file: renameFileTool,
  duplicate_file: duplicateFileTool,
  get_file_hash: getFileHash,
  file_exists: fileExists,
  copy_file_path: copyFilePath,
  count_file_lines: countFileLines,
  create_directory: createDirectoryTool,
  get_file_info: getFileInfo,
  get_special_folder_path: getSpecialFolderPath,
  get_folder_size: getFolderSize,
  list_files_by_extension: listFilesByExtension,
  get_newest_file: getNewestFile,
  is_directory_empty: isDirectoryEmpty,
  get_largest_file: getLargestFile,
  count_files_by_extension: countFilesByExtension,
  list_subdirectories: listSubdirectories,
  list_today_files: listTodayFiles,
  get_oldest_file: getOldestFile,
  count_subdirectories: countSubdirectories,
  get_smallest_file: getSmallestFile,
  list_this_week_files: listThisWeekFiles,
  list_yesterday_files: listYesterdayFiles,
  count_today_files: countTodayFiles,
  list_this_month_files: listThisMonthFiles,
  count_yesterday_files: countYesterdayFiles,
  count_this_week_files: countThisWeekFiles,
  count_this_month_files: countThisMonthFiles,
  list_recent_files: listRecentFiles,
  show_in_folder: showInFolder,
  save_selected_text: saveSelectedText,

  get_cpu_usage: getCpuUsage,
  get_ram_usage: () => getRamUsage(),
  get_gpu_usage: async () => ({ ...(await getGpuUsage()) }),
  get_disk_usage: getDiskUsage,
  list_processes: listProcesses,
  is_process_running: isProcessRunning,
  kill_process: killProcess,
  set_volume: setVolume,
  get_volume: () => getVolume(),
  take_screenshot: takeScreenshot,
  clipboard_read: () => clipboardRead(),
  clipboard_write: clipboardWrite,
  clipboard_clear: () => clipboardClear(),
  get_power_status: () => getPowerStatus(),
  get_battery_level: () => getBatteryLevel(),
  get_computer_info: () => getComputerInfo(),
  get_system_locale: () => getSystemLocale(),
  get_system_time: () => getSystemTime(),
  get_dark_mode: () => getDarkMode(),
  get_internet_status: () => getInternetStatus(),
  list_startup_apps: () => listStartupApps(),
  get_default_browser: () => getDefaultBrowser(),
  list_removable_drives: () => listRemovableDrives(),
  list_logical_drives: () => listLogicalDrives(),
  eject_removable_drive: ejectRemovableDrive,
  list_printers: () => listPrinters(),
  get_default_printer: () => getDefaultPrinter(),
  get_file_association: getFileAssociation,
  get_power_plan: () => getPowerPlan(),
  get_user_profile_path: () => getUserProfilePath(),
  get_uptime: () => getUptime(),
  get_wifi_status: () => getWifiStatus(),
  list_nearby_wifi: () => listNearbyWifi(),
  get_last_boot_time: () => getLastBootTime(),
  get_system_model: () => getSystemModel(),
  get_night_light: () => getNightLight(),
  get_bluetooth_status: () => getBluetoothStatus(),
  get_timezone: () => getTimezone(),
  get_temp_folder_path: () => getTempFolderPath(),
  get_wallpaper_path: () => getWallpaperPath(),
  get_wifi_radio: () => getWifiRadio(),
  get_default_playback_device: () => getDefaultPlaybackDevice(),
  get_drive_label: getDriveLabel,
  get_onedrive_path: () => getOnedrivePath(),
  get_cpu_name: () => getCpuName(),
  get_gpu_name: () => getGpuName(),
  get_ethernet_status: () => getEthernetStatus(),
  get_default_recording_device: () => getDefaultRecordingDevice(),
  get_refresh_rate: () => getRefreshRate(),
  get_screen_scale: () => getScreenScale(),
  get_ram_size: () => getRamSize(),
  get_cpu_count: () => getCpuCount(),
  get_mute_status: () => getMuteStatus(),
  get_drive_filesystem: getDriveFilesystem,
  get_airplane_mode: () => getAirplaneMode(),
  list_calendar_events: listCalendarEvents,
  list_outlook_tasks: listOutlookTasks,
  get_os_version: () => getOsVersion(),
  get_username: () => getUsername(),
  get_brightness: () => getBrightness(),
  get_vpn_status: () => getVpnStatus(),
  get_keyboard_layout: () => getKeyboardLayout(),
  get_battery_saver: () => getBatterySaver(),
  get_architecture: () => getArchitecture(),
  get_focus_assist: () => getFocusAssist(),
  get_firewall_status: () => getFirewallStatus(),
  get_default_mail_app: () => getDefaultMailApp(),
  get_screenshots_folder: () => getScreenshotsFolder(),
  get_wifi_signal: () => getWifiSignal(),
  copy_selected_text: copySelectedText,
  lock_workstation: lockWorkstation,
  get_selected_text: getSelectedText,
  get_foreground_window: getForegroundWindow,
  list_open_windows: listOpenWindows,
  get_display_info: () => getDisplayInfo(),
  get_idle_time: () => getIdleTime(),
  get_network_interfaces: () => getNetworkInterfaces(),
  notify_user: notifyUser,
  get_docker_engine_status: getDockerEngineStatus,
  open_docker_desktop: openDockerDesktopTool,
  get_docker_desktop_logs: getDockerDesktopLogsTool,

  git_status: gitStatus,
  git_commit: gitCommit,
  git_push: gitPush,

  run_powershell: runPowerShellTool,
  run_cmd: runCmdTool,

  mcp_call: callMcpTool,
  mcp_list_tools: async (args) => {
    const result = await listMcpTools(args);
    requestHostCapabilitiesRefresh();
    return result;
  },
};

export interface HostToolOutcome {
  success: boolean;
  result: Record<string, unknown>;
  error: string | null;
}

/**
 * Host aracını çalıştırır.
 *
 * Hiçbir hata dışarı sızdırılmaz; hepsi `{success:false, error}` olarak döner
 * ki backend tarafı LLM'e anlamlı bir hata mesajı verebilsin.
 */
export interface ExecuteHostToolOptions {
  timeoutMs?: number;
  signal?: AbortSignal;
}

export async function executeHostTool(
  toolName: string,
  args: Record<string, unknown>,
  options: ExecuteHostToolOptions = {},
): Promise<HostToolOutcome> {
  const name = sanitizeToolName(toolName);
  if (!name) {
    return {
      success: false,
      result: {},
      error: hostT('host.unknownTool'),
    };
  }

  const handler = HOST_TOOLS[name];
  if (!handler) {
    return {
      success: false,
      result: {},
      error: hostT('host.undefinedTool', { name }),
    };
  }

  return runWithHostAbort(options.signal, async () => {
    const unbind = bindHostAbortSignal(options.signal);
    try {
      const safeArgs = sanitizeToolArgs(args ?? {});
      const result = await runHostToolGuarded(
        name,
        () => Promise.resolve(handler(safeArgs)),
        { timeoutMs: options.timeoutMs, signal: options.signal },
      );
      const capped = truncateHostResult(result ?? {});
      return {
        success: true,
        result: {
          ...capped.result,
          execution_policy: classifyHostToolPolicy(name),
          ...(capped.truncated ? { output_truncated: true } : {}),
        },
        error: null,
      };
    } catch (error) {
      return { success: false, result: {}, error: formatHostError(error).slice(0, 800) };
    } finally {
      unbind();
    }
  });
}

/** Jan/Continue MCP `tools/list` kalıbı — köprü açılınca backend'e ilan edilir. */
export function hostCapabilityPayload(version: string): Record<string, unknown> {
  return {
    type: 'host_capabilities',
    tools: hostToolNames(),
    platform: process.platform,
    arch: process.arch,
    version,
    features: {
      cancel: true,
      timeout: true,
      docker_compose: true,
      nvidia_smi: process.platform === 'win32' || process.platform === 'linux',
      powershell: process.platform === 'win32',
      mcp: true,
      selected_text: process.platform === 'win32',
      foreground_window: process.platform === 'win32',
      display: true,
      idle: true,
      power_status: true,
      notify: true,
      docker_engine: true,
      docker_logs: true,
      mcp_list: true,
      process_tree_cancel: true,
      max_output: true,
      cancel_ack: true,
      docker_context: true,
      lan_preferred: true,
      safe_url: true,
      host_error_class: true,
      power_resume: true,
      ws_liveness: true,
      auth_close: true,
      mcp_win_cmd: true,
      reconnect_jitter: true,
      reconnect_grace: true,
      mcp_stderr: true,
      mcp_env: true,
      mcp_catalog: true,
    },
    mcp: mcpCapabilitySnapshot(),
  };
}

let capabilitiesRefreshSink: (() => void) | null = null;

/** Köprü, MCP list / ayar sonrası yetenekleri yeniden ilan eder. */
export function setHostCapabilitiesRefreshSink(sink: (() => void) | null): void {
  capabilitiesRefreshSink = sink;
}

export function requestHostCapabilitiesRefresh(): void {
  capabilitiesRefreshSink?.();
}

/** Kayıtlı host araçlarının adları. */
export function hostToolNames(): string[] {
  return Object.keys(HOST_TOOLS).sort();
}

/** Son host araç çağrıları (köprü durum ekranı). */
export { recentHostToolAudit, resetHostToolGuard } from './guard';
