import { lazy, Suspense } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import { AppShell } from '../components/AppShell';
import { AudioTab } from '../pages/AudioTab';
import { ComposePage } from '../pages/ComposePage';
import { ExportTab } from '../pages/ExportTab';
import { HomePage } from '../pages/HomePage';
import { PostvLayout } from '../pages/PostvLayout';
import { PostvPickPage } from '../pages/PostvPickPage';
import { PostvPreviewPage } from '../pages/PostvPreviewPage';
import { PostvScriptPage } from '../pages/PostvScriptPage';
import { PostvSoonPage } from '../pages/PostvSoonPage';
import { PostvSourcePage } from '../pages/PostvSourcePage';
import { ProjectsPage } from '../pages/ProjectsPage';
import { ScenesTab } from '../pages/ScenesTab';
import { SettingsPage } from '../pages/SettingsPage';

// Trang xem bộ thành phần: chỉ có khi `npm run dev`. Vite thay `import.meta.env.DEV` bằng
// `false` khi build nên cả nhánh này (và file trang) bị loại khỏi dist/.
const UiKit = import.meta.env.DEV ? lazy(() => import('../pages/Gallery')) : null;

export function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<HomePage />} />
        <Route path="projects" element={<ProjectsPage />} />
        <Route path="p/:slug" element={<ComposePage />}>
          <Route index element={<ScenesTab />} />
          <Route path="audio" element={<AudioTab />} />
          <Route path="export" element={<ExportTab />} />
        </Route>
        <Route path="postv" element={<ProjectsPage kind="postv" />} />
        <Route path="postv/:slug" element={<PostvLayout />}>
          <Route index element={<PostvSourcePage />} />
          <Route path="pick" element={<PostvPickPage />} />
          <Route path="script" element={<PostvScriptPage />} />
          <Route path="preview" element={<PostvPreviewPage />} />
          <Route path="export" element={<PostvSoonPage step={4} />} />
        </Route>
        <Route path="settings" element={<SettingsPage />} />
        {UiKit && (
          <Route
            path="dev/ui"
            element={
              <Suspense fallback={null}>
                <UiKit />
              </Suspense>
            }
          />
        )}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
