import { Navigate, Route, Routes } from 'react-router-dom';
import { AppShell } from '../components/AppShell';
import { AudioTab } from '../pages/AudioTab';
import { ComposePage } from '../pages/ComposePage';
import { ExportTab } from '../pages/ExportTab';
import { ProjectsPage } from '../pages/ProjectsPage';
import { ScenesTab } from '../pages/ScenesTab';
import { SettingsPage } from '../pages/SettingsPage';

export function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<ProjectsPage />} />
        <Route path="p/:slug" element={<ComposePage />}>
          <Route index element={<ScenesTab />} />
          <Route path="audio" element={<AudioTab />} />
          <Route path="export" element={<ExportTab />} />
        </Route>
        <Route path="settings" element={<SettingsPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
