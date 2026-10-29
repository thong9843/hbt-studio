import { createContext, useContext } from 'react';
import type { PostvProject } from '../api/types';
import type { SaveStatus } from './useAutosave';

export interface PostvEditor {
  project: PostvProject;
  /** Sửa trên máy rồi tự lưu sau 1 s. */
  update: (fn: (p: PostvProject) => PostvProject) => void;
  /** Lưu ngay những gì đang chờ. */
  flush: () => Promise<void>;
  status: SaveStatus;
  saveError: string | null;
  /** Tăng sau mỗi lần lưu thành công, để chạy lại kiểm tra kịch bản. */
  savedCount: number;
}

export const PostvEditorContext = createContext<PostvEditor | null>(null);

export function usePostvEditor(): PostvEditor {
  const ctx = useContext(PostvEditorContext);
  if (!ctx) throw new Error('usePostvEditor phải nằm trong PostvLayout');
  return ctx;
}
