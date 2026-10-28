import { useRef, useState } from 'react';
import type { ScriptCheck, ScriptExtra } from '../../api/types';
import { api } from '../../api/endpoints';
import { useProjectEditor } from '../../hooks/projectEditor';
import { useToast } from '../../hooks/toast';
import { vi } from '../../i18n/vi';
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
    reader.onerror = () => reject(reader.error ?? new Error('Không đọc được file'));
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
  const { project, flush } = useProjectEditor();
  const toast = useToast();
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
          <Button tone="soft" onClick={edit}>
            {T.back}
          </Button>
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
