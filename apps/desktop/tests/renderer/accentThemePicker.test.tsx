import '@testing-library/jest-dom/vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { AccentThemePicker } from '@/components/common/AccentThemePicker';

describe('AccentThemePicker', () => {
  it('ayarlarda yeşil seçili başlar ve maviye tıklayınca yazar', () => {
    const onChange = vi.fn();
    render(<AccentThemePicker value="green" onChange={onChange} />);

    expect(screen.getByRole('radio', { name: 'Green' })).toHaveAttribute('aria-checked', 'true');
    fireEvent.click(screen.getByRole('radio', { name: 'Blue' }));
    expect(onChange).toHaveBeenCalledWith('blue');
  });

  it('HUD varyantı ok tuşuyla döner', () => {
    const onChange = vi.fn();
    render(<AccentThemePicker variant="hud" value="green" onChange={onChange} />);

    fireEvent.keyDown(screen.getByRole('radiogroup', { name: 'Accent color' }), {
      key: 'ArrowRight',
    });
    expect(onChange).toHaveBeenCalledWith('blue');
  });

  it('HUD çubuğunda YEŞİL/MAVİ yazısı durmaz', () => {
    render(<AccentThemePicker variant="hud" value="green" onChange={vi.fn()} />);
    expect(screen.queryByText('YEŞİL')).not.toBeInTheDocument();
    expect(screen.queryByText('MAVİ')).not.toBeInTheDocument();
    expect(screen.queryByText('GREEN')).not.toBeInTheDocument();
    expect(screen.queryByText('BLUE')).not.toBeInTheDocument();
    expect(screen.getByRole('radio', { name: 'Green' })).toBeInTheDocument();
  });
});
