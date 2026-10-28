import { useRef, useState } from 'react';
import type { ScriptCheck, ScriptExtra, ScriptIssue } from '../../api/types';
import { ApiError } from '../../api/client';
import { api } from '../../api/endpoints';
import { useProjectEditor } from '../../hooks/projectEditor';
import { useRenderJob } from '../../hooks/renderJob';
import { useToast } from '../../hooks/toast';
import { vi } from '../../i18n/vi';
import { appliedScenes } from '../../utils/scriptDiff';
import { Button } from '../ui/Button';
import { Dialog } from '../ui/Dialog';
import { Textarea } from '../ui/Field';
import { ScriptCheckView } from './ScriptCheckView';

const T = vi.script;

/** Đọc file văn bản; dùng FileReader vì `Blob.text` chưa có ở mọi môi trường. */
function readText(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result ?? ''));
    reader.onerror = () => reject(reader.error ?? new Error(T.readFailed));
    reader.readAsText(file);
  });
}

interface Props {
  open: boolean;
  onClose: () => void;
}

/**
 * Hộp Dán JSON (13.B4.6): 1 Dán → 2 Kiểm tra. Trước khi kiểm, app lưu ngay bản đang soạn vì
 * `script/check` đọc `project.json` thẳng từ đĩa.
 */
export function PasteJsonDialog({ open, onClose }: Props) {
  const { project, flush, applyServer, bumpImages } = useProjectEditor();
  const job = useRenderJob();
  const toast = useToast();
  /** Đang dựng chính dự án này: không áp, không hoàn tác (backend cũng trả 409). */
  const locked = (job.running || job.starting) && job.slug === project.slug;
  const [applying, setApplying] = useState(false);
  const [text, setText] = useState('');
  const [step, setStep] = useState<'paste' | 'check'>('paste');
  const [extra, setExtra] = useState<ScriptExtra | null>(null);
  const [check, setCheck] = useState<ScriptCheck | null>(null);
  const [checking, setChecking] = useState(false);
  const [dragging, setDragging] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  const runCheck = async (nextExtra: ScriptExtra | null) => {
    setChecking(true);
    try {
      await flush();
      const res = await api.checkScript(project.slug, text, nextExtra ?? undefined);
      setExtra(nextExtra);
      setCheck(res);
      setStep('check');
    } catch (e) {
      toast.error(e);
    } finally {
      setChecking(false);
    }
  };

  const loadFile = async (file: File | undefined) => {
    if (!file) return;
    if (!/\.json$/i.test(file.name)) {
      toast.error(new Error(T.notJsonFile));
      return;
    }
    try {
      setText(await readText(file));
      setStep('paste');
    } catch (e) {
      toast.error(e);
    }
  };

  const undo = async (backupId: string) => {
    try {
      await flush();
      const res = await api.restoreBackup(project.slug, backupId);
      applyServer(() => res.project);
      bumpImages();
      toast.info(T.undone);
    } catch (e) {
      toast.error(e);
    }
  };

  const apply = async () => {
    if (!check) return;
    const n = appliedScenes(check);
    setApplying(true);
    try {
      const res = await api.applyScript(project.slug, text, check.base_hash, extra ?? undefined);
      applyServer(() => res.project);
      bumpImages();
      toast.info(T.applied(n), locked ? undefined : { undo: () => void undo(res.backup_id) });
      setText('');
      edit();
      onClose();
    } catch (e) {
      if (e instanceof ApiError && e.status === 422) {
        const errors = (e.body as { errors?: ScriptIssue[] } | null)?.errors;
        if (errors) setCheck({ ...check, ok: false, errors });
        else toast.error(e);
      } else {
        toast.error(e);
        // Hash lệch (dự án đổi sau lần kiểm): kiểm lại để lấy hash mới. Đang dựng thì giữ nguyên.
        if (e instanceof ApiError && e.status === 409 && !locked) {
          toast.info(T.staleRecheck);
          await runCheck(extra);
        }
      }
    } finally {
      setApplying(false);
    }
  };

  const edit = () => {
    setStep('paste');
    setCheck(null);
    setExtra(null);
  };

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={T.title}
      className="!max-w-[760px]"
      footer={
        step === 'paste' ? (
          <Button disabled={checking || !text.trim()} onClick={() => void runCheck(null)}>
            {checking ? T.checking : T.check}
          </Button>
        ) : (
          <>
            {check && !check.ok && (
              <span role="status" className="mr-auto self-center text-small font-bold text-danger">
                {T.hasErrors}
              </span>
            )}
            {locked && (
              <span role="status" className="mr-auto self-center text-small font-bold text-muted">
                {T.busy}
              </span>
            )}
            <Button tone="soft" onClick={edit}>
              {T.back}
            </Button>
            <Button
              disabled={!check?.ok || locked || applying || checking}
              title={locked ? T.busy : !check?.ok ? T.hasErrors : undefined}
              onClick={() => void apply()}
            >
              {applying
                ? T.applying
                : check && appliedScenes(check) > 0
                  ? T.applyN(appliedScenes(check))
                  : T.apply}
            </Button>
          </>
        )
      }
    >
      {step === 'paste' ? (
        <div
          className="ui-drop !block !border-solid !p-2 text-left"
          data-active={dragging}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            void loadFile(e.dataTransfer.files[0]);
          }}
        >
          <Textarea
            data-autofocus
            label={T.pasteLabel}
            value={text}
            rows={12}
            spellCheck={false}
            placeholder={T.pastePlaceholder}
            hint={<p className="mt-1 text-tiny font-normal text-muted">{T.pasteHint}</p>}
            className="!bg-hero !font-mono !text-small !text-on-hero"
            onChange={(e) => setText(e.target.value)}
          />
          <div className="mt-2 flex items-center gap-3">
            <Button tone="soft" size="sm" onClick={() => fileInput.current?.click()}>
              {T.pickFile}
            </Button>
            <span className="text-tiny text-muted">{T.dropFile}</span>
            <input
              ref={fileInput}
              type="file"
              accept=".json,application/json"
              hidden
              data-testid="script-file"
              onChange={(e) => {
                void loadFile(e.target.files?.[0]);
                e.target.value = '';
              }}
            />
          </div>
        </div>
      ) : (
        check && (
          <ScriptCheckView
            check={check}
            theme={project.theme}
            extra={extra}
            busy={checking}
            onExtra={(x) => void runCheck(x)}
          />
        )
      )}
    </Dialog>
  );
}
