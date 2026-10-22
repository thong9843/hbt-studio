import { useEffect, useState } from 'react';
import type { Project, Scene } from '../api/types';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { EyeIcon, XIcon } from '../components/icons';
import { SceneEditor } from '../components/SceneEditor';
import { SceneList } from '../components/SceneList';
import { ScenePreview } from '../components/ScenePreview';
import { useProjectEditor } from '../hooks/projectEditor';
import { useToast } from '../hooks/toast';
import { useMediaQuery } from '../hooks/useMediaQuery';
import { vi } from '../i18n/vi';
import { MAX_SCENES, MIN_SCENES } from '../utils/limits';
import { emptyScene } from '../utils/newScene';
import { sceneNumber } from '../utils/scene';
import { countProjectVoiceChars } from '../utils/voice';

/** `thumbnail.scene` (số từ 1) không được vượt số cảnh còn lại, nếu không máy chủ từ chối lưu. */
function clampThumbnail(p: Project): Project {
  const t = p.thumbnail as { scene?: number } | null;
  if (t && typeof t.scene === 'number' && t.scene > p.scenes.length) {
    return { ...p, thumbnail: { ...t, scene: p.scenes.length } };
  }
  return p;
}

export function ScenesTab() {
  const editor = useProjectEditor();
  const toast = useToast();
  const { project } = editor;
  const wide = useMediaQuery('(min-width: 1280px)');
  const medium = useMediaQuery('(min-width: 1024px)');
  const [selected, setSelected] = useState(0);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [removing, setRemoving] = useState(false);
  const [drawer, setDrawer] = useState(false);

  const count = project.scenes.length;
  const index = Math.min(selected, count - 1);
  const scene = project.scenes[index];

  // Alt+↑ / Alt+↓ chuyển cảnh
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!e.altKey || (e.key !== 'ArrowUp' && e.key !== 'ArrowDown')) return;
      e.preventDefault();
      setSelected((cur) => Math.min(count - 1, Math.max(0, cur + (e.key === 'ArrowUp' ? -1 : 1))));
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [count]);

  const reorder = async (order: number[], selectedAfter: number) => {
    setBusy(true);
    try {
      await editor.reorder(order);
      setSelected(selectedAfter);
      setMessage(vi.compose.scenes.moved);
    } catch (e) {
      toast.error(e, () => void reorder(order, selectedAfter));
    } finally {
      setBusy(false);
    }
  };

  const addScene = () => {
    if (count >= MAX_SCENES) return;
    editor.update((p) => ({ ...p, scenes: [...p.scenes, emptyScene()] }));
    setSelected(count);
  };

  const removeScene = async () => {
    if (count <= MIN_SCENES) return;
    setBusy(true);
    try {
      // Đưa cảnh cần xoá xuống cuối (máy chủ đổi tên ảnh cho khớp), rồi cắt bỏ cảnh cuối.
      if (index !== count - 1) {
        const order = [...Array(count).keys()].filter((i) => i !== index).concat(index);
        await editor.reorder(order);
      }
      editor.update((p) => clampThumbnail({ ...p, scenes: p.scenes.slice(0, -1) }));
      setSelected(Math.min(index, count - 2));
    } catch (e) {
      toast.error(e);
    } finally {
      setBusy(false);
      setRemoving(false);
    }
  };

  const changeScene = (fn: (s: Scene) => Scene) =>
    editor.update((p) => ({
      ...p,
      scenes: p.scenes.map((s, i) => (i === index ? fn(s) : s)),
    }));

  const preview = (
    <ScenePreview
      slug={project.slug}
      sceneIndex={index}
      scene={scene}
      theme={project.theme}
      imageVersion={editor.imageVersion}
    />
  );

  const list = (
    <SceneList
      slug={project.slug}
      scenes={project.scenes}
      selected={index}
      imageVersion={editor.imageVersion}
      disabled={busy}
      horizontal={!wide}
      onSelect={setSelected}
      onReorder={(order, after) => void reorder(order, after)}
      onAdd={addScene}
      onRemove={() => setRemoving(true)}
    />
  );

  return (
    <div
      className={
        wide
          ? 'grid grid-cols-[280px_minmax(0,1fr)_360px] gap-8'
          : medium
            ? 'grid grid-cols-[minmax(0,1fr)_360px] gap-8'
            : 'grid gap-8'
      }
    >
      <div className={medium && !wide ? 'col-span-2' : ''}>
        {list}
        <p role="status" className="sr-only">
          {message}
        </p>
        <p className="mt-3 text-small text-text-muted">{vi.compose.shortcuts}</p>
      </div>

      <div className="min-w-0">
        <h1 className="mb-6">{vi.compose.scenes.scene(sceneNumber(index))}</h1>
        <SceneEditor
          key={index}
          slug={project.slug}
          sceneIndex={index}
          scene={scene}
          imageVersion={editor.imageVersion}
          totalVoiceChars={countProjectVoiceChars(project.scenes)}
          onChange={changeScene}
          onUploadImage={(file) => editor.uploadImage(index, file)}
        />
      </div>

      {medium ? (
        <div className="self-start lg:sticky lg:top-24">{preview}</div>
      ) : (
        <>
          <button
            type="button"
            className="btn btn-primary fixed bottom-6 right-6 z-30 shadow-lg"
            onClick={() => setDrawer(true)}
          >
            <EyeIcon size={20} />
            {vi.compose.preview.open}
          </button>
          {drawer && (
            <aside
              role="dialog"
              aria-modal="true"
              aria-label={vi.compose.preview.title}
              className="fixed inset-y-0 right-0 z-40 w-full max-w-[420px] overflow-y-auto bg-bg p-6 shadow-xl"
            >
              <button
                type="button"
                className="btn btn-icon mb-4 ml-auto"
                aria-label={vi.compose.preview.closeDrawer}
                onClick={() => setDrawer(false)}
              >
                <XIcon />
              </button>
              {preview}
            </aside>
          )}
        </>
      )}

      {removing && (
        <ConfirmDialog
          title={vi.compose.scenes.removeTitle(sceneNumber(index))}
          message={vi.compose.scenes.removeMessage}
          confirmLabel={vi.compose.scenes.remove}
          danger
          busy={busy}
          onConfirm={() => void removeScene()}
          onCancel={() => setRemoving(false)}
        />
      )}
    </div>
  );
}
