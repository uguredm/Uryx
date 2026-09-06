/** MCP SDK allowlist + VS Code dangerous-env strip. */

import { describe, expect, it } from 'vitest';

import {
  mcpChildEnv,
  mcpFallbackPath,
  mcpInheritedKeys,
  sanitizeInheritedEnvValue,
} from '../electron/host-tools/mcp-env';

describe('MCP child env', () => {
  it('GH_TOKEN ve NODE_OPTIONS düşer, PATH kalır', () => {
    const env = mcpChildEnv(
      {
        PATH: 'C:\\Windows\\System32',
        GH_TOKEN: 'ghs_secret',
        GITHUB_TOKEN: 'gho_secret',
        NODE_OPTIONS: '--inspect=127.0.0.1:9229',
        DEBUG: '*',
        URYX_API_TOKEN: 'leak',
      },
      'win32',
    );
    expect(env.PATH).toBe('C:\\Windows\\System32');
    expect(env.PYTHONIOENCODING).toBe('utf-8');
    expect(env.PYTHONUNBUFFERED).toBe('1');
    expect(env.PYTHONUTF8).toBe('1');
    expect(env.PYTHONSAFEPATH).toBe('1');
    expect(env.PYTHONDONTWRITEBYTECODE).toBe('1');
    expect(env.npm_config_yes).toBe('true');
    expect(env.npm_config_update_notifier).toBe('false');
    expect(env.NO_COLOR).toBe('1');
    expect(env.FORCE_COLOR).toBe('0');
    expect(env.GH_TOKEN).toBeUndefined();
    expect(env.GITHUB_TOKEN).toBeUndefined();
    expect(env.NODE_OPTIONS).toBeUndefined();
    expect(env.DEBUG).toBeUndefined();
    expect(env.URYX_API_TOKEN).toBeUndefined();
  });

  it('() fonksiyon değeri atlanır', () => {
    const env = mcpChildEnv({ PATH: '() { :; }; echo pwn', HOME: '/home/j' }, 'linux');
    expect(env.PATH).toBe('/usr/bin:/bin');
    expect(env.HOME).toBe('/home/j');
  });

  it('win32 PATHEXT/COMSPEC alır, linux APPDATA almaz', () => {
    expect(mcpInheritedKeys('win32')).toContain('PATHEXT');
    expect(mcpInheritedKeys('win32')).toContain('COMSPEC');
    expect(mcpInheritedKeys('linux')).toContain('LANG');
    expect(mcpInheritedKeys('linux')).not.toContain('APPDATA');
    expect(mcpInheritedKeys('linux')).not.toContain('LD_LIBRARY_PATH');
    const linux = mcpChildEnv({ APPDATA: 'C:\\leak', PATH: '/usr/bin' }, 'linux');
    expect(linux.APPDATA).toBeUndefined();
    expect(linux.PATH).toBe('/usr/bin');
  });

  it('sunucu env allowlist geçer, GH_TOKEN ve NODE_OPTIONS geçmez', () => {
    const env = mcpChildEnv(
      { PATH: '/usr/bin', GH_TOKEN: 'ghs_secret' },
      'linux',
      {
        CONTEXT7_API_KEY: 'ctx7sk_user',
        GH_TOKEN: 'ghs_injected',
        NODE_OPTIONS: '--inspect',
      },
    );
    expect(env.CONTEXT7_API_KEY).toBe('ctx7sk_user');
    expect(env.GH_TOKEN).toBeUndefined();
    expect(env.NODE_OPTIONS).toBeUndefined();
  });

  it('GITHUB_PERSONAL_ACCESS_TOKEN sunucu env ile geçer, süreç GH_TOKEN geçmez', () => {
    const env = mcpChildEnv(
      { PATH: '/usr/bin', GH_TOKEN: 'ghs_secret', GITHUB_PERSONAL_ACCESS_TOKEN: 'from_process' },
      'linux',
      { GITHUB_PERSONAL_ACCESS_TOKEN: 'from_settings' },
    );
    expect(env.GITHUB_PERSONAL_ACCESS_TOKEN).toBe('from_settings');
    expect(env.GH_TOKEN).toBeUndefined();
  });

  it('TRANSPORT ve MCP_TRANSPORT_TYPE allowlist dışı kalır', () => {
    const env = mcpChildEnv(
      { PATH: '/usr/bin' },
      'linux',
      { TRANSPORT: 'http', MCP_TRANSPORT_TYPE: 'http', BRAVE_API_KEY: 'BSA_ok' },
    );
    expect(env.TRANSPORT).toBeUndefined();
    expect(env.MCP_TRANSPORT_TYPE).toBeUndefined();
    expect(env.BRAVE_API_KEY).toBe('BSA_ok');
  });

  it('DDG_REGION allowlist geçer, HTTP_PROXY geçmez', () => {
    const env = mcpChildEnv(
      { PATH: '/usr/bin', HTTP_PROXY: 'http://evil' },
      'linux',
      { DDG_REGION: 'tr-tr', DDG_SAFE_SEARCH: 'MODERATE', HTTP_PROXY: 'http://injected' },
    );
    expect(env.DDG_REGION).toBe('tr-tr');
    expect(env.DDG_SAFE_SEARCH).toBe('MODERATE');
    expect(env.HTTP_PROXY).toBeUndefined();
  });

  it('LibreTranslate ve Nominatim UA allowlist geçer, süreç sızıntısı yok', () => {
    const env = mcpChildEnv(
      {
        PATH: '/usr/bin',
        LIBRETRANSLATE_API_KEY: 'from_process',
        GEOCODE_USER_AGENT: 'from_process',
      },
      'linux',
      {
        LIBRETRANSLATE_API_URL: 'http://127.0.0.1:5000',
        LIBRETRANSLATE_API_KEY: 'from_settings',
        GEOCODE_USER_AGENT: 'Uryx local assistant',
      },
    );
    expect(env.LIBRETRANSLATE_API_URL).toBe('http://127.0.0.1:5000');
    expect(env.LIBRETRANSLATE_API_KEY).toBe('from_settings');
    expect(env.GEOCODE_USER_AGENT).toBe('Uryx local assistant');
  });

  it('env değerindeki CR/LF ve ELECTRON_RUN_AS_NODE düşer', () => {
    const env = mcpChildEnv(
      { PATH: '/usr/bin\nbad', HOME: '/home/j' },
      'linux',
      {
        LIBRETRANSLATE_API_URL: 'http://127.0.0.1:5000\r\nX-Injected: 1',
        ELECTRON_RUN_AS_NODE: '1',
      },
    );
    expect(env.PATH).toBe('/usr/bin');
    expect(env.LIBRETRANSLATE_API_URL).toBeUndefined();
    expect(env.ELECTRON_RUN_AS_NODE).toBeUndefined();
  });

  it('win32 HOME yoksa USERPROFILE, linux LANG yoksa C.UTF-8', () => {
    const win = mcpChildEnv({ PATH: 'C:\\Windows', USERPROFILE: 'C:\\Users\\uryx' }, 'win32');
    expect(win.HOME).toBe('C:\\Users\\uryx');
    const linux = mcpChildEnv({ PATH: '/usr/bin', HOME: '/home/j' }, 'linux');
    expect(linux.LANG).toBe('C.UTF-8');
    expect(sanitizeInheritedEnvValue('C:\\Windows\\System32\r\n')).toBe('C:\\Windows\\System32');
    expect(sanitizeInheritedEnvValue('"C:\\Program Files\\nodejs;C:\\Windows"')).toBe(
      'C:\\Program Files\\nodejs;C:\\Windows',
    );
    expect(sanitizeInheritedEnvValue("'/usr/bin:/bin'")).toBe('/usr/bin:/bin');
    expect(sanitizeInheritedEnvValue('() { :; }; pwn')).toBeUndefined();
    expect(mcpFallbackPath('win32', { SYSTEMROOT: 'C:\\Windows' })).toBe('C:\\Windows\\System32;C:\\Windows');
    expect(mcpFallbackPath('linux')).toBe('/usr/bin:/bin');
    expect(mcpChildEnv({ HOME: '/home/j' }, 'linux').PATH).toBe('/usr/bin:/bin');
    expect(mcpChildEnv({ SYSTEMROOT: 'C:\\Windows' }, 'win32').PATH).toBe('C:\\Windows\\System32;C:\\Windows');
    expect(mcpChildEnv({ SYSTEMROOT: 'C:\\Windows' }, 'win32').PATHEXT).toBe('.COM;.EXE;.BAT;.CMD');
    expect(mcpChildEnv({ SYSTEMROOT: 'C:\\Windows' }, 'win32').COMSPEC).toBe(
      'C:\\Windows\\System32\\cmd.exe',
    );
    expect(
      mcpChildEnv({ PATH: 'C:\\Windows', COMSPEC: 'C:\\Windows\\System32\\cmd.exe' }, 'win32').COMSPEC,
    ).toBe('C:\\Windows\\System32\\cmd.exe');
    expect(
      mcpChildEnv(
        { PATH: 'C:\\Windows', SYSTEMROOT: 'C:\\Windows', COMSPEC: 'C:\\evil\\cmd.exe' },
        'win32',
      ).COMSPEC,
    ).toBe('C:\\Windows\\System32\\cmd.exe');
    expect(mcpChildEnv({ PATH: 'C:\\Windows' }, 'win32').NoDefaultCurrentDirectoryInExePath).toBe('1');
    expect(mcpChildEnv({ PATH: '/usr/bin' }, 'linux').NoDefaultCurrentDirectoryInExePath).toBeUndefined();
    expect(mcpChildEnv({ PATH: '/usr/bin' }, 'linux').COMSPEC).toBeUndefined();
    expect(mcpChildEnv({ PATH: 'C:\\Windows', PATHEXT: '.EXE;.CMD' }, 'win32').PATHEXT).toBe('.EXE;.CMD');
    expect(mcpChildEnv({ PATH: 'C:\\Windows', PATHEXT: '.EXE;.JS;.VBS;.CMD' }, 'win32').PATHEXT).toBe(
      '.EXE;.CMD',
    );
    expect(mcpChildEnv({ PATH: '/usr/bin' }, 'linux').PATHEXT).toBeUndefined();
    expect(mcpChildEnv({ SYSTEMROOT: 'C:\\Windows' }, 'win32').TEMP).toBe('C:\\Windows\\Temp');
    expect(mcpChildEnv({ SYSTEMROOT: 'C:\\Windows' }, 'win32').TMP).toBe('C:\\Windows\\Temp');
    expect(
      mcpChildEnv({ PATH: 'C:\\Windows', LOCALAPPDATA: 'C:\\Users\\uryx\\AppData\\Local' }, 'win32').TEMP,
    ).toBe('C:\\Users\\uryx\\AppData\\Local\\Temp');
    expect(mcpChildEnv({ PATH: 'C:\\Windows', TEMP: 'D:\\tmp' }, 'win32').TMP).toBe('D:\\tmp');
    expect(mcpChildEnv({ PATH: '/usr/bin' }, 'linux').TEMP).toBeUndefined();
    expect(mcpChildEnv({ PATH: '"C:\\Windows\\System32"' }, 'win32').PATH).toBe('C:\\Windows\\System32');
  });

  it('BRAVE_API_KEY ve HF_TOKEN yalnız sunucu env ile geçer', () => {
    const env = mcpChildEnv(
      { PATH: '/usr/bin', BRAVE_API_KEY: 'from_process', HF_TOKEN: 'from_process' },
      'linux',
      { BRAVE_API_KEY: 'from_settings', HF_TOKEN: 'hf_settings' },
    );
    expect(env.BRAVE_API_KEY).toBe('from_settings');
    expect(env.HF_TOKEN).toBe('hf_settings');
  });
});
