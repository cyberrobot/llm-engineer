import type { Meta, StoryObj } from '@storybook/react-vite';
import type { ReactNode } from 'react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { AdminApiError, type AdminApi, type Administrator } from '../api/adminApi';
import { AuthProvider } from '../auth/AuthContext';
import { AdminShell } from './AdminShell';
import { ConfigurationError } from './FullPageStatus';
import { LoginPage } from './LoginPage';

const user: Administrator = {
  id: 'fictional-admin',
  email: 'admin@example.test',
  role: 'administrator',
};
const assistantMethods = {
  listAssistants: async () => ({ items: [], total: 0, limit: 50, offset: 0 }),
  getAssistant: async () => { throw new AdminApiError('not_found'); },
  createAssistant: async () => { throw new AdminApiError('invalid_request'); },
  updateAssistant: async () => { throw new AdminApiError('invalid_request'); },
  deleteAssistant: async () => undefined,
};

const authenticatedApi: AdminApi = {
  ...assistantMethods,
  currentUser: async () => user,
  login: async () => user,
  logout: async () => undefined,
};
const unauthenticatedApi: AdminApi = {
  ...assistantMethods,
  currentUser: async () => {
    throw new AdminApiError('unauthenticated');
  },
  login: async () => user,
  logout: async () => undefined,
};
const pendingApi: AdminApi = {
  ...assistantMethods,
  currentUser: () => new Promise<Administrator>(() => undefined),
  login: () => new Promise<Administrator>(() => undefined),
  logout: async () => undefined,
};
const restorationFailureApi: AdminApi = {
  ...assistantMethods,
  currentUser: async () => {
    throw new AdminApiError('network');
  },
  login: async () => user,
  logout: async () => undefined,
};
const invalidCredentialsApi: AdminApi = {
  ...unauthenticatedApi,
  login: async () => {
    throw new AdminApiError('invalid_credentials');
  },
};

const meta = { title: 'Foundation/States' } satisfies Meta;
export default meta;
type Story = StoryObj;

function Context({
  children,
  api,
  initialUser,
}: {
  children: ReactNode;
  api: AdminApi;
  initialUser?: Administrator;
}) {
  return (
    <MemoryRouter>
      <AuthProvider api={api} initialUser={initialUser}>
        {children}
      </AuthProvider>
    </MemoryRouter>
  );
}

export const SessionRestorationLoading: Story = {
  render: () => (
    <Context api={pendingApi}>
      <LoginPage />
    </Context>
  ),
};
export const SessionRestorationFailure: Story = {
  render: () => (
    <Context api={restorationFailureApi}>
      <LoginPage />
    </Context>
  ),
};
export const InvalidConfiguration: Story = {
  render: () => (
    <Context api={unauthenticatedApi}>
      <ConfigurationError variable="VITE_ADMIN_API_BASE_URL" reason="missing" />
    </Context>
  ),
};
export const LoginDefault: Story = {
  render: () => (
    <Context api={unauthenticatedApi}>
      <LoginPage />
    </Context>
  ),
};
export const LoginPending: Story = {
  render: () => (
    <Context api={unauthenticatedApi}>
      <LoginPage forcedPending />
    </Context>
  ),
};
export const LoginInvalidCredentials: Story = {
  render: () => (
    <Context api={invalidCredentialsApi}>
      <LoginPage forcedError="The email or password is invalid." />
    </Context>
  ),
};

function Shell() {
  return (
    <Context api={authenticatedApi} initialUser={user}>
      <Routes>
        <Route element={<AdminShell />}>
          <Route
            path="*"
            element={
              <section className="placeholder">
                <p>Dashboard functionality is not implemented yet.</p>
              </section>
            }
          />
        </Route>
      </Routes>
    </Context>
  );
}

export const ShellDesktopAuthenticated: Story = { render: () => <Shell /> };
export const ShellMobileAuthenticated: Story = {
  render: () => (
    <div className="stories-mobile">
      <Shell />
    </div>
  ),
};
