/** Barge-in: yalnız söylenen asistan metni kalsın. */

export function spokenAssistantContent(full: string, spoken: string): string {
  const heard = spoken.trim();
  if (!heard) return '';
  const text = full.trim();
  if (text.startsWith(heard)) return heard;
  return heard;
}

export function spokenFromPlayback(completed: string[], current: string, fraction: number): string {
  const clamped = Math.min(1, Math.max(0, fraction));
  const cut = current.slice(0, Math.floor(current.length * clamped));
  return [...completed, cut].filter((part) => part.length > 0).join(' ').trim();
}

export interface TrimLiveAssistantInput {
  streamContent: string;
  messages: Array<{ id: string; role: string; content: string; stopped?: boolean }>;
  spoken: string;
}

export function trimLiveAssistant<T extends TrimLiveAssistantInput['messages'][number]>(
  input: { streamContent: string; messages: T[]; spoken: string },
): { streamContent: string; messages: T[] } {
  const streamContent = input.streamContent.trim()
    ? spokenAssistantContent(input.streamContent, input.spoken)
    : input.streamContent;
  const last = input.messages.at(-1);
  if (!last || last.role !== 'assistant') {
    return { streamContent, messages: input.messages };
  }
  return {
    streamContent,
    messages: [
      ...input.messages.slice(0, -1),
      {
        ...last,
        content: spokenAssistantContent(last.content, input.spoken),
        stopped: true,
      },
    ],
  };
}
