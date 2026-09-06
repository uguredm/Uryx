/**
 * NextChat `chat.tsx` kısayollar:
 * Ctrl/Cmd+Shift+O yeni sohbet; Shift+Esc kutuya odak.
 * Düz Escape başka görünümden chat'e döner (footer "ESC // RETURN").
 * NextChat Ctrl+Shift+C / kod kopyası / modal — çalınmadı (Cherry kopya var).
 */

export type ChatShortcut = 'newChat' | 'focusComposer' | 'returnChat';

export function isEditableTarget(target: EventTarget | null): boolean {
  if (!target || !(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  return tag === 'INPUT' || tag === 'TEXTAREA' || target.isContentEditable;
}

export function matchChatShortcut(event: {
  key: string;
  shiftKey: boolean;
  ctrlKey: boolean;
  metaKey: boolean;
  altKey?: boolean;
  defaultPrevented?: boolean;
}): ChatShortcut | null {
  if (event.defaultPrevented) return null;
  const key = event.key.length === 1 ? event.key.toLowerCase() : event.key;
  const mod = event.ctrlKey || event.metaKey;

  if (mod && event.shiftKey && key === 'o') return 'newChat';
  if (event.shiftKey && key === 'Escape') return 'focusComposer';
  if (!mod && !event.shiftKey && !event.altKey && key === 'Escape') return 'returnChat';
  return null;
}
