/** Tarayıcı form araçları: stale snapshot, şifre, Playwright clicksız. */

import { describe, expect, it } from 'vitest';

import {
  normalizePublicWebUrl,
  rejectPasswordControl,
  resolveBrowserControl,
} from '../electron/host-tools/browser';
import { PLAYWRIGHT_MCP_RECIPE } from '@shared/settings';
import { executeHostTool, resetHostToolGuard } from '../electron/host-tools';

const sample = [
  {
    index: 0,
    tag: 'input',
    type: 'text',
    role: 'textbox',
    name: 'e-posta',
    href: null,
  },
  {
    index: 1,
    tag: 'input',
    type: 'password',
    role: 'textbox',
    name: 'şifre',
    href: null,
  },
];

describe('browser form guards', () => {
  it('eski indeks stale_snapshot verir', () => {
    expect(() => resolveBrowserControl(sample, { index: 9 })).toThrow(/stale_snapshot/);
    expect(() => resolveBrowserControl(sample, { role: 'button', name: 'yok' })).toThrow(
      /stale_snapshot/,
    );
  });

  it('şifre alanına yazmayı keser', () => {
    const control = resolveBrowserControl(sample, { index: 1 });
    expect(() => rejectPasswordControl(control.type)).toThrow(/Şifre/i);
    expect(() => rejectPasswordControl('text')).not.toThrow();
  });

  it('private URL tıklama yolunda da reddedilir', () => {
    expect(() => normalizePublicWebUrl('http://192.168.0.5/form')).toThrow(/özel ağ/i);
  });

  it('Playwright tarifinde click/type yok', () => {
    expect(PLAYWRIGHT_MCP_RECIPE.allowedTools).not.toContain('browser_click');
    expect(PLAYWRIGHT_MCP_RECIPE.allowedTools).not.toContain('browser_type');
    expect(PLAYWRIGHT_MCP_RECIPE.allowedTools).not.toContain('browser_evaluate');
  });

  it('HOST click sayfa yokken çalışmaz', async () => {
    resetHostToolGuard();
    const fill = await executeHostTool('browser_fill_form', {
      fields: [{ index: 0, text: 'a' }],
    });
    expect(fill.success).toBe(false);
  });
});
