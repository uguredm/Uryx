import '@testing-library/jest-dom/vitest';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { SecretInput } from '@/components/common/SecretInput';

describe('SecretInput', () => {
  it('varsayılan olarak gizler, göz ile gösterir', () => {
    const onChange = vi.fn();
    render(<SecretInput value="gizli-token" onChange={onChange} />);

    const field = screen.getByDisplayValue('gizli-token');
    expect(field).toHaveAttribute('type', 'password');

    fireEvent.click(screen.getByRole('button', { name: 'Show' }));
    expect(field).toHaveAttribute('type', 'text');

    fireEvent.click(screen.getByRole('button', { name: 'Hide' }));
    expect(field).toHaveAttribute('type', 'password');
  });

  it('boşken göster deyince kayıtlı anahtarı bir kez çeker', async () => {
    const onChange = vi.fn();
    const onReveal = vi.fn().mockResolvedValue('ui-test-key-9f3a');
    render(<SecretInput value="" onChange={onChange} onReveal={onReveal} />);

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Show' }));
    });
    expect(onReveal).toHaveBeenCalledOnce();
    expect(onChange).toHaveBeenCalledWith('ui-test-key-9f3a');
  });
});
