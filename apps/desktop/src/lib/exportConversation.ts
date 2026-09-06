/**
 * LobeChat ShareText + Cody downloadChatHistory:
 * sohbeti markdown yap. Masaüstünde native kaydet (R&D 4);
 * köprü yoksa tarayıcı <a download>.
 */

import { hudMessagePlainText } from '@/lib/confirmResponse';
import { tNow } from '@/lib/tNow';

export type ExportToolCall = {
  tool_name: string;
  display_name?: string;
  arguments?: Record<string, unknown>;
  success?: boolean;
  rejected?: boolean;
  error?: string | null;
  result?: Record<string, unknown>;
};

export type ExportMessage = {
  role: string;
  content: string;
  toolCalls?: ExportToolCall[];
  meta?: { tool_calls?: ExportToolCall[] };
};

function exportBody(message: ExportMessage): string {
  return hudMessagePlainText(message.content, message.toolCalls ?? message.meta?.tool_calls);
}

export const EXPORT_TITLE_MAX = 80;

export function sanitizeExportFilename(title: string): string {
  const cleaned = title
    .replace(/[<>:"/\\|?*\u0000-\u001f]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, EXPORT_TITLE_MAX);
  return cleaned || tNow('export.file');
}

export function exportFilename(title: string, now = new Date()): string {
  const stamp = now.toISOString().replace(/[:.]/g, '-').slice(0, 16);
  return `uryx-${sanitizeExportFilename(title)}-${stamp}.md`;
}

export function titleFromMessages(messages: ExportMessage[]): string {
  const first = messages.find((message) => message.role === 'user' && message.content.trim());
  if (!first) return tNow('export.chat');
  return first.content.replace(/\s+/g, ' ').trim().slice(0, EXPORT_TITLE_MAX);
}

export function canExportConversation(messages: ExportMessage[]): boolean {
  return messages.some((message) => exportBody(message).length > 0);
}

export function formatConversationMarkdown(input: {
  title: string;
  messages: ExportMessage[];
}): string {
  const title = input.title.trim() || tNow('export.chat');
  const parts = [`# ${title}`, ''];

  for (const message of input.messages) {
    const content = exportBody(message);
    if (!content) continue;
    const heading =
      message.role === 'user' ? tNow('export.user') : message.role === 'assistant' ? 'Uryx' : message.role;
    parts.push(`##### ${heading}:`, '', content, '');
  }

  return `${parts.join('\n').replace(/\n{3,}/g, '\n\n').trim()}\n`;
}

export function downloadTextFile(content: string, filename: string): boolean {
  if (typeof document === 'undefined' || !content.trim()) return false;
  const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
  return true;
}

export async function exportConversationMarkdown(input: {
  title: string;
  messages: ExportMessage[];
  now?: Date;
}): Promise<boolean> {
  if (!canExportConversation(input.messages)) return false;
  const markdown = formatConversationMarkdown(input);
  const filename = exportFilename(input.title, input.now);
  const save = typeof window !== 'undefined' ? window.uryx?.dialog.saveFile : undefined;
  if (typeof save === 'function') {
    const result = await save({ defaultName: filename, content: markdown });
    return !result.canceled && result.filePaths.length > 0;
  }
  return downloadTextFile(markdown, filename);
}
