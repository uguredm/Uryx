/**
 * Mattermost ShowMore: scrollHeight > maxHeight ise kısalt.
 * HUD terminal sıkı; bubble Mattermost 600 analogu.
 * compact/RHS/ellipsis attachment çalınmadı.
 */

/** Mattermost `MAX_POST_HEIGHT`. */
export const BUBBLE_COLLAPSE_MAX_PX = 600;
/** HUD satırı daha kısa — 600 terminali yutar. */
export const HUD_COLLAPSE_MAX_PX = 240;

export function shouldCollapseMessage(scrollHeight: number, maxHeight: number): boolean {
  return scrollHeight > maxHeight;
}
