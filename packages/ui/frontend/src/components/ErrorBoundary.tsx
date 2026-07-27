"use client";

import { Component, type ReactNode } from "react";

interface Props {
  children: ReactNode;
  /** Optional label shown in the fallback UI (e.g. "Graph View") */
  label?: string;
  /** Optional custom fallback renderer */
  fallback?: (error: Error, retry: () => void) => ReactNode;
}

interface State {
  error: Error | null;
}

/**
 * Generic React Error Boundary for wrapping specific UI sections.
 * Use this to isolate crashes so a broken panel doesn't take down the whole page.
 *
 * Usage:
 *   <ErrorBoundary label="World Graph">
 *     <GraphView />
 *   </ErrorBoundary>
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error(`[MONITOR] ErrorBoundary (${this.props.label ?? "unnamed"}):`, error, info.componentStack);
  }

  handleRetry = () => {
    this.setState({ error: null });
  };

  render() {
    if (this.state.error) {
      if (this.props.fallback) {
        return this.props.fallback(this.state.error, this.handleRetry);
      }

      return (
        <div className="rounded-xl border border-red-500/20 bg-red-500/5 p-6 text-center space-y-3">
          <div className="w-10 h-10 mx-auto rounded-full bg-red-500/10 border border-red-500/20 flex items-center justify-center">
            <svg
              className="w-5 h-5 text-red-400"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z"
              />
            </svg>
          </div>
          {this.props.label && (
            <p className="text-sm font-medium text-slate-300">{this.props.label}</p>
          )}
          <p className="text-xs text-slate-500">
            {this.state.error.message || "An unexpected error occurred"}
          </p>
          <button
            onClick={this.handleRetry}
            className="px-3 py-1.5 rounded-lg text-xs font-medium bg-cyan-500/15 text-cyan-400 border border-cyan-500/30 hover:bg-cyan-500/25 transition-all"
          >
            Retry
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}