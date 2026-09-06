/** Renderer Rollup split — main/preload bu dosyayı kullanmaz. */

export function rendererManualChunks(id: string): string | undefined {
  const path = id.replace(/\\/g, '/');
  if (
    path.includes('/node_modules/react/') ||
    path.includes('/node_modules/react-dom/') ||
    path.includes('/node_modules/scheduler/')
  ) {
    return 'react';
  }
  if (path.includes('/node_modules/highlight.js/') || path.includes('/node_modules/rehype-highlight/')) {
    return 'highlight';
  }
  if (
    path.includes('/node_modules/react-markdown/') ||
    path.includes('/node_modules/remark-parse/') ||
    path.includes('/node_modules/remark-rehype/') ||
    path.includes('/node_modules/unified/') ||
    path.includes('/node_modules/mdast-util-') ||
    path.includes('/node_modules/micromark')
  ) {
    return 'markdown';
  }
  return undefined;
}
