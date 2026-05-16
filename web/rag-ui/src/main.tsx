import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './index.css';
import App from './App.tsx';
import { DebugProvider } from './components/DebugContext.tsx';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <DebugProvider>
      <App />
    </DebugProvider>
  </StrictMode>,
);
