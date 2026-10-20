import { HealthStatus } from '../components/HealthStatus';
import { vi } from '../i18n/vi';

export function App() {
  return (
    <div className="min-h-screen">
      <header className="px-6 py-5">
        {/* Logo từ brand/ gắn ở M3 (IMPLEMENT.md mục 10.1). */}
        <span className="text-xl font-extrabold uppercase tracking-tight">{vi.appName}</span>
      </header>
      <main className="mx-auto max-w-3xl px-6 py-16">
        <h1 className="text-5xl font-extrabold uppercase leading-none tracking-tight">
          {vi.appName}
        </h1>
        <div className="mt-12">
          <HealthStatus />
        </div>
      </main>
    </div>
  );
}
