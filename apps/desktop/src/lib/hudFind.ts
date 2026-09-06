/**
 * CodeMirror searchKeymap: Mod-f panel, F3/Mod-g sonraki, Shift-F3 önceki, sarmala.
 * HUD satır araması mesaj id listesinde yürür.
 * gotoLine / selectNextOccurrence / replace çalınmadı.
 */

import { hudToolLabel, mcpResultText } from '@/lib/confirmResponse';
import { messageMatchesQuery } from '@/lib/historySearch';

export type FindShortcut = 'openFind' | 'findNext' | 'findPrev' | 'clearFind';

export function matchingMessageIds(
  messages: Array<{
    id: string;
    content: string;
    toolCalls?: Array<{
      tool_name: string;
      display_name?: string;
      arguments?: Record<string, unknown>;
      result?: Record<string, unknown>;
    }>;
  }>,
  query: string,
): string[] {
  const needle = query.trim();
  if (!needle) return [];
  return messages
    .filter((message) => {
      if (messageMatchesQuery(message.content, needle)) return true;
      return (message.toolCalls ?? []).some((call) => {
        const label = hudToolLabel(
          call.tool_name,
          call.display_name ?? call.tool_name,
          call.arguments,
          call.result,
        );
        if (messageMatchesQuery(label, needle)) return true;
        return messageMatchesQuery(mcpResultText(call.tool_name, call.result), needle);
      });
    })
    .map((message) => message.id);
}

/** CodeMirror findNext — sonda başa dolar. Odysseus clamp değil. */
export function wrapFindIndex(current: number, delta: number, length: number): number {
  if (length <= 0) return -1;
  if (current < 0) return delta > 0 ? 0 : length - 1;
  return (current + delta + length * 8) % length;
}

export function formatFindCount(index: number, length: number): string {
  if (length <= 0) return '0/0';
  return `${Math.max(0, index) + 1}/${length}`;
}

export function matchFindShortcut(
  event: {
    key: string;
    shiftKey: boolean;
    ctrlKey: boolean;
    metaKey: boolean;
    altKey?: boolean;
    defaultPrevented?: boolean;
  },
  findFocused: boolean,
): FindShortcut | null {
  if (event.defaultPrevented) return null;
  const key = event.key.length === 1 ? event.key.toLowerCase() : event.key;
  const mod = event.ctrlKey || event.metaKey;

  if (mod && !event.shiftKey && !event.altKey && key === 'f') return 'openFind';
  if (key === 'F3' || (mod && !event.altKey && key === 'g')) {
    return event.shiftKey ? 'findPrev' : 'findNext';
  }
  if (findFocused && key === 'Enter') {
    return event.shiftKey ? 'findPrev' : 'findNext';
  }
  if (findFocused && key === 'Escape' && !mod && !event.shiftKey && !event.altKey) {
    return 'clearFind';
  }
  return null;
}
