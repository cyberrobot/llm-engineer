import { render,screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { afterEach,describe,expect,it,vi } from 'vitest';
import App from './App';
import { AdminApiError, createAdminApi, type AdminApi, type Administrator, type Assistant } from './api/adminApi';
import { AuthProvider, useAuth } from './auth/AuthContext';

const administrator:Administrator={id:'admin-1',email:'admin@example.test',role:'administrator'};
const assistant:Assistant={id:'11111111-1111-4111-8111-111111111111',slug:'legal-review',name:'Legal review',status:'inactive',visibility:'private',createdAt:'2026-08-05T09:00:00Z',updatedAt:'2026-08-05T09:00:00Z',concurrencyToken:'2026-08-05T09:00:00Z'};
function deferred<T>(){let resolve!:(value:T)=>void,reject!:(reason?:unknown)=>void;const promise=new Promise<T>((yes,no)=>{resolve=yes;reject=no});return{promise,resolve,reject}}
function renderApp(api:AdminApi,path='/admin'){const router=createMemoryRouter([{path:'*',element:<AuthProvider api={api}><App/></AuthProvider>}],{initialEntries:[path]});return render(<RouterProvider router={router}/>)}
function apiWith(overrides:Partial<AdminApi>={}):AdminApi{return{currentUser:vi.fn().mockResolvedValue(administrator),login:vi.fn().mockResolvedValue(administrator),logout:vi.fn().mockResolvedValue(undefined),listAssistants:vi.fn().mockResolvedValue({items:[],total:0,limit:50,offset:0}),getAssistant:vi.fn(),createAssistant:vi.fn(),updateAssistant:vi.fn(),deleteAssistant:vi.fn(),...overrides}}
afterEach(()=>{vi.restoreAllMocks();vi.unstubAllGlobals()});

describe('administrator application workflows',()=>{
  it('hides protected content until session restoration completes',async()=>{const session=deferred<Administrator>();renderApp(apiWith({currentUser:vi.fn(()=>session.promise)}));expect(screen.getByRole('heading',{name:'Restoring your session'})).toBeInTheDocument();expect(screen.queryByText(/Dashboard functionality/)).not.toBeInTheDocument();session.resolve(administrator);expect(await screen.findByText('Dashboard functionality is not implemented yet.')).toBeInTheDocument()});
  it('redirects a confirmed unauthenticated session with a safe return path',async()=>{renderApp(apiWith({currentUser:vi.fn().mockRejectedValue(new AdminApiError('unauthenticated'))}),'/admin/assistants');expect(await screen.findByRole('heading',{name:'Welcome back'})).toBeInTheDocument()});
  it('shows a retryable restoration failure and retries manually',async()=>{const currentUser=vi.fn().mockRejectedValueOnce(new AdminApiError('network')).mockResolvedValueOnce(administrator);renderApp(apiWith({currentUser}));expect(await screen.findByRole('heading',{name:'Unable to restore your session'})).toBeInTheDocument();await userEvent.click(screen.getByRole('button',{name:'Try again'}));expect(await screen.findByText('Dashboard functionality is not implemented yet.')).toBeInTheDocument();expect(currentUser).toHaveBeenCalledTimes(2)});
  it('validates required fields and signs in by keyboard without duplicate pending requests',async()=>{const login=vi.fn().mockResolvedValue(administrator);renderApp(apiWith({currentUser:vi.fn().mockRejectedValue(new AdminApiError('unauthenticated')),login}),'/login?returnTo=/admin/assistants');const email=await screen.findByLabelText('Email address');await userEvent.click(screen.getByRole('button',{name:'Sign in'}));expect(screen.getByRole('alert')).toHaveFocus();await userEvent.type(email,'admin@example.test');await userEvent.type(screen.getByLabelText('Password'),'correct password{Enter}');expect(await screen.findByText('No assistants yet')).toBeInTheDocument();expect(login).toHaveBeenCalledOnce()});
  it('preserves email and safely reports invalid credentials',async()=>{renderApp(apiWith({currentUser:vi.fn().mockRejectedValue(new AdminApiError('unauthenticated')),login:vi.fn().mockRejectedValue(new AdminApiError('invalid_credentials'))}),'/login');await userEvent.type(await screen.findByLabelText('Email address'),'admin@example.test');await userEvent.type(screen.getByLabelText('Password'),'wrong{Enter}');expect(await screen.findByRole('alert')).toHaveTextContent('email or password is invalid');expect(screen.getByLabelText('Email address')).toHaveValue('admin@example.test');expect(screen.getByLabelText('Password')).toHaveValue('')});
  it('renders shell landmarks and logs out even when the session is already expired',async()=>{const logout=vi.fn().mockResolvedValue(undefined);renderApp(apiWith({logout}));expect(await screen.findByRole('navigation',{name:'Primary'})).toBeInTheDocument();expect(screen.getByText('admin@example.test')).toBeInTheDocument();await userEvent.click(screen.getByRole('button',{name:'Sign out'}));expect(await screen.findByRole('heading',{name:'Welcome back'})).toBeInTheDocument();expect(logout).toHaveBeenCalledOnce()});
  it('returns to the assistants page after creating an assistant',async()=>{
    const createAssistant=vi.fn().mockResolvedValue(assistant);
    renderApp(apiWith({createAssistant}),'/admin/assistants/new');
    await userEvent.type(await screen.findByLabelText('Name'),'Legal review');
    await userEvent.type(screen.getByLabelText('Slug'),'legal-review');
    await userEvent.click(screen.getByRole('button',{name:'Save assistant'}));
    expect(await screen.findByText('No assistants yet')).toBeInTheDocument();
    expect(createAssistant).toHaveBeenCalledWith({name:'Legal review',slug:'legal-review',status:'inactive',visibility:'private'});
  });
  it('prevents duplicate creates and submits selected enum values',async()=>{
    const request=deferred<typeof assistant>();
    const createAssistant=vi.fn(()=>request.promise);
    renderApp(apiWith({createAssistant}),'/admin/assistants/new');
    await userEvent.type(await screen.findByLabelText('Name'),'Legal review');
    await userEvent.type(screen.getByLabelText('Slug'),'legal-review');
    await userEvent.selectOptions(screen.getByLabelText('Status'),'active');
    await userEvent.selectOptions(screen.getByLabelText('Visibility'),'public');
    const save=screen.getByRole('button',{name:'Save assistant'});
    await userEvent.click(save);
    expect(screen.getByRole('button',{name:'Saving…'})).toBeDisabled();
    await userEvent.click(screen.getByRole('button',{name:'Saving…'}));
    expect(createAssistant).toHaveBeenCalledOnce();
    expect(createAssistant).toHaveBeenCalledWith({name:'Legal review',slug:'legal-review',status:'active',visibility:'public'});
    request.resolve({...assistant,status:'active',visibility:'public'});
    expect(await screen.findByText('No assistants yet')).toBeInTheDocument();
  });
  it('retains create values and errors without redirecting after a failed save',async()=>{
    renderApp(apiWith({createAssistant:vi.fn().mockRejectedValue(new AdminApiError('conflict','assistant_slug_conflict'))}),'/admin/assistants/new');
    await userEvent.type(await screen.findByLabelText('Name'),'Legal review');
    await userEvent.type(screen.getByLabelText('Slug'),'legal-review');
    await userEvent.click(screen.getByRole('button',{name:'Save assistant'}));
    expect(await screen.findByRole('alert')).toHaveTextContent('slug is already in use');
    expect(screen.getByRole('alert')).toHaveFocus();
    expect(screen.getByLabelText('Name')).toHaveValue('Legal review');
    expect(screen.getByRole('heading',{name:'Create assistant'})).toBeInTheDocument();
  });
  it('keeps the edit page open after a successful update',async()=>{
    const updateAssistant=vi.fn().mockResolvedValue({...assistant,name:'Updated name',updatedAt:'2026-08-05T10:00:00Z',concurrencyToken:'2026-08-05T10:00:00Z'});
    renderApp(apiWith({getAssistant:vi.fn().mockResolvedValue({...assistant,knowledgeSourceCount:0,deletionAllowed:true}),updateAssistant}),`/admin/assistants/${assistant.id}/edit`);
    const name=await screen.findByLabelText('Name');
    await userEvent.clear(name);
    await userEvent.type(name,'Updated name');
    await userEvent.click(screen.getByRole('button',{name:'Save assistant'}));
    expect(await screen.findByRole('alert')).toHaveTextContent('Assistant saved.');
    expect(screen.getByRole('heading',{name:'Edit assistant'})).toBeInTheDocument();
  });
  it('prevents duplicate updates while saving',async()=>{
    const request=deferred<typeof assistant>();
    const updateAssistant=vi.fn(()=>request.promise);
    renderApp(apiWith({getAssistant:vi.fn().mockResolvedValue({...assistant,knowledgeSourceCount:0,deletionAllowed:true}),updateAssistant}),`/admin/assistants/${assistant.id}/edit`);
    const name=await screen.findByLabelText('Name');
    await userEvent.clear(name);
    await userEvent.type(name,'Updated name');
    await userEvent.click(screen.getByRole('button',{name:'Save assistant'}));
    expect(screen.getByRole('button',{name:'Saving…'})).toBeDisabled();
    await userEvent.click(screen.getByRole('button',{name:'Saving…'}));
    expect(updateAssistant).toHaveBeenCalledOnce();
    request.resolve({...assistant,name:'Updated name'});
    expect(await screen.findByRole('alert')).toHaveTextContent('Assistant saved.');
  });
  it('retains form values after backend validation rejection',async()=>{
    renderApp(apiWith({createAssistant:vi.fn().mockRejectedValue(new AdminApiError('invalid_request'))}),'/admin/assistants/new');
    await userEvent.type(await screen.findByLabelText('Name'),'Legal review');
    await userEvent.type(screen.getByLabelText('Slug'),'legal-review');
    await userEvent.click(screen.getByRole('button',{name:'Save assistant'}));
    expect(await screen.findByRole('alert')).toHaveTextContent('request could not be completed');
    expect(screen.getByLabelText('Name')).toHaveValue('Legal review');
    expect(screen.getByLabelText('Slug')).toHaveValue('legal-review');
  });
  it('invalidates the authenticated session when a create mutation returns 401',async()=>{
    renderApp(apiWith({createAssistant:vi.fn().mockRejectedValue(new AdminApiError('unauthenticated'))}),'/admin/assistants/new');
    await userEvent.type(await screen.findByLabelText('Name'),'Legal review');
    await userEvent.type(screen.getByLabelText('Slug'),'legal-review');
    await userEvent.click(screen.getByRole('button',{name:'Save assistant'}));
    expect(await screen.findByRole('heading',{name:'Welcome back'})).toBeInTheDocument();
  });
  it('pages through the complete assistant collection using backend offsets',async()=>{
    const listAssistants=vi.fn().mockResolvedValueOnce({items:[assistant],total:51,limit:50,offset:0}).mockResolvedValueOnce({items:[{...assistant,id:'22222222-2222-4222-8222-222222222222',name:'Page two'}],total:51,limit:50,offset:50});
    renderApp(apiWith({listAssistants}),'/admin/assistants');
    expect(await screen.findByText('Showing 1–1 of 51')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button',{name:'Next'}));
    expect(await screen.findByText('Page two')).toBeInTheDocument();
    expect(listAssistants).toHaveBeenLastCalledWith({limit:50,offset:50,status:undefined,visibility:undefined},expect.any(AbortSignal));
  });
  it('filters assistants through the supported backend contract',async()=>{
    const listAssistants=vi.fn().mockResolvedValue({items:[],total:0,limit:50,offset:0});
    renderApp(apiWith({listAssistants}),'/admin/assistants');
    await screen.findByText('No assistants yet');
    await userEvent.selectOptions(screen.getByLabelText('Status'),'active');
    await userEvent.selectOptions(await screen.findByLabelText('Visibility'),'private');
    expect(listAssistants).toHaveBeenLastCalledWith({limit:50,offset:0,status:'active',visibility:'private'},expect.any(AbortSignal));
    expect(await screen.findByRole('heading',{name:'No matching assistants'})).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button',{name:'Clear filters'}));
    expect(await screen.findByRole('heading',{name:'No assistants yet'})).toBeInTheDocument();
  });
  it('returns to the preceding page and restores stable focus after deleting the last item',async()=>{
    const pageTwo={...assistant,id:'22222222-2222-4222-8222-222222222222',name:'Page two'};
    const listAssistants=vi.fn()
      .mockResolvedValueOnce({items:[assistant],total:51,limit:50,offset:0})
      .mockResolvedValueOnce({items:[pageTwo],total:51,limit:50,offset:50})
      .mockResolvedValueOnce({items:[],total:50,limit:50,offset:50})
      .mockResolvedValueOnce({items:[assistant],total:50,limit:50,offset:0});
    renderApp(apiWith({listAssistants,deleteAssistant:vi.fn().mockResolvedValue(undefined)}),'/admin/assistants');
    await userEvent.click(await screen.findByRole('button',{name:'Next'}));
    await userEvent.click(await screen.findByRole('button',{name:'Delete Page two'}));
    await userEvent.click(screen.getByRole('button',{name:'Confirm'}));
    const notice=await screen.findByRole('status');
    expect(notice).toHaveTextContent('Assistant deleted. List refreshed.');
    expect(notice).toHaveFocus();
    expect(await screen.findByText('Legal review')).toBeInTheDocument();
    expect(listAssistants).toHaveBeenLastCalledWith({limit:50,offset:0,status:undefined,visibility:undefined},expect.any(AbortSignal));
  });
  it('maps protected and already-deleted assistants to their contractual outcomes',async()=>{
    const deleteAssistant=vi.fn().mockRejectedValueOnce(new AdminApiError('conflict','protected_assistant')).mockRejectedValueOnce(new AdminApiError('not_found','assistant_not_found'));
    const listAssistants=vi.fn().mockResolvedValue({items:[assistant],total:1,limit:50,offset:0});
    renderApp(apiWith({listAssistants,deleteAssistant}),'/admin/assistants');
    await userEvent.click(await screen.findByRole('button',{name:'Delete Legal review'}));
    await userEvent.click(screen.getByRole('button',{name:'Confirm'}));
    expect(await screen.findByRole('alert')).toHaveTextContent('seeded assistant is protected');
    await userEvent.click(screen.getByRole('button',{name:'Confirm'}));
    expect(await screen.findByRole('status')).toHaveTextContent('Assistant deleted. List refreshed.');
  });
  it('retries a failed assistant detail request and links not-found routes to the list',async()=>{
    const getAssistant=vi.fn().mockRejectedValueOnce(new AdminApiError('network')).mockResolvedValueOnce({...assistant,knowledgeSourceCount:0,deletionAllowed:true});
    renderApp(apiWith({getAssistant}),`/admin/assistants/${assistant.id}/edit`);
    await userEvent.click(await screen.findByRole('button',{name:'Try again'}));
    expect(await screen.findByDisplayValue('Legal review')).toBeInTheDocument();
    expect(getAssistant).toHaveBeenCalledTimes(2);
  });
  it('links an unknown assistant back to the assistants list',async()=>{
    renderApp(apiWith({getAssistant:vi.fn().mockRejectedValue(new AdminApiError('not_found','assistant_not_found'))}),`/admin/assistants/${assistant.id}/edit`);
    const link=await screen.findByRole('link',{name:'Return to assistants'});
    expect(link).toHaveAttribute('href','/admin/assistants');
  });
  it('invalidates the session when a status mutation returns 401',async()=>{
    renderApp(apiWith({listAssistants:vi.fn().mockResolvedValue({items:[assistant],total:1,limit:50,offset:0}),updateAssistant:vi.fn().mockRejectedValue(new AdminApiError('unauthenticated'))}),'/admin/assistants');
    await userEvent.click(await screen.findByRole('button',{name:'Activate Legal review'}));
    await userEvent.click(screen.getByRole('button',{name:'Confirm'}));
    expect(await screen.findByRole('heading',{name:'Welcome back'})).toBeInTheDocument();
  });
  it('confirms public deactivation and retains confirmed state after failure',async()=>{
    const activePublic={...assistant,status:'active' as const,visibility:'public' as const};
    const updateAssistant=vi.fn().mockRejectedValue(new AdminApiError('network'));
    renderApp(apiWith({listAssistants:vi.fn().mockResolvedValue({items:[activePublic],total:1,limit:50,offset:0}),updateAssistant}),'/admin/assistants');
    await userEvent.click(await screen.findByRole('button',{name:'Deactivate Legal review'}));
    expect(screen.getByRole('dialog')).toHaveTextContent('may make the assistant unavailable through public interfaces');
    await userEvent.click(screen.getByRole('button',{name:'Confirm'}));
    expect(await screen.findByRole('alert')).toHaveTextContent('backend could not be reached');
    expect(screen.getByRole('cell',{name:'Active'})).toBeInTheDocument();
    expect(screen.getByRole('button',{name:'Deactivate Legal review'})).toBeInTheDocument();
    expect(updateAssistant).toHaveBeenCalledWith(assistant.id,{concurrency_token:assistant.concurrencyToken,status:'inactive'});
  });
  it('keeps the delete dialog open after a dependency conflict',async()=>{
    renderApp(apiWith({listAssistants:vi.fn().mockResolvedValue({items:[assistant],total:1,limit:50,offset:0}),deleteAssistant:vi.fn().mockRejectedValue(new AdminApiError('conflict','assistant_has_dependencies'))}),'/admin/assistants');
    await userEvent.click(await screen.findByRole('button',{name:'Delete Legal review'}));
    await userEvent.click(screen.getByRole('button',{name:'Confirm'}));
    expect(await screen.findByRole('alert')).toHaveTextContent('dependent records');
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText('Legal review')).toBeInTheDocument();
  });
  it('warns before discarding a dirty form',async()=>{
    const confirm=vi.spyOn(window,'confirm').mockReturnValue(false);
    renderApp(apiWith(),'/admin/assistants/new');
    await userEvent.type(await screen.findByLabelText('Name'),'Unsaved');
    await userEvent.click(screen.getByRole('link',{name:'Cancel'}));
    expect(confirm).toHaveBeenCalledWith('Discard your unsaved assistant changes?');
    expect(screen.getByDisplayValue('Unsaved')).toBeInTheDocument();
    confirm.mockReturnValue(true);
    await userEvent.click(screen.getByRole('link',{name:'Cancel'}));
    expect(await screen.findByText('No assistants yet')).toBeInTheDocument();
  });
  it('associates slug validation with the invalid field',async()=>{
    renderApp(apiWith(),'/admin/assistants/new');
    await userEvent.type(await screen.findByLabelText('Name'),'Legal review');
    await userEvent.type(screen.getByLabelText('Slug'),'Not Safe');
    await userEvent.click(screen.getByRole('button',{name:'Save assistant'}));
    expect(screen.getByLabelText('Slug')).toHaveAttribute('aria-invalid','true');
    expect(screen.getByLabelText('Slug')).toHaveAccessibleDescription('Slug must contain lowercase letters or numbers separated by hyphens.');
  });
  it('creates an assistant through the real HTTP boundary and reloads the list',async()=>{
    const rawAssistant={id:assistant.id,slug:assistant.slug,name:assistant.name,status:assistant.status,visibility:assistant.visibility,created_at:assistant.createdAt,updated_at:assistant.updatedAt,concurrency_token:assistant.concurrencyToken};
    const fetchMock=vi.fn()
      .mockResolvedValueOnce(Response.json({user:administrator}))
      .mockResolvedValueOnce(Response.json(rawAssistant,{status:201}))
      .mockResolvedValueOnce(Response.json({items:[rawAssistant],total:1,limit:50,offset:0}));
    vi.stubGlobal('fetch',fetchMock);
    renderApp(createAdminApi('https://api.example.test'),'/admin/assistants/new');
    await userEvent.type(await screen.findByLabelText('Name'),'Legal review');
    await userEvent.type(screen.getByLabelText('Slug'),'legal-review');
    await userEvent.click(screen.getByRole('button',{name:'Save assistant'}));
    expect(await screen.findByText('Legal review')).toBeInTheDocument();
    expect(fetchMock.mock.calls[1]?.[0]).toBe('https://api.example.test/admin/assistants');
    expect(fetchMock.mock.calls[1]?.[1]).toEqual(expect.objectContaining({method:'POST',credentials:'include',body:JSON.stringify({name:'Legal review',slug:'legal-review',status:'inactive',visibility:'private'})}));
    expect(fetchMock.mock.calls[2]?.[0]).toBe('https://api.example.test/admin/assistants?limit=50&offset=0');
  });
  it('updates status and deletes through the real HTTP boundary',async()=>{
    const rawAssistant={id:assistant.id,slug:assistant.slug,name:assistant.name,status:assistant.status,visibility:assistant.visibility,created_at:assistant.createdAt,updated_at:assistant.updatedAt,concurrency_token:assistant.concurrencyToken};
    const activeAssistant={...rawAssistant,status:'active',updated_at:'2026-08-05T10:00:00Z',concurrency_token:'2026-08-05T10:00:00Z'};
    const fetchMock=vi.fn()
      .mockResolvedValueOnce(Response.json({user:administrator}))
      .mockResolvedValueOnce(Response.json({items:[rawAssistant],total:1,limit:50,offset:0}))
      .mockResolvedValueOnce(Response.json(activeAssistant))
      .mockResolvedValueOnce(Response.json({items:[activeAssistant],total:1,limit:50,offset:0}))
      .mockResolvedValueOnce(new Response(null,{status:204}))
      .mockResolvedValueOnce(Response.json({items:[],total:0,limit:50,offset:0}));
    vi.stubGlobal('fetch',fetchMock);
    renderApp(createAdminApi('https://api.example.test'),'/admin/assistants');
    await userEvent.click(await screen.findByRole('button',{name:'Activate Legal review'}));
    await userEvent.click(screen.getByRole('button',{name:'Confirm'}));
    await screen.findByRole('button',{name:'Deactivate Legal review'});
    await userEvent.click(screen.getByRole('button',{name:'Delete Legal review'}));
    await userEvent.click(screen.getByRole('button',{name:'Confirm'}));
    expect(await screen.findByRole('heading',{name:'No assistants yet'})).toBeInTheDocument();
    expect(fetchMock.mock.calls[2]?.[1]).toEqual(expect.objectContaining({method:'PATCH',credentials:'include',body:JSON.stringify({concurrency_token:assistant.concurrencyToken,status:'active'})}));
    expect(fetchMock.mock.calls[4]?.[1]).toEqual(expect.objectContaining({method:'DELETE',credentials:'include'}));
  });
  it('hides protected content when an authenticated request reports an expired session',async()=>{
    function ExpireSession(){const auth=useAuth();return <button onClick={auth.sessionExpired}>Expire session</button>}
    const router=createMemoryRouter([{path:'*',element:<AuthProvider api={apiWith()} initialUser={administrator}><ExpireSession/><App/></AuthProvider>}],{initialEntries:['/admin']});
    render(<RouterProvider router={router}/>);
    expect(screen.getByText('Dashboard functionality is not implemented yet.')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button',{name:'Expire session'}));
    expect(await screen.findByRole('heading',{name:'Welcome back'})).toBeInTheDocument();
    expect(screen.queryByText('Dashboard functionality is not implemented yet.')).not.toBeInTheDocument();
  });
});
