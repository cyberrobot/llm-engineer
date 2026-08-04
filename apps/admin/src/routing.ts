export function safeReturnLocation(value: string|null): string {
  if (!value || !value.startsWith('/') || value.startsWith('//')) return '/admin';
  try { const url=new URL(value,'https://admin.invalid'); if(url.origin!=='https://admin.invalid'||url.pathname==='/login'||url.pathname.startsWith('/login/')) return '/admin'; return `${url.pathname}${url.search}${url.hash}`; } catch { return '/admin'; }
}
