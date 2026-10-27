import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { Badge } from './Badge';
import { Card } from './Card';
import { Input, Textarea } from './Field';
import { Progress } from './Progress';
import { Skeleton } from './Skeleton';

describe('Card', () => {
  it('static card has no button role and no tab stop', () => {
    render(<Card data-testid="c">Thẻ</Card>);
    const c = screen.getByTestId('c');
    expect(c).not.toHaveAttribute('role');
    expect(c).not.toHaveAttribute('tabindex');
    expect(c).not.toHaveClass('ui-card-link');
  });

  it('interactive card is a keyboard button: Tab, Enter and Space click it', async () => {
    const onClick = vi.fn();
    render(
      <Card interactive onClick={onClick}>
        Dự án
      </Card>,
    );
    await userEvent.tab();
    const c = screen.getByRole('button', { name: 'Dự án' });
    expect(c).toHaveFocus();
    expect(c).toHaveClass('ui-card-link');
    await userEvent.keyboard('{Enter}');
    await userEvent.keyboard(' ');
    expect(onClick).toHaveBeenCalledTimes(2);
  });
});

describe('Badge', () => {
  it('always carries text and maps tone to a class', () => {
    render(<Badge tone="red">Đã xuất · 50 fps</Badge>);
    expect(screen.getByText('Đã xuất · 50 fps')).toHaveClass('ui-badge', 'ui-badge-red');
  });
});

describe('Input and Textarea', () => {
  it('links label, error and counter through aria', () => {
    render(<Input label="Tên video" value="abc" onChange={() => {}} limit={10} error="Đã có" />);
    const input = screen.getByLabelText('Tên video');
    expect(input).toHaveAttribute('aria-invalid', 'true');
    const desc = input.getAttribute('aria-describedby') ?? '';
    expect(desc.split(' ')).toHaveLength(2);
    expect(screen.getByRole('alert')).toHaveTextContent('Đã có');
    expect(screen.getByText('3/10')).toBeInTheDocument();
  });

  it('marks over-limit text (yellow) but does not mark it invalid', () => {
    render(<Textarea label="Lời đọc" value="12345678" onChange={() => {}} limit={5} />);
    const area = screen.getByLabelText('Lời đọc');
    expect(area).toHaveAttribute('data-over', 'true');
    expect(area).not.toHaveAttribute('aria-invalid');
    expect(screen.getByText('8/5')).toHaveAttribute('data-over', 'true');
  });

  it('counts Unicode characters, not UTF-16 units', () => {
    render(<Input label="Tên" value="a😀b" onChange={() => {}} limit={3} />);
    expect(screen.getByText('3/3')).toHaveAttribute('data-over', 'false');
    expect(screen.getByLabelText('Tên')).not.toHaveAttribute('data-over');
  });

  it('has no error or counter without those props, and can be disabled', () => {
    render(<Input label="Tên" defaultValue="x" disabled />);
    expect(screen.getByLabelText('Tên')).toBeDisabled();
    expect(screen.queryByRole('alert')).toBeNull();
    expect(screen.getByLabelText('Tên')).not.toHaveAttribute('aria-describedby');
  });
});

describe('Progress', () => {
  it('moves with scaleX, not width', () => {
    render(<Progress value={40} label="Tiến độ dựng" />);
    const bar = screen.getByRole('progressbar', { name: 'Tiến độ dựng' });
    expect(bar).toHaveAttribute('aria-valuenow', '40');
    const fill = bar.firstElementChild as HTMLElement;
    expect(fill.style.transform).toBe('scaleX(0.4)');
    expect(fill.style.width).toBe('');
  });

  it('clamps and tolerates NaN', () => {
    const { rerender } = render(<Progress value={250} label="t" />);
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '100');
    rerender(<Progress value={-5} label="t" />);
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '0');
    rerender(<Progress value={Number.NaN} label="t" />);
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '0');
  });
});

describe('Skeleton', () => {
  it('is a static placeholder with a Vietnamese status name', () => {
    render(<Skeleton height={20} width="60%" />);
    const s = screen.getByRole('status', { name: 'Đang tải' });
    expect(s).toHaveStyle({ height: '20px', width: '60%' });
    expect(s).toHaveClass('ui-skeleton');
  });
});
