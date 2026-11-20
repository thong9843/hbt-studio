import { useQueryClient } from '@tanstack/react-query';
import { useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ApiError } from '../../api/client';
import { api } from '../../api/endpoints';
import type { DraftCheck, ScriptIssue } from '../../api/types';
import { useToast } from '../../hooks/toast';
import { vi } from '../../i18n/vi';
import { projectHref } from '../../utils/projectHref';
import { AlertIcon } from '../icons';
import { Button } from '../ui/Button';
import { Dialog } from '../ui/Dialog';
import { Textarea } from '../ui/Field';

const T = vi.gd2;

/** Đọc file văn bản; dùng FileReader vì `Blob.text` chưa có ở mọi môi trường. */
function readText(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result ?? ''));
    reader.onerror = () => reject(reader.error ?? new Error(T.readFailed));
    reader.readAsText(file);
  });
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-inner bg-soft-2 p-3">
      <p className="text-tiny font-semibold text-muted">{label}</p>
      <p className="break-words text-h2 font-bold">{value}</p>
    </div>
  );
}

function Issue({ issue, kind }: { issue: ScriptIssue; kind: 'error' | 'warning' }) {
  const block = issue.level === 'block';
  return (
    <li
      className={`flex items-start gap-2 rounded-input px-3 py-2 text-small ${
        kind === 'error' || block ? 'bg-danger-soft text-danger' : 'bg-tint-yel text-on-tint-yel'
      }`}
    >
      <AlertIcon size={16} />
      <span className="min-w-0 flex-1 break-words">
        <span className="font-bold">
          {kind === 'error' ? T.errorsHeading : block ? T.levelBlock : T.levelWarn} · {issue.code}
        </span>
        {' — '}
        {issue.message}
      </span>
    </li>
  );
}

function Issues({ issues, kind }: { issues: ScriptIssue[]; kind: 'error' | 'warning' }) {
  if (issues.length === 0) return null;
  return (
    <section aria-label={kind === 'error' ? T.errorsHeading : T.warningsHeading}>
      <h3 className="mb-2 text-small font-bold">
        {kind === 'error' ? T.errorCount(issues.length) : T.warningCount(issues.length)}
      </h3>
      <ul className="space-y-1">
        {issues.map((issue, i) => (
          <Issue key={i} issue={issue} kind={kind} />
        ))}
      </ul>
    </section>
  );
}

interface Props {
  open: boolean;
  onClose: () => void;
}

/**
 * Hộp "Tạo dự án từ JSON nháp" (GĐ2, G1): 1 Dán → 2 Kiểm tra → Tạo dự án.
 * Kiểm không ghi gì; chỉ nút Tạo mới tạo dự án và `draft.json`.
 */
export function DraftDialog({ open, onClose }: Props) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const toast = useToast();
  const [text, setText] = useState('');
  const [check, setCheck] = useState<DraftCheck | null>(null);
  const [checking, setChecking] = useState(false);
  const [creating, setCreating] = useState(false);
  const [dragging, setDragging] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  const busy = checking || creating;
  const close = () => {
    if (busy) return;
    onClose();
  };

  const runCheck = async () => {
    setChecking(true);
    try {
      setCheck(await api.checkDraft(text));
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
      setCheck(null);
    } catch (e) {
      toast.error(e);
    }
  };

  const create = async () => {
    setCreating(true);
    try {
      const res = await api.createDraft(text);
      void queryClient.invalidateQueries({ queryKey: ['projects'] });
      toast.info(T.created);
      setText('');
      setCheck(null);
      onClose();
      navigate(projectHref({ slug: res.slug }));
    } catch (e) {
      if (e instanceof ApiError && e.status === 422) {
        const errors = (e.body as { errors?: ScriptIssue[] } | null)?.errors;
        if (errors && check) setCheck({ ...check, ok: false, errors });
        else toast.error(e);
      } else {
        toast.error(e);
      }
    } finally {
      setCreating(false);
    }
  };

  return (
    <Dialog
      open={open}
      onClose={close}
      title={T.title}
      className="!max-w-[760px]"
      footer={
        check === null ? (
          <Button disabled={checking || !text.trim()} onClick={() => void runCheck()}>
            {checking ? T.checking : T.check}
          </Button>
        ) : (
          <>
            <span
              role="status"
              className={`mr-auto self-center text-small font-bold ${check.ok ? 'text-ok' : 'text-danger'}`}
            >
              {check.ok ? T.allGood : T.hasErrors}
            </span>
            <Button tone="soft" disabled={creating} onClick={() => setCheck(null)}>
              {T.back}
            </Button>
            <Button disabled={!check.ok || busy} onClick={() => void create()}>
              {creating ? T.creating : T.create}
            </Button>
          </>
        )
      }
    >
      {check === null ? (
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
              data-testid="draft-file"
              onChange={(e) => {
                void loadFile(e.target.files?.[0]);
                e.target.value = '';
              }}
            />
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          <div className="grid grid-cols-3 gap-3">
            <Stat label={T.stats.topic} value={check.topic || '—'} />
            <Stat label={T.stats.scenes} value={String(check.scenes)} />
            <Stat label={T.stats.music} value={check.music_match?.title ?? T.musicNone} />
          </div>
          <Issues issues={check.errors} kind="error" />
          <Issues issues={check.warnings} kind="warning" />
        </div>
      )}
    </Dialog>
  );
}
