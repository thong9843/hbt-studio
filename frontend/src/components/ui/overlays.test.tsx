import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { ToastProvider, TOAST_MS, TOAST_UNDO_MS } from '../Toast';
import { useToast } from '../../hooks/toast';
import { Button } from './Button';
import { Dialog } from './Dialog';
import { Drawer } from './Drawer';
import { Menu } from './Menu';
import { CLOSE_MS } from './overlay';

function DialogHost({ onClose }: { onClose?: () => void }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button onClick={() => setOpen(true)}>Mở</Button>
      <Dialog
        open={open}
        onClose={() => {
          setOpen(false);
          onClose?.();
        }}
        title="Video mới"
        footer={<Button onClick={() => setOpen(false)}>Tạo</Button>}
      >
        <input aria-label="Tên" />
      </Dialog>
    </>
  );
}

describe('Dialog', () => {
  it('is not in the DOM while closed, then labelled by its title when open', async () => {
    render(<DialogHost />);
    expect(screen.queryByRole('dialog')).toBeNull();
    await userEvent.click(screen.getByRole('button', { name: 'Mở' }));
    const d = screen.getByRole('dialog', { name: 'Video mới' });
    expect(d).toHaveAttribute('aria-modal', 'true');
  });

  it('moves focus to the first field, closes on Esc and returns focus to the opener', async () => {
    const onClose = vi.fn();
    render(<DialogHost onClose={onClose} />);
    const opener = screen.getByRole('button', { name: 'Mở' });
    await userEvent.click(opener);
    // Ô đầu tiên bấm được là nút Đóng ở đầu hộp.
    expect(screen.getByRole('button', { name: 'Đóng' })).toHaveFocus();
    await userEvent.keyboard('{Escape}');
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(opener).toHaveFocus();
  });

  it('keeps Tab inside the dialog in both directions', async () => {
    render(<DialogHost />);
    await userEvent.click(screen.getByRole('button', { name: 'Mở' }));
    const close = screen.getByRole('button', { name: 'Đóng' });
    const create = screen.getByRole('button', { name: 'Tạo' });
    expect(close).toHaveFocus();
    await userEvent.tab({ shift: true });
    expect(create).toHaveFocus();
    await userEvent.tab();
    expect(close).toHaveFocus();
  });

  it('prefers the data-autofocus element', async () => {
    render(
      <Dialog open onClose={() => {}} title="Xoá dự án?">
        <button type="button">Một</button>
        <button type="button" data-autofocus>
          Huỷ
        </button>
      </Dialog>,
    );
    expect(screen.getByRole('button', { name: 'Huỷ' })).toHaveFocus();
  });

  it('stays mounted for the 120 ms exit, then unmounts', () => {
    vi.useFakeTimers();
    const { rerender } = render(
      <Dialog open onClose={() => {}} title="T">
        x
      </Dialog>,
    );
    rerender(
      <Dialog open={false} onClose={() => {}} title="T">
        x
      </Dialog>,
    );
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(document.querySelector('.ui-scrim')).toHaveAttribute('data-closing', 'true');
    act(() => {
      vi.advanceTimersByTime(CLOSE_MS + 5);
    });
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('closes on a click on the scrim but not on a click inside', async () => {
    const onClose = vi.fn();
    render(
      <Dialog open onClose={onClose} title="T">
        <p>nội dung</p>
      </Dialog>,
    );
    await userEvent.click(screen.getByText('nội dung'));
    expect(onClose).not.toHaveBeenCalled();
    await userEvent.click(document.querySelector('.ui-scrim') as HTMLElement);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('supports role=alertdialog for confirmations', () => {
    render(
      <Dialog open onClose={() => {}} title="Xoá?" role="alertdialog">
        x
      </Dialog>,
    );
    expect(screen.getByRole('alertdialog', { name: 'Xoá?' })).toBeInTheDocument();
  });
});

describe('Drawer', () => {
  it('opens as a labelled dialog and closes on Esc', async () => {
    const onClose = vi.fn();
    render(
      <Drawer open onClose={onClose} title="Xem trước">
        <button type="button">Phát</button>
      </Drawer>,
    );
    expect(screen.getByRole('dialog', { name: 'Xem trước' })).toBeInTheDocument();
    await userEvent.keyboard('{Escape}');
    expect(onClose).toHaveBeenCalled();
  });
});

describe('Menu', () => {
  const setup = () => {
    const a = vi.fn();
    const b = vi.fn();
    render(
      <Menu
        label="Thêm việc"
        icon={<svg />}
        items={[
          { key: 'dup', label: 'Nhân bản', onSelect: a },
          { key: 'del', label: 'Xoá…', danger: true, onSelect: b },
          { key: 'off', label: 'Khoá', disabled: true, reason: 'Đang dựng', onSelect: vi.fn() },
        ]}
      />,
    );
    return { a, b };
  };

  it('opens with the first enabled item focused and walks with arrow keys', async () => {
    setup();
    const btn = screen.getByRole('button', { name: 'Thêm việc' });
    expect(btn).toHaveAttribute('aria-expanded', 'false');
    await userEvent.click(btn);
    expect(btn).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByRole('menuitem', { name: 'Nhân bản' })).toHaveFocus();
    await userEvent.keyboard('{ArrowDown}');
    expect(screen.getByRole('menuitem', { name: 'Xoá…' })).toHaveFocus();
    await userEvent.keyboard('{ArrowDown}'); // bỏ qua dòng bị khoá, quay về đầu
    expect(screen.getByRole('menuitem', { name: 'Nhân bản' })).toHaveFocus();
    await userEvent.keyboard('{ArrowUp}');
    expect(screen.getByRole('menuitem', { name: 'Xoá…' })).toHaveFocus();
  });

  it('keeps Tab and Shift+Tab inside the open menu', async () => {
    setup();
    await userEvent.click(screen.getByRole('button', { name: 'Thêm việc' }));
    expect(screen.getByRole('menuitem', { name: 'Nhân bản' })).toHaveFocus();
    await userEvent.tab();
    expect(screen.getByRole('menuitem', { name: 'Xoá…' })).toHaveFocus();
    await userEvent.tab();
    expect(screen.getByRole('menuitem', { name: 'Nhân bản' })).toHaveFocus();
    await userEvent.tab({ shift: true });
    expect(screen.getByRole('menuitem', { name: 'Xoá…' })).toHaveFocus();
    await userEvent.keyboard('{Home}');
    expect(screen.getByRole('menuitem', { name: 'Nhân bản' })).toHaveFocus();
    await userEvent.keyboard('{End}');
    expect(screen.getByRole('menuitem', { name: 'Xoá…' })).toHaveFocus();
    expect(screen.getByRole('menu')).toBeInTheDocument();
  });

  it('does not hijack Tab while the menu is closed', async () => {
    render(
      <>
        <Menu
          label="Thêm việc"
          icon={<svg />}
          items={[{ key: 'a', label: 'A', onSelect: vi.fn() }]}
        />
        <button type="button">Sau</button>
      </>,
    );
    screen.getByRole('button', { name: 'Thêm việc' }).focus();
    await userEvent.tab();
    expect(screen.getByRole('button', { name: 'Sau' })).toHaveFocus();
  });

  it('runs the chosen item, closes, and returns focus to the button', async () => {
    const { a } = setup();
    const btn = screen.getByRole('button', { name: 'Thêm việc' });
    await userEvent.click(btn);
    await userEvent.click(screen.getByRole('menuitem', { name: 'Nhân bản' }));
    expect(a).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('menu')).toBeNull();
    expect(btn).toHaveFocus();
  });

  it('closes on Esc and on an outside click', async () => {
    setup();
    const btn = screen.getByRole('button', { name: 'Thêm việc' });
    await userEvent.click(btn);
    await userEvent.keyboard('{Escape}');
    expect(screen.queryByRole('menu')).toBeNull();
    expect(btn).toHaveFocus();
    await userEvent.click(btn);
    await userEvent.click(document.body);
    expect(screen.queryByRole('menu')).toBeNull();
  });

  it('shows the reason of a disabled item and does not run it', async () => {
    setup();
    await userEvent.click(screen.getByRole('button', { name: 'Thêm việc' }));
    const off = screen.getByRole('menuitem', { name: 'Khoá' });
    expect(off).toBeDisabled();
    expect(off).toHaveAttribute('title', 'Đang dựng');
  });
});

function ToastHost({ undo }: { undo?: () => void }) {
  const toast = useToast();
  return (
    <>
      <Button onClick={() => toast.info('Đã lưu')}>Lưu</Button>
      <Button onClick={() => toast.info('Đã xoá cảnh 3', { undo })}>Xoá</Button>
    </>
  );
}

describe('Toast', () => {
  // userEvent dùng timer thật, nên bấm bằng click đồng bộ rồi chạy đồng hồ giả.
  const press = (name: string) => {
    act(() => {
      screen.getByRole('button', { name }).click();
    });
  };

  it('disappears after 3 s', () => {
    vi.useFakeTimers();
    render(
      <ToastProvider>
        <ToastHost />
      </ToastProvider>,
    );
    press('Lưu');
    expect(screen.getByRole('status')).toHaveTextContent('Đã lưu');
    act(() => {
      vi.advanceTimersByTime(TOAST_MS - 50);
    });
    expect(screen.getByRole('status')).toBeInTheDocument();
    act(() => {
      vi.advanceTimersByTime(100);
    });
    expect(screen.queryByRole('status')).toBeNull();
  });

  it('stays 8 s with an Undo button, and Undo runs once and dismisses', () => {
    vi.useFakeTimers();
    const undo = vi.fn();
    render(
      <ToastProvider>
        <ToastHost undo={undo} />
      </ToastProvider>,
    );
    press('Xoá');
    act(() => {
      vi.advanceTimersByTime(TOAST_MS + 500);
    });
    expect(screen.getByRole('status')).toHaveTextContent('Đã xoá cảnh 3');
    act(() => {
      screen.getByRole('button', { name: 'Hoàn tác' }).click();
    });
    expect(undo).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('status')).toBeNull();
    expect(TOAST_UNDO_MS).toBe(8000);
  });

  it('Undo toast expires after 8 s', () => {
    vi.useFakeTimers();
    render(
      <ToastProvider>
        <ToastHost undo={() => {}} />
      </ToastProvider>,
    );
    press('Xoá');
    act(() => {
      vi.advanceTimersByTime(TOAST_UNDO_MS + 50);
    });
    expect(screen.queryByRole('status')).toBeNull();
  });
});
