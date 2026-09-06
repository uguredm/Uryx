/**
 * Host tarafı güvenlik katmanı.
 *
 * Bu modül Electron **main process** içinde çalışır ve modele/renderer'a
 * verilebilecek yetkileri sınırlar:
 *
 * - Dosya işlemleri yalnızca izin verilen köklerin altında yapılabilir
 *   (path traversal koruması, `realpath` sonrası doğrulama).
 * - Program açma yalnızca sabit bir takma ad listesi veya izin verilen
 *   klasörlerdeki `.exe`/`.lnk` dosyaları ile mümkündür.
 * - PowerShell/CMD komutları allowlist'li bir ilk token gerektirir; boru hattı,
 *   yönlendirme ve komut zincirleme reddedilir.
 */

import { app } from 'electron';
import { existsSync, realpathSync, statSync } from 'node:fs';
import { homedir } from 'node:os';
import path from 'node:path';

import { hostText } from './host-i18n';

/** İzin verilen kök klasörlerin önbelleği. */
let allowedRootsCache: string[] | null = null;

/** Kullanıcının ek olarak yetkilendirdiği kökler (ayarlardan gelir). */
let extraRoots: string[] = [];

/**
 * Varsayılan güvenli kökler: kullanıcının belge/masaüstü/indirilenler
 * klasörleri, resimler ve uygulamanın kendi veri klasörü.
 */
function defaultRoots(): string[] {
  const home = homedir();
  const candidates = [
    app.getPath('documents'),
    app.getPath('desktop'),
    app.getPath('downloads'),
    app.getPath('pictures'),
    app.getPath('userData'),
    path.join(home, 'Projects'),
    path.join(home, 'source'),
  ];
  return candidates.filter((p) => !!p && existsSync(p));
}

/** Masaüstü / Belgeler / İndirilenler / Resimler takma adını gerçek yola çevirir. */
export function resolveSpecialFolder(raw: string): string | null {
  const key = raw.trim().toLocaleLowerCase('tr-TR').replace(/\s+/g, '');
  const map: Record<string, 'desktop' | 'documents' | 'downloads' | 'pictures'> = {
    desktop: 'desktop',
    masaüstü: 'desktop',
    masaustu: 'desktop',
    documents: 'documents',
    belgeler: 'documents',
    belgelerim: 'documents',
    downloads: 'downloads',
    indirilenler: 'downloads',
    indirilenlerim: 'downloads',
    pictures: 'pictures',
    resimler: 'pictures',
    resimlerim: 'pictures',
  };
  const name = map[key];
  return name ? app.getPath(name) : null;
}

/** Ayarlardan gelen ek kökleri tanımlar. */
export function setExtraAllowedRoots(roots: string[]): void {
  extraRoots = roots.filter((r) => r.trim().length > 0 && existsSync(r));
  allowedRootsCache = null;
}

/** İzin verilen normalize edilmiş kökleri döndürür. */
export function allowedRoots(): string[] {
  if (allowedRootsCache) return allowedRootsCache;
  const all = [...defaultRoots(), ...extraRoots];
  const normalized = new Set<string>();
  for (const root of all) {
    try {
      normalized.add(path.resolve(realpathSync(root)).toLowerCase());
    } catch {
    }
  }
  allowedRootsCache = [...normalized];
  return allowedRootsCache;
}

/**
 * Yolu normalize eder; sembolik bağlantıları çözer.
 * Var olmayan yollarda en yakın var olan üst klasörden türetir; böylece
 * "oluşturulacak dosya" yolları da doğrulanabilir.
 */
function normalize(target: string): string {
  const absolute = path.resolve(target.replace(/^~(?=[\\/]|$)/, homedir()));
  let probe = absolute;
  const tail: string[] = [];

  while (!existsSync(probe)) {
    const parent = path.dirname(probe);
    if (parent === probe) break;
    tail.unshift(path.basename(probe));
    probe = parent;
  }

  try {
    return path.resolve(realpathSync(probe), ...tail).toLowerCase();
  } catch {
    return absolute.toLowerCase();
  }
}

/** UNC / aygıt yolu sızıntısını reddeder. */
function isUncOrDevicePath(target: string): boolean {
  const trimmed = target.trim();
  if (/^\\\\/.test(trimmed) || /^\/\/[^/]/.test(trimmed)) return true;
  if (trimmed.includes('\\??\\') || trimmed.startsWith('\\\\?\\')) return true;
  return false;
}

/** Yol izin verilen köklerden birinin altında mı? */
export function isPathAllowed(target: string): boolean {
  if (!target || typeof target !== 'string') return false;
  if (isUncOrDevicePath(target)) return false;
  const normalized = normalize(target);
  if (normalized.startsWith('\\\\') || normalized.startsWith('//')) return false;
  return allowedRoots().some(
    (root) => normalized === root || normalized.startsWith(root + path.sep),
  );
}

/**
 * Yolu doğrular ve gerçek (normalize edilmemiş büyük/küçük harf) hâlini döndürür.
 * @throws İzin verilmeyen yol için hata.
 */
export function ensurePathAllowed(target: string): string {
  if (!isPathAllowed(target)) {
    throw new Error(
      hostText(
        `'${target}' izin verilen klasörlerin dışında. İzinli kökler: ${allowedRoots().join(', ')}`,
        `'${target}' is outside the allowed folders. Allowed roots: ${allowedRoots().join(', ')}`,
      ),
    );
  }
  return path.resolve(target.replace(/^~(?=[\\/]|$)/, homedir()));
}

/** Yolun var olan bir klasör olduğunu doğrular. */
export function ensureDirectory(target: string): string {
  const resolved = ensurePathAllowed(target);
  if (!existsSync(resolved) || !statSync(resolved).isDirectory()) {
    throw new Error(
      hostText(
        `'${target}' bir klasör değil veya bulunamadı.`,
        `'${target}' is not a folder or was not found.`,
      ),
    );
  }
  return resolved;
}

/** Yolun var olan bir dosya olduğunu doğrular. */
export function ensureFile(target: string): string {
  const resolved = ensurePathAllowed(target);
  if (!existsSync(resolved) || !statSync(resolved).isFile()) {
    throw new Error(
      hostText(
        `'${target}' bir dosya değil veya bulunamadı.`,
        `'${target}' is not a file or was not found.`,
      ),
    );
  }
  return resolved;
}

/**
 * Açılmasına izin verilen uygulamalar.
 * Değer, `start` kabuğu olmadan doğrudan çalıştırılabilecek komuttur.
 */
export const APPLICATION_ALLOWLIST: Record<string, { command: string; args: string[] }> = {
  notepad: { command: 'notepad.exe', args: [] },
  calc: { command: 'calc.exe', args: [] },
  hesap: { command: 'calc.exe', args: [] },
  explorer: { command: 'explorer.exe', args: [] },
  gezgin: { command: 'explorer.exe', args: [] },
  paint: { command: 'mspaint.exe', args: [] },
  cmd: { command: 'cmd.exe', args: [] },
  powershell: { command: 'powershell.exe', args: [] },
  terminal: { command: 'wt.exe', args: [] },
  chrome: { command: 'chrome.exe', args: [] },
  edge: { command: 'msedge.exe', args: [] },
  firefox: { command: 'firefox.exe', args: [] },
  vscode: { command: 'code.cmd', args: [] },
  code: { command: 'code.cmd', args: [] },
  spotify: { command: 'spotify:', args: [] },
  task_manager: { command: 'taskmgr.exe', args: [] },
  gorev_yoneticisi: { command: 'taskmgr.exe', args: [] },
  settings: { command: 'ms-settings:', args: [] },
  ayarlar: { command: 'ms-settings:', args: [] },
  snippingtool: { command: 'snippingtool.exe', args: [] },
  wordpad: { command: 'write.exe', args: [] },
  regedit: { command: '', args: [] }, // kasıtlı olarak devre dışı
};

/** Kapatılmasına izin verilen program adları (taskkill hedefleri). */
export const CLOSABLE_APPS = new Set([
  'notepad',
  'calc',
  'mspaint',
  'wordpad',
  'write',
  'chrome',
  'msedge',
  'firefox',
  'spotify',
  'code',
  'wt',
  'snippingtool',
  'explorer',
]);

/** PowerShell'de izin verilen ilk komutlar (salt okunur ağırlıklı). */
export const POWERSHELL_ALLOWLIST = new Set([
  'get-childitem',
  'get-content',
  'get-process',
  'get-service',
  'get-date',
  'get-location',
  'get-computerinfo',
  'get-volume',
  'get-netipaddress',
  'get-nettcpconnection',
  'get-hotfix',
  'get-command',
  'get-help',
  'get-item',
  'get-itemproperty',
  'test-path',
  'test-connection',
  'test-netconnection',
  'resolve-dnsname',
  'measure-object',
  'select-string',
  'write-output',
  'ls',
  'dir',
  'pwd',
  'cat',
  'echo',
]);

/** CMD'de izin verilen komutlar. `net` yok: `net use` / `net user` sızıntısı. */
export const CMD_ALLOWLIST = new Set([
  'dir',
  'ipconfig',
  'ping',
  'systeminfo',
  'tasklist',
  'where',
  'echo',
  'hostname',
  'whoami',
  'ver',
  'netstat',
  'nslookup',
  'tracert',
]);

/** Komut satırında kesinlikle kabul edilmeyen karakter/desenler. */
const FORBIDDEN_SHELL_PATTERN = /[|;&`$><]|\breturn\b|\$\(|&&|\|\||\n|\r/;

/** Komutun tehlikeli anahtar kelimeler içermediğini doğrular. */
const DANGEROUS_KEYWORDS =
  /\b(remove-item|rd|rmdir|del|erase|format|diskpart|shutdown|restart-computer|stop-computer|set-executionpolicy|invoke-expression|iex|invoke-webrequest|iwr|curl|wget|new-service|sc\s+delete|reg\s+delete|bcdedit|cipher|takeown|icacls|net\s+user|net\s+localgroup|net\s+use|net\s+share)\b/i;

const SENSITIVE_SHELL_PATH =
  /\\windows\\system32\\config|\\windows\\repair\\|hk(lm|u):\\sam\b|hk(lm|u):\\security\b/i;

export interface ShellValidation {
  command: string;
  args: string[];
}

/**
 * PowerShell komutunu doğrular.
 * @throws Komut allowlist dışıysa veya tehlikeli yapı içeriyorsa.
 */
function rejectShellEscapes(command: string): void {
  if (/%[a-z0-9_]+%/i.test(command)) {
    throw new Error(
      hostText(
        'Ortam değişkeni genişletmesi (%) komutta kullanılamaz.',
        'Environment variable expansion (%) cannot be used in the command.',
      ),
    );
  }
  if (/\\\\|\/\/[a-z0-9._-]/i.test(command)) {
    throw new Error(
      hostText(
        'UNC veya uzak paylaşım yolları komutta kullanılamaz.',
        'UNC or remote share paths cannot be used in the command.',
      ),
    );
  }
  if (SENSITIVE_SHELL_PATH.test(command)) {
    throw new Error(
      hostText(
        'Hassas sistem/kayıt defteri yollarına erişim yok.',
        'Access to sensitive system or registry paths is not allowed.',
      ),
    );
  }
}

export function validatePowerShell(raw: string): string {
  const command = raw.trim();
  if (!command) throw new Error(hostText('Komut boş olamaz.', 'Command cannot be empty.'));
  if (command.length > 500) {
    throw new Error(
      hostText('Komut çok uzun (en fazla 500 karakter).', 'Command is too long (max 500 characters).'),
    );
  }
  if (FORBIDDEN_SHELL_PATTERN.test(command)) {
    throw new Error(
      hostText(
        'Komut boru hattı (|), yönlendirme (>), zincirleme (;, &&) veya alt kabuk içeremez.',
        'The command cannot include a pipeline (|), redirection (>), chaining (;, &&), or a subshell.',
      ),
    );
  }
  rejectShellEscapes(command);
  if (DANGEROUS_KEYWORDS.test(command)) {
    throw new Error(
      hostText(
        'Komut, izin verilmeyen tehlikeli bir cmdlet içeriyor.',
        'The command contains a disallowed dangerous cmdlet.',
      ),
    );
  }
  const first = command.split(/\s+/)[0]!.toLowerCase();
  if (!POWERSHELL_ALLOWLIST.has(first)) {
    throw new Error(
      hostText(
        `'${first}' izin listesinde değil. İzinli komutlar: ${[...POWERSHELL_ALLOWLIST].slice(0, 12).join(', ')}…`,
        `'${first}' is not on the allowlist. Allowed commands: ${[...POWERSHELL_ALLOWLIST].slice(0, 12).join(', ')}…`,
      ),
    );
  }
  return command;
}

/**
 * CMD komutunu doğrular ve `(komut, argümanlar)` olarak ayrıştırır.
 * @throws Komut allowlist dışıysa.
 */
export function validateCmd(raw: string): ShellValidation {
  const command = raw.trim();
  if (!command) throw new Error(hostText('Komut boş olamaz.', 'Command cannot be empty.'));
  if (command.length > 500) {
    throw new Error(
      hostText('Komut çok uzun (en fazla 500 karakter).', 'Command is too long (max 500 characters).'),
    );
  }
  if (FORBIDDEN_SHELL_PATTERN.test(command)) {
    throw new Error(
      hostText(
        'Komut boru hattı, yönlendirme veya zincirleme içeremez.',
        'The command cannot include a pipeline, redirection, or chaining.',
      ),
    );
  }
  rejectShellEscapes(command);
  if (DANGEROUS_KEYWORDS.test(command)) {
    throw new Error(
      hostText(
        'Komut, izin verilmeyen tehlikeli bir işlem içeriyor.',
        'The command contains a disallowed dangerous operation.',
      ),
    );
  }
  const parts = command.split(/\s+/);
  const head = parts[0]!.toLowerCase();
  if (!CMD_ALLOWLIST.has(head)) {
    throw new Error(
      hostText(
        `'${head}' izin listesinde değil. İzinli komutlar: ${[...CMD_ALLOWLIST].join(', ')}`,
        `'${head}' is not on the allowlist. Allowed commands: ${[...CMD_ALLOWLIST].join(', ')}`,
      ),
    );
  }
  return { command: head, args: parts.slice(1) };
}

/** Kullanıcı girdisindeki tek satırlık metni güvenli hâle getirir. */
export function sanitizeSingleLine(value: unknown, maxLength = 500): string {
  return String(value ?? '')
    .replace(/[\r\n\t]+/g, ' ')
    .trim()
    .slice(0, maxLength);
}
