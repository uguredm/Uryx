import { readdirSync, readFileSync, statSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '../src');
const skip = new Set(['lib/messages.ts']);
const TR = /[çğıöşüÇĞİÖŞÜ]/;
const WORDS =
  /\b(Kaydet|Sohbet|Ayarlar|Servisleri|Konteyner|Getir|Yüklü|Efendim|Mikrofon|Güncelleme|Zaten|hazır|Aktif model|Kaynak kullanımı|Bağlam|Sıcaklık|çekirdek)\b/;
const STR = /'(?:\\.|[^'\\])*'|"(?:\\.|[^"\\])*"/g;

function walk(dir, acc = []) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) walk(p, acc);
    else if (/\.(ts|tsx)$/.test(name)) acc.push(p);
  }
  return acc;
}

const hits = [];
for (const file of walk(root)) {
  const rel = relative(root, file).replaceAll('\\', '/');
  if (skip.has(rel)) continue;
  const lines = readFileSync(file, 'utf8').split(/\n/);
  lines.forEach((line, i) => {
    if (/^\s*\/\//.test(line) || /^\s*\*/.test(line)) return;
    const matches = line.match(STR);
    if (!matches) return;
    for (const s of matches) {
      const inner = s.slice(1, -1);
      if (TR.test(inner) || WORDS.test(inner)) {
        hits.push(`${rel}:${i + 1}:${inner.slice(0, 140)}`);
      }
    }
  });
}
process.stdout.write(`${hits.join('\n')}\n---COUNT--- ${hits.length}\n`);
