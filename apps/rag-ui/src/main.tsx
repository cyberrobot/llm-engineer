import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './index.css';
import App from './App.tsx';
import { DebugProvider } from './components/DebugContext.tsx';
import AuthenticatedRagBoundary from './components/AuthenticatedRagBoundary.tsx';
import UserProvider from './components/UserProvider.tsx';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AuthenticatedRagBoundary>
      <DebugProvider>
        <UserProvider>
          <App />
        </UserProvider>
      </DebugProvider>
    </AuthenticatedRagBoundary>
  </StrictMode>,
);
