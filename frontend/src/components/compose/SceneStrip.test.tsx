import { act, render, renderHook, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { ToastContext } from '../../hooks/toast';
import { useImageDrop } from '../../hooks/useImageDrop';
import { scene } from '../../test/project';
import { SceneStrip } from './SceneStrip';

const file = (name: string) => new File(['x'], name, { type: 'image/png' });

const base = {
  slug: 'muoi',
  selected: 0,
  imageVersion: 3,
  onSelect: vi.fn(),
  onReorder: vi.fn(),
  onAdd: vi.fn(),
  onDropFiles: vi.fn(),
};

describe('SceneStrip', () => {
  it('shows 1-based numbers, the cache-busted image and marks the selected scene', async () => {
    const onSelect = vi.fn();
    render(
      <SceneStrip
        {...base}
        onSelect={onSelect}
        scenes={[scene({ image: 'images/scene-01.png' }), scene()]}
      />,
    );
    expect(document.querySelector('img')).toHaveAttribute(
      'src',
      '/api/files/projects/muoi/images/scene-01.png?v=3',
    );
    const first = screen.getByRole('button', { name: 'Cảnh 1' });
    expect(first).toHaveAttribute('aria-current', 'true');
    const second = screen.getByRole('button', { name: /^Cảnh 2/ });
    expect(second).toHaveAccessibleName(/chưa có ảnh/);
    await userEvent.click(second);
    expect(onSelect).toHaveBeenCalledWith(1);
  });

  it('names the drag handles in Vietnamese', () => {
    render(<SceneStrip {...base} scenes={[scene(), scene()]} />);
    expect(screen.getByRole('button', { name: 'Kéo để đổi thứ tự cảnh 2' })).toBeInTheDocument();
  });

  it('disables add at 12 scenes', () => {
    const { rerender } = render(
      <SceneStrip {...base} scenes={Array.from({ length: 12 }, () => scene())} />,
    );
    expect(screen.getByRole('button', { name: 'Thêm cảnh' })).toBeDisabled();
    rerender(<SceneStrip {...base} scenes={Array.from({ length: 11 }, () => scene())} />);
    expect(screen.getByRole('button', { name: 'Thêm cảnh' })).toBeEnabled();
  });

  it('hands every dropped image to the caller in one call', async () => {
    const onDropFiles = vi.fn();
    render(<SceneStrip {...base} onDropFiles={onDropFiles} scenes={[scene(), scene()]} />);
    const input = screen.getByLabelText('Thêm ảnh', { selector: 'input' });
    await userEvent.upload(input, [file('b.png'), file('a.png')]);
    expect(onDropFiles).toHaveBeenCalledTimes(1);
    expect(onDropFiles.mock.calls[0][0]).toHaveLength(2);
  });

  it('reports upload progress', () => {
    render(<SceneStrip {...base} progress={{ done: 3, total: 8 }} scenes={[scene()]} />);
    expect(screen.getByText('Đang tải ảnh 3/8')).toBeInTheDocument();
  });
});

describe('useImageDrop', () => {
  function harness(scenes: { image: string }[]) {
    const upload = vi.fn<(index: number, file: File) => Promise<void>>(async () => {});
    const addScenes = vi.fn<(count: number) => Promise<void>>(async () => {});
    const toast = { info: vi.fn(), error: vi.fn() };
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <ToastContext.Provider value={toast}>{children}</ToastContext.Provider>
    );
    const hook = renderHook(() => useImageDrop({ scenes, addScenes, upload }), { wrapper });
    return { hook, upload, addScenes, toast };
  }
  const empty = (n: number) => Array.from({ length: n }, () => ({ image: '' }));

  it('uploads sorted files one by one from scene 1 with no dialog on empty scenes', async () => {
    const { hook, upload, toast } = harness(empty(8));
    await act(async () => hook.result.current.onFiles([file('s10.png'), file('s2.png')]));
    expect(upload.mock.calls.map((c) => [c[0], c[1].name])).toEqual([
      [0, 's2.png'],
      [1, 's10.png'],
    ]);
    expect(toast.info).toHaveBeenCalledWith('Đã gán 2 ảnh');
  });

  it('asks once before overwriting scenes that already have an image', async () => {
    const scenes = [{ image: 'a.png' }, ...empty(7)];
    const { hook, upload } = harness(scenes);
    act(() => hook.result.current.onFiles([file('1.png'), file('2.png')]));
    expect(upload).not.toHaveBeenCalled();
    expect(hook.result.current.dialogs).not.toBeNull();
  });

  it('chains the overwrite box into the add-scenes box, then adds scenes before uploading', async () => {
    const scenes = [{ image: 'a.png' }, ...empty(7)];
    const { hook, upload, addScenes } = harness(scenes);
    const files = Array.from({ length: 10 }, (_, i) => file(`${i + 1}.png`));
    act(() => hook.result.current.onFiles(files));
    const view = render(<>{hook.result.current.dialogs}</>);
    expect(screen.getByText('Ghi đè ảnh đã có?')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Ghi đè' }));
    view.unmount();
    const second = render(<>{hook.result.current.dialogs}</>);
    expect(screen.getByText('Thêm cảnh cho ảnh còn dư?')).toBeInTheDocument();
    await act(async () => {
      await userEvent.click(screen.getByRole('button', { name: 'Thêm cảnh' }));
    });
    second.unmount();
    expect(addScenes).toHaveBeenCalledWith(2);
    expect(upload).toHaveBeenCalledTimes(10);
    expect(addScenes.mock.invocationCallOrder[0]).toBeLessThan(upload.mock.invocationCallOrder[0]);
  });

  it('skips surplus images when the user declines new scenes, and reports files over 12', async () => {
    const { hook, upload, addScenes, toast } = harness(empty(11));
    const files = Array.from({ length: 14 }, (_, i) => file(`${i + 1}.png`));
    act(() => hook.result.current.onFiles(files));
    render(<>{hook.result.current.dialogs}</>);
    await act(async () => {
      await userEvent.click(screen.getByRole('button', { name: 'Bỏ ảnh dư' }));
    });
    expect(addScenes).not.toHaveBeenCalled();
    expect(upload).toHaveBeenCalledTimes(11);
    expect(toast.info).toHaveBeenCalledWith(expect.stringContaining('Đã gán 11 ảnh'));
  });

  it('stops and shows the error when an upload fails', async () => {
    const { hook, upload, toast } = harness(empty(3));
    upload.mockRejectedValueOnce(new Error('hỏng'));
    await act(async () => hook.result.current.onFiles([file('1.png'), file('2.png')]));
    expect(toast.error).toHaveBeenCalled();
    expect(upload).toHaveBeenCalledTimes(1);
    expect(toast.info).not.toHaveBeenCalled();
  });
});
