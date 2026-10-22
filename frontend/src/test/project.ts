import type { Project, Scene } from '../api/types';

export const scene = (over: Partial<Scene> = {}): Scene => ({
  image: '',
  card: { y: 'top', lines: [{ text: 'Tiêu đề', size: 'l', color: 'ink' }] },
  labels: [],
  voice: 'Lời đọc.',
  punch: false,
  caption_y: null,
  ...over,
});

export const project = (over: Partial<Project> = {}): Project => ({
  version: 1,
  slug: 'muoi',
  title: 'Muỗi',
  series: '',
  theme: { primary: '#146268', accent: '#DE5C48' },
  voice: null,
  music: null,
  settings: { fps: 50, captions: true, aligner: 'auto', sfx_on_punch: true, outro: true },
  scenes: [
    scene({ image: 'images/scene-01.png' }),
    scene({ image: 'images/scene-02.png' }),
    scene(),
  ],
  publish: { hook: '', hashtags: [] },
  thumbnail: null,
  ...over,
});
