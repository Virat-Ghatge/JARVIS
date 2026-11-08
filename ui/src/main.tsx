import React, { Component, ErrorInfo, ReactNode } from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './styles/hud.css';

interface ErrorBoundaryProps {
  children: ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('[HUD Error Boundary caught error]:', error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="h-screen w-screen bg-[#07111F] text-[#4DA3FF] flex flex-col items-center justify-center p-6 font-mono select-none">
          <div className="max-w-md w-full bg-[#0F2039] border border-[#FF3B5C]/50 rounded-lg p-6 space-y-4 shadow-lg shadow-[#FF3B5C]/20">
            <div className="flex items-center space-x-2 text-[#FF3B5C]">
              <span className="text-xl font-bold font-hud">SYSTEM ALERT: HUD RECOVERY</span>
            </div>
            <p className="text-xs text-gray-300">
              An unexpected interface rendering issue was intercepted. The core subsystems remain active in the background.
            </p>
            {this.state.error && (
              <pre className="bg-[#07111F] border border-[#1C3B62] p-3 rounded text-[11px] text-[#FF8A1F] overflow-x-auto whitespace-pre-wrap">
                {this.state.error.message}
              </pre>
            )}
            <button
              onClick={() => {
                this.setState({ hasError: false, error: null });
                window.location.reload();
              }}
              className="w-full py-2 bg-[#4DA3FF]/20 hover:bg-[#4DA3FF]/30 border border-[#4DA3FF] text-[#4DA3FF] text-xs font-bold uppercase rounded transition-all tracking-wider font-hud"
            >
              Reinitialize Holographic Interface
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
  <React.StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </React.StrictMode>
);
