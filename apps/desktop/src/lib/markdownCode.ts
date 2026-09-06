/**
 * BetterChatGPT CodeBlock / CodeBar:
 * çitli bloktan düz metin + dil; kopya codeRef.textContent.
 */

export function markdownCodeLanguage(className?: string | null): string {
  const match = /language-([A-Za-z0-9_+-]+)/.exec(className ?? '');
  return match?.[1] ?? '';
}

export function codeBlockPlainText(node: unknown): string {
  if (node == null || typeof node === 'boolean') return '';
  if (typeof node === 'string' || typeof node === 'number') return String(node);
  if (Array.isArray(node)) return node.map(codeBlockPlainText).join('');
  if (typeof node === 'object' && 'props' in node) {
    return codeBlockPlainText((node as { props?: { children?: unknown } }).props?.children);
  }
  return '';
}

export function languageFromPreChildren(children: unknown): string {
  const child = Array.isArray(children) ? children[0] : children;
  if (child && typeof child === 'object' && 'props' in child) {
    return markdownCodeLanguage(
      (child as { props?: { className?: string } }).props?.className,
    );
  }
  return '';
}

export function trimCodeFence(text: string): string {
  return text.replace(/\n$/, '');
}
