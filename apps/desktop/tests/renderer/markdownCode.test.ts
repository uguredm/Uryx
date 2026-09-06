import { describe, expect, it } from 'vitest';

import {
  codeBlockPlainText,
  languageFromPreChildren,
  markdownCodeLanguage,
  trimCodeFence,
} from '@/lib/markdownCode';

describe('markdownCode', () => {
  it('dil sınıfını ve sondaki satırı keser', () => {
    expect(markdownCodeLanguage('language-ts')).toBe('ts');
    expect(markdownCodeLanguage('hljs language-python')).toBe('python');
    expect(trimCodeFence('print(1)\n')).toBe('print(1)');
  });

  it('pre çocuklarından metin ve dil çıkarır', () => {
    const code = { props: { className: 'language-js', children: 'const x = 1;\n' } };
    expect(codeBlockPlainText(code)).toBe('const x = 1;\n');
    expect(languageFromPreChildren(code)).toBe('js');
    expect(languageFromPreChildren([code])).toBe('js');
  });
});
