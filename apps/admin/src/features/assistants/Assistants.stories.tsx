import type { Meta, StoryObj } from '@storybook/react-vite';
import type { ReactNode } from 'react';
import { createMemoryRouter, Route, RouterProvider, Routes } from 'react-router-dom';
import { expect, userEvent, within } from 'storybook/test';
import { AdminApiError, type AdminApi, type Assistant } from '../../api/adminApi';
import { AuthProvider } from '../../auth/AuthContext';
import { AssistantFormPage, AssistantsPage, Badge } from './Assistants';

const item: Assistant = { id:'11111111-1111-4111-8111-111111111111',slug:'legal-review',name:'Legal review',status:'inactive',visibility:'private',createdAt:'2026-08-01T09:00:00Z',updatedAt:'2026-08-04T09:00:00Z',concurrencyToken:'2026-08-04T09:00:00Z' };
const base: AdminApi = {
  currentUser: async()=>({id:'admin',email:'admin@example.test',role:'administrator'}), login:async()=>({id:'admin',email:'admin@example.test',role:'administrator'}), logout:async()=>undefined,
  listAssistants:async()=>({items:[item,{...item,id:'22222222-2222-4222-8222-222222222222',slug:'support',name:'Support',status:'active',visibility:'public'}],total:2,limit:50,offset:0}),
  getAssistant:async()=>({...item,knowledgeSourceCount:0,deletionAllowed:true}),createAssistant:async()=>item,updateAssistant:async()=>item,deleteAssistant:async()=>undefined,
  listKnowledgeSources:async()=>({items:[],total:0,limit:50,offset:0}),getKnowledgeSource:async()=>{throw new AdminApiError('not_found')},createKnowledgeSource:async()=>{throw new AdminApiError('invalid_request')},updateKnowledgeSourceRetrieval:async()=>{throw new AdminApiError('invalid_request')},reingestKnowledgeSource:async()=>{throw new AdminApiError('invalid_request')},deleteKnowledgeSource:async()=>undefined,
};
function Frame({api=base,path='/admin/assistants',children}:{api?:AdminApi;path?:string;children:ReactNode}){const router=createMemoryRouter([{path:'*',element:<AuthProvider api={api} initialUser={{id:'admin',email:'admin@example.test',role:'administrator'}}>{children}</AuthProvider>}],{initialEntries:[path]});return <RouterProvider router={router}/>}
const meta={title:'Assistants/Management'} satisfies Meta; export default meta; type Story=StoryObj;
export const PopulatedList:Story={render:()=> <Frame><AssistantsPage/></Frame>};
export const EmptyList:Story={render:()=> <Frame api={{...base,listAssistants:async()=>({items:[],total:0,limit:50,offset:0})}}><AssistantsPage/></Frame>};
export const LoadingList:Story={render:()=> <Frame api={{...base,listAssistants:()=>new Promise(()=>undefined)}}><AssistantsPage/></Frame>};
export const ErrorList:Story={render:()=> <Frame api={{...base,listAssistants:async()=>{throw new AdminApiError('network')}}}><AssistantsPage/></Frame>};
export const CreateForm:Story={render:()=> <Frame path="/admin/assistants/new"><AssistantFormPage mode="create"/></Frame>};
export const EditForm:Story={render:()=> <Frame path={`/admin/assistants/${item.id}/edit`}><Routes><Route path="/admin/assistants/:assistantId/edit" element={<AssistantFormPage mode="edit"/>}/></Routes></Frame>};
export const ValidationErrors:Story={
  render:()=> <Frame path="/admin/assistants/new"><AssistantFormPage mode="create"/></Frame>,
  play:async({canvasElement})=>{const canvas=within(canvasElement);await userEvent.click(await canvas.findByRole('button',{name:'Save assistant'}));await expect(canvas.getByRole('alert')).toHaveTextContent('Name is required.');},
};
export const DeleteConfirmation:Story={
  render:()=> <Frame><AssistantsPage/></Frame>,
  play:async({canvasElement})=>{const canvas=within(canvasElement);await userEvent.click(await canvas.findByRole('button',{name:'Delete Legal review'}));await expect(canvas.getByRole('dialog')).toHaveTextContent('Delete Legal review?');},
};
export const PendingStatusAction:Story={
  render:()=> <Frame api={{...base,updateAssistant:()=>new Promise(()=>undefined)}}><AssistantsPage/></Frame>,
  play:async({canvasElement})=>{const canvas=within(canvasElement);await userEvent.click(await canvas.findByRole('button',{name:'Activate Legal review'}));await userEvent.click(canvas.getByRole('button',{name:'Confirm'}));await expect(canvas.getByRole('button',{name:'Working…'})).toBeDisabled();},
};
export const StatusBadges:Story={render:()=> <div className="actions"><Badge value="active"/><Badge value="inactive"/><Badge value="public"/><Badge value="private"/></div>};
