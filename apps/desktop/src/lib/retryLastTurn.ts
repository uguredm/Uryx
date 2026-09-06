/**
 * Agnai `responseStore.retry` / `resend`: üretim yokken son tur.
 * Yerinde replace (kind:'retry') çalınmadı — API yok; son kullanıcı metni yeni tur.
 */

import type { AppSettings } from '@shared/settings';

export function lastUserPrompt(
  messages: Array<{ role: string; content: string }>,
): string {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    if (messages[i]?.role !== 'user') continue;
    const text = messages[i].content.replace(/\s+/g, ' ').trim();
    if (text) return text;
  }
  return '';
}

/** Agnai: `waiting` ise çık; son mesaj asistan (kullanıcıysa replace yok). */
export function canRetryLastTurn(opts: {
  generating: boolean;
  messages: Array<{ role: string; content: string }>;
}): boolean {
  if (opts.generating) return false;
  if (!lastUserPrompt(opts.messages)) return false;
  return opts.messages[opts.messages.length - 1]?.role === 'assistant';
}

export function chatTurnOptions(settings: AppSettings): Record<string, unknown> {
  return {
    use_rag: settings.ragEnabled,
    use_memory: settings.autoMemoryEnabled,
    use_tools: settings.toolsEnabled,
    thinking: settings.thinkingMode,
    concise: settings.conciseMode,
    tts: settings.ttsEnabled,
    tts_voice: settings.ttsVoice,
    tts_speed: settings.ttsSpeed,
    temperature: settings.temperature,
    max_tokens: settings.maxTokens,
    rag_top_k: settings.ragTopK,
    require_confirmation: settings.requireRiskConfirmation,
    language: settings.language === 'tr' ? 'tr' : 'en',
  };
}
