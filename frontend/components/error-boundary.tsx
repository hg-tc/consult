"use client"

import React from "react"

interface ErrorBoundaryProps {
  children: React.ReactNode
  fallback?: React.ReactNode
}

interface ErrorBoundaryState {
  hasError: boolean
  error?: Error
  errorInfo?: React.ErrorInfo
}

export class ErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props)
    this.state = { hasError: false }
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error("[v0] ErrorBoundary caught an error:", error, errorInfo)
    this.setState({ errorInfo })
  }

  private handleRetry = () => {
    this.setState({ hasError: false, error: undefined, errorInfo: undefined })
  }

  render() {
    if (this.state.hasError) {
      return this.props.fallback || (
        <div className="flex items-center justify-center py-12">
          <div className="text-center text-destructive max-w-md">
            <div className="mb-4">
              <svg className="w-12 h-12 mx-auto mb-3 text-destructive/60" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L3.732 16.5c-.77.833.192 2.5 1.732 2.5z" />
              </svg>
            </div>
            <h3 className="text-lg font-semibold mb-2">组件加载失败</h3>
            <p className="text-sm text-muted-foreground mb-4">
              页面组件遇到了错误，请尝试刷新页面或重试
            </p>
            {process.env.NODE_ENV === 'development' && this.state.error && (
              <details className="text-left text-xs text-muted-foreground mb-4 p-3 bg-muted rounded">
                <summary className="cursor-pointer font-medium">错误详情</summary>
                <div className="mt-2">
                  <p><strong>错误:</strong> {this.state.error.message}</p>
                  {this.state.errorInfo && (
                    <p><strong>组件栈:</strong></p>
                  )}
                  <pre className="whitespace-pre-wrap text-xs">
                    {this.state.errorInfo?.componentStack}
                  </pre>
                </div>
              </details>
            )}
            <div className="flex gap-2 justify-center">
              <button
                onClick={this.handleRetry}
                className="px-4 py-2 bg-primary text-primary-foreground rounded-md hover:bg-primary/90 transition-colors"
              >
                重试
              </button>
              <button
                onClick={() => window.location.reload()}
                className="px-4 py-2 bg-secondary text-secondary-foreground rounded-md hover:bg-secondary/90 transition-colors"
              >
                刷新页面
              </button>
            </div>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}
