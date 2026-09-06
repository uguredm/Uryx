const CODE_BLOCK = /```[\s\S]*?```/g;
const IMAGE = /!\[[^\]]*\]\([^)]*\)/g;
const SOURCE_LINE = /^\s*[*_-]?\s*(?:kaynak|source)\s*:.*$/gim;
const LINK = /\[([^\]]+)\]\([^)]*\)/g;
const URL = /https?:\/\/\S+/g;
const MARKUP = /[*_~>#`]+/g;

export function cleanSpeechText(text: string): string {
  return text
    .replace(CODE_BLOCK, ' ')
    .replace(IMAGE, ' ')
    .replace(SOURCE_LINE, ' ')
    .replace(LINK, '$1')
    .replace(URL, ' ')
    .replace(MARKUP, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}
