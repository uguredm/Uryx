/** Host güvenlik katmanı testleri. */

import { mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { beforeAll, describe, expect, it } from 'vitest';

import {
  APPLICATION_ALLOWLIST,
  CMD_ALLOWLIST,
  POWERSHELL_ALLOWLIST,
  ensurePathAllowed,
  isPathAllowed,
  resolveSpecialFolder,
  sanitizeSingleLine,
  validateCmd,
  validatePowerShell,
} from '../electron/security';

const root = process.env.URYX_TEST_ROOT!;
const documents = join(root, 'Documents');

beforeAll(() => {
  mkdirSync(documents, { recursive: true });
  writeFileSync(join(documents, 'not.txt'), 'içerik', 'utf8');
});

describe('path traversal koruması', () => {
  it('izin verilen klasördeki dosyayı kabul eder', () => {
    expect(isPathAllowed(join(documents, 'not.txt'))).toBe(true);
  });

  it('izin verilen klasörde olmayan dosyayı reddeder', () => {
    expect(isPathAllowed('C:\\Windows\\System32\\config\\SAM')).toBe(false);
  });

  it('.. ile üst dizine çıkışı engeller', () => {
    expect(isPathAllowed(join(documents, '..', '..', '..', 'Windows'))).toBe(false);
  });

  it('henüz oluşturulmamış ama izinli yolu kabul eder', () => {
    expect(isPathAllowed(join(documents, 'alt', 'yeni.txt'))).toBe(true);
  });

  it('ensurePathAllowed izinsiz yolda hata fırlatır', () => {
    expect(() => ensurePathAllowed('C:\\Windows\\notepad.exe')).toThrow(/izin verilen/i);
  });
});

describe('PowerShell allowlist', () => {
  it('izinli salt okunur komutu kabul eder', () => {
    expect(validatePowerShell('Get-Process')).toBe('Get-Process');
    expect(validatePowerShell('Get-ChildItem C:\\')).toContain('Get-ChildItem');
  });

  it('izin listesi dışındaki komutu reddeder', () => {
    expect(() => validatePowerShell('Remove-Item -Recurse C:\\')).toThrow();
    expect(() => validatePowerShell('Invoke-Expression $payload')).toThrow();
    expect(() => validatePowerShell('Start-Process kotu.exe')).toThrow(/izin listesinde/i);
  });

  it('boru hattı ve zincirlemeyi reddeder', () => {
    expect(() => validatePowerShell('Get-Process | Stop-Process')).toThrow(/boru hattı/i);
    expect(() => validatePowerShell('Get-Date; Remove-Item x')).toThrow();
    expect(() => validatePowerShell('Get-Date && del x')).toThrow();
  });

  it('yönlendirmeyi reddeder', () => {
    expect(() => validatePowerShell('Get-Process > C:\\out.txt')).toThrow();
  });

  it('alt kabuk denemesini reddeder', () => {
    expect(() => validatePowerShell('Get-Content $(kotu-komut)')).toThrow();
  });

  it('tehlikeli anahtar kelimeleri reddeder', () => {
    expect(() => validatePowerShell('Get-Content C:\\a.txt shutdown')).toThrow(/tehlikeli/i);
  });

  it('boş komutu reddeder', () => {
    expect(() => validatePowerShell('   ')).toThrow(/boş/i);
  });

  it('aşırı uzun komutu reddeder', () => {
    expect(() => validatePowerShell(`Get-Process ${'a'.repeat(600)}`)).toThrow(/çok uzun/i);
  });
});

describe('CMD allowlist', () => {
  it('izinli komutu ayrıştırır', () => {
    const result = validateCmd('ipconfig /all');
    expect(result.command).toBe('ipconfig');
    expect(result.args).toEqual(['/all']);
  });

  it('izinsiz komutu reddeder', () => {
    expect(() => validateCmd('format C:')).toThrow();
    expect(() => validateCmd('del /f /q C:\\*')).toThrow();
    expect(() => validateCmd('net user')).toThrow();
  });

  it('geniş net komutunu reddeder, netstat kabul eder', () => {
    expect(() => validateCmd('net use \\\\evil\\share')).toThrow();
    expect(validateCmd('netstat -an').command).toBe('netstat');
  });

  it('UNC ve ortam değişkeni genişletmesini reddeder', () => {
    expect(() => validatePowerShell('Get-Content \\\\evil\\share\\a.txt')).toThrow(/UNC/i);
    expect(() => validateCmd('dir %WINDIR%')).toThrow(/%/);
    expect(isPathAllowed('\\\\evil\\share\\secret.txt')).toBe(false);
  });

  it('zincirlemeyi reddeder', () => {
    expect(() => validateCmd('dir & del x')).toThrow();
  });
});

describe('uygulama allowlist', () => {
  it('bilinen uygulamalar tanımlı', () => {
    for (const alias of ['notepad', 'calc', 'explorer', 'vscode', 'chrome']) {
      expect(APPLICATION_ALLOWLIST[alias]).toBeDefined();
    }
  });

  it('regedit kasıtlı olarak devre dışı', () => {
    expect(APPLICATION_ALLOWLIST.regedit?.command).toBe('');
  });

  it('allowlist setleri boş değil', () => {
    expect(POWERSHELL_ALLOWLIST.size).toBeGreaterThan(10);
    expect(CMD_ALLOWLIST.size).toBeGreaterThan(5);
  });
});

describe('özel klasör takma adları', () => {
  it('masaüstü ve indirilenleri çözer', () => {
    expect(resolveSpecialFolder('desktop')).toBe(join(root, 'Desktop'));
    expect(resolveSpecialFolder('masaüstü')).toBe(join(root, 'Desktop'));
    expect(resolveSpecialFolder('indirilenler')).toBe(join(root, 'Downloads'));
    expect(resolveSpecialFolder('resimler')).toBe(join(root, 'Pictures'));
    expect(resolveSpecialFolder('belgeler')).toBe(join(root, 'Documents'));
    expect(resolveSpecialFolder('C:\\Windows')).toBeNull();
  });
});

describe('sanitizeSingleLine', () => {
  it('satır sonlarını temizler', () => {
    expect(sanitizeSingleLine('a\nb\rc\td')).toBe('a b c d');
  });

  it('uzunluğu sınırlar', () => {
    expect(sanitizeSingleLine('x'.repeat(1000), 50)).toHaveLength(50);
  });

  it('null ve undefined ile çalışır', () => {
    expect(sanitizeSingleLine(null)).toBe('');
    expect(sanitizeSingleLine(undefined)).toBe('');
  });
});
