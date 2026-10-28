import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import type { Scene } from '../api/types';
import { CardEditor } from '../components/compose/CardEditor';
import { OptionsPanel } from '../components/compose/OptionsPanel';
import { PreviewPane } from '../components/compose/PreviewPane';
import { SceneStrip } from '../components/compose/SceneStrip';
import { VoicePanel } from '../components/compose/VoicePanel';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { EyeIcon, TrashIcon } from '../components/icons';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { Drawer } from '../components/ui/Drawer';
import { IconButton } from '../components/ui/IconButton';
import { useProjectEditor } from '../hooks/projectEditor';
import { useToast } from '../hooks/toast';
import { useImageDrop } from '../hooks/useImageDrop';
import { useMediaQuery } from '../hooks/useMediaQuery';
import { vi } from '../i18n/vi';
import { primaryActionState } from '../utils/blockers';
import { MAX_SCENES, MIN_SCENES } from '../utils/limits';
import { emptyScene } from '../utils/newScene';
import { sceneNumber } from '../utils/scene';
import { countProjectVoiceChars } from '../utils/voice';

/** Từ 1024 px cột xem trước nằm cạnh; dưới đó thành ngăn kéo (DESIGN-HBT.md mục 5). */
const PREVIEW_INLINE_QUERY = '(min-width: 1024px)';

/** Màn Soạn video: dải cảnh + 3 cột (thẻ chữ · lời đọc và tuỳ chọn · xem trước 9:16). */
export function ScenesTab() {
  const editor = useProjectEditor();
  const toast = useToast();
  const navigate = useNavigate();
  const { project } = editor;
  const inline = useMediaQuery(PREVIEW_INLINE_QUERY);
  const [selected, setSelected] = useState(0);
  const [busy, setBusy] = useState(false);
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
    } catch (e) {
      // 409 khi đang dựng: Toast kèm gợi ý, có nút Thử lại.
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

  const addScenes = useCallback(
    async (n: number) => {
      editor.update((p) => ({
        ...p,
        scenes: [...p.scenes, ...Array.from({ length: n }, () => emptyScene())],
      }));
      await editor.flush();
    },
    [editor],
  );

  const drop = useImageDrop({
    scenes: project.scenes,
    addScenes,
    upload: editor.uploadImage,
  });

  const removeScene = async () => {
    if (count <= MIN_SCENES) return;
    setBusy(true);
    try {
      await editor.deleteScene(index);
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

  const action = primaryActionState(project);
  const preview = (
    <PreviewPane
      slug={project.slug}
      sceneIndex={index}
      sceneCount={count}
      scene={scene}
      theme={project.theme}
      imageVersion={editor.imageVersion}
      blockedReason={action.enabled ? undefined : action.reason}
      onPrev={() => setSelected(Math.max(0, index - 1))}
      onNext={() => setSelected(Math.min(count - 1, index + 1))}
      onGoExport={() => navigate(`/p/${project.slug}/export`)}
    />
  );

  return (
    <div className="space-y-5">
      <SceneStrip
        slug={project.slug}
        scenes={project.scenes}
        selected={index}
        imageVersion={editor.imageVersion}
        disabled={busy || drop.progress !== null}
        progress={drop.progress}
        onSelect={setSelected}
        onReorder={(order, after) => void reorder(order, after)}
        onAdd={addScene}
        onDropFiles={drop.onFiles}
      />

      <div
        className={
          inline
            ? 'grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)_300px] gap-[18px]'
            : 'grid grid-cols-1 gap-[18px] min-[700px]:grid-cols-2'
        }
      >
        <Card as="div" className="min-w-0 self-start">
          <CardEditor
            key={index}
            slug={project.slug}
            sceneIndex={index}
            scene={scene}
            theme={project.theme}
            imageVersion={editor.imageVersion}
            onChange={changeScene}
            onUploadImage={(file) => editor.uploadImage(index, file)}
            actions={
              <IconButton
                label={vi.compose.scenes.remove}
                small
                disabled={count <= MIN_SCENES || busy}
                title={count <= MIN_SCENES ? vi.compose.scenes.min : vi.compose.scenes.remove}
                onClick={() => setRemoving(true)}
              >
                <TrashIcon size={18} />
              </IconButton>
            }
          />
        </Card>

        <div className="min-w-0 space-y-[18px] self-start">
          <Card as="div">
            <VoicePanel
              sceneIndex={index}
              voice={scene.voice}
              totalChars={countProjectVoiceChars(project.scenes)}
              onChange={(voice) => changeScene((s) => ({ ...s, voice }))}
            />
          </Card>
          <OptionsPanel
            sceneIndex={index}
            scene={scene}
            theme={project.theme}
            onChange={changeScene}
          />
        </div>

        {inline && <div className="sticky top-5 self-start">{preview}</div>}
      </div>

      {!inline && (
        <>
          <Button
            tone="ink"
            className="fixed bottom-6 right-6 z-30 shadow-lg"
            icon={<EyeIcon size={20} />}
            onClick={() => setDrawer(true)}
          >
            {vi.compose.preview.open}
          </Button>
          <Drawer open={drawer} onClose={() => setDrawer(false)} title={vi.compose.preview.title}>
            {preview}
          </Drawer>
        </>
      )}

      <p className="text-small text-muted">{vi.compose.shortcuts}</p>
      {drop.dialogs}
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
