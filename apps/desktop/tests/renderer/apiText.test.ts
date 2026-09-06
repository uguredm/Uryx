import { describe, expect, it } from 'vitest';

import {
  englishToolLabel,
  hasTurkishLetters,
  localizeApiText,
  serviceDisplayName,
  toolDisplayName,
} from '@/lib/apiText';
import { chatTurnOptions } from '@/lib/retryLastTurn';
import type { AppSettings } from '@shared/settings';

describe('apiText', () => {
  it('İngilizce arayüzde Türkçe API metnini gizler', () => {
    expect(hasTurkishLetters('Masaüstü köprüsü')).toBe(true);
    expect(localizeApiText('Masaüstü köprüsü', 'en')).toBe('');
    expect(localizeApiText('Masaüstü köprüsü', 'tr')).toBe('Masaüstü köprüsü');
    expect(localizeApiText('Electron connected', 'en')).toBe('Electron connected');
    expect(localizeApiText('Panoyu okudum.', 'en')).toBe('');
    expect(localizeApiText('Spotify açılır', 'en')).toBe('');
    expect(localizeApiText('Runs on this Windows PC (open_application).', 'tr')).toBe('');
  });

  it('araç adını İngilizce etikete çevirir', () => {
    expect(englishToolLabel('open_application')).toBe('Open application');
    expect(englishToolLabel('get_cpu_usage')).toBe('Get CPU usage');
    expect(englishToolLabel('open_vscode')).toBe('Open VS Code');
    expect(toolDisplayName('open_application', 'Program aç', 'en')).toBe('Open application');
    expect(toolDisplayName('set_wifi_radio', 'Wi-Fi radyo', 'en')).toBe('Set Wi-Fi radio');
    expect(toolDisplayName('open_application', 'Program aç', 'tr')).toBe('Program aç');
  });

  it('servis adını dile göre çevirir', () => {
    expect(serviceDisplayName('desktop', 'Masaüstü köprüsü', 'en')).toBe('Desktop bridge');
    expect(serviceDisplayName('desktop', 'Masaüstü köprüsü', 'tr')).toBe('Masaüstü köprüsü');
    expect(serviceDisplayName('llm', 'LLM (llama.cpp)', 'tr')).toBe('Yerel model');
    expect(serviceDisplayName('llm', 'LLM (llama.cpp)', 'en')).toBe('Local model');
  });
});

describe('chatTurnOptions', () => {
  it('sohbet turuna arayüz dilini ekler', () => {
    const settings = { language: 'en', toolsEnabled: true } as AppSettings;
    expect(chatTurnOptions(settings).language).toBe('en');
    expect(chatTurnOptions({ ...settings, language: 'tr' }).language).toBe('tr');
  });
});
