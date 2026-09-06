import type { UiLanguage } from '@shared/settings';

import { translate, type MessageKey } from '@/lib/i18n';

const TR_LETTER = /[çğıöşüÇĞİÖŞÜ]/;
const ASCII_TR_NARRATE =
  /kaydettim|kopyalad|bulamad|okudum|gönderdim|gonderdim|dosyası|klasör|açtım|yaptım|\bKonum:|\bveya\b|yoksa|açılır|kapanır/i;
const EN_TOOL_STUB = /^(Runs on this Windows PC|Runs in the Uryx backend)\b/i;

const ACRONYMS: Record<string, string> = {
  cpu: 'CPU',
  gpu: 'GPU',
  ram: 'RAM',
  usb: 'USB',
  sha: 'SHA',
  vscode: 'VS Code',
  wifi: 'Wi-Fi',
  ssid: 'SSID',
  iban: 'IBAN',
  dns: 'DNS',
  doi: 'DOI',
  fx: 'FX',
  mcp: 'MCP',
  tts: 'TTS',
  stt: 'STT',
  rag: 'RAG',
  os: 'OS',
  ip: 'IP',
  uv: 'UV',
  aqi: 'AQI',
  rss: 'RSS',
  osm: 'OSM',
  npm: 'npm',
  pypi: 'PyPI',
  iss: 'ISS',
  llm: 'LLM',
  pid: 'PID',
};

const SERVICE_KEYS: Record<string, MessageKey> = {
  postgres: 'svc.postgres',
  qdrant: 'svc.qdrant',
  llm: 'svc.llm',
  whisper: 'svc.whisper',
  tts: 'svc.tts',
  'uryx-api': 'svc.api',
  desktop: 'svc.desktop',
};

export function hasTurkishLetters(text: string): boolean {
  return TR_LETTER.test(text);
}

/** Hide Turkish API copy when the HUD is English. */
export function localizeApiText(text: string | null | undefined, language: UiLanguage): string {
  const value = (text ?? '').trim();
  if (!value) return '';
  if (language === 'tr') {
    if (EN_TOOL_STUB.test(value)) return '';
    return value;
  }
  if (hasTurkishLetters(value) || ASCII_TR_NARRATE.test(value)) return '';
  return value;
}

export function englishToolLabel(name: string): string {
  return name
    .split('_')
    .map((part, index) => {
      const key = part.toLowerCase();
      if (ACRONYMS[key]) return ACRONYMS[key];
      if (index === 0) return part.charAt(0).toUpperCase() + part.slice(1).toLowerCase();
      return part.toLowerCase();
    })
    .join(' ');
}

export function toolDisplayName(
  name: string,
  displayName: string,
  language: UiLanguage,
): string {
  if (language === 'tr') return displayName || englishToolLabel(name);
  return englishToolLabel(name);
}

export function serviceDisplayName(
  name: string,
  fallback: string,
  language: UiLanguage,
): string {
  const key = SERVICE_KEYS[name];
  if (key) return translate(language, key);
  if (language === 'en' && hasTurkishLetters(fallback)) return englishToolLabel(name);
  return fallback;
}
