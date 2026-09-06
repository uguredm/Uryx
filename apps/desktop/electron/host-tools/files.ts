/** Dosya sistemi araçları (izin verilen kökler içinde). */

import { shell } from 'electron';
import { constants } from 'node:fs';
import { createHash } from 'node:crypto';
import { access, appendFile, copyFile, mkdir, readdir, readFile, rename, stat, writeFile } from 'node:fs/promises';
import path from 'node:path';

import { hostText } from '../host-i18n';
import {
  allowedRoots,
  ensureDirectory,
  ensureFile,
  ensurePathAllowed,
  resolveSpecialFolder,
  sanitizeSingleLine,
} from '../security';
import { clipboardRead, clipboardWrite, getSelectedText } from './system';

function isAlreadyExistsError(error: unknown): boolean {
  return error instanceof Error && /zaten var|already exists/i.test(error.message);
}

/** Aramada atlanan klasörler. */
const SKIP_DIRS = new Set([
  'node_modules',
  '.git',
  '__pycache__',
  '.venv',
  'venv',
  'dist',
  'build',
  '.next',
  '.cache',
  'AppData',
  '$RECYCLE.BIN',
  'System Volume Information',
]);

const MAX_SEARCH_ENTRIES = 40_000;
const MAX_READ_CHARS = 200_000;

/** Joker karakterli deseni büyük/küçük harf duyarsız RegExp'e çevirir. */
function globToRegExp(pattern: string): RegExp {
  const escaped = pattern.replace(/[.+^${}()|[\]\\]/g, '\\$&').replace(/\*/g, '.*').replace(/\?/g, '.');
  return new RegExp(escaped, 'i');
}

/** `search_files` aracı. */
export async function searchFiles(args: Record<string, unknown>): Promise<Record<string, unknown>> {
  const query = sanitizeSingleLine(args.query, 200);
  if (!query) throw new Error(hostText('Arama deseni gerekli.', 'A search pattern is required.'));

  const limit = Math.max(1, Math.min(Number(args.limit ?? 50) || 50, 200));
  const rawRoot = sanitizeSingleLine(args.root ?? '', 1000);
  const roots = rawRoot ? [ensurePathAllowed(rawRoot)] : allowedRoots();

  const matcher = query.includes('*') || query.includes('?')
    ? globToRegExp(query)
    : new RegExp(query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'i');

  const results: { path: string; name: string; size: number; modified: string }[] = [];
  let visited = 0;

  for (const root of roots) {
    if (results.length >= limit) break;
    const queue: string[] = [root];

    while (queue.length && results.length < limit && visited < MAX_SEARCH_ENTRIES) {
      const current = queue.shift()!;
      let entries;
      try {
        entries = await readdir(current, { withFileTypes: true });
      } catch {
        continue;
      }

      for (const entry of entries) {
        visited += 1;
        if (visited > MAX_SEARCH_ENTRIES) break;
        if (entry.name.startsWith('.') || SKIP_DIRS.has(entry.name)) continue;

        const full = path.join(current, entry.name);
        if (entry.isDirectory()) {
          queue.push(full);
        } else if (entry.isFile() && matcher.test(entry.name)) {
          try {
            const info = await stat(full);
            results.push({
              path: full,
              name: entry.name,
              size: info.size,
              modified: info.mtime.toISOString(),
            });
          } catch {
          }
          if (results.length >= limit) break;
        }
      }
    }
  }

  return {
    query,
    count: results.length,
    truncated: visited >= MAX_SEARCH_ENTRIES,
    results,
  };
}

/** `read_file` aracı. */
export async function readTextFile(args: Record<string, unknown>): Promise<Record<string, unknown>> {
  const raw = sanitizeSingleLine(args.path, 1000);
  if (!raw) throw new Error(hostText('Dosya yolu gerekli.', 'A file path is required.'));

  const resolved = ensureFile(raw);
  const maxChars = Math.max(100, Math.min(Number(args.max_chars ?? 20_000) || 20_000, MAX_READ_CHARS));

  const info = await stat(resolved);
  if (info.size > 20 * 1024 * 1024) {
    throw new Error(
      hostText(
        `Dosya çok büyük (${(info.size / 1e6).toFixed(1)} MB). Sınır: 20 MB.`,
        `File is too large (${(info.size / 1e6).toFixed(1)} MB). Limit: 20 MB.`,
      ),
    );
  }

  const buffer = await readFile(resolved);
  if (buffer.subarray(0, 8192).includes(0)) {
    throw new Error(
      hostText(
        'Bu bir metin dosyası değil (ikili içerik tespit edildi).',
        'This is not a text file (binary content detected).',
      ),
    );
  }

  const content = buffer.toString('utf8');
  return {
    path: resolved,
    size_bytes: info.size,
    truncated: content.length > maxChars,
    content: content.slice(0, maxChars),
  };
}

/** `create_file` aracı. */
export async function createFile(args: Record<string, unknown>): Promise<Record<string, unknown>> {
  const raw = sanitizeSingleLine(args.path, 1000);
  if (!raw) throw new Error(hostText('Dosya yolu gerekli.', 'A file path is required.'));
  const content = String(args.content ?? '');
  if (content.length > 2_000_000) {
    throw new Error(hostText('İçerik çok büyük (sınır: 2 MB).', 'Content is too large (limit: 2 MB).'));
  }

  const resolved = ensurePathAllowed(resolveFolderPath(raw));

  try {
    await access(resolved, constants.F_OK);
    throw new Error(
      hostText(
        `'${raw}' zaten var. Var olan dosyayı değiştirmek için 'dosya düzenle' aracını kullanın.`,
        `'${raw}' already exists. Use the 'edit file' tool to change an existing file.`,
      ),
    );
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== 'ENOENT') {
      if (isAlreadyExistsError(error)) throw error;
    }
  }

  await mkdir(path.dirname(resolved), { recursive: true });
  await writeFile(resolved, content, 'utf8');
  return { created: true, path: resolved, bytes: Buffer.byteLength(content, 'utf8') };
}

/** `edit_file` aracı — düzenlemeden önce `.bak` yedeği alır. */
export async function editFile(args: Record<string, unknown>): Promise<Record<string, unknown>> {
  const raw = sanitizeSingleLine(args.path, 1000);
  if (!raw) throw new Error(hostText('Dosya yolu gerekli.', 'A file path is required.'));
  const content = String(args.content ?? '');
  const mode = String(args.mode ?? 'append').toLowerCase();
  if (!['append', 'replace'].includes(mode)) {
    throw new Error(
      hostText(
        "mode yalnızca 'append' veya 'replace' olabilir.",
        "mode can only be 'append' or 'replace'.",
      ),
    );
  }
  if (content.length > 2_000_000) {
    throw new Error(hostText('İçerik çok büyük (sınır: 2 MB).', 'Content is too large (limit: 2 MB).'));
  }

  const resolved = ensureFile(raw);
  const backup = `${resolved}.bak`;
  await copyFile(resolved, backup);

  if (mode === 'replace') {
    await writeFile(resolved, content, 'utf8');
  } else {
    const existing = await readFile(resolved, 'utf8');
    const separator = existing.length && !existing.endsWith('\n') ? '\n' : '';
    await writeFile(resolved, existing + separator + content, 'utf8');
  }

  const info = await stat(resolved);
  return { edited: true, path: resolved, mode, backup, size_bytes: info.size };
}

/** `delete_file` aracı — Geri Dönüşüm Kutusu'na taşır. */
export async function deleteFile(args: Record<string, unknown>): Promise<Record<string, unknown>> {
  const raw = sanitizeSingleLine(args.path, 1000);
  if (!raw) throw new Error(hostText('Dosya yolu gerekli.', 'A file path is required.'));

  const resolved = ensureFile(resolveFolderPath(raw));
  await shell.trashItem(resolved);
  return {
    deleted: true,
    path: resolved,
    destination: hostText('Geri Dönüşüm Kutusu', 'Recycle Bin'),
  };
}

function resolveFolderPath(raw: string): string {
  const special = resolveSpecialFolder(raw);
  if (special) return special;
  const normalized = raw.replace(/\\/g, '/');
  const slash = normalized.indexOf('/');
  if (slash > 0) {
    const root = resolveSpecialFolder(normalized.slice(0, slash));
    const tail = normalized.slice(slash + 1).replace(/^\/+/, '');
    if (root && tail && !tail.split('/').includes('..')) {
      return path.join(root, ...tail.split('/').filter(Boolean));
    }
  }
  return raw;
}

/** `list_directory` aracı. */
export async function listDirectory(args: Record<string, unknown>): Promise<Record<string, unknown>> {
  const raw = sanitizeSingleLine(args.path, 1000);
  if (!raw) throw new Error(hostText('Klasör yolu gerekli.', 'A folder path is required.'));
  const resolved = ensureDirectory(resolveFolderPath(raw));
  const limit = Math.max(1, Math.min(Number(args.limit ?? 80) || 80, 200));
  const entries = await readdir(resolved, { withFileTypes: true });
  const items: { name: string; type: string; size: number | null }[] = [];
  for (const entry of entries) {
    if (items.length >= limit) break;
    if (entry.name.startsWith('.')) continue;
    const full = path.join(resolved, entry.name);
    let size: number | null = null;
    if (entry.isFile()) {
      try {
        size = (await stat(full)).size;
      } catch {
        size = null;
      }
    }
    items.push({
      name: entry.name,
      type: entry.isDirectory() ? 'directory' : 'file',
      size,
    });
  }
  return {
    path: resolved,
    count: items.length,
    truncated: entries.length > items.length,
    entries: items,
  };
}

/** `copy_file` aracı — üzerine yazmaz. */
export async function copyFileTool(args: Record<string, unknown>): Promise<Record<string, unknown>> {
  const sourceRaw = sanitizeSingleLine(args.source, 1000);
  const destRaw = sanitizeSingleLine(args.destination, 1000);
  if (!sourceRaw || !destRaw) {
    throw new Error(hostText('Kaynak ve hedef yolları gerekli.', 'Source and destination paths are required.'));
  }
  const source = ensureFile(resolveFolderPath(sourceRaw));
  const destination = ensurePathAllowed(resolveFolderPath(destRaw));
  try {
    await access(destination, constants.F_OK);
    throw new Error(
      hostText(`'${destRaw}' zaten var. Üzerine yazılmadı.`, `'${destRaw}' already exists. It was not overwritten.`),
    );
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== 'ENOENT') {
      if (isAlreadyExistsError(error)) throw error;
    }
  }
  await mkdir(path.dirname(destination), { recursive: true });
  await copyFile(source, destination);
  const info = await stat(destination);
  return { copied: true, source, destination, bytes: info.size };
}

/** `move_file` — üzerine yazmaz; izinli kökler. */
export async function moveFileTool(args: Record<string, unknown>): Promise<Record<string, unknown>> {
  const sourceRaw = sanitizeSingleLine(args.source, 1000);
  const destRaw = sanitizeSingleLine(args.destination, 1000);
  if (!sourceRaw || !destRaw) {
    throw new Error(hostText('Kaynak ve hedef yolları gerekli.', 'Source and destination paths are required.'));
  }
  const source = ensureFile(resolveFolderPath(sourceRaw));
  const destination = ensurePathAllowed(resolveFolderPath(destRaw));
  try {
    await access(destination, constants.F_OK);
    throw new Error(
      hostText(`'${destRaw}' zaten var. Üzerine yazılmadı.`, `'${destRaw}' already exists. It was not overwritten.`),
    );
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== 'ENOENT') {
      if (isAlreadyExistsError(error)) throw error;
    }
  }
  await mkdir(path.dirname(destination), { recursive: true });
  await rename(source, destination);
  return { moved: true, source, destination };
}

/** `rename_file` — aynı klasörde yeni ad; üzerine yazmaz. */
export async function renameFileTool(args: Record<string, unknown>): Promise<Record<string, unknown>> {
  const sourceRaw = sanitizeSingleLine(args.source, 1000);
  const name = sanitizeSingleLine(args.name, 240);
  if (!sourceRaw || !name) {
    throw new Error(hostText('Kaynak yolu ve yeni ad gerekli.', 'Source path and new name are required.'));
  }
  if (/[\\/]/.test(name) || name === '.' || name === '..') {
    throw new Error(hostText('Yeni ad yol içeremez.', 'The new name cannot contain a path.'));
  }
  const source = ensureFile(resolveFolderPath(sourceRaw));
  const destination = ensurePathAllowed(path.join(path.dirname(source), name));
  try {
    await access(destination, constants.F_OK);
    throw new Error(
      hostText(`'${name}' zaten var. Üzerine yazılmadı.`, `'${name}' already exists. It was not overwritten.`),
    );
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== 'ENOENT') {
      if (isAlreadyExistsError(error)) throw error;
    }
  }
  await rename(source, destination);
  return { renamed: true, source, destination, name };
}

/** `duplicate_file` — aynı klasörde `-kopya`; üzerine yazmaz. */
export async function duplicateFileTool(
  args: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  const raw = sanitizeSingleLine(args.path, 1000);
  if (!raw) throw new Error(hostText('Dosya yolu gerekli.', 'A file path is required.'));
  const source = ensureFile(resolveFolderPath(raw));
  const ext = path.extname(source);
  const stem = path.basename(source, ext);
  const directory = path.dirname(source);
  const copyTag = hostText('-kopya', '-copy');
  let destination = '';
  for (let index = 1; index <= 20; index += 1) {
    const suffix = index === 1 ? copyTag : `${copyTag}-${index}`;
    const candidate = ensurePathAllowed(path.join(directory, `${stem}${suffix}${ext}`));
    try {
      await access(candidate, constants.F_OK);
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === 'ENOENT') {
        destination = candidate;
        break;
      }
      throw error;
    }
  }
  if (!destination) throw new Error(hostText('Kopya adı bulunamadı.', 'Could not find a copy name.'));
  await copyFile(source, destination);
  const info = await stat(destination);
  return { duplicated: true, source, destination, bytes: info.size };
}

/** `get_file_hash` — SHA-256; içerik LLM'e gitmez. */
export async function getFileHash(args: Record<string, unknown>): Promise<Record<string, unknown>> {
  const raw = sanitizeSingleLine(args.path, 1000);
  if (!raw) throw new Error(hostText('Dosya yolu gerekli.', 'A file path is required.'));
  const resolved = ensureFile(resolveFolderPath(raw));
  const info = await stat(resolved);
  if (info.size > 20_000_000) {
    throw new Error(hostText('Dosya çok büyük (sınır: 20 MB).', 'File is too large (limit: 20 MB).'));
  }
  const buffer = await readFile(resolved);
  return {
    path: resolved,
    algorithm: 'sha256',
    hash: createHash('sha256').update(buffer).digest('hex'),
    size: info.size,
  };
}

/** `file_exists` — izinli kökte varlık; içerik yok. */
export async function fileExists(args: Record<string, unknown>): Promise<Record<string, unknown>> {
  const raw = sanitizeSingleLine(args.path, 1000);
  if (!raw) throw new Error(hostText('Dosya yolu gerekli.', 'A file path is required.'));
  const resolved = ensurePathAllowed(resolveFolderPath(raw));
  try {
    const info = await stat(resolved);
    return {
      exists: true,
      path: resolved,
      is_file: info.isFile(),
      is_directory: info.isDirectory(),
    };
  } catch {
    return { exists: false, path: resolved, is_file: false, is_directory: false };
  }
}

/** `copy_file_path` — tam yolu panoya yazar; dosya taşımaz. */
export async function copyFilePath(args: Record<string, unknown>): Promise<Record<string, unknown>> {
  const raw = sanitizeSingleLine(args.path, 1000);
  if (!raw) throw new Error(hostText('Dosya yolu gerekli.', 'A file path is required.'));
  const resolved = ensureFile(resolveFolderPath(raw));
  clipboardWrite({ text: resolved });
  return { copied: true, path: resolved };
}

/** `count_file_lines` — metin satır sayısı; 2 MB tavan. */
export async function countFileLines(args: Record<string, unknown>): Promise<Record<string, unknown>> {
  const raw = sanitizeSingleLine(args.path, 1000);
  if (!raw) throw new Error(hostText('Dosya yolu gerekli.', 'A file path is required.'));
  const resolved = ensureFile(resolveFolderPath(raw));
  const info = await stat(resolved);
  if (info.size > 2_000_000) {
    throw new Error(hostText('Dosya çok büyük (sınır: 2 MB).', 'File is too large (limit: 2 MB).'));
  }
  const text = await readFile(resolved, 'utf8');
  const lines = text.length === 0 ? 0 : text.split(/\r\n|\n|\r/).length;
  return { path: resolved, lines, size: info.size };
}

/** `create_directory` — izinli kök altında. */
export async function createDirectoryTool(
  args: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  const raw = sanitizeSingleLine(args.path, 1000);
  if (!raw) throw new Error(hostText('Klasör yolu gerekli.', 'A folder path is required.'));
  const resolved = ensurePathAllowed(resolveFolderPath(raw));
  await mkdir(resolved, { recursive: true });
  return { created: true, path: resolved };
}

/** `get_file_info` — boyut / tarih; içerik yok. */
export async function getFileInfo(args: Record<string, unknown>): Promise<Record<string, unknown>> {
  const raw = sanitizeSingleLine(args.path, 1000);
  if (!raw) throw new Error(hostText('Dosya yolu gerekli.', 'A file path is required.'));
  const resolved = ensurePathAllowed(resolveFolderPath(raw));
  const info = await stat(resolved);
  return {
    path: resolved,
    is_file: info.isFile(),
    is_directory: info.isDirectory(),
    size: info.size,
    modified: info.mtime.toISOString(),
  };
}

/** `get_special_folder_path` — masaüstü/belgeler yolu; panoya yazmaz. */
export function getSpecialFolderPath(args: Record<string, unknown>): Record<string, unknown> {
  const raw = sanitizeSingleLine(args.folder ?? args.path ?? 'desktop', 80);
  const resolved = resolveSpecialFolder(raw) ?? resolveSpecialFolder(raw.replace(/\s+/g, ''));
  if (!resolved) {
    throw new Error(
      hostText(`'${raw}' bilinen bir özel klasör değil.`, `'${raw}' is not a known special folder.`),
    );
  }
  return { folder: raw, path: resolved };
}

/** `get_folder_size` — izinli klasör toplamı; içerik yok. */
export async function getFolderSize(args: Record<string, unknown>): Promise<Record<string, unknown>> {
  const raw = sanitizeSingleLine(args.path ?? 'desktop', 1000);
  if (!raw) throw new Error(hostText('Klasör yolu gerekli.', 'A folder path is required.'));
  const resolved = ensureDirectory(resolveFolderPath(raw));
  let bytes = 0;
  let files = 0;
  let scanned = 0;
  const stack = [resolved];
  while (stack.length && scanned < 20_000) {
    const dir = stack.pop()!;
    let entries;
    try {
      entries = await readdir(dir, { withFileTypes: true });
    } catch {
      continue;
    }
    for (const entry of entries) {
      if (SKIP_DIRS.has(entry.name) || entry.name.startsWith('.')) continue;
      scanned += 1;
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        stack.push(full);
        continue;
      }
      if (!entry.isFile()) continue;
      try {
        bytes += (await stat(full)).size;
        files += 1;
      } catch {
      }
    }
  }
  return {
    path: resolved,
    bytes,
    files,
    mb: Math.round((bytes / 1_000_000) * 10) / 10,
    truncated: scanned >= 20_000,
  };
}

const LIST_EXT_ALLOW = new Set([
  'pdf',
  'txt',
  'doc',
  'docx',
  'xls',
  'xlsx',
  'ppt',
  'pptx',
  'jpg',
  'jpeg',
  'png',
  'gif',
  'zip',
  'mp3',
  'mp4',
  'md',
  'csv',
  'json',
]);

/** `list_files_by_extension` — izinli klasörde uzantı süzgeci. */
export async function listFilesByExtension(
  args: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  const raw = sanitizeSingleLine(args.path ?? 'desktop', 1000);
  const ext = sanitizeSingleLine(args.extension ?? args.ext ?? '', 8)
    .toLowerCase()
    .replace(/^\./, '');
  if (!LIST_EXT_ALLOW.has(ext)) {
    throw new Error(
      hostText(`'${ext}' izinli bir uzantı değil.`, `'${ext}' is not an allowed extension.`),
    );
  }
  const resolved = ensureDirectory(resolveFolderPath(raw));
  const limit = Math.max(1, Math.min(Number(args.limit ?? 40) || 40, 80));
  const entries = await readdir(resolved, { withFileTypes: true });
  const files: { name: string; size: number }[] = [];
  for (const entry of entries) {
    if (files.length >= limit) break;
    if (!entry.isFile() || entry.name.startsWith('.')) continue;
    if (path.extname(entry.name).toLowerCase() !== `.${ext}`) continue;
    let size = 0;
    try {
      size = (await stat(path.join(resolved, entry.name))).size;
    } catch {
      size = 0;
    }
    files.push({ name: entry.name, size });
  }
  return { path: resolved, extension: ext, count: files.length, files };
}

/** `get_newest_file` — klasörde en son değişen dosya. */
export async function getNewestFile(args: Record<string, unknown>): Promise<Record<string, unknown>> {
  const raw = sanitizeSingleLine(args.path ?? 'downloads', 1000);
  const resolved = ensureDirectory(resolveFolderPath(raw));
  const entries = await readdir(resolved, { withFileTypes: true });
  let newest: { name: string; path: string; size: number; modified: string } | null = null;
  for (const entry of entries) {
    if (!entry.isFile() || entry.name.startsWith('.')) continue;
    const full = path.join(resolved, entry.name);
    try {
      const info = await stat(full);
      const modified = info.mtime.toISOString();
      if (!newest || modified > newest.modified) {
        newest = { name: entry.name, path: full, size: info.size, modified };
      }
    } catch {
    }
  }
  return { found: Boolean(newest), path: resolved, file: newest };
}

/** `is_directory_empty` — yalnızca dosya/klasör varlığı. */
export async function isDirectoryEmpty(
  args: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  const raw = sanitizeSingleLine(args.path ?? 'desktop', 1000);
  const resolved = ensureDirectory(resolveFolderPath(raw));
  const entries = await readdir(resolved);
  const visible = entries.filter((name) => !name.startsWith('.')).length;
  return { path: resolved, empty: visible === 0, count: visible };
}

/** `get_largest_file` — klasörde en büyük dosya; içerik yok. */
export async function getLargestFile(args: Record<string, unknown>): Promise<Record<string, unknown>> {
  const raw = sanitizeSingleLine(args.path ?? 'desktop', 1000);
  const resolved = ensureDirectory(resolveFolderPath(raw));
  const entries = await readdir(resolved, { withFileTypes: true });
  let largest: { name: string; path: string; size: number } | null = null;
  for (const entry of entries) {
    if (!entry.isFile() || entry.name.startsWith('.')) continue;
    const full = path.join(resolved, entry.name);
    try {
      const size = (await stat(full)).size;
      if (!largest || size > largest.size) {
        largest = { name: entry.name, path: full, size };
      }
    } catch {
    }
  }
  return { found: Boolean(largest), path: resolved, file: largest };
}

/** `count_files_by_extension` — sayı; liste değil. */
export async function countFilesByExtension(
  args: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  const raw = sanitizeSingleLine(args.path ?? 'desktop', 1000);
  const ext = sanitizeSingleLine(args.extension ?? args.ext ?? '', 8)
    .toLowerCase()
    .replace(/^\./, '');
  if (!LIST_EXT_ALLOW.has(ext)) {
    throw new Error(
      hostText(`'${ext}' izinli bir uzantı değil.`, `'${ext}' is not an allowed extension.`),
    );
  }
  const resolved = ensureDirectory(resolveFolderPath(raw));
  const entries = await readdir(resolved, { withFileTypes: true });
  let count = 0;
  for (const entry of entries) {
    if (!entry.isFile() || entry.name.startsWith('.')) continue;
    if (path.extname(entry.name).toLowerCase() === `.${ext}`) count += 1;
  }
  return { path: resolved, extension: ext, count };
}

/** `list_subdirectories` — yalnızca klasör adları. */
export async function listSubdirectories(
  args: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  const raw = sanitizeSingleLine(args.path ?? 'desktop', 1000);
  const resolved = ensureDirectory(resolveFolderPath(raw));
  const limit = Math.max(1, Math.min(Number(args.limit ?? 40) || 40, 80));
  const entries = await readdir(resolved, { withFileTypes: true });
  const folders = entries
    .filter((entry) => entry.isDirectory() && !entry.name.startsWith('.') && !SKIP_DIRS.has(entry.name))
    .map((entry) => entry.name)
    .slice(0, limit);
  return { path: resolved, count: folders.length, folders };
}

/** `list_today_files` — bugün değişen dosyalar (yerel gün). */
export async function listTodayFiles(args: Record<string, unknown>): Promise<Record<string, unknown>> {
  const raw = sanitizeSingleLine(args.path ?? 'downloads', 1000);
  const resolved = ensureDirectory(resolveFolderPath(raw));
  const start = new Date();
  start.setHours(0, 0, 0, 0);
  const startMs = start.getTime();
  const limit = Math.max(1, Math.min(Number(args.limit ?? 20) || 20, 40));
  const entries = await readdir(resolved, { withFileTypes: true });
  const files: { name: string; size: number; modified: string }[] = [];
  for (const entry of entries) {
    if (!entry.isFile() || entry.name.startsWith('.')) continue;
    const full = path.join(resolved, entry.name);
    try {
      const info = await stat(full);
      if (info.mtimeMs < startMs) continue;
      files.push({
        name: entry.name,
        size: info.size,
        modified: info.mtime.toISOString(),
      });
    } catch {
    }
  }
  files.sort((a, b) => (a.modified < b.modified ? 1 : -1));
  const items = files.slice(0, limit);
  return { path: resolved, count: items.length, files: items };
}

/** `get_oldest_file` — klasörde en eski dosya; en büyüğü/yeniyi ezmez. */
export async function getOldestFile(args: Record<string, unknown>): Promise<Record<string, unknown>> {
  const raw = sanitizeSingleLine(args.path ?? 'desktop', 1000);
  const resolved = ensureDirectory(resolveFolderPath(raw));
  const entries = await readdir(resolved, { withFileTypes: true });
  let oldest: { name: string; path: string; size: number; modified: string } | null = null;
  for (const entry of entries) {
    if (!entry.isFile() || entry.name.startsWith('.')) continue;
    const full = path.join(resolved, entry.name);
    try {
      const info = await stat(full);
      const modified = info.mtime.toISOString();
      if (!oldest || modified < oldest.modified) {
        oldest = { name: entry.name, path: full, size: info.size, modified };
      }
    } catch {
    }
  }
  return { found: Boolean(oldest), path: resolved, file: oldest };
}

/** `count_subdirectories` — sayı; klasör listesi değil. */
export async function countSubdirectories(
  args: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  const raw = sanitizeSingleLine(args.path ?? 'desktop', 1000);
  const resolved = ensureDirectory(resolveFolderPath(raw));
  const entries = await readdir(resolved, { withFileTypes: true });
  let count = 0;
  for (const entry of entries) {
    if (!entry.isDirectory() || entry.name.startsWith('.') || SKIP_DIRS.has(entry.name)) continue;
    count += 1;
  }
  return { path: resolved, count };
}

/** `get_smallest_file` — klasörde en küçük dosya; en büyüğü/eskisi değil. */
export async function getSmallestFile(args: Record<string, unknown>): Promise<Record<string, unknown>> {
  const raw = sanitizeSingleLine(args.path ?? 'desktop', 1000);
  const resolved = ensureDirectory(resolveFolderPath(raw));
  const entries = await readdir(resolved, { withFileTypes: true });
  let smallest: { name: string; path: string; size: number } | null = null;
  for (const entry of entries) {
    if (!entry.isFile() || entry.name.startsWith('.')) continue;
    const full = path.join(resolved, entry.name);
    try {
      const size = (await stat(full)).size;
      if (!smallest || size < smallest.size) {
        smallest = { name: entry.name, path: full, size };
      }
    } catch {
    }
  }
  return { found: Boolean(smallest), path: resolved, file: smallest };
}

/** `list_this_week_files` — bu hafta değişen dosyalar; bugün/son N değil. */
export async function listThisWeekFiles(
  args: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  const raw = sanitizeSingleLine(args.path ?? 'downloads', 1000);
  const resolved = ensureDirectory(resolveFolderPath(raw));
  const now = new Date();
  const mondayOffset = (now.getDay() + 6) % 7;
  const start = new Date(now);
  start.setDate(now.getDate() - mondayOffset);
  start.setHours(0, 0, 0, 0);
  const startMs = start.getTime();
  const limit = Math.max(1, Math.min(Number(args.limit ?? 20) || 20, 40));
  const entries = await readdir(resolved, { withFileTypes: true });
  const files: { name: string; size: number; modified: string }[] = [];
  for (const entry of entries) {
    if (!entry.isFile() || entry.name.startsWith('.')) continue;
    const full = path.join(resolved, entry.name);
    try {
      const info = await stat(full);
      if (info.mtimeMs < startMs) continue;
      files.push({
        name: entry.name,
        size: info.size,
        modified: info.mtime.toISOString(),
      });
    } catch {
    }
  }
  files.sort((a, b) => (a.modified < b.modified ? 1 : -1));
  const items = files.slice(0, limit);
  return { path: resolved, count: items.length, files: items };
}

/** `list_yesterday_files` — dün değişen dosyalar; bugün/hafta değil. */
export async function listYesterdayFiles(
  args: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  const raw = sanitizeSingleLine(args.path ?? 'downloads', 1000);
  const resolved = ensureDirectory(resolveFolderPath(raw));
  const start = new Date();
  start.setDate(start.getDate() - 1);
  start.setHours(0, 0, 0, 0);
  const end = new Date(start);
  end.setDate(end.getDate() + 1);
  const startMs = start.getTime();
  const endMs = end.getTime();
  const limit = Math.max(1, Math.min(Number(args.limit ?? 20) || 20, 40));
  const entries = await readdir(resolved, { withFileTypes: true });
  const files: { name: string; size: number; modified: string }[] = [];
  for (const entry of entries) {
    if (!entry.isFile() || entry.name.startsWith('.')) continue;
    const full = path.join(resolved, entry.name);
    try {
      const info = await stat(full);
      if (info.mtimeMs < startMs || info.mtimeMs >= endMs) continue;
      files.push({
        name: entry.name,
        size: info.size,
        modified: info.mtime.toISOString(),
      });
    } catch {
    }
  }
  files.sort((a, b) => (a.modified < b.modified ? 1 : -1));
  const items = files.slice(0, limit);
  return { path: resolved, count: items.length, files: items };
}

/** `count_today_files` — bugünkü sayı; liste değil. */
export async function countTodayFiles(args: Record<string, unknown>): Promise<Record<string, unknown>> {
  const raw = sanitizeSingleLine(args.path ?? 'downloads', 1000);
  const resolved = ensureDirectory(resolveFolderPath(raw));
  const start = new Date();
  start.setHours(0, 0, 0, 0);
  const startMs = start.getTime();
  const entries = await readdir(resolved, { withFileTypes: true });
  let count = 0;
  for (const entry of entries) {
    if (!entry.isFile() || entry.name.startsWith('.')) continue;
    const full = path.join(resolved, entry.name);
    try {
      if ((await stat(full)).mtimeMs >= startMs) count += 1;
    } catch {
    }
  }
  return { path: resolved, count };
}

/** `list_this_month_files` — bu ay değişenler; bugün/hafta/dün değil. */
export async function listThisMonthFiles(
  args: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  const raw = sanitizeSingleLine(args.path ?? 'downloads', 1000);
  const resolved = ensureDirectory(resolveFolderPath(raw));
  const start = new Date();
  start.setDate(1);
  start.setHours(0, 0, 0, 0);
  const startMs = start.getTime();
  const limit = Math.max(1, Math.min(Number(args.limit ?? 20) || 20, 40));
  const entries = await readdir(resolved, { withFileTypes: true });
  const files: { name: string; size: number; modified: string }[] = [];
  for (const entry of entries) {
    if (!entry.isFile() || entry.name.startsWith('.')) continue;
    const full = path.join(resolved, entry.name);
    try {
      const info = await stat(full);
      if (info.mtimeMs < startMs) continue;
      files.push({
        name: entry.name,
        size: info.size,
        modified: info.mtime.toISOString(),
      });
    } catch {
    }
  }
  files.sort((a, b) => (a.modified < b.modified ? 1 : -1));
  const items = files.slice(0, limit);
  return { path: resolved, count: items.length, files: items };
}

/** `count_yesterday_files` — dünkü sayı; liste / bugün sayı değil. */
export async function countYesterdayFiles(
  args: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  const raw = sanitizeSingleLine(args.path ?? 'downloads', 1000);
  const resolved = ensureDirectory(resolveFolderPath(raw));
  const start = new Date();
  start.setDate(start.getDate() - 1);
  start.setHours(0, 0, 0, 0);
  const end = new Date(start);
  end.setDate(end.getDate() + 1);
  const startMs = start.getTime();
  const endMs = end.getTime();
  const entries = await readdir(resolved, { withFileTypes: true });
  let count = 0;
  for (const entry of entries) {
    if (!entry.isFile() || entry.name.startsWith('.')) continue;
    const full = path.join(resolved, entry.name);
    try {
      const mtime = (await stat(full)).mtimeMs;
      if (mtime >= startMs && mtime < endMs) count += 1;
    } catch {
    }
  }
  return { path: resolved, count };
}

/** `count_this_week_files` — bu hafta sayı; liste / bugün-dün sayı değil. */
export async function countThisWeekFiles(
  args: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  const raw = sanitizeSingleLine(args.path ?? 'downloads', 1000);
  const resolved = ensureDirectory(resolveFolderPath(raw));
  const now = new Date();
  const mondayOffset = (now.getDay() + 6) % 7;
  const start = new Date(now);
  start.setDate(now.getDate() - mondayOffset);
  start.setHours(0, 0, 0, 0);
  const startMs = start.getTime();
  const entries = await readdir(resolved, { withFileTypes: true });
  let count = 0;
  for (const entry of entries) {
    if (!entry.isFile() || entry.name.startsWith('.')) continue;
    const full = path.join(resolved, entry.name);
    try {
      if ((await stat(full)).mtimeMs >= startMs) count += 1;
    } catch {
    }
  }
  return { path: resolved, count };
}

/** `count_this_month_files` — bu ay sayı; liste değil. */
export async function countThisMonthFiles(
  args: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  const raw = sanitizeSingleLine(args.path ?? 'downloads', 1000);
  const resolved = ensureDirectory(resolveFolderPath(raw));
  const start = new Date();
  start.setDate(1);
  start.setHours(0, 0, 0, 0);
  const startMs = start.getTime();
  const entries = await readdir(resolved, { withFileTypes: true });
  let count = 0;
  for (const entry of entries) {
    if (!entry.isFile() || entry.name.startsWith('.')) continue;
    const full = path.join(resolved, entry.name);
    try {
      if ((await stat(full)).mtimeMs >= startMs) count += 1;
    } catch {
    }
  }
  return { path: resolved, count };
}

/** `list_recent_files` — özel klasörde son değişen dosyalar. */
export async function listRecentFiles(
  args: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  const raw = sanitizeSingleLine(args.path ?? 'downloads', 1000);
  const resolved = ensureDirectory(resolveFolderPath(raw));
  const limit = Math.max(1, Math.min(Number(args.limit ?? 8) || 8, 30));
  const entries = await readdir(resolved, { withFileTypes: true });
  const files: { name: string; path: string; size: number; modified: string }[] = [];
  for (const entry of entries) {
    if (entry.name.startsWith('.') || !entry.isFile()) continue;
    const full = path.join(resolved, entry.name);
    try {
      const info = await stat(full);
      files.push({
        name: entry.name,
        path: full,
        size: info.size,
        modified: info.mtime.toISOString(),
      });
    } catch {
    }
  }
  files.sort((a, b) => (a.modified < b.modified ? 1 : -1));
  const items = files.slice(0, limit);
  return { path: resolved, count: items.length, files: items };
}

/** `save_selected_text` — seçim veya pano → izinli dosya; panoyu ezmez, üzerine yazmaz (create). */
export async function saveSelectedText(
  args: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  const source = String(args.source ?? 'selection').toLowerCase() === 'clipboard' ? 'clipboard' : 'selection';
  const mode = String(args.mode ?? 'create').toLowerCase() === 'append' ? 'append' : 'create';
  const payload =
    source === 'clipboard'
      ? clipboardRead()
      : await getSelectedText();
  const text = String(payload.text ?? '');
  if (!text.trim()) {
    return { saved: false, empty: true, path: '', source, mode };
  }
  if (text.length > 2_000_000) {
    throw new Error(hostText('İçerik çok büyük (sınır: 2 MB).', 'Content is too large (limit: 2 MB).'));
  }

  const rawPath = sanitizeSingleLine(args.path ?? '', 1000);
  const folderHint = sanitizeSingleLine(args.folder ?? 'desktop', 200);
  let target = rawPath;
  if (!target) {
    const stamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
    target = `${folderHint}/uryx-secim-${stamp}.txt`;
  } else if (!/\.\w{2,4}$/.test(target) && !target.includes('/') && !target.includes('\\')) {
    target = `${folderHint}/${target}.txt`;
  }
  const resolved = ensurePathAllowed(resolveFolderPath(target));

  if (mode === 'create') {
    try {
      await access(resolved, constants.F_OK);
      throw new Error(
        hostText(`'${target}' zaten var. Üzerine yazılmadı.`, `'${target}' already exists. It was not overwritten.`),
      );
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== 'ENOENT') {
        if (isAlreadyExistsError(error)) throw error;
      }
    }
    await mkdir(path.dirname(resolved), { recursive: true });
    await writeFile(resolved, text, 'utf8');
    return {
      saved: true,
      empty: false,
      appended: false,
      path: resolved,
      bytes: Buffer.byteLength(text, 'utf8'),
      source,
      mode,
    };
  }

  let prefix = '';
  try {
    await access(resolved, constants.F_OK);
    prefix = '\n';
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error;
  }
  await mkdir(path.dirname(resolved), { recursive: true });
  await appendFile(resolved, prefix + text, 'utf8');
  return {
    saved: true,
    empty: false,
    appended: true,
    path: resolved,
    bytes: Buffer.byteLength(text, 'utf8'),
    source,
    mode,
  };
}

/** `show_in_folder` — Gezgin'de seçili göster; kabuk yok. */
export function showInFolder(args: Record<string, unknown>): Record<string, unknown> {
  const raw = sanitizeSingleLine(args.path, 1000);
  if (!raw) {
    throw new Error(hostText('Dosya veya klasör yolu gerekli.', 'A file or folder path is required.'));
  }
  const resolved = ensurePathAllowed(resolveFolderPath(raw));
  shell.showItemInFolder(resolved);
  return { shown: true, path: resolved };
}
