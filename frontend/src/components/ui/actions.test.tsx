import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { Button } from './Button';
import { Chip } from './Chip';
import { IconButton } from './IconButton';
import { Switch } from './Switch';

describe('Button', () => {
  it('only ever renders a <button>; links use <a class="ui-btn"> instead', () => {
    const { container } = render(
      <>
        <Button>Một</Button>
        <Button tone="accent" busy>
          Hai
        </Button>
        <Button disabled reason="Thiếu ảnh">
          Ba
        </Button>
      </>,
    );
    expect(container.querySelectorAll('a')).toHaveLength(0);
    const nodes = Array.from(container.querySelectorAll('.ui-btn'));
    expect(nodes).toHaveLength(3);
    for (const n of nodes) expect(n.tagName).toBe('BUTTON');
  });

  it('renders each tone as a class and fires onClick', async () => {
    const onClick = vi.fn();
    render(
      <Button tone="accent" onClick={onClick}>
        Xuất bản đẹp
      </Button>,
    );
    const b = screen.getByRole('button', { name: 'Xuất bản đẹp' });
    expect(b).toHaveClass('ui-btn', 'ui-btn-accent');
    await userEvent.click(b);
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it('is disabled with the reason as title and readable text, and does not click', async () => {
    const onClick = vi.fn();
    render(
      <Button disabled reason="Thiếu ảnh cảnh 3" onClick={onClick}>
        Xem nhanh
      </Button>,
    );
    const b = screen.getByRole('button', { name: /Xem nhanh/ });
    expect(b).toBeDisabled();
    expect(b).toHaveAttribute('title', 'Thiếu ảnh cảnh 3');
    expect(b).toHaveTextContent('Thiếu ảnh cảnh 3');
    await userEvent.click(b);
    expect(onClick).not.toHaveBeenCalled();
  });

  it('shows a spinner and blocks clicks while busy', async () => {
    const onClick = vi.fn();
    const { container } = render(
      <Button busy onClick={onClick}>
        Đang dựng
      </Button>,
    );
    const b = screen.getByRole('button');
    expect(b).toBeDisabled();
    expect(b).toHaveAttribute('aria-busy', 'true');
    expect(container.querySelector('.ui-spinner')).not.toBeNull();
    await userEvent.click(b);
    expect(onClick).not.toHaveBeenCalled();
  });

  it('activates from the keyboard and is a reachable Tab stop', async () => {
    const onClick = vi.fn();
    render(<Button onClick={onClick}>Tạo video</Button>);
    await userEvent.tab();
    expect(screen.getByRole('button')).toHaveFocus();
    await userEvent.keyboard('{Enter}');
    await userEvent.keyboard(' ');
    expect(onClick).toHaveBeenCalledTimes(2);
  });

  it('defaults to type=button so it never submits a form by accident', () => {
    render(<Button>Lưu</Button>);
    expect(screen.getByRole('button')).toHaveAttribute('type', 'button');
  });
});

describe('IconButton', () => {
  it('uses the Vietnamese label as accessible name and tooltip', () => {
    render(
      <IconButton label="Đóng">
        <svg />
      </IconButton>,
    );
    const b = screen.getByRole('button', { name: 'Đóng' });
    expect(b).toHaveAttribute('title', 'Đóng');
  });

  it('is skipped by clicks when disabled', async () => {
    const onClick = vi.fn();
    render(
      <IconButton label="Phát" disabled onClick={onClick}>
        <svg />
      </IconButton>,
    );
    await userEvent.click(screen.getByRole('button'));
    expect(onClick).not.toHaveBeenCalled();
  });
});

describe('Chip', () => {
  it('reports the selected state with aria-pressed and toggles by click and keyboard', async () => {
    const onClick = vi.fn();
    const { rerender } = render(
      <Chip selected={false} onClick={onClick}>
        Trên
      </Chip>,
    );
    const chip = screen.getByRole('button', { name: 'Trên' });
    expect(chip).toHaveAttribute('aria-pressed', 'false');
    await userEvent.click(chip);
    chip.focus();
    await userEvent.keyboard('{Enter}');
    expect(onClick).toHaveBeenCalledTimes(2);
    rerender(
      <Chip selected onClick={onClick}>
        Trên
      </Chip>,
    );
    expect(screen.getByRole('button', { name: 'Trên' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('does nothing when disabled', async () => {
    const onClick = vi.fn();
    render(
      <Chip disabled onClick={onClick}>
        XL
      </Chip>,
    );
    await userEvent.click(screen.getByRole('button'));
    expect(onClick).not.toHaveBeenCalled();
  });
});

describe('Switch', () => {
  it('is a switch that flips on click and Space', async () => {
    const onChange = vi.fn();
    render(<Switch checked={false} onChange={onChange} label="Cú lật" />);
    const sw = screen.getByRole('switch', { name: 'Cú lật' });
    expect(sw).toHaveAttribute('aria-checked', 'false');
    await userEvent.click(sw);
    expect(onChange).toHaveBeenLastCalledWith(true);
    sw.focus();
    await userEvent.keyboard(' ');
    expect(onChange).toHaveBeenCalledTimes(2);
  });

  it('shows checked state and ignores clicks when disabled', async () => {
    const onChange = vi.fn();
    render(<Switch checked disabled onChange={onChange} label="Outro" />);
    const sw = screen.getByRole('switch', { name: 'Outro' });
    expect(sw).toHaveAttribute('aria-checked', 'true');
    await userEvent.click(sw);
    expect(onChange).not.toHaveBeenCalled();
  });
});
