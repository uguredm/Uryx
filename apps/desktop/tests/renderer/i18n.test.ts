import { describe, expect, it } from 'vitest';

import { MESSAGE_TABLES, translate, type MessageKey } from '@/lib/i18n';

const SKIP_FIRST_LETTER = /^(?:\{|\.|`|llama-server|docker-compose|uryx-api|nvidia-smi|arXiv|search\.|large-v3|motor |kayıtlı|çıkış kodu|s\.\{)/i;
const CHROME_PREFIX = /^(?:hud|ws)\./;
const CHROME_SENTENCE = /(?:Detail|Hint|desc)$/;

function firstLetterIsCapital(text: string): boolean {
  const trimmed = text.trim();
  if (!trimmed || SKIP_FIRST_LETTER.test(trimmed)) return true;
  const ch = trimmed[0]!;
  return ch === ch.toLocaleUpperCase('tr-TR');
}

function skipCapitalKey(key: string): boolean {
  return /^(?:fmt\.(?:sec|min)|mcp\.(?:server|callable|arg|advertised)|host\.verb|system\.routingCloud|settings\.cloud\.modelPh)/.test(
    key,
  );
}

function lettersAreUppercaseTr(text: string): boolean {
  const stripped = text.replace(/\{[^}]+\}/g, '');
  for (const ch of stripped) {
    if (/\p{L}/u.test(ch) && ch !== ch.toLocaleUpperCase('tr-TR')) return false;
  }
  return true;
}

describe('i18n', () => {
  it('Türkçe HUD etiketlerini verir', () => {
    expect(translate('tr', 'hud.nav.settings')).toBe('AYARLAR');
    expect(translate('tr', 'hud.toggle.tools')).toBe('ARAÇLAR');
    expect(translate('tr', 'settings.section.connection')).toBe('Bağlantı');
    expect(translate('en', 'settings.section.connection')).toBe('Connection');
  });

  it('İngilizce HUD etiketlerini verir', () => {
    expect(translate('en', 'hud.nav.settings')).toBe('CONFIGURATION');
    expect(translate('en', 'hud.toggle.voice')).toBe('VOICE');
    expect(translate('en', 'hud.artifact.pageMatch', { page: 3, pct: '82' })).toBe(
      'PAGE 3 // 82% MATCH',
    );
  });

  it('yerel yedek modeli bulut diye yazmaz', () => {
    expect(translate('en', 'hud.health.modelDetail')).not.toMatch(/cloud/i);
    expect(translate('en', 'banner.model')).not.toMatch(/cloud/i);
    expect(translate('en', 'hud.health.modelDetail')).toMatch(/backup model/i);
    expect(translate('tr', 'hud.health.modelDetail')).toMatch(/yedek model/i);
  });

  it('Türkçe HUD/menü metinleri ilk harfi büyük başlar', () => {
    const failed = (Object.entries(MESSAGE_TABLES.tr) as Array<[MessageKey, string]>)
      .filter(([key]) => !skipCapitalKey(key))
      .filter(([, text]) => !firstLetterIsCapital(text))
      .map(([key, text]) => `${key}: ${text}`);
    expect(failed).toEqual([]);
  });

  it('D26 TR HUD/ws kromu ALL-CAPS; cümle detayları sentence case', () => {
    const failed = (Object.entries(MESSAGE_TABLES.tr) as Array<[MessageKey, string]>)
      .filter(([key]) => CHROME_PREFIX.test(key) && !CHROME_SENTENCE.test(key))
      .filter(([, text]) => !lettersAreUppercaseTr(text))
      .map(([key, text]) => `${key}: ${text}`);
    expect(failed).toEqual([]);
    expect(translate('tr', 'hud.health.modelDetail')).toBe(
      'Yerel model yüklenmedi — sohbet yedek modele düşebilir.',
    );
    expect(translate('tr', 'hud.metric.cpu')).toBe('İŞLEMCİ');
  });

  it('HUD eylemleri Türkçe ve İngilizce ayrıdır', () => {
    expect(translate('tr', 'hud.action.copyLine')).toBe('SATIRI KOPYALA');
    expect(translate('tr', 'hud.showMore')).toBe('DAHA FAZLA');
    expect(translate('en', 'hud.showMore')).toBe('MORE');
    expect(translate('tr', 'ws.footer.sys', { state: 'ÇEVRİMİÇİ' })).toBe('SİSTEM · ÇEVRİMİÇİ');
    expect(translate('en', 'settings.sttActive', { model: 'medium', device: 'cpu' })).toBe(
      'Active: medium · cpu',
    );
    expect(translate('en', 'hud.action.copyLine')).toBe('COPY LINE');
    expect(translate('tr', 'hud.core.listenStart')).toBe('KONUŞMAYA BAŞLA');
    expect(translate('en', 'hud.core.listenStart')).toBe('START TALKING');
    expect(translate('tr', 'tray.show')).toBe("Uryx'i göster");
    expect(translate('en', 'tray.show')).toBe('Show Uryx');
    expect(translate('tr', 'tray.bridgeUp')).toBe('Köprü bağlı');
    expect(translate('en', 'tray.bridgeUp')).toBe('Host bridge connected');
  });

  it('dil seçici ve HUD kromu karışık dil taşımaz', () => {
    expect(translate('tr', 'settings.lang.en')).toBe('İngilizce');
    expect(translate('en', 'settings.lang.tr')).toBe('Turkish');
    expect(translate('tr', 'ws.brand.sub')).toBe('YEREL ÇEKİRDEK');
    expect(translate('en', 'ws.brand.sub')).toBe('LOCAL WINDOWS CORE');
    expect(translate('tr', 'svc.llm')).toBe('Yerel model');
    expect(translate('en', 'svc.llm')).toBe('Local model');
    expect(translate('en', 'hud.health.offline')).toBe('NO SERVER');
    expect(translate('tr', 'settings.wakeEnable')).toBe('Uyandırma ifadesini aç');
    expect(translate('tr', 'hud.health.offline')).toBe('SUNUCU YOK');
    expect(translate('en', 'settings.wakeEnableDesc')).not.toMatch(/uyan|dinle /i);
  });

  it('MCP açma metni boşluksuz slash zinciri taşımaz', () => {
    for (const language of ['tr', 'en'] as const) {
      const longSlash = translate(language, 'settings.mcpEnableDesc')
        .split(/\s+/)
        .some((word) => word.includes('/') && word.length > 32);
      expect(longSlash, language).toBe(false);
    }
  });

  it('güncelleme ipucu gh auth / gizli depo demez', () => {
    expect(translate('tr', 'settings.about.updateHint').toLowerCase()).not.toMatch(
      /gh auth|gizli github/,
    );
    expect(translate('en', 'settings.about.updateHint').toLowerCase()).not.toMatch(
      /gh auth|private github/,
    );
  });
});
