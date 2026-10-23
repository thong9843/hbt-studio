import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ProgressBar } from './ProgressBar';

describe('ProgressBar', () => {
  it('exposes value, step name and percent as text', () => {
    render(<ProgressBar label="Tiến độ" value={42.4} step="Ghép cảnh" message="cảnh 3/8" />);
    const bar = screen.getByRole('progressbar', { name: 'Tiến độ' });
    expect(bar).toHaveAttribute('aria-valuenow', '42');
    expect(screen.getByText('42%')).toBeInTheDocument();
    expect(screen.getByText(/Ghép cảnh/)).toBeInTheDocument();
    expect(screen.getByText(/cảnh 3\/8/)).toBeInTheDocument();
  });

  it('clamps out-of-range values', () => {
    const { rerender } = render(<ProgressBar label="t" value={140} step="" />);
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '100');
    rerender(<ProgressBar label="t" value={-3} step="" />);
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '0');
  });
});
