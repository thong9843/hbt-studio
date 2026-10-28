import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import type { Scene } from '../../api/types';
import { scene as makeScene } from '../../test/project';
import { renderWithProviders } from '../../test/render';
import { CardEditor } from './CardEditor';

const theme = { primary: '#146268', accent: '#DE5C48' };

function Harness({
  initial,
  upload = vi.fn(async () => {}),
}: {
  initial: Scene;
  upload?: () => Promise<void>;
}) {
  const [scene, setScene] = useState(initial);
  return (
    <>
      <CardEditor
        slug="muoi"
        sceneIndex={0}
        scene={scene}
        theme={theme}
        imageVersion={1}
        onChange={(fn) => setScene(fn)}
        onUploadImage={upload}
      />
      <output data-testid="json">{JSON.stringify(scene)}</output>
    </>
  );
}
const current = (): Scene => JSON.parse(screen.getByTestId('json').textContent ?? '{}');
const withLine = (text: string, size: 'xl' | 'l' | 'm' | 's' = 'l') =>
  makeScene({ card: { y: 'top', lines: [{ text, size, color: 'ink' }] } });

describe('CardEditor', () => {
  it('titles the section "Cảnh n · Thẻ chữ" with the 1-based number', () => {
    renderWithProviders(<Harness initial={makeScene()} />);
    expect(screen.getByRole('heading', { name: 'Cảnh 1 · Thẻ chữ' })).toBeInTheDocument();
  });

  it('picks the card position with chips; px reveals a number box', async () => {
    const user = userEvent.setup();
    renderWithProviders(<Harness initial={makeScene()} />);
    const group = screen.getByRole('group', { name: 'Vị trí thẻ' });
    expect(within(group).getByRole('button', { name: 'Trên', pressed: true })).toBeInTheDocument();
    await user.click(within(group).getByRole('button', { name: 'Trên giữa' }));
    expect(current().card.y).toBe('upper');
    await user.click(within(group).getByRole('button', { name: 'px' }));
    expect(current().card.y).toBe(300);
    const px = screen.getByLabelText('Vị trí thẻ (px)');
    await user.clear(px);
    await user.type(px, '640');
    expect(current().card.y).toBe(640);
  });

  it('counts characters per line against the size limit and turns amber past it', async () => {
    const user = userEvent.setup();
    renderWithProviders(<Harness initial={withLine('gấp 100 lần')} />);
    const input = screen.getByLabelText('Dòng 1: Chữ');
    expect(screen.getByText('11/15')).toBeInTheDocument();
    expect(input).not.toHaveAttribute('data-over');
    const sizes = screen.getByRole('group', { name: 'Dòng 1: Cỡ' });
    await user.click(within(sizes).getByRole('button', { name: 'Rất lớn' }));
    expect(screen.getByText('11/10')).toHaveAttribute('data-over', 'true');
    expect(input).toHaveAttribute('data-over', 'true');
    expect(current().card.lines[0].size).toBe('xl');
  });

  it('warns only: typing past the limit is still accepted', async () => {
    const user = userEvent.setup();
    renderWithProviders(<Harness initial={withLine('', 'xl')} />);
    await user.type(screen.getByLabelText('Dòng 1: Chữ'), 'mười một ký');
    expect(current().card.lines[0].text).toBe('mười một ký');
    expect(screen.getByText('11/10')).toBeInTheDocument();
  });

  it('chooses colours with named dots', async () => {
    const user = userEvent.setup();
    renderWithProviders(<Harness initial={makeScene()} />);
    const dots = screen.getByRole('group', { name: 'Dòng 1: Màu' });
    expect(within(dots).getByRole('button', { name: 'Mực', pressed: true })).toBeInTheDocument();
    await user.click(within(dots).getByRole('button', { name: 'Nhấn' }));
    expect(current().card.lines[0].color).toBe('accent');
    await user.click(within(dots).getByRole('button', { name: 'Chính' }));
    expect(current().card.lines[0].color).toBe('primary');
  });

  it('adds up to 5 lines and removes a line', async () => {
    const user = userEvent.setup();
    renderWithProviders(<Harness initial={makeScene()} />);
    const add = screen.getByRole('button', { name: /^Dòng$/ });
    for (let i = 0; i < 4; i++) await user.click(add);
    expect(screen.getAllByLabelText(/^Dòng \d: Chữ$/)).toHaveLength(5);
    expect(add).toBeDisabled();
    await user.click(screen.getByRole('button', { name: 'Bỏ dòng 2' }));
    expect(screen.getAllByLabelText(/^Dòng \d: Chữ$/)).toHaveLength(4);
  });

  it('uploads a single chosen image for the scene', async () => {
    const upload = vi.fn(async () => {});
    const user = userEvent.setup();
    renderWithProviders(
      <Harness initial={makeScene({ image: 'images/scene-01.png' })} upload={upload} />,
    );
    expect(screen.getByRole('button', { name: 'Đổi ảnh' })).toBeInTheDocument();
    await user.upload(
      screen.getByLabelText('Ảnh cảnh', { selector: 'input' }),
      new File(['x'], 'a.png', { type: 'image/png' }),
    );
    expect(upload).toHaveBeenCalledTimes(1);
  });
});
