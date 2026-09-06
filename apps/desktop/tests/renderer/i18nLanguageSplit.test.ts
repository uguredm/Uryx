import { describe, expect, it } from 'vitest';

import { MESSAGE_TABLES, type MessageKey } from '@/lib/i18n';

const TR_LETTER = /[çğıöşüÇĞİÖŞÜ]/;
const EN_ASCII_TR = /\b(?:uyan|dinle Uryx|veya)\b/i;
const TR_ENGLISH_UI =
  /\b(?:Allowlist|Wake word|Backend URL|LLM URL|llama\.cpp|llama-server|WebSocket|whitelist|Push-to-talk|sequential thinking|Global kısayol|Host denetim|Yerel token|En fazla token|Local API|NO API|Uryx API)\b|Compose \(host\)|'English'|HASH YEDEK|API YOK|backend['’]e/;

function entries(table: Record<MessageKey, string>): Array<[MessageKey, string]> {
  return Object.entries(table) as Array<[MessageKey, string]>;
}

describe('dil ayrımı', () => {
  it('İngilizce sözlükte Türkçe harf ve uyandırma kalıbı yok', () => {
    const failed = entries(MESSAGE_TABLES.en)
      .filter(([, text]) => TR_LETTER.test(text) || EN_ASCII_TR.test(text))
      .map(([key, text]) => `${key}: ${text}`);
    expect(failed).toEqual([]);
  });

  it('Türkçe sözlükte İngilizce arayüz kalıbı yok', () => {
    const failed = entries(MESSAGE_TABLES.tr)
      .filter(([, text]) => TR_ENGLISH_UI.test(text))
      .map(([key, text]) => `${key}: ${text}`);
    expect(failed).toEqual([]);
  });
});
