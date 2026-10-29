import { usePostvEditor } from '../../hooks/postvEditor';
import { MusicCardView } from '../audio/MusicCard';

/** Thẻ Nhạc nền của PostV: cùng thẻ với video HBT, nối vào trình soạn PostV. */
export function PostvMusicCard() {
  const { project, update, flush } = usePostvEditor();
  return (
    <MusicCardView
      host={{
        slug: project.slug,
        music: project.music,
        setMusic: (music) => update((p) => ({ ...p, music })),
        applyMusic: (music) => update((p) => ({ ...p, music })),
        flush,
      }}
    />
  );
}
