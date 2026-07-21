import { Component, type ErrorInfo, type ReactNode } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";

interface HeorReviewBoundaryProps {
  children: ReactNode;
  title: string;
  body: string;
  retryLabel: string;
  onRetry: () => void;
}

interface HeorReviewBoundaryState {
  failed: boolean;
}

/** Keep a malformed or partially migrated research artifact from replacing the
 * whole desktop workspace with React Router's developer error screen. The
 * underlying artifact remains untouched and can be retried after repair. */
export class HeorReviewBoundary extends Component<
  HeorReviewBoundaryProps,
  HeorReviewBoundaryState
> {
  state: HeorReviewBoundaryState = { failed: false };

  static getDerivedStateFromError(): HeorReviewBoundaryState {
    return { failed: true };
  }

  componentDidCatch(_error: Error, _info: ErrorInfo): void {
    // The researcher-facing pane deliberately does not display stack traces or
    // development logs. Native diagnostics remain available to developers.
  }

  private retry = () => {
    this.setState({ failed: false });
    this.props.onRetry();
  };

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <div className="flex h-full flex-col border-l border-border bg-surface">
        <div className="m-5 rounded-card border border-border bg-bg p-5">
          <div className="flex items-start gap-3">
            <AlertTriangle size={18} className="mt-0.5 shrink-0 text-warn" aria-hidden />
            <div className="min-w-0">
              <h2 className="text-sm font-medium text-text">{this.props.title}</h2>
              <p className="mt-1 text-sm leading-6 text-muted">{this.props.body}</p>
              <button
                type="button"
                className="mt-4 inline-flex items-center gap-1.5 rounded-input border border-border bg-surface px-3 py-1.5 text-sm text-text hover:bg-surface-2"
                onClick={this.retry}
              >
                <RefreshCw size={14} aria-hidden />
                {this.props.retryLabel}
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }
}
