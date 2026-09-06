import { useEffect, useState } from 'react';

import { api } from '@/lib/api';
import { readEmbeddingFallback } from '@/lib/hudEmbedding';
import { useI18n } from '@/lib/i18n';

/** SYSTEM STATUS: MiniLM yoksa hash-embedding. ConnectionBanner değil. */
export function HudHashEmbed(): JSX.Element | null {
  const { t } = useI18n();
  const [hash, setHash] = useState(false);

  useEffect(() => {
    let alive = true;
    const tick = async (): Promise<void> => {
      try {
        const config = await api.system.config();
        if (alive) setHash(readEmbeddingFallback(config));
      } catch {
        if (alive) setHash(false);
      }
    };
    void tick();
    const id = window.setInterval(() => void tick(), 30_000);
    return () => {
      alive = false;
      window.clearInterval(id);
    };
  }, []);

  if (!hash) return null;

  return (
    <div className="hud-system-detail">
      <span>{t('hud.embed.hash')}</span>
      <strong>{t('hud.embed.hashValue')}</strong>
    </div>
  );
}
