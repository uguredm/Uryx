import { describe, expect, it } from 'vitest';

import { detectCloudProvider } from '@/lib/cloudProvider';

describe('detectCloudProvider', () => {
  it('OpenAI sk-proj anahtarını algılar', () => {
    expect(detectCloudProvider('sk-proj-abc')?.id).toBe('openai');
  });

  it('OpenRouter sk-or anahtarını algılar', () => {
    expect(detectCloudProvider('sk-or-v1-abc')?.id).toBe('openrouter');
  });

  it('Groq gsk_ anahtarını algılar', () => {
    expect(detectCloudProvider('gsk_abc')?.id).toBe('groq');
  });

  it('Gemini AIza anahtarını algılar', () => {
    expect(detectCloudProvider('AIzaSyDummy')?.id).toBe('gemini');
  });

  it('Claude anahtarını reddeder', () => {
    expect(detectCloudProvider('sk-ant-api03-abc')).toBeNull();
  });
});
