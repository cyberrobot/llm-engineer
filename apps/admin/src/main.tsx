import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { createBrowserRouter, RouterProvider } from 'react-router-dom';
import App from './App';
import { createAdminApi } from './api/adminApi';
import { AuthProvider } from './auth/AuthContext';
import { ConfigurationError } from './components/FullPageStatus';
import { readAdminConfig } from './config';
import './styles.css';
const config=readAdminConfig();
const application=config.ok
  ? <RouterProvider router={createBrowserRouter([{path:'*',element:<AuthProvider api={createAdminApi(config.apiBaseUrl)}><App/></AuthProvider>}])}/>
  : <ConfigurationError variable={config.variable} reason={config.reason}/>;
createRoot(document.getElementById('root')!).render(<StrictMode>{application}</StrictMode>);
