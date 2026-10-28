import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { api } from '../../api/endpoints';
import type { BackupEntry } from '../../api/types';
import { useProjectEditor } from '../../hooks/projectEditor';
import { useRenderJob } from '../../hooks/renderJob';
import { useToast } from '../../hooks/toast';
import { vi } from '../../i18n/vi';
import { formatDateTime } from '../../utils/format';
import { ConfirmDialog } from '../ConfirmDialog';
import { ErrorNote } from '../ErrorNote';
import { Button } from '../ui/Button';
import { Dialog } from '../ui/Dialog';

const T = vi.script.backups;

const reasonLabel = (reason: BackupEntry['reason']) =>
  reason === 'apply' ? T.reason.apply : reason === 'restore' ? T.reason.restore : T.reason.unknown;

interface Props {
  open: boolean;
  onClose: () => void;
}

/** Danh sách ≤ 10 bản sao lưu `project.json` và Khôi phục (có xác nhận). Lấy một lần khi mở. */
export function BackupsDialog({ open, onClose }: Props) {
  const { project, flush, applyServer, bumpImages } = useProjectEditor();
  const job = useRenderJob();
  const toast = useToast();
  const queryClient = useQueryClient();
  const slug = project.slug;
  const locked = (job.running || job.starting) && job.slug === slug;
  const [pending, setPending] = useState<BackupEntry | null>(null);
  const [busy, setBusy] = useState(false);

  const { data, isPending, error } = useQuery({
    queryKey: ['backups', slug],
    queryFn: () => api.listBackups(slug),
    enabled: open,
    staleTime: 0,
    gcTime: 0,
    refetchOnWindowFocus: false,
    retry: false,
  });

  const restore = async (entry: BackupEntry) => {
    setBusy(true);
    try {
      await flush();
      const res = await api.restoreBackup(slug, entry.id);
      applyServer(() => res.project);
      bumpImages();
      void queryClient.invalidateQueries({ queryKey: ['backups', slug] });
      setPending(null);
      onClose();
      toast.info(T.done);
    } catch (e) {
      setPending(null);
      toast.error(e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <Dialog open={open} onClose={onClose} title={T.title}>
        {isPending && !error && <p className="text-muted">{T.loading}</p>}
        {error && <ErrorNote error={error} />}
        {data && data.length === 0 && <p className="text-muted">{T.empty}</p>}
        {data && data.length > 0 && (
          <ul className="space-y-2">
            {data.map((b) => (
              <li
                key={b.id}
                className="flex items-center justify-between gap-3 rounded-inner bg-soft-2 px-4 py-3"
              >
                <div className="min-w-0">
                  <p className="font-bold tabular-nums">{formatDateTime(b.created_at)}</p>
                  <p className="text-small text-muted">{reasonLabel(b.reason)}</p>
                </div>
                <Button
                  tone="soft"
                  size="sm"
                  disabled={locked || busy}
                  title={locked ? T.busy : undefined}
                  onClick={() => setPending(b)}
                >
                  {T.restore}
                </Button>
              </li>
            ))}
          </ul>
        )}
        {locked && <p className="mt-3 text-small font-bold text-muted">{T.busy}</p>}
      </Dialog>
      {pending && (
        <ConfirmDialog
          title={T.confirmTitle}
          message={T.confirmMessage(formatDateTime(pending.created_at))}
          confirmLabel={busy ? T.restoring : T.restore}
          busy={busy}
          onCancel={() => setPending(null)}
          onConfirm={() => void restore(pending)}
        />
      )}
    </>
  );
}
