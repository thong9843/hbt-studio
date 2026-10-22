import type { Scene } from '../api/types';

/** Cảnh trống để thêm vào video (khớp `Scene()` mặc định của backend). */
export const emptyScene = (): Scene => ({
  image: '',
  card: { y: 'top', lines: [] },
  labels: [],
  voice: '',
  punch: false,
  caption_y: null,
});
