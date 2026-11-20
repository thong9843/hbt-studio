import { createContext, useContext } from 'react';
import type { ProjectKind } from '../api/types';

export interface NewProjectApi {
  /** Mở hộp "Video mới" (nút Tạo video ở thanh trái, nút trong màn trống). */
  open: (kind?: ProjectKind) => void;
}

export const NewProjectContext = createContext<NewProjectApi>({ open: () => {} });

export const useNewProject = () => useContext(NewProjectContext);
