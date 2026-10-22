import { createContext, useContext } from 'react';
import type { Project } from '../api/types';
import type { SaveStatus } from './useAutosave';

export interface ProjectEditor {
  project: Project;
  /** Sửa trên máy rồi tự lưu sau 1 s. */
  update: (fn: (p: Project) => Project) => void;
  /** Áp kết quả máy chủ đã lưu sẵn (tải file, nhạc thư viện…): không hẹn lưu thêm. */
  applyServer: (fn: (p: Project) => Project) => void;
  /** Lưu ngay những gì đang chờ (gọi trước khi tải file hoặc dựng). */
  flush: () => Promise<void>;
  status: SaveStatus;
  saveError: string | null;
  /** Tăng sau mỗi lần lưu thành công — để chạy lại kiểm tra lint. */
  savedCount: number;
  /** Tăng khi ảnh trong thư mục project đổi — để làm mới ảnh thu nhỏ. */
  imageVersion: number;
  bumpImages: () => void;
  /** Đổi thứ tự cảnh qua API và nạp lại project. */
  reorder: (order: number[]) => Promise<void>;
  /** Xoá cảnh qua API và nạp lại project. */
  deleteScene: (sceneIndex: number) => Promise<void>;
  /** Tải ảnh cho cảnh `sceneIndex` (từ 0). */
  uploadImage: (sceneIndex: number, file: File) => Promise<void>;
}

export const ProjectEditorContext = createContext<ProjectEditor | null>(null);

export function useProjectEditor(): ProjectEditor {
  const ctx = useContext(ProjectEditorContext);
  if (!ctx) throw new Error('useProjectEditor phải nằm trong ComposePage');
  return ctx;
}
