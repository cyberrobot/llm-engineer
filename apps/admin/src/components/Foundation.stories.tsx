import type { Meta, StoryObj } from '@storybook/react-vite';
import { MemoryRouter, Outlet, Route, Routes } from 'react-router-dom';
import { createAdminApi } from '../api/adminApi';
import { AuthProvider } from '../auth/AuthContext';
import { AdminShell } from './AdminShell';
import { ConfigurationError, FullPageStatus } from './FullPageStatus';
import { LoginPage } from './LoginPage';
const user={id:'fictional-admin',email:'admin@example.test',role:'administrator' as const};
const api=createAdminApi('https://api.example.test');
const meta={title:'Foundation/States'} satisfies Meta;export default meta;type Story=StoryObj;
function Context({children,authenticated=false}:{children:React.ReactNode;authenticated?:boolean}){return <MemoryRouter><AuthProvider api={api} initialUser={authenticated?user:undefined}>{children}</AuthProvider></MemoryRouter>}
export const Loading:Story={render:()=> <FullPageStatus title="Restoring your session" message="Checking your administrator session…"/>};
export const RestorationFailure:Story={render:()=> <FullPageStatus title="Unable to restore your session" message="The backend could not be reached. Protected content remains hidden." action={{label:'Try again',onClick:()=>{}}}/>};
export const ConfigError:Story={render:()=> <ConfigurationError variable="VITE_ADMIN_API_BASE_URL" reason="missing"/>};
export const LoginDefault:Story={render:()=> <Context><LoginPage/></Context>};
export const LoginSubmitting:Story={render:()=> <Context><LoginPage forcedPending/></Context>};
export const LoginError:Story={render:()=> <Context><LoginPage forcedError="The email or password is invalid."/></Context>};
function Shell(){return <Context authenticated><Routes><Route element={<AdminShell storyUser={user}/>}><Route path="*" element={<section className="placeholder"><p>Dashboard functionality is not implemented yet.</p><Outlet/></section>}/></Route></Routes></Context>}
export const ShellDesktop:Story={render:()=> <Shell/>};
export const ShellMobile:Story={render:()=> <div className="stories-mobile"><Shell/></div>};
