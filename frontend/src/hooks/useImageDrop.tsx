import { useCallback, useState, type ReactNode } from 'react';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { vi } from '../i18n/vi';
import { planImageDrop, type DropPlan } from '../utils/dropImages';
import { MAX_SCENES } from '../utils/limits';
import { useToast } from './toast';

const T = vi.compose.strip;

interface Options {
  scenes: { image: string }[];
  /** Thêm `count` cảnh trống và lưu ngay để máy chủ có đủ cảnh trước khi tải ảnh. */
  addScenes: (count: number) => Promise<void>;
  /** Tải ảnh cho cảnh `sceneIndex` (từ 0). */
  upload: (sceneIndex: number, file: File) => Promise<void>;
}

type Step = { kind: 'overwrite' | 'addScenes'; plan: DropPlan; skipExtra?: boolean };

/**
 * Thả nhiều ảnh (13.B2.1): hỏi ghi đè một lần, rồi hỏi thêm cảnh cho ảnh dư (hai hộp nối tiếp),
 * sau đó tải **lần lượt từng file** và báo tiến độ `done/total`.
 */
export function useImageDrop({ scenes, addScenes, upload }: Options) {
  const toast = useToast();
  const [step, setStep] = useState<Step | null>(null);
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null);

  const run = useCallback(
    async (plan: DropPlan, withExtra: boolean) => {
      const extra = withExtra ? plan.extra : [];
      const total = plan.existing.length + extra.length;
      if (total === 0) return;
      let done = 0;
      setProgress({ done, total });
      try {
        if (extra.length > 0) await addScenes(extra.length);
        const queue = [...plan.existing, ...extra];
        for (const [i, file] of queue.entries()) {
          await upload(i, file);
          setProgress({ done: ++done, total });
        }
      } catch (e) {
        toast.error(e);
        return;
      } finally {
        setProgress(null);
      }
      const notes = [T.uploaded(done)];
      if (plan.dropped > 0) notes.push(T.droppedOver(plan.dropped));
      toast.info(notes.join(' · '));
    },
    [addScenes, toast, upload],
  );

  const askExtra = useCallback(
    (plan: DropPlan) => {
      if (plan.extra.length > 0) setStep({ kind: 'addScenes', plan });
      else void run(plan, false);
    },
    [run],
  );

  const onFiles = useCallback(
    (files: File[]) => {
      const plan = planImageDrop(files, scenes, MAX_SCENES);
      if (plan.overwrite.length > 0) setStep({ kind: 'overwrite', plan });
      else askExtra(plan);
    },
    [askExtra, scenes],
  );

  let dialogs: ReactNode = null;
  if (step?.kind === 'overwrite') {
    const { plan } = step;
    dialogs = (
      <ConfirmDialog
        title={T.overwriteTitle}
        message={T.overwriteMessage(plan.overwrite.length)}
        confirmLabel={T.overwriteConfirm}
        onCancel={() => setStep(null)}
        onConfirm={() => {
          setStep(null);
          askExtra(plan);
        }}
      />
    );
  } else if (step?.kind === 'addScenes') {
    const { plan } = step;
    dialogs = (
      <ConfirmDialog
        title={T.addScenesTitle}
        message={T.addScenesMessage(plan.extra.length, scenes.length + plan.extra.length)}
        confirmLabel={T.addScenesConfirm}
        cancelLabel={T.addScenesSkip}
        onCancel={() => {
          setStep(null);
          void run(plan, false);
        }}
        onConfirm={() => {
          setStep(null);
          void run(plan, true);
        }}
      />
    );
  }

  return { onFiles, progress, dialogs };
}
