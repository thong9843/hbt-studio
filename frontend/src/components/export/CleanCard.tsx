import { useMutation } from '@tanstack/react-query';
import { useState } from 'react';
import { api } from '../../api/endpoints';
import { useToast } from '../../hooks/toast';
import { vi } from '../../i18n/vi';
import { formatBytes } from '../../utils/format';
import { ConfirmDialog } from '../ConfirmDialog';
import { Button } from '../ui/Button';
import { Card } from '../ui/Card';

const C = vi.export.clean;

/** Dọn file tạm trong build/ (hỏi xác nhận, báo dung lượng đã giải phóng, khoá khi đang dựng). */
export function CleanCard({ slug, disabled }: { slug: string; disabled: boolean }) {
  const toast = useToast();
  const [confirming, setConfirming] = useState(false);
  const clean = useMutation({
    mutationFn: () => api.cleanBuild(slug),
    onSuccess: (r) => {
      setConfirming(false);
      toast.info(C.done(formatBytes(r.freed_bytes)));
    },
    onError: (e) => {
      setConfirming(false);
      toast.error(e);
    },
  });
  return (
    <Card as="section" aria-label={C.title} className="space-y-3">
      <h2 className="text-h2 font-bold">{C.title}</h2>
      <p className="text-small text-muted">{C.help}</p>
      <Button
        tone="soft"
        disabled={disabled || clean.isPending}
        onClick={() => setConfirming(true)}
      >
        {C.button}
      </Button>
      {confirming && (
        <ConfirmDialog
          title={C.confirmTitle}
          message={C.confirmMessage}
          confirmLabel={clean.isPending ? C.busy : C.confirm}
          busy={clean.isPending}
          onConfirm={() => clean.mutate()}
          onCancel={() => setConfirming(false)}
        />
      )}
    </Card>
  );
}
