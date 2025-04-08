import { useState, useRef, useEffect } from 'react'
import { ChatUI } from './components/ChatUI'
import './App.css'

function App() {
  // Generate and store the user ID in format 'Human-<3 random characters>'
  const userId = useRef(`Human-${Math.random().toString(36).substring(2, 5)}`);
  const [currentTime, setCurrentTime] = useState(new Date().toLocaleTimeString());
  const [sessionValue] = useState(() => `CB-${Math.floor(Math.random() * 9000) + 1000}`);
  
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
        <ChatUI userId={userId.current} />
      </main>
      <style>{`
        .app {
          min-height: 100vh;
          display: flex;
          flex-direction: column;
          background-color: var(--color-background);
          position: relative;
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
          padding: 15px 25px;
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
          justify-content: center;
          padding: 0 0 20px;
          margin: 0;
          max-width: none;
          width: 100%;
          overflow: auto;
        }
      `}</style>
    </div>
  )
}

export default App
