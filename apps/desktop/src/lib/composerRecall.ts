/**
 * Odysseus `wireArrowUpRecall` + Goose `ChatInput` ArrowUp:
 * boş kutuda yukarı = son kullanıcı; taslak varken caret çalınmaz.
 */

export function userPromptsNewestFirst(
  messages: Array<{ role: string; content: string }>,
): string[] {
  const prompts: string[] = [];
  for (let i = messages.length - 1; i >= 0; i--) {
    const message = messages[i];
    if (message.role !== 'user') continue;
    const text = message.content.replace(/\s+/g, ' ').trim();
    if (text) prompts.push(text);
  }
  return prompts;
}

export function applyComposerRecall(
  current: string,
  history: string[],
  key: 'ArrowUp' | 'ArrowDown',
  lastRecalled: string,
): { text: string; recalled: string } | null {
  if (!history.length) return null;
  const norm = (value: string): string => value.replace(/\r\n/g, '\n').trimEnd();
  const cur = norm(current);
  const recalled = norm(lastRecalled);

  if (cur && cur !== recalled) return null;

  if (!cur) {
    if (key === 'ArrowDown') return { text: '', recalled: '' };
    return { text: history[0] ?? '', recalled: history[0] ?? '' };
  }

  const index = history.findIndex((item) => norm(item) === recalled);
  if (key === 'ArrowDown') {
    if (index <= 0) return { text: '', recalled: '' };
    const newer = history[index - 1] ?? '';
    return { text: newer, recalled: newer };
  }

  const olderIndex = index < 0 ? 0 : Math.min(index + 1, history.length - 1);
  const older = history[olderIndex];
  if (!older) return null;
  return { text: older, recalled: older };
}
