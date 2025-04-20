import { useState, useRef, useEffect } from 'react'
import { ChatUI } from './components/ChatUI'
import './App.css'
import React from 'react';

function App() {
  // Generate and store the user ID in format 'Human-<3 random characters>'
  const userId = useRef(`Human-${Math.random().toString(36).substring(2, 5)}`);
  const [currentTime, setCurrentTime] = useState(new Date().toLocaleTimeString());
  const [sessionValue] = useState(() => `CB-${Math.floor(Math.random() * 9000) + 1000}`);

  // Systemwide control handlers from ChatUI
  const systemControlRef = useRef({
    isConnected: false,
    handlePauseAll: () => { },
    handleresumeAll: () => { },
    handleDeregisterAll: () => { },
    handleReregisterAll: () => { },
    handleResetAllQueues: () => { },
  });

  // Update time every second
  useEffect(() => {
    const timer = setInterval(() => {
      setCurrentTime(new Date().toLocaleTimeString());
    }, 1000);

    return () => clearInterval(timer);
  }, []);

  return (
    <div className="app">
      <header>
        <div className="header-left">
          <div className="logo">
            <span className="logo-icon">⚙</span>
            <h1>COMMAND<span className="accent">HUB</span></h1>
          </div>
        </div>
        <div className="header-center">
          <div className="status-bar">
            <div className="status-pill">SYSTEM ACTIVE</div>
            <div className="status-time">{currentTime}</div>
          </div>
        </div>
        <div className="header-right">
          {/* Systemwide control icon buttons */}
          <div className="systemwide-controls-header">
            <button className="icon-btn" title="Pause All Agents" onClick={() => systemControlRef.current.handlePauseAll()} disabled={!systemControlRef.current.isConnected}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="6" y="4" width="4" height="16" /><rect x="14" y="4" width="4" height="16" /></svg>
            </button>
            <button className="icon-btn" title="resume All Agents" onClick={() => systemControlRef.current.handleresumeAll()} disabled={!systemControlRef.current.isConnected}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polygon points="5 3 19 12 5 21 5 3" /></svg>
            </button>
            <button className="icon-btn" title="Deregister All Agents" onClick={() => systemControlRef.current.handleDeregisterAll()} disabled={!systemControlRef.current.isConnected}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6L6 18" /><path d="M6 6l12 12" /></svg>
            </button>
            <button className="icon-btn" title="Reregister All Agents" onClick={() => systemControlRef.current.handleReregisterAll()} disabled={!systemControlRef.current.isConnected}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="1 4 1 10 7 10" /><polyline points="23 20 23 14 17 14" /><path d="M20.49 9A9 9 0 0 0 5.51 15M3.51 9A9 9 0 0 1 18.49 15" /></svg>
            </button>
            <button className="icon-btn" title="Reset All Queues & Restart" onClick={() => systemControlRef.current.handleResetAllQueues()} disabled={!systemControlRef.current.isConnected}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="1 4 1 10 7 10" /><polyline points="23 20 23 14 17 14" /><path d="M20.49 9A9 9 0 0 0 5.51 15M3.51 9A9 9 0 0 1 18.49 15" /><rect x="9" y="9" width="6" height="6" rx="1" /></svg>
            </button>
          </div>
          <div className="session-info">
            <div className="session-label">SESSION ID</div>
            <div className="session-value">{sessionValue}</div>
          </div>
          <div className="user-info">
            <div className="user-label">USER ID</div>
            <div className="user-value">{userId.current}</div>
          </div>
        </div>
      </header>
      <main>
        <ChatUI userId={userId.current} onSystemControl={systemControlRef.current} />
      </main>
      <style>{`
        .app {
          height: 100vh;
          display: flex;
          flex-direction: column;
          background-color: var(--color-background);
          position: relative;
          overflow: hidden;
        }
        
        /* Grid background overlay */
        .app::before {
          content: '';
          position: absolute;
          top: 0;
          left: 0;
          right: 0;
          bottom: 0;
          background-image: 
            linear-gradient(var(--grid-color) 1px, transparent 1px),
            linear-gradient(90deg, var(--grid-color) 1px, transparent 1px);
          background-size: var(--grid-size) var(--grid-size);
          pointer-events: none;
          z-index: -1;
        }

        header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 15px 20px;
          background-color: var(--color-surface-raised);
          border-bottom: 1px solid var(--color-border-strong);
          height: 70px;
          box-shadow: 0 2px 10px rgba(0, 0, 0, 0.2);
        }
        
        .header-left, .header-center, .header-right {
          display: flex;
          align-items: center;
        }
        
        .header-right {
          display: flex;
          gap: 20px;
        }
        
        .logo {
          display: flex;
          align-items: center;
          gap: 12px;
        }
        
        .logo-icon {
          font-size: 1.8rem;
          color: var(--color-primary);
        }
        
        h1 {
          margin: 0;
          font-size: 1.4rem;
          letter-spacing: 1px;
          font-weight: 700;
          color: var(--color-text);
        }
        
        .accent {
          color: var(--color-primary);
        }
        
        .status-bar {
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 4px;
        }
        
        .status-pill {
          background-color: var(--color-success);
          color: black;
          font-size: 0.7rem;
          font-weight: 700;
          padding: 3px 10px;
          border-radius: 12px;
          letter-spacing: 0.5px;
        }
        
        .status-time {
          font-family: monospace;
          font-size: 0.8rem;
          color: var(--color-text-secondary);
        }
        
        .systemwide-controls-header {
          display: flex;
          gap: 6px;
          margin-right: 18px;
        }

        .icon-btn {
          background: none;
          border: none;
          padding: 2px;
          margin: 0 1px;
          cursor: pointer;
          color: var(--color-text-secondary);
          border-radius: 3px;
          transition: background 0.15s;
          height: 28px;
          width: 28px;
          display: flex;
          align-items: center;
          justify-content: center;
        }

        .icon-btn:disabled {
          opacity: 0.4;
          cursor: not-allowed;
        }

        .icon-btn:hover:not(:disabled) {
          background: var(--color-surface-raised);
          color: var(--color-primary);
        }
        
        .session-info, .user-info {
          display: flex;
          flex-direction: column;
          align-items: flex-end;
          gap: 2px;
        }
        
        .session-label, .user-label {
          font-size: 0.65rem;
          color: var(--color-text-tertiary);
          letter-spacing: 0.5px;
        }
        
        .session-value, .user-value {
          font-family: monospace;
          font-size: 0.9rem;
          color: var(--color-primary);
          font-weight: 600;
        }
        
        .user-value {
          color: var(--color-accent);
        }

        main {
          flex: 1;
          display: flex;
          flex-direction: column;
          overflow: hidden;
          position: relative;
          min-height: 0; /* Required for Firefox */
          padding: 20px;
        }
      `}</style>
    </div>
  )
}

export default App
