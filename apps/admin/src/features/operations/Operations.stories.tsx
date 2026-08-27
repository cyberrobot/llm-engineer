import type { Meta, StoryObj } from '@storybook/react-vite';
import { MemoryRouter } from 'react-router-dom';
import { expect, userEvent, within } from 'storybook/test';
import { AdminApiError, createAdminApi, type AdminApi } from '../../api/adminApi';
import { AuthProvider } from '../../auth/AuthContext';
import { AuditPage, OperationalJobsPage, OperationsCachePage, OperationsHealthPage, OperationsMaintenancePage, OperationsPage } from './Operations';

const timestamp='2026-08-25T10:00:00Z';
const region={name:'assistant',entries:24,estimatedMemoryBytes:4096,hitCount:90,missCount:10,hitRatio:.9};
function apiWith(overrides:Partial<AdminApi>={}):AdminApi{return{...createAdminApi(''),getOperations:async()=>({generatedAt:timestamp,service:'operations',status:'available',capabilities:['health','cache','maintenance','jobs','audit']}),getOperationsHealth:async()=>({generatedAt:timestamp,status:'healthy',checks:[{name:'postgres',status:'healthy',required:true,latencyMs:5,code:null,checkedAt:timestamp}]}),listCacheRegions:async()=>[region],getMaintenance:async()=>({enabled:true,message:'Planned maintenance',updatedAt:timestamp,updatedBy:'admin@example.test',requestId:null,correlationId:null}),listOperationalJobs:async()=>({items:[],total:0,limit:50,offset:0}),listAuditEntries:async()=>({items:[],total:0,limit:50,offset:0}),...overrides}}
function Frame({api,children}:{api:AdminApi;children:React.ReactNode}){return <MemoryRouter><AuthProvider api={api} initialUser={{id:'admin',email:'admin@example.test',role:'administrator'}}>{children}</AuthProvider></MemoryRouter>}
const meta={title:'Operations/Detailed operations'} satisfies Meta;export default meta;type Story=StoryObj;
export const Landing:Story={render:()=> <Frame api={apiWith()}><OperationsPage/></Frame>};
export const Healthy:Story={render:()=> <Frame api={apiWith()}><OperationsHealthPage/></Frame>};
export const Degraded:Story={render:()=> <Frame api={apiWith({getOperationsHealth:async()=>({generatedAt:timestamp,status:'degraded',checks:[{name:'redis',status:'unhealthy',required:false,latencyMs:100,code:'dependency_timeout',checkedAt:timestamp}]})})}><OperationsHealthPage/></Frame>};
export const CachePopulated:Story={render:()=> <Frame api={apiWith()}><OperationsCachePage/></Frame>};
export const CacheEmpty:Story={render:()=> <Frame api={apiWith({listCacheRegions:async()=>[]})}><OperationsCachePage/></Frame>};
export const MaintenanceEnabled:Story={render:()=> <Frame api={apiWith()}><OperationsMaintenancePage/></Frame>};
export const JobsEmpty:Story={render:()=> <Frame api={apiWith()}><OperationalJobsPage/></Frame>};
export const JobsPopulated:Story={render:()=> <Frame api={apiWith({listOperationalJobs:async()=>({items:[{id:'11111111-1111-4111-8111-111111111111',status:'running',createdAt:timestamp,startedAt:timestamp,completedAt:null,durationMs:null,retryCount:0,lastError:null,executionNode:'worker-1',jobType:'ingestion'}],total:1,limit:50,offset:0})})}><OperationalJobsPage/></Frame>};
export const AuditEmpty:Story={render:()=> <Frame api={apiWith()}><AuditPage/></Frame>};
export const AuditPopulated:Story={render:()=> <Frame api={apiWith({listAuditEntries:async()=>({items:[{id:'11111111-1111-4111-8111-111111111111',timestamp,user:'admin@example.test',action:'cache.clear',resource:'cache',result:'SUCCESS'}],total:1,limit:50,offset:0})})}><AuditPage/></Frame>};
export const PermissionFailure:Story={render:()=> <Frame api={apiWith({getOperationsHealth:async()=>{throw new AdminApiError('forbidden')}})}><OperationsHealthPage/></Frame>};
export const DestructiveConfirmation:Story={render:()=> <Frame api={apiWith()}><OperationsCachePage/></Frame>,play:async({canvasElement})=>{const canvas=within(canvasElement);await userEvent.click(await canvas.findByRole('button',{name:'Clear all cache regions'}));await expect(canvas.findByRole('dialog')).resolves.toHaveTextContent('all registered cache regions')}};
