import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { AdminApiError, type AdminApi, type Administrator } from '../api/adminApi';

type State = 'loading'|'authenticated'|'unauthenticated'|'error';
type AuthValue = { state: State; user: Administrator|null; login(email:string,password:string):Promise<void>; logout():Promise<void>; retry():void };
const AuthContext = createContext<AuthValue|null>(null);

export function AuthProvider({ api, children, initialUser }: { api: AdminApi; children: ReactNode; initialUser?: Administrator }) {
  const [state,setState]=useState<State>(initialUser?'authenticated':'loading');
  const [user,setUser]=useState<Administrator|null>(initialUser??null);
  const [attempt,setAttempt]=useState(0);
  useEffect(()=>{ if(initialUser) return; const controller=new AbortController(); api.currentUser(controller.signal).then(value=>{setUser(value);setState('authenticated')}).catch(error=>{if(error instanceof DOMException&&error.name==='AbortError')return;setUser(null);setState(error instanceof AdminApiError&&error.kind==='unauthenticated'?'unauthenticated':'error')}); return ()=>controller.abort(); },[api,attempt,initialUser]);
  const login=useCallback(async(email:string,password:string)=>{const value=await api.login(email,password);setUser(value);setState('authenticated')},[api]);
  const logout=useCallback(async()=>{try{await api.logout()}catch(error){if(!(error instanceof AdminApiError&&error.kind==='unauthenticated'))throw error}finally{setUser(null);setState('unauthenticated')}},[api]);
  const value=useMemo(()=>({state,user,login,logout,retry:()=>{setState('loading');setAttempt(value=>value+1)}}),[state,user,login,logout]);
  return <AuthContext value={value}>{children}</AuthContext>;
}
// Context and its hook intentionally share this small provider module.
// eslint-disable-next-line react-refresh/only-export-components
export function useAuth(){const value=useContext(AuthContext);if(!value)throw new Error('AuthProvider is required');return value}
