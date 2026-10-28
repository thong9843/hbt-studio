import { createContext, useContext } from 'react';

export interface NewProjectApi {
  /** Mở hộp "Video mới" (nút Tạo video ở thanh trái, nút trong màn trống). */
  open: () => void;
}

export const NewProjectContext = createContext<NewProjectApi>({ open: () => {} });

export const useNewProject = () => useContext(NewProjectContext);
