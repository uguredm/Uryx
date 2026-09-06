import { readdirSync, readFileSync, statSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const desktopRoot = join(dirname(fileURLToPath(import.meta.url)), '../..');
const srcRoot = join(desktopRoot, 'src');
const electronRoot = join(desktopRoot, 'electron');

const SRC_SKIP = new Set([
  'lib/messages.ts',
]);
const ELECTRON_SKIP = new Set<string>([]);

const TR_LETTER = /[çğıöşüÇĞİÖŞÜ]/;
const ASCII_TR =
  /\b(Kaydet|Sohbet|Ayarlar|Konteyner|Getir|Yüklü|Efendim|Mikrofon|Aktif model|Aktif:|Kaynak kullanımı|Bağlam|Sıcaklık|çekirdek|Kullanıcı|Grubu aç|Grubu kapat|Başarılı|Sesli cevap|Daha fazla|Daha az|indirilecek|veya)\b/;

function walk(dir: string, acc: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) walk(full, acc);
    else if (/\.(ts|tsx)$/.test(name)) acc.push(full);
  }
  return acc;
}

function isComment(line: string): boolean {
  const trimmed = line.trim();
  return (
    trimmed.startsWith('//') ||
    trimmed.startsWith('*') ||
    trimmed.startsWith('/*') ||
    trimmed.startsWith('*/') ||
    trimmed.startsWith('{/*')
  );
}

function isIntentRegex(line: string): boolean {
  return (
    (/\/\^/.test(line) && /\.test\(/.test(line)) ||
    /\/[^/\n]*[çğıöşüÇĞİÖŞÜ][^/\n]*\//.test(line) ||
    line.includes('reddetti|iptal|zaman') ||
    line.includes('Kaynak|Görsel|Fotoğraf') ||
    line.includes('giriş yap') ||
    line.includes('beğenilen|') ||
    line.includes('zaten var|already exists') ||
    line.includes('not found|bulunamadı')
  );
}

function isTechnicalTr(line: string): boolean {
  return (
    line.includes("'tr-TR'") ||
    line.includes('"tr-TR"') ||
    /replace\(\/\[çÇ\]/.test(line) ||
    /replace\(\/\[ğĞ\]/.test(line) ||
    /replace\(\/\[ıİ\]/.test(line) ||
    /replace\(\/\[öÖ\]/.test(line) ||
    /replace\(\/\[şŞ\]/.test(line) ||
    /replace\(\/\[üÜ\]/.test(line) ||
    /toLocaleLowerCase\('tr-TR'\)/.test(line) ||
    line.includes("'Sonraki'") ||
    line.includes("'Önceki'") ||
    line.includes("'Sonraki parça'") ||
    line.includes("'Önceki parça'")
  );
}

function isLogLine(line: string): boolean {
  return /\bconsole\.(?:info|warn|error|debug|log)\s*\(/.test(line);
}

function collectHits(root: string, skip: Set<string>): string[] {
  const hits: string[] = [];
  for (const file of walk(root)) {
    const rel = relative(root, file).replaceAll('\\', '/');
    if (skip.has(rel)) continue;
    const source = readFileSync(file, 'utf8');
    const lines = source.split(/\n/);
    let wrapDepth = 0;
    lines.forEach((line, index) => {
      const opens = (line.match(/\b(?:hostT|hostText|translate|tNow)\s*\(/g) ?? []).length;
      wrapDepth += opens;
      const isWrapped = wrapDepth > 0;
      wrapDepth += (line.match(/\(/g) ?? []).length - opens - (line.match(/\)/g) ?? []).length;
      if (wrapDepth < 0) wrapDepth = 0;

      const code = line.includes('://') ? line : line.split('//')[0] ?? line;
      if (isComment(line) || isIntentRegex(code) || isTechnicalTr(code) || isLogLine(line)) return;
      if (isWrapped) return;
      if (/english/i.test(code) && /türkçe/i.test(code)) return;
      if (/^\s*masaüstü:/.test(code)) return;
      if (TR_LETTER.test(code) || ASCII_TR.test(code)) {
        hits.push(`${rel}:${index + 1}:${line.trim().slice(0, 160)}`);
      }
    });
  }
  return hits;
}

describe('sabit Türkçe UI metni', () => {
  it('renderer src (messages.ts hariç) kullanıcı metnini t() ile taşır', () => {
    expect(collectHits(srcRoot, SRC_SKIP)).toEqual([]);
  });

  it('Electron kullanıcı metnini hostT/hostText ile taşır', () => {
    expect(collectHits(electronRoot, ELECTRON_SKIP)).toEqual([]);
  });
});
