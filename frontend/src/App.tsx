import { Chat } from './components/Chat'

function App() {
  return (
    <div className="app">
      <header>
        <h1>WebSocket Chat</h1>
      </header>
      <main>
        <Chat />
      </main>
      <style>{`
        .app {
          min-height: 100vh;
          background-color: #f0f2f5;
          padding: 20px;
        }

        header {
          text-align: center;
          margin-bottom: 30px;
        }

        h1 {
          color: #1a1a1a;
          margin: 0;
          font-size: 2.5rem;
        }

        main {
          max-width: 800px;
          margin: 0 auto;
        }
      `}</style>
    </div>
  )
}

export default App
