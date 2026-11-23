import { Component, type ErrorInfo, type ReactNode } from 'react';
import { isRouteErrorResponse, useRouteError } from 'react-router-dom';
import { Button } from './ui/Button';

function FallbackView({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex min-h-[60vh] items-center justify-center p-6">
      <div className="max-w-md space-y-4 rounded-card border border-line bg-card p-6 text-center shadow-card">
        <h1 className="text-title font-extrabold text-text">Đã xảy ra lỗi hiển thị</h1>
        <p className="rounded-inner bg-danger-soft p-3 text-small font-medium text-danger">
          {message}
        </p>
        <div className="flex flex-wrap justify-center gap-3 pt-1">
          <Button
            tone="primary"
            onClick={() => {
              if (onRetry) onRetry();
              else window.location.reload();
            }}
          >
            Thử lại
          </Button>
          <Button
            tone="soft"
            onClick={() => {
              window.location.assign('/');
            }}
          >
            Về Trang chủ
          </Button>
        </div>
      </div>
    </div>
  );
}

export function RouteErrorFallback() {
  const err = useRouteError();
  let msg = 'Không thể tải trang này. Vui lòng thử lại.';
  if (isRouteErrorResponse(err)) {
    msg = `${err.status} ${err.statusText || msg}`;
  } else if (err instanceof Error) {
    msg = err.message;
  }
  return <FallbackView message={msg} />;
}

export class AppErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state: { error: Error | null } = { error: null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('AppErrorBoundary:', error, info);
  }

  render() {
    if (this.state.error) {
      return (
        <FallbackView
          message={this.state.error.message || 'Lỗi không xác định'}
          onRetry={() => this.setState({ error: null })}
        />
      );
    }
    return this.props.children;
  }
}
