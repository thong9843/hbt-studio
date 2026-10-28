import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { describe, expect, it } from 'vitest';
import type { Scene } from '../../api/types';
import { scene as makeScene } from '../../test/project';
import { OptionsPanel } from './OptionsPanel';
import { VoicePanel } from './VoicePanel';

const theme = { primary: '#146268', accent: '#DE5C48' };

function Voice({ initial, total }: { initial: string; total: number }) {
  const [voice, setVoice] = useState(initial);
  return <VoicePanel sceneIndex={0} voice={voice} totalChars={total} onChange={setVoice} />;
}

function Options({ initial }: { initial: Scene }) {
  const [scene, setScene] = useState(initial);
  return (
    <>
      <OptionsPanel sceneIndex={0} scene={scene} theme={theme} onChange={(fn) => setScene(fn)} />
      <output data-testid="json">{JSON.stringify(scene)}</output>
    </>
  );
}
const current = (): Scene => JSON.parse(screen.getByTestId('json').textContent ?? '{}');

describe('VoicePanel', () => {
  it('counts the scene characters the way the backend does and shows the whole-video bar', () => {
    render(<Voice initial="Muỗi | thích {100}" total={26} />);
    expect(screen.getByText('14 ký tự')).toBeInTheDocument();
    expect(screen.getByText('Cả video 26/750')).toBeInTheDocument();
    expect(screen.getByRole('progressbar', { name: 'Số ký tự lời đọc cả video' })).toHaveAttribute(
      'aria-valuenow',
      '3',
    );
    expect(screen.queryByText('Vượt 750 ký tự')).not.toBeInTheDocument();
  });

  it('flags the whole-video total past 750 (750 itself is fine)', () => {
    const { rerender } = render(<Voice initial="a" total={750} />);
    expect(screen.queryByText('Vượt 750 ký tự')).not.toBeInTheDocument();
    rerender(<Voice initial="a" total={751} />);
    expect(screen.getByText('Vượt 750 ký tự')).toBeInTheDocument();
  });

  it('inserts | at the caret and {} after the selection', async () => {
    const user = userEvent.setup();
    render(<Voice initial="Muỗi thích bạn" total={14} />);
    const area = screen.getByLabelText('Lời đọc cảnh') as HTMLTextAreaElement;
    area.focus();
    area.setSelectionRange(4, 4);
    await user.click(screen.getByRole('button', { name: /Ngắt cụm/ }));
    expect(area.value).toBe('Muỗi| thích bạn');
    await new Promise((r) => requestAnimationFrame(r)); // chờ con trỏ được đặt lại
    area.setSelectionRange(0, 4);
    await user.click(screen.getByRole('button', { name: /Cách đọc số/ }));
    expect(area.value).toBe('Muỗi{}| thích bạn');
  });
});

describe('OptionsPanel', () => {
  it('toggles the punch scene', async () => {
    const user = userEvent.setup();
    render(<Options initial={makeScene()} />);
    const sw = screen.getByRole('switch', { name: 'Cú lật' });
    expect(sw).toHaveAttribute('aria-checked', 'false');
    await user.click(sw);
    expect(current().punch).toBe(true);
  });

  it('switches captions between Tự động (null) and a px value', async () => {
    const user = userEvent.setup();
    render(<Options initial={makeScene()} />);
    const group = screen.getByRole('group', { name: 'Phụ đề' });
    expect(within(group).getByRole('button', { name: 'Tự động', pressed: true })).toBeVisible();
    await user.click(within(group).getByRole('button', { name: 'px' }));
    expect(current().caption_y).toBe(1400);
    const px = screen.getByLabelText('Vị trí phụ đề (px)');
    await user.clear(px);
    await user.type(px, '1300');
    expect(current().caption_y).toBe(1300);
    await user.click(within(group).getByRole('button', { name: 'Tự động' }));
    expect(current().caption_y).toBeNull();
    expect(screen.queryByLabelText('Vị trí phụ đề (px)')).not.toBeInTheDocument();
  });

  it('opens the fixed-labels drawer with the label count, and edits labels there', async () => {
    const user = userEvent.setup();
    render(<Options initial={makeScene()} />);
    await user.click(screen.getByRole('button', { name: /Nhãn cố định \(0\)/ }));
    const drawer = await screen.findByRole('dialog', { name: 'Nhãn cảnh 1' });
    await user.click(within(drawer).getByRole('button', { name: 'Thêm nhãn' }));
    await user.type(within(drawer).getByLabelText('Chữ nhãn 1'), 'MUỖI');
    expect(current().labels).toEqual([
      { text: 'MUỖI', x: 540, y: 960, size: 80, color: 'ink', rot: 0 },
    ]);
    await user.click(within(drawer).getByRole('button', { name: 'Bỏ nhãn 1' }));
    expect(current().labels).toEqual([]);
  });
});
