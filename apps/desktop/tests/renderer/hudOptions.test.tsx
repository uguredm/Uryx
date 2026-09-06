import '@testing-library/jest-dom/vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { HudTerminalOptions } from '@/components/hud/HudTerminalOptions';
import { DEFAULT_SETTINGS } from '@shared/settings';

describe('HudTerminalOptions', () => {
  it('aktif anahtarları işaretler ve tıklayınca store yamasını gönderir', () => {
    const onUpdate = vi.fn();
    const stopSpeech = vi.fn();
    render(
      <HudTerminalOptions
        settings={{
          toolsEnabled: true,
          ragEnabled: false,
          thinkingMode: true,
          ttsEnabled: true,
        }}
        onUpdate={onUpdate}
        stopSpeech={stopSpeech}
      />,
    );

    expect(screen.getByRole('button', { name: 'TOOLS' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: 'DOCS' })).toHaveAttribute('aria-pressed', 'false');

    fireEvent.click(screen.getByRole('button', { name: 'DOCS' }));
    expect(onUpdate).toHaveBeenCalledWith({ ragEnabled: true });
    expect(stopSpeech).not.toHaveBeenCalled();
  });

  it('ses kapanınca konuşmayı durdurur', () => {
    const onUpdate = vi.fn();
    const stopSpeech = vi.fn();
    render(
      <HudTerminalOptions
        settings={{ ...DEFAULT_SETTINGS, ttsEnabled: true }}
        onUpdate={onUpdate}
        stopSpeech={stopSpeech}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'VOICE' }));
    expect(stopSpeech).toHaveBeenCalledOnce();
    expect(onUpdate).toHaveBeenCalledWith({ ttsEnabled: false });
  });
});
