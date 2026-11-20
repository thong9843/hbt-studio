import { useMutation } from '@tanstack/react-query';
import { useState } from 'react';
import { api } from '../../api/endpoints';
import { usePostvEditor } from '../../hooks/postvEditor';
import { vi } from '../../i18n/vi';
import { MusicCardView } from '../audio/MusicCard';
import { ConfirmDialog } from '../ConfirmDialog';
import { ErrorNote } from '../ErrorNote';

const T = vi.audio.music;

/** Thẻ Nhạc nền của PostV: cùng thẻ với video HBT, nối vào trình soạn PostV. */
export function PostvMusicCard() {
  const { project, update, flush } = usePostvEditor();
  const [confirmingRemove, setConfirmingRemove] = useState(false);

  const removeMutation = useMutation({
    mutationFn: () => api.deletePostvMusic(project.slug),
    onSuccess: () => {
      update((p) => ({ ...p, music: null }));
      setConfirmingRemove(false);
    },
  });

  return (
    <>
      <MusicCardView
        host={{
          slug: project.slug,
          music: project.music,
          setMusic: (music) => update((p) => ({ ...p, music })),
          applyMusic: (music) => update((p) => ({ ...p, music })),
          flush,
          onRemoveAsset: () => setConfirmingRemove(true),
          isRemovingAsset: removeMutation.isPending,
        }}
      />
      <ErrorNote error={removeMutation.error} />
      {confirmingRemove && (
        <ConfirmDialog
          title={T.removeConfirmTitle}
          message={T.removeConfirmMessage}
          confirmLabel={T.remove}
          danger
          busy={removeMutation.isPending}
          onConfirm={() => removeMutation.mutate()}
          onCancel={() => !removeMutation.isPending && setConfirmingRemove(false)}
        />
      )}
    </>
  );
}
