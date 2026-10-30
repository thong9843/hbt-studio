import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { api } from '../../api/endpoints';
import type { ScriptJsonCheckResult } from '../../api/types';
import { usePostvEditor } from '../../hooks/postvEditor';
import { vi } from '../../i18n/vi';
import { ErrorNote } from '../ErrorNote';
import { Badge } from '../ui/Badge';
import { Button } from '../ui/Button';
import { Dialog } from '../ui/Dialog';
import { Textarea } from '../ui/Field';

const T = vi.postv.scriptJson;

interface Props {
  open: boolean;
  onClose: () => void;
}

export function PostvScriptJsonDialog({ open, onClose }: Props) {
  const { project } = usePostvEditor();
  const queryClient = useQueryClient();
  const slug = project.slug;

  const [rawJson, setRawJson] = useState('');
  const [parseError, setParseError] = useState<string | null>(null);
  const [checkResult, setCheckResult] = useState<ScriptJsonCheckResult | null>(null);
  const [appliedNotice, setAppliedNotice] = useState<string | null>(null);

  const backupsQuery = useQuery({
    queryKey: ['postv-backups', slug],
    queryFn: () => api.listPostvBackups(slug),
    enabled: open,
  });

  const checkMutation = useMutation({
    mutationFn: (body: unknown) => api.checkPostvScriptJson(slug, body),
    onSuccess: (res) => {
      setCheckResult(res);
      setAppliedNotice(null);
    },
  });

  const applyMutation = useMutation({
    mutationFn: (body: unknown) => api.applyPostvScriptJson(slug, body),
    onSuccess: () => {
      setAppliedNotice(T.applied);
      void queryClient.invalidateQueries({ queryKey: ['postv-project', slug] });
      void queryClient.invalidateQueries({ queryKey: ['postv-backups', slug] });
      // Reload lại trang sau khi áp dụng để tải kịch bản mới
      window.location.reload();
    },
  });

  const restoreMutation = useMutation({
    mutationFn: (backupId: string) => api.restorePostvBackup(slug, backupId),
    onSuccess: () => {
      setAppliedNotice(T.restored);
      void queryClient.invalidateQueries({ queryKey: ['postv-project', slug] });
      void queryClient.invalidateQueries({ queryKey: ['postv-backups', slug] });
      window.location.reload();
    },
  });

  const handleCheck = () => {
    setParseError(null);
    setCheckResult(null);
    let parsed: unknown;
    try {
      parsed = JSON.parse(rawJson);
    } catch (e) {
      setParseError(e instanceof Error ? e.message : 'JSON không đúng cú pháp');
      return;
    }
    checkMutation.mutate(parsed);
  };

  const handleApply = () => {
    setParseError(null);
    let parsed: unknown;
    try {
      parsed = JSON.parse(rawJson);
    } catch (e) {
      setParseError(e instanceof Error ? e.message : 'JSON không đúng cú pháp');
      return;
    }
    applyMutation.mutate(parsed);
  };

  const backups = backupsQuery.data ?? [];

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={T.dialogTitle}
      footer={
        <>
          <Button tone="soft" onClick={onClose}>
            {vi.common.cancel}
          </Button>
          <Button
            tone="soft"
            onClick={handleCheck}
            disabled={!rawJson.trim() || checkMutation.isPending}
            busy={checkMutation.isPending}
          >
            {checkMutation.isPending ? T.checking : T.check}
          </Button>
          <Button
            tone="ink"
            onClick={handleApply}
            disabled={!checkResult?.ok || applyMutation.isPending}
            busy={applyMutation.isPending}
          >
            {applyMutation.isPending ? T.applying : T.apply}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <p className="text-small text-muted">{T.lead}</p>

        <Textarea
          aria-label={T.dialogTitle}
          rows={10}
          value={rawJson}
          onChange={(e) => {
            setRawJson(e.target.value);
            setCheckResult(null);
            setParseError(null);
          }}
          placeholder={T.placeholder}
          className="font-mono text-tiny"
        />

        {parseError && <p className="text-small font-semibold text-danger">{parseError}</p>}

        <ErrorNote error={checkMutation.error ?? applyMutation.error ?? restoreMutation.error} />

        {appliedNotice && <p className="text-small font-semibold text-ok">{appliedNotice}</p>}

        {checkResult && (
          <div className="space-y-2 rounded-inner bg-soft p-3">
            <div className="flex items-center gap-2">
              <Badge tone={checkResult.ok ? 'ok' : 'danger'}>
                {checkResult.ok ? 'Hợp lệ' : 'Lỗi'}
              </Badge>
              <span className="text-small font-semibold">
                {checkResult.ok ? T.valid : T.errors(checkResult.errors.length)}
              </span>
            </div>

            {checkResult.summary && (
              <p className="text-small text-muted">
                {T.summary(
                  checkResult.summary.hook,
                  checkResult.summary.segments_count,
                  checkResult.summary.total_chars,
                  checkResult.summary.estimated_seconds,
                )}
              </p>
            )}

            {checkResult.errors.length > 0 && (
              <ul className="list-disc pl-5 text-small text-danger">
                {checkResult.errors.map((err, i) => (
                  <li key={i}>{err}</li>
                ))}
              </ul>
            )}

            {checkResult.warnings.length > 0 && (
              <ul className="list-disc pl-5 text-small text-amber-600 dark:text-amber-400">
                {checkResult.warnings.map((warn, i) => (
                  <li key={i}>{warn}</li>
                ))}
              </ul>
            )}
          </div>
        )}

        <div className="pt-2">
          <h3 className="text-small font-bold text-muted">{T.backupsTitle}</h3>
          {backups.length === 0 ? (
            <p className="text-tiny text-muted">{T.noBackups}</p>
          ) : (
            <ul className="mt-2 space-y-1.5" aria-label={T.backupsTitle}>
              {backups.map((b) => (
                <li
                  key={b.id}
                  className="flex items-center justify-between rounded-inner bg-soft px-3 py-1.5 text-tiny"
                >
                  <span className="font-mono text-muted">
                    {b.id} · {new Date(b.created_at).toLocaleString('vi-VN')}
                  </span>
                  <Button
                    tone="soft"
                    size="sm"
                    disabled={restoreMutation.isPending}
                    onClick={() => restoreMutation.mutate(b.id)}
                  >
                    {T.restore}
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </Dialog>
  );
}
