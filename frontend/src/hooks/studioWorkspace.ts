import { createContext, useContext } from 'react';
import type { HbtCoreScript, HbtCoreSegment, HbtCoreTopic } from '../api/types';

export const SAMPLE_V1_SCRIPT: HbtCoreScript = {
  title: 'Vì sao Đấu trường La Mã vẫn đứng vững sau 2000 năm?',
  topic: 'history',
  total_segments: 3,
  segments: [
    {
      id: 1,
      order: 1,
      title: 'BÍ MẬT ĐẤU TRƯỜNG LA MÃ',
      text: 'Bạn có biết vì sao Đấu trường La Mã trải qua hàng chục trận động đất mà vẫn hiên ngang suốt hai thiên niên kỷ?',
      sticker: 'shock',
      image_prompt:
        'Cinematic shot of ancient Roman Colosseum under dramatic golden hour sunlight, ultra realistic, highly detailed historical atmosphere, 9:16 vertical framing',
      image: 'scene-01.png',
      sfx: 'impact',
    },
    {
      id: 2,
      order: 2,
      title: 'BÊ TÔNG TỰ LIỀN VẾT NỨT',
      text: 'Nhưng khoan đã, bí mật thực sự nằm ở loại bê tông tro núi lửa Pozzolana kết hợp với vôi sống tự liền vết nứt khi gặp nước mưa.',
      sticker: 'think',
      image_prompt:
        'Close-up cinematic shot of ancient Roman pozzolanic volcanic ash concrete texture with subtle golden light rays, photorealistic, 9:16 vertical framing',
      image: 'scene-02.png',
      sfx: 'pop',
    },
    {
      id: 3,
      order: 3,
      title: 'THEO DÕI HAY BIẾT TỐT',
      text: 'Theo bạn công trình cổ đại nào bền bỉ nhất? Hãy bình luận bên dưới và theo dõi Hay Biết Tốt trên TikTok và YouTube nhé!',
      sticker: 'question',
      image_prompt:
        'Wide aerial twilight shot of illuminated Roman Colosseum with starry sky, epic atmosphere, ultra detailed, 9:16 vertical framing',
      image: 'scene-03.png',
      sfx: 'whoosh',
    },
  ],
};

export interface StudioWorkspaceDraft {
  mode: 'v1' | 'v2';
  setMode: (mode: 'v1' | 'v2') => void;
  title: string;
  setTitle: (title: string) => void;
  topic: HbtCoreTopic;
  setTopic: (topic: HbtCoreTopic) => void;
  segments: HbtCoreSegment[];
  setSegments: (segments: HbtCoreSegment[]) => void;
  jsonText: string;
  setJsonText: (jsonText: string) => void;
  prompt: string;
  setPrompt: (prompt: string) => void;
  v2Topic: HbtCoreTopic;
  setV2Topic: (topic: HbtCoreTopic) => void;
  selectedModel: string;
  setSelectedModel: (model: string) => void;
  fallbackNotice: string | null;
  setFallbackNotice: (notice: string | null) => void;
  resultVideoUrl: string | null;
  setResultVideoUrl: (url: string | null) => void;
  resultSlug: string | null;
  setResultSlug: (slug: string | null) => void;
}

export const StudioWorkspaceContext = createContext<StudioWorkspaceDraft | null>(null);

export function useStudioWorkspace(): StudioWorkspaceDraft | null {
  return useContext(StudioWorkspaceContext);
}
