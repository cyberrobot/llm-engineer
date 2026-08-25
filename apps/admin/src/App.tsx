import { Link, Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { useAuth } from './auth/AuthContext';
import { AdminShell } from './components/AdminShell';
import { FullPageStatus } from './components/FullPageStatus';
import { LoginPage } from './components/LoginPage';
import { AssistantFormPage, AssistantsPage } from './features/assistants/Assistants';
import { AssistantBehaviourPage, AssistantPreviewPage } from './features/assistants/AssistantBehaviour';
import { DashboardPage } from './features/dashboard/Dashboard';
import { KnowledgeEntryPage, KnowledgeSourceCreatePage, KnowledgeSourceDetailPage, KnowledgeSourcesPage } from './features/knowledge-sources/KnowledgeSources';

function Protected() {
  const auth = useAuth();
  const location = useLocation();

  if (auth.state === 'loading') {
    return (
      <FullPageStatus
        title="Restoring your session"
        message="Checking your administrator session…"
      />
    );
  }
  if (auth.state === 'error') {
    return (
      <FullPageStatus
        title="Unable to restore your session"
        message="The backend could not be reached. Protected content remains hidden."
        action={{ label: 'Try again', onClick: auth.retry }}
      />
    );
  }
  if (auth.state === 'unauthenticated') {
    const returnTo = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`/login?returnTo=${returnTo}`} replace />;
  }
  return <AdminShell />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<Protected />}>
        <Route path="/admin" element={<DashboardPage />} />
        <Route
          path="/admin/assistants"
          element={<AssistantsPage />}
        />
        <Route path="/admin/assistants/new" element={<AssistantFormPage mode="create" />} />
        <Route path="/admin/assistants/:assistantId/edit" element={<AssistantFormPage mode="edit" />} />
        <Route path="/admin/assistants/:assistantId/behaviour" element={<AssistantBehaviourPage />} />
        <Route path="/admin/assistants/:assistantId/knowledge" element={<KnowledgeSourcesPage />} />
        <Route path="/admin/assistants/:assistantId/knowledge/new" element={<KnowledgeSourceCreatePage />} />
        <Route path="/admin/assistants/:assistantId/knowledge/:sourceId" element={<KnowledgeSourceDetailPage />} />
        <Route path="/admin/assistants/:assistantId/preview" element={<AssistantPreviewPage />} />
        <Route
          path="/admin/knowledge-sources"
          element={<KnowledgeEntryPage />}
        />
        <Route
          path="*"
          element={
            <section className="placeholder">
              <p>The page you requested could not be found.</p>
              <Link to="/admin">Return to dashboard</Link>
            </section>
          }
        />
      </Route>
      <Route path="/" element={<Navigate to="/admin" replace />} />
    </Routes>
  );
}
