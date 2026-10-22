import { DndContext } from '@dnd-kit/core';
import { SortableContext } from '@dnd-kit/sortable';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import type { Scene } from '../api/types';
import { scene } from '../test/project';
import { SceneItem, SceneList } from './SceneList';

function item(over: Partial<Scene> = {}, active = false, onSelect = vi.fn()) {
  render(
    <DndContext>
      <SortableContext items={['scene-0']}>
        <ul>
          <SceneItem
            id="scene-0"
            index={0}
            slug="muoi"
            active={active}
            imageVersion={3}
            onSelect={onSelect}
            scene={scene({ image: 'images/scene-01.png', voice: 'Muỗi | thích {100}', ...over })}
          />
        </ul>
      </SortableContext>
    </DndContext>,
  );
  return onSelect;
}

describe('SceneItem', () => {
  it('shows the 1-based number, a clean voice excerpt and the cache-busted image', () => {
    item();
    expect(screen.getByText('Cảnh 1')).toBeInTheDocument();
    expect(screen.getByText('Muỗi thích 100')).toBeInTheDocument();
    expect(document.querySelector('img')).toHaveAttribute(
      'src',
      '/api/files/projects/muoi/images/scene-01.png?v=3',
    );
  });

  it('marks the active item and reports selection', async () => {
    const onSelect = item({}, true);
    const button = screen.getByRole('button', { name: /Cảnh 1/ });
    expect(button).toHaveAttribute('aria-current', 'true');
    await userEvent.click(button);
    expect(onSelect).toHaveBeenCalled();
  });

  it('says so when the scene has no image', () => {
    item({ image: '' });
    expect(screen.getByText('chưa có ảnh')).toBeInTheDocument();
  });

  it('names the drag handle in Vietnamese', () => {
    item();
    expect(screen.getByRole('button', { name: 'Kéo để đổi thứ tự cảnh 1' })).toBeInTheDocument();
  });
});

describe('SceneList limits', () => {
  const base = {
    slug: 'muoi',
    selected: 0,
    imageVersion: 0,
    onSelect: vi.fn(),
    onReorder: vi.fn(),
    onAdd: vi.fn(),
    onRemove: vi.fn(),
  };

  it('disables add at 12 scenes and remove at 3', () => {
    const { rerender } = render(
      <SceneList {...base} scenes={Array.from({ length: 12 }, () => scene())} />,
    );
    expect(screen.getByRole('button', { name: /Thêm cảnh/ })).toBeDisabled();
    expect(screen.getByRole('button', { name: /Xoá cảnh này/ })).toBeEnabled();
    rerender(<SceneList {...base} scenes={Array.from({ length: 3 }, () => scene())} />);
    expect(screen.getByRole('button', { name: /Thêm cảnh/ })).toBeEnabled();
    expect(screen.getByRole('button', { name: /Xoá cảnh này/ })).toBeDisabled();
  });
});
