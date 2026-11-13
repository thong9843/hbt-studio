import { Navigate, Route, Routes } from 'react-router-dom';
import { AppLayout } from '../components/layout/AppLayout';
import { AssetHubPage } from '../pages/AssetHubPage';
import { AudioTab } from '../pages/AudioTab';
import { ComposePage } from '../pages/ComposePage';
import { ExportTab } from '../pages/ExportTab';
import { HbtCorePage } from '../pages/HbtCorePage';
import { HomePage } from '../pages/HomePage';
import { PostvLayout } from '../pages/PostvLayout';
import { PostvPickPage } from '../pages/PostvPickPage';
import { PostvPreviewPage } from '../pages/PostvPreviewPage';
import { PostvQuickPage } from '../pages/PostvQuickPage';
import { PostvScriptPage } from '../pages/PostvScriptPage';
import { PostvExportPage } from '../pages/PostvExportPage';
import { PostvSourcePage } from '../pages/PostvSourcePage';
import { ProjectsPage } from '../pages/ProjectsPage';
import { ImagesTab } from '../pages/ImagesTab';
import { ScenesTab } from '../pages/ScenesTab';
import { SettingsPage } from '../pages/SettingsPage';
import { ChattingHome } from '../pages/chatting/ChattingHome';
import { ChattingEditor } from '../pages/chatting/ChattingEditor';

export function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<HomePage />} />
        <Route path="core" element={<HbtCorePage />} />
        <Route path="projects" element={<ProjectsPage />} />
        <Route path="p/:slug" element={<ComposePage />}>
          <Route index element={<ScenesTab />} />
          <Route path="images" element={<ImagesTab />} />
          <Route path="audio" element={<AudioTab />} />
          <Route path="export" element={<ExportTab />} />
        </Route>
        <Route path="postv" element={<PostvQuickPage />} />
        <Route path="postv/projects" element={<ProjectsPage kind="postv" />} />
        <Route path="postv/:slug" element={<PostvLayout />}>
          <Route index element={<PostvSourcePage />} />
          <Route path="pick" element={<PostvPickPage />} />
          <Route path="script" element={<PostvScriptPage />} />
          <Route path="preview" element={<PostvPreviewPage />} />
          <Route path="export" element={<PostvExportPage />} />
        </Route>
        <Route path="chatting" element={<ChattingHome />} />
        <Route path="chatting/:slug" element={<ChattingEditor />} />
        <Route path="library" element={<AssetHubPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
