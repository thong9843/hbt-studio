import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi as vitest } from 'vitest';
import { SceneTimelineStrip } from './SceneTimelineStrip';
import { StudioTopBar } from './StudioTopBar';

describe('StudioTopBar & SceneTimelineStrip layout guards', () => {
  it('keeps right export controls shrink-0 and caps project selector width', () => {
    render(
      <MemoryRouter>
        <StudioTopBar
          projectSelector={
            <button type="button" className="truncate">
              Dự án StickV có tiêu đề cực kỳ dài để kiểm tra không đẩy nút xuất video ra khỏi khung
            </button>
          }
          aspect="9:16"
          onAspectChange={vitest.fn()}
          exportProps={{
            aspect: '9:16',
            onExportFinal: vitest.fn(),
          }}
        />
      </MemoryRouter>,
    );

    const exportBtn = screen.getByRole('button', { name: 'Xuất video' });
    const rightGroup = exportBtn.closest('header > div:last-child');
    expect(rightGroup).toHaveClass('shrink-0');

    const selectorBtn = screen.getByRole('button', { name: /Dự án StickV có tiêu đề cực kỳ dài/i });
    expect(selectorBtn.parentElement).toHaveClass('max-w-[260px]');
    expect(selectorBtn.parentElement).toHaveClass('lg:max-w-[360px]');
  });

  it('gives SceneTimelineStrip 96px cards, 1.35 line-height, and 14px scrollbar bottom padding', () => {
    render(
      <SceneTimelineStrip
        items={[
          {
            id: 'b001',
            index: 1,
            summary: 'Câu lời thoại tiếng Việt có dấu nặng hỏi ngã rất dài để kiểm tra hai dòng',
            durationSec: 4.5,
          },
        ]}
        selectedId="b001"
        onSelect={vitest.fn()}
        onAdd={vitest.fn()}
        totalDurationSec={4.5}
      />,
    );

    const card = screen.getByRole('button', { name: /#1/i });
    expect(card).toHaveClass('h-[96px]');
    expect(card).toHaveClass('py-2.5');
    expect(card.parentElement).toHaveClass('pb-[14px]');

    const textEl = screen.getByText(/Câu lời thoại tiếng Việt/i);
    expect(textEl).toHaveClass('leading-[1.35]');
    expect(textEl).toHaveClass('line-clamp-2');
  });
});
