/** Anahtar önekine göre OpenAI-uyumlu bulut sağlayıcı (kaydetmeden önce UI). */

export interface CloudProviderHint {
  id: string;
  label: string;
  defaultModel: string;
}

const CATALOG: Record<string, CloudProviderHint> = {
  gemini: { id: 'gemini', label: 'Google Gemini', defaultModel: 'gemini-3-flash-preview' },
  openai: { id: 'openai', label: 'OpenAI', defaultModel: 'gpt-4o-mini' },
  openrouter: { id: 'openrouter', label: 'OpenRouter', defaultModel: 'openai/gpt-4o-mini' },
  groq: { id: 'groq', label: 'Groq', defaultModel: 'llama-3.3-70b-versatile' },
  deepseek: { id: 'deepseek', label: 'DeepSeek', defaultModel: 'deepseek-chat' },
  xai: { id: 'xai', label: 'xAI', defaultModel: 'grok-2-latest' },
  mistral: { id: 'mistral', label: 'Mistral', defaultModel: 'mistral-small-latest' },
};

export function detectCloudProvider(apiKey: string, model = ''): CloudProviderHint | null {
  const key = apiKey.trim();
  const catalog = model.trim().toLowerCase();
  if (!key && !catalog) return null;

  if (catalog.startsWith('claude')) return null;
  if (catalog.startsWith('gemini') || catalog.startsWith('models/gemini')) return CATALOG.gemini;
  if (/^(gpt-|o1|o3|o4|chatgpt-)/.test(catalog)) return CATALOG.openai;
  if (catalog.startsWith('deepseek')) return CATALOG.deepseek;
  if (catalog.startsWith('grok')) return CATALOG.xai;
  if (/^(mistral|codestral|pixtral|ministral)/.test(catalog)) return CATALOG.mistral;
  if (catalog.includes('/')) return CATALOG.openrouter;

  if (!key) return null;
  if (key.startsWith('sk-or-')) return CATALOG.openrouter;
  if (key.startsWith('sk-ant-')) return null;
  if (key.startsWith('gsk_')) return CATALOG.groq;
  if (key.startsWith('AIza')) return CATALOG.gemini;
  if (key.startsWith('xai-')) return CATALOG.xai;
  if (key.startsWith('sk-proj-') || key.startsWith('sk-svcacct-') || key.startsWith('sk-')) {
    return CATALOG.openai;
  }
  return CATALOG.gemini;
}
