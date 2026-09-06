/**
 * Host çıktısındaki URL sızıntısı.
 *
 * Odysseus `_safe_url`: userinfo / query / fragment yok; scheme+host+port+path kalır.
 * Sentry `stripUrlQueryAndFragment` / `getSanitizedUrlString`: `?` `#` ve `user:pass@`.
 */

const URL_IN_TEXT = /(?:https?|wss?|ssh|tcp):\/\/[^\s"'<>\\]+/gi;

/** Tek URL'yi kimlik ve sorgu olmadan döndürür. */
export function safeUrl(raw: string): string {
  const value = String(raw ?? '')
    .trim()
    .replace(/[),.;]+$/, '');
  if (!value) return '';

  try {
    const parsed = new URL(value);
    if (!parsed.hostname) return '';
    parsed.username = '';
    parsed.password = '';
    parsed.search = '';
    parsed.hash = '';
    const port = parsed.port ? `:${parsed.port}` : '';
    const path = parsed.pathname === '/' ? '' : parsed.pathname;
    return `${parsed.protocol}//${parsed.hostname}${port}${path}`;
  } catch {
    const noQuery = value.split(/[?#]/, 1)[0] ?? '';
    return noQuery.replace(/^(https?|wss?|ssh|tcp):\/\/[^/@]+@/i, '$1://');
  }
}

/** Log / hata metnindeki URL'leri güvenli forma çevirir. */
export function redactUrlsInText(text: string): string {
  if (!text) return text;
  return text.replace(URL_IN_TEXT, (match) => {
    const cleaned = match.replace(/[),.;]+$/, '');
    const suffix = match.slice(cleaned.length);
    return `${safeUrl(cleaned) || '[url]'}${suffix}`;
  });
}

const SECRET_PATTERNS: readonly RegExp[] = [
  /\b(?:github_pat|ghp|gho|ghs|ghu|ghr)_[A-Za-z0-9_]{8,}\b/g,
  /\bhf_[A-Za-z0-9]{8,}\b/g,
  /\bctx7sk_[A-Za-z0-9_-]{8,}\b/gi,
  /\bnpm_[A-Za-z0-9]{8,}\b/g,
  /\bsk-[A-Za-z0-9]{12,}\b/g,
  /\bBearer\s+[A-Za-z0-9._\-+=/]{8,}/gi,
  /\b(?:Authorization|x-api-key)\s*:\s*\S+/gi,
  /\b(?:GITHUB_PERSONAL_ACCESS_TOKEN|GH_TOKEN|GITHUB_TOKEN|HF_TOKEN|BRAVE_API_KEY|CONTEXT7_API_KEY|LIBRETRANSLATE_API_KEY|NPM_TOKEN|NODE_AUTH_TOKEN)\s*[=:]\s*\S+/gi,
];

/** PAT / Bearer / env=değer — stderr ve JSON-RPC mesajı. */
export function redactSecretsInText(text: string): string {
  if (!text) return text;
  let next = text;
  for (const pattern of SECRET_PATTERNS) {
    next = next.replace(new RegExp(pattern.source, pattern.flags), '[redacted]');
  }
  return next;
}

/** URL + sır; MCP hata/log yolu. */
export function redactHostText(text: string): string {
  return redactSecretsInText(redactUrlsInText(text));
}
