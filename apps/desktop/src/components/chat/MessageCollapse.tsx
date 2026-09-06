import { useEffect, useRef, useState, type ReactNode } from 'react';

import { cn } from '@/lib/cn';
import { useI18n } from '@/lib/i18n';
import { shouldCollapseMessage } from '@/lib/messageCollapse';

export function MessageCollapse({
  children,
  contentKey,
  maxHeight,
  disabled = false,
  className,
  buttonClassName,
}: {
  children: ReactNode;
  contentKey: string;
  maxHeight: number;
  disabled?: boolean;
  className?: string;
  buttonClassName?: string;
}): JSX.Element {
  const { t } = useI18n();
  const ref = useRef<HTMLDivElement>(null);
  const [overflow, setOverflow] = useState(false);
  const [collapsed, setCollapsed] = useState(true);

  useEffect(() => {
    setCollapsed(true);
  }, [contentKey]);

  useEffect(() => {
    if (disabled) {
      setOverflow(false);
      return;
    }
    const frame = window.requestAnimationFrame(() => {
      const element = ref.current;
      setOverflow(Boolean(element && shouldCollapseMessage(element.scrollHeight, maxHeight)));
    });
    return () => window.cancelAnimationFrame(frame);
  }, [contentKey, maxHeight, disabled]);

  const clip = !disabled && overflow && collapsed;

  return (
    <div>
      <div
        ref={ref}
        className={cn(className, clip && 'is-collapsed')}
        style={clip ? { maxHeight, overflow: 'hidden' } : undefined}
      >
        {children}
      </div>
      {overflow && !disabled ? (
        <button
          type="button"
          className={buttonClassName}
          onClick={() => setCollapsed((current) => !current)}
        >
          {collapsed ? t('hud.showMore') : t('hud.showLess')}
        </button>
      ) : null}
    </div>
  );
}
