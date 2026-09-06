/**
 * Host hata sınıflandırması.
 *
 * Odysseus `_classify_error`: `str(exc)` yok; timeout / refused / dns / tls.
 * Undici `UND_ERR_CONNECT_TIMEOUT` / `UND_ERR_SOCKET` / `UND_ERR_ABORT`.
 */

import type { MessageKey } from '../../src/lib/messages';
import { hostT } from '../host-i18n';
import { redactHostText } from './safe-url';

export type HostErrorKind =
  | 'timeout'
  | 'not_found'
  | 'permission'
  | 'connection_refused'
  | 'dns'
  | 'cancelled'
  | 'network'
  | 'tls'
  | 'error';

const HOST_ERROR_KEYS: Record<HostErrorKind, MessageKey> = {
  timeout: 'hostErr.timeout',
  not_found: 'hostErr.notFound',
  permission: 'hostErr.permission',
  connection_refused: 'hostErr.refused',
  dns: 'hostErr.dns',
  cancelled: 'hostErr.cancelled',
  network: 'hostErr.network',
  tls: 'hostErr.tls',
  error: 'hostErr.error',
};

const PRODUCT_MESSAGE =
  /geçersiz|izin verilen|tanımlı bir araç|MCP|medya|kendi sürecini|çok uzun|reddedildi|allowlist|klasöre kayıt|zaten var|boş olamaz|gerekli|olmalı|okunamadı|ayarlanamadı|açılamadı|desteklenmiyor|metin dosyası değil|ikili içerik|invalid host|not allowed|is required|too long|already exists|must be|permission denied|unsupported|cannot be empty|not a text file|binary content|was cancelled|outside the allowed|was not overwritten|could not be|is not a defined|is not on the/i;

function errorCode(error: unknown): string {
  if (error && typeof error === 'object' && 'code' in error) {
    return String((error as { code?: unknown }).code ?? '');
  }
  return '';
}

function errorText(error: unknown): string {
  if (error instanceof Error) return error.message;
  return String(error ?? '');
}

/** Errno / Undici kodunu gizli metin sızdırmadan sınıfa indirger. */
export function classifyHostError(error: unknown): HostErrorKind {
  const code = errorCode(error).toUpperCase();
  const text = errorText(error).toLowerCase();
  const blob = `${code}\n${text}`;

  if (
    code === 'ABORT_ERR' ||
    code === 'UND_ERR_ABORT' ||
    code === 'UND_ERR_ABORTED' ||
    /\b(aborted|iptal|cancelled|canceled)\b/.test(blob)
  ) {
    return 'cancelled';
  }
  if (
    code === 'ETIMEDOUT' ||
    code === 'UND_ERR_CONNECT_TIMEOUT' ||
    code === 'UND_ERR_HEADERS_TIMEOUT' ||
    code === 'UND_ERR_BODY_TIMEOUT' ||
    /etimedout|connect timeout|zaman aşımı|timed out/.test(blob)
  ) {
    return 'timeout';
  }
  if (
    code === 'ENOENT' ||
    /enoent|cannot find the file|cannot find the path|is not recognized/.test(blob)
  ) {
    return 'not_found';
  }
  if (code === 'EACCES' || code === 'EPERM' || /eacces|eperm|access is denied/.test(blob)) {
    return 'permission';
  }
  if (
    code === 'ECONNREFUSED' ||
    code === 'ECONNRESET' ||
    code === 'ECONNABORTED' ||
    code === 'EPIPE' ||
    /econnrefused|econnreset|econnaborted|epipe|connection refused/.test(blob)
  ) {
    return 'connection_refused';
  }
  if (
    code === 'UND_ERR_TLS' ||
    code === 'ERR_TLS_CERT_ALTNAME_INVALID' ||
    /cert_has_expired|unable to verify|certificate|tls|ssl/.test(blob)
  ) {
    return 'tls';
  }
  if (
    code === 'ENOTFOUND' ||
    code === 'EAI_AGAIN' ||
    /enotfound|eai_again|getaddrinfo|could not be resolved/.test(blob)
  ) {
    return 'dns';
  }
  if (
    code === 'UND_ERR_SOCKET' ||
    /failed to fetch|network error|fetch failed|socket hang up|und_err_socket/.test(blob)
  ) {
    return 'network';
  }
  return 'error';
}

/**
 * LLM / IPC'ye giden metin. Bilinen ürün cümlesi kalır;
 * sistem/istisna metni asla olduğu gibi dönmez.
 */
export function formatHostError(error: unknown): string {
  const raw = redactHostText(errorText(error)).trim();
  const kind = classifyHostError(error);
  if (kind === 'cancelled' && /iptal|cancelled|canceled/i.test(raw) && !/https?:/i.test(raw)) {
    return raw.slice(0, 200);
  }
  if (kind === 'timeout' && /zaman aşımına|timed out \(\d+/i.test(raw)) return raw.slice(0, 200);
  if (kind === 'not_found' && /bulunamadı|was not found/i.test(raw) && !/https?:/i.test(raw)) {
    return raw.slice(0, 200);
  }
  if (raw.length > 0 && PRODUCT_MESSAGE.test(raw) && !/spawn |\bat [A-Za-z.]+\s*\(/.test(raw)) {
    return raw.slice(0, 400);
  }
  return hostT(HOST_ERROR_KEYS[kind]);
}
