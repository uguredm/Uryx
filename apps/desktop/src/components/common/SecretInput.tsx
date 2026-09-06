/** Parola alanına göz ile göster/gizle. */

import { useState } from 'react';
import { Eye, EyeOff } from 'lucide-react';

import { cn } from '@/lib/cn';
import { useI18n } from '@/lib/i18n';

export function SecretInput({
  value,
  onChange,
  placeholder,
  className,
  autoComplete = 'off',
  onReveal,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  className?: string;
  autoComplete?: string;
  onReveal?: () => Promise<string>;
}): JSX.Element {
  const { t } = useI18n();
  const [visible, setVisible] = useState(false);
  const [revealing, setRevealing] = useState(false);

  const toggle = async (): Promise<void> => {
    if (!visible && !value && onReveal) {
      setRevealing(true);
      try {
        const revealed = await onReveal();
        onChange(revealed);
      } finally {
        setRevealing(false);
      }
    }
    setVisible((current) => !current);
  };

  return (
    <div className="relative">
      <input
        type={visible ? 'text' : 'password'}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className={cn('input pr-10', className)}
        placeholder={placeholder}
        autoComplete={autoComplete}
        spellCheck={false}
      />
      <button
        type="button"
        className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-slate-500 hover:text-slate-200"
        onClick={() => void toggle()}
        disabled={revealing}
        aria-label={visible ? t('action.hide') : t('action.show')}
        aria-pressed={visible}
      >
        {visible ? <EyeOff size={14} /> : <Eye size={14} />}
      </button>
    </div>
  );
}
