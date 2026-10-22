import { useState } from 'react';
import { ErrorNote } from '../components/ErrorNote';
import { SceneEditor } from '../components/SceneEditor';
import { SceneList } from '../components/SceneList';
import { ScenePreview } from '../components/ScenePreview';
import { useProjectEditor } from '../hooks/projectEditor';
import { vi } from '../i18n/vi';
import { errorMessage } from '../utils/errors';
import { sceneNumber } from '../utils/scene';
import { countProjectVoiceChars } from '../utils/voice';

export function ScenesTab() {
  const editor = useProjectEditor();
  const { project } = editor;
  const [selected, setSelected] = useState(0);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const index = Math.min(selected, project.scenes.length - 1);
  const scene = project.scenes[index];

  const reorder = async (order: number[], selectedAfter: number) => {
    setBusy(true);
    setError(null);
    try {
      await editor.reorder(order);
      setSelected(selectedAfter);
      setMessage(vi.compose.scenes.moved);
    } catch (e) {
      setError(`${vi.compose.scenes.reorderFailed}: ${errorMessage(e)}`);
    } finally {
      setBusy(false);
    }
  };

  const changeScene = (fn: (s: typeof scene) => typeof scene) =>
    editor.update((p) => ({
      ...p,
      scenes: p.scenes.map((s, i) => (i === index ? fn(s) : s)),
    }));

  return (
    <div className="grid gap-8 lg:grid-cols-[260px_minmax(0,1fr)_320px]">
      <div>
        <SceneList
          slug={project.slug}
          scenes={project.scenes}
          selected={index}
          imageVersion={editor.imageVersion}
          disabled={busy}
          onSelect={setSelected}
          onReorder={(order, after) => void reorder(order, after)}
        />
        <p role="status" className="sr-only">
          {message}
        </p>
        <ErrorNote error={error} className="mt-3" />
      </div>

      <div className="min-w-0">
        <h2 className="mb-5 text-3xl">{vi.compose.scenes.scene(sceneNumber(index))}</h2>
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

      <div className="lg:sticky lg:top-24 lg:self-start">
        <ScenePreview
          slug={project.slug}
          sceneIndex={index}
          scene={scene}
          theme={project.theme}
          imageVersion={editor.imageVersion}
        />
      </div>
    </div>
  );
}
