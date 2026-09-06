/** Continue Windows MCP batch → cmd.exe; Node `/d /s /c`. */

import { describe, expect, it } from 'vitest';

import {
  mcpChildStdioReady,
  mcpSpawnCwd,
  mcpSystemCmdExe,
  mcpWindowsVerbatimArguments,
  quoteWin32CmdToken,
  resolveMcpSpawn,
  writeMcpStdin,
} from '../electron/host-tools/mcp-spawn';

const WIN = { SYSTEMROOT: 'C:\\Windows' };
const CMD = 'C:\\Windows\\System32\\cmd.exe';

describe('Continue MCP win32 spawn', () => {
  it('npx/uvx cmd.exe ile sarılır, node.exe durur', () => {
    expect(resolveMcpSpawn('  npx  ', ['-y', 'pkg'], 'win32', WIN)).toEqual({
      command: CMD,
      args: ['/d', '/s', '/c', 'npx', '-y', 'pkg'],
    });
    expect(resolveMcpSpawn('npx', ['-y', 'pkg'], 'win32', WIN)).toEqual({
      command: CMD,
      args: ['/d', '/s', '/c', 'npx', '-y', 'pkg'],
    });
    expect(resolveMcpSpawn('pnpx.cmd', ['pkg'], 'win32', WIN)).toEqual({
      command: CMD,
      args: ['/d', '/s', '/c', 'pnpx.cmd', 'pkg'],
    });
    expect(resolveMcpSpawn('npm.cmd', ['exec', 'pkg'], 'win32', WIN)).toEqual({
      command: CMD,
      args: ['/d', '/s', '/c', 'npm.cmd', 'exec', 'pkg'],
    });
    expect(resolveMcpSpawn('npx.cmd', ['-y', 'pkg'], 'win32', WIN)).toEqual({
      command: CMD,
      args: ['/d', '/s', '/c', 'npx.cmd', '-y', 'pkg'],
    });
    expect(resolveMcpSpawn('npx.bat', ['-y', 'pkg'], 'win32', WIN)).toEqual({
      command: CMD,
      args: ['/d', '/s', '/c', 'npx.bat', '-y', 'pkg'],
    });
    expect(resolveMcpSpawn('uv', ['tool', 'run', 'pkg'], 'win32', WIN)).toEqual({
      command: CMD,
      args: ['/d', '/s', '/c', 'uv', 'tool', 'run', 'pkg'],
    });
    expect(resolveMcpSpawn('uvx', ['tool'], 'win32', WIN)).toEqual({
      command: CMD,
      args: ['/d', '/s', '/c', 'uvx', 'tool'],
    });
    expect(resolveMcpSpawn('uvx.cmd', ['tool'], 'win32', WIN)).toEqual({
      command: CMD,
      args: ['/d', '/s', '/c', 'uvx.cmd', 'tool'],
    });
    expect(resolveMcpSpawn('bun.cmd', ['run', 'server.js'], 'win32', WIN)).toEqual({
      command: CMD,
      args: ['/d', '/s', '/c', 'bun.cmd', 'run', 'server.js'],
    });
    expect(resolveMcpSpawn('bunx', ['pkg'], 'win32', WIN)).toEqual({
      command: CMD,
      args: ['/d', '/s', '/c', 'bunx', 'pkg'],
    });
    expect(resolveMcpSpawn('pnpm.exe', ['dlx', 'pkg'], 'win32', WIN)).toEqual({
      command: 'pnpm.exe',
      args: ['dlx', 'pkg'],
    });
    expect(resolveMcpSpawn('yarn.cmd', ['dlx', 'pkg'], 'win32', WIN)).toEqual({
      command: CMD,
      args: ['/d', '/s', '/c', 'yarn.cmd', 'dlx', 'pkg'],
    });
    expect(resolveMcpSpawn('yarn.exe', ['dlx', 'pkg'], 'win32', WIN)).toEqual({
      command: 'yarn.exe',
      args: ['dlx', 'pkg'],
    });
    expect(resolveMcpSpawn('  node.exe  ', ['server.js'], 'win32', WIN)).toEqual({
      command: 'node.exe',
      args: ['server.js'],
    });
    expect(resolveMcpSpawn('node.exe', ['server.js'], 'win32', WIN)).toEqual({
      command: 'node.exe',
      args: ['server.js'],
    });
    expect(resolveMcpSpawn('node.cmd', ['server.js'], 'win32', WIN)).toEqual({
      command: CMD,
      args: ['/d', '/s', '/c', 'node.cmd', 'server.js'],
    });
    expect(resolveMcpSpawn('python.cmd', ['-m', 'pkg'], 'win32', WIN)).toEqual({
      command: CMD,
      args: ['/d', '/s', '/c', 'python.cmd', '-m', 'pkg'],
    });
  });

  it('linux npx sarılmaz', () => {
    expect(resolveMcpSpawn('npx', ['-y', 'pkg'], 'linux')).toEqual({
      command: 'npx',
      args: ['-y', 'pkg'],
    });
  });

  it('boşluklu Windows yolunu tırnaklar, cmd girişini reddeder', () => {
    expect(resolveMcpSpawn('C:\\\\Program Files\\\\nodejs\\\\npx.cmd', ['-y', 'pkg'], 'win32', WIN)).toEqual({
      command: CMD,
      args: ['/d', '/s', '/c', '"C:\\\\Program Files\\\\nodejs\\\\npx.cmd"', '-y', 'pkg'],
    });
    expect(() => resolveMcpSpawn('cmd.exe', ['/c', 'calc'], 'win32', WIN)).toThrow(/cmd MCP komutu değil/);
    expect(() => resolveMcpSpawn('cmd', ['/c', 'calc'], 'linux')).toThrow(/cmd MCP komutu değil/);
  });

  it('çalışma dizini evdir, bozuk HOME cwd’ye düşer', () => {
    const exists = (): boolean => true;
    expect(mcpSpawnCwd('win32', { USERPROFILE: 'C:\\Users\\uryx' }, 'C:\\app', exists)).toBe(
      'C:\\Users\\uryx',
    );
    expect(mcpSpawnCwd('linux', { HOME: '/home/j' }, '/opt/app', exists)).toBe('/home/j');
    expect(mcpSpawnCwd('linux', { HOME: '/home/j\nbad' }, '/opt/app', exists)).toBe('/opt/app');
    expect(mcpSpawnCwd('win32', {}, 'C:\\app', exists)).toBe('C:\\app');
    expect(
      mcpSpawnCwd(
        'win32',
        { HOMEDRIVE: 'C:', HOMEPATH: '\\Users\\uryx' },
        'C:\\app',
        exists,
      ),
    ).toBe('C:\\Users\\uryx');
    expect(
      mcpSpawnCwd(
        'win32',
        { HOMEDRIVE: 'C:', HOMEPATH: '\\Users\\..\\Windows' },
        'C:\\app',
        exists,
      ),
    ).toBe('C:\\app');
    expect(mcpSpawnCwd('win32', { USERPROFILE: 'C:\\missing' }, 'C:\\app', () => false)).toBe(
      'C:\\app',
    );
    expect(
      mcpSpawnCwd('win32', { USERPROFILE: 'C:\\Users\\foo\\..\\Windows' }, 'C:\\app', exists),
    ).toBe('C:\\app');
    expect(mcpSpawnCwd('linux', { HOME: '/home/j/../root' }, '/opt/app', exists)).toBe('/opt/app');
  });

  it('cmd %/! genişlemesini kaçırır, stdio yoksa reddeder', () => {
    expect(quoteWin32CmdToken('foo%PATH%')).toBe('"foo^%PATH^%"');
    expect(quoteWin32CmdToken('x!TEMP!')).toBe('"x^!TEMP^!"');
    expect(mcpChildStdioReady({ stdin: {}, stdout: {} })).toBe(true);
    expect(mcpChildStdioReady({ stdin: {}, stdout: undefined })).toBe(false);
    expect(mcpChildStdioReady({})).toBe(false);
  });

  it('cmd.exe verbatim, stdin kapalıysa yazmaz', () => {
    expect(mcpWindowsVerbatimArguments('cmd.exe', 'win32')).toBe(true);
    expect(mcpWindowsVerbatimArguments('C:\\\\Windows\\\\System32\\\\cmd.exe', 'win32')).toBe(true);
    expect(mcpWindowsVerbatimArguments('node.exe', 'win32')).toBe(false);
    expect(mcpWindowsVerbatimArguments('cmd.exe', 'linux')).toBe(false);
    expect(mcpSystemCmdExe('win32', WIN)).toBe(CMD);
    expect(mcpSystemCmdExe('win32', { SYSTEMROOT: 'C:\\evil\\..\\Windows' })).toBe(CMD);
    expect(mcpSystemCmdExe('linux')).toBe('cmd.exe');
    const wrote: string[] = [];
    expect(writeMcpStdin({ write: (chunk) => wrote.push(chunk) }, 'frame')).toBe(true);
    expect(wrote).toEqual(['frame']);
    expect(writeMcpStdin({ write: () => true, writable: false }, 'frame')).toBe(false);
    expect(writeMcpStdin({ write: () => true, destroyed: true }, 'frame')).toBe(false);
    expect(writeMcpStdin({ write: () => true, writableEnded: true }, 'frame')).toBe(false);
    expect(writeMcpStdin({ write: () => true, ended: true }, 'frame')).toBe(false);
    expect(writeMcpStdin(null, 'frame')).toBe(false);
    expect(
      writeMcpStdin(
        {
          write: () => {
            throw new Error('EPIPE');
          },
        },
        'frame',
      ),
    ).toBe(false);
  });
});
