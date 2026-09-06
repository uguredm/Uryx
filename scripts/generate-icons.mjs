#!/usr/bin/env node
/**
 * Uygulama ikonlarını kaynak ICO'dan üretir (harici bağımlılık yok).
 *
 * Kaynak (öncelik):
 *   1. repo kökü uryx-app-icon-transparent.ico
 *   2. apps/desktop/build/icon.ico
 *
 * Çıktı:
 *   apps/desktop/build/icon.ico  (Windows exe / kısayol / installer)
 *   apps/desktop/build/icon.png  (256×256 pencere)
 *   apps/desktop/build/tray.png  (32×32 tepsi)
 */

import { copyFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = join(here, '..');
const buildDir = join(repoRoot, 'apps', 'desktop', 'build');
const sourceCandidates = [
  join(repoRoot, 'uryx-app-icon-transparent.ico'),
  join(buildDir, 'icon.ico'),
];

function extractIcoPngs(buffer) {
  if (buffer.length < 6 || buffer.readUInt16LE(0) !== 0 || buffer.readUInt16LE(2) !== 1) {
    throw new Error('Geçerli bir ICO dosyası değil.');
  }
  const count = buffer.readUInt16LE(4);
  const images = [];
  let offset = 6;
  for (let i = 0; i < count; i += 1) {
    let width = buffer[offset];
    let height = buffer[offset + 1];
    if (width === 0) width = 256;
    if (height === 0) height = 256;
    const bytes = buffer.readUInt32LE(offset + 8);
    const imageOffset = buffer.readUInt32LE(offset + 12);
    const slice = buffer.subarray(imageOffset, imageOffset + bytes);
    if (slice.length >= 8 && slice[0] === 0x89 && slice[1] === 0x50 && slice[2] === 0x4e && slice[3] === 0x47) {
      images.push({ width, height, png: Buffer.from(slice) });
    }
    offset += 16;
  }
  if (images.length === 0) {
    throw new Error('ICO içinde PNG katmanı yok.');
  }
  return images;
}

function pickPng(images, size) {
  const exact = images.find((image) => image.width === size && image.height === size);
  if (exact) return exact.png;
  const sorted = [...images].sort(
    (a, b) => Math.abs(a.width - size) - Math.abs(b.width - size),
  );
  return sorted[0].png;
}

const source = sourceCandidates.find((candidate) => existsSync(candidate));
if (!source) {
  console.error('[icons] Kaynak ICO bulunamadı (uryx-app-icon-transparent.ico).');
  process.exit(1);
}

mkdirSync(buildDir, { recursive: true });
const icoBuffer = readFileSync(source);
const images = extractIcoPngs(icoBuffer);

const iconIcoPath = join(buildDir, 'icon.ico');
if (source !== iconIcoPath) {
  copyFileSync(source, iconIcoPath);
}

const iconPng = pickPng(images, 256);
const trayPng = pickPng(images, 32);
writeFileSync(join(buildDir, 'icon.png'), iconPng);
writeFileSync(join(buildDir, 'tray.png'), trayPng);

console.info(`[icons] kaynak → ${source}`);
console.info(`[icons] icon.ico → ${icoBuffer.length} bayt`);
console.info(`[icons] icon.png (256) → ${iconPng.length} bayt`);
console.info(`[icons] tray.png (32) → ${trayPng.length} bayt`);
console.info('[icons] Tamamlandı.');
