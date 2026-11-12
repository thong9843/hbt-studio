import { useState, type ReactNode } from 'react';
import type { HbtCoreSegment, HbtCoreTopic } from '../../api/types';
import { SAMPLE_V1_SCRIPT, StudioWorkspaceContext } from '../../hooks/studioWorkspace';

/**
 * Provider lưu giữ trạng thái nháp của HBT Core Studio ở cấp AppLayout.
 * Giúp chuyển qua lại giữa Trang chủ, HBT Core, PostV, Chatting, Cài đặt mà không mất dữ liệu đang nhập.
 */
export function StudioWorkspaceProvider({ children }: { children: ReactNode }) {
  const [mode, setMode] = useState<'v1' | 'v2'>('v1');
  const [title, setTitle] = useState(SAMPLE_V1_SCRIPT.title);
  const [topic, setTopic] = useState<HbtCoreTopic>('history');
  const [segments, setSegments] = useState<HbtCoreSegment[]>(SAMPLE_V1_SCRIPT.segments);
  const [jsonText, setJsonText] = useState(() => JSON.stringify(SAMPLE_V1_SCRIPT, null, 2));
  const [prompt, setPrompt] = useState('');
  const [v2Topic, setV2Topic] = useState<HbtCoreTopic>('history');
  const [selectedModel, setSelectedModel] = useState('gemini-3.8-flash');
  const [fallbackNotice, setFallbackNotice] = useState<string | null>(null);
  const [resultVideoUrl, setResultVideoUrl] = useState<string | null>(null);
  const [resultSlug, setResultSlug] = useState<string | null>(null);

  return (
    <StudioWorkspaceContext.Provider
      value={{
        mode,
        setMode,
        title,
        setTitle,
        topic,
        setTopic,
        segments,
        setSegments,
        jsonText,
        setJsonText,
        prompt,
        setPrompt,
        v2Topic,
        setV2Topic,
        selectedModel,
        setSelectedModel,
        fallbackNotice,
        setFallbackNotice,
        resultVideoUrl,
        setResultVideoUrl,
        resultSlug,
        setResultSlug,
      }}
    >
      {children}
    </StudioWorkspaceContext.Provider>
  );
}
