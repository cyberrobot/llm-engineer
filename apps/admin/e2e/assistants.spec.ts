import { expect, test, type Page, type Route } from '@playwright/test';

const administrator = {
  user: { id: 'admin-assistants', email: 'admin@example.test', role: 'administrator' },
};

const assistants = [
  {
    id: '11111111-1111-4111-8111-111111111111', slug: 'legal-review', name: 'Legal review',
    status: 'inactive', visibility: 'private', created_at: '2026-08-01T09:00:00Z',
    updated_at: '2026-08-04T09:00:00Z', concurrency_token: '2026-08-04T09:00:00Z',
  },
  {
    id: '22222222-2222-4222-8222-222222222222', slug: 'customer-support', name: 'Customer support',
    status: 'active', visibility: 'public', created_at: '2026-08-01T09:00:00Z',
    updated_at: '2026-08-08T13:30:00Z', concurrency_token: '2026-08-08T13:30:00Z',
  },
  {
    id: '33333333-3333-4333-8333-333333333333', slug: 'people-operations', name: 'People operations',
    status: 'active', visibility: 'private', created_at: '2026-08-01T09:00:00Z',
    updated_at: '2026-08-06T11:15:00Z', concurrency_token: '2026-08-06T11:15:00Z',
  },
  {
    id: '44444444-4444-4444-8444-444444444444', slug: 'product-guide', name: 'Product guide',
    status: 'inactive', visibility: 'public', created_at: '2026-08-01T09:00:00Z',
    updated_at: '2026-08-02T08:45:00Z', concurrency_token: '2026-08-02T08:45:00Z',
  },
];

async function arrangeAuthentication(page: Page) {
  await page.route('**/admin/auth/me', async (route) => {
    expect(route.request().method()).toBe('GET');
    await route.fulfill({ status: 200, contentType: 'application/json', json: administrator });
  });
}

async function fulfillList(route: Route, items = assistants) {
  await route.fulfill({
    status: 200,
    contentType: 'application/json',
    json: { items, total: items.length, limit: 50, offset: 0 },
  });
}

async function expectCollectionShell(page: Page) {
  await expect(page.getByRole('heading', { level: 1, name: 'Assistants' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'New Assistant' }).first()).toHaveAttribute('href', '/admin/assistants/new');
  await expect(page.getByRole('button', { name: 'Refresh assistants list' })).toBeEnabled();
}

test.describe('Assistants collection', () => {
  test.beforeEach(async ({ page }) => {
    await arrangeAuthentication(page);
  });

  test('renders a populated desktop collection @visual', async ({ page }) => {
    await page.route('**/admin/assistants?**', (route) => fulfillList(route));
    await page.goto('/admin/assistants');
    await expectCollectionShell(page);
    await expect(page.getByRole('region', { name: 'Collection summary' })).toContainText('Customer support');
    await expect(page.getByRole('button', { name: 'Actions for Legal review' })).toHaveAttribute('aria-expanded', 'false');
    await expect(page.locator('tbody .badge-active')).toHaveCount(2);
    await expect(page).toHaveScreenshot('assistants-populated-desktop-linux.png', { fullPage: true });
  });

  test('renders the real filtered result @visual', async ({ page }) => {
    await page.route('**/admin/assistants?**', async (route) => {
      const url = new URL(route.request().url());
      const status = url.searchParams.get('status');
      const visibility = url.searchParams.get('visibility');
      const filtered = assistants.filter((assistant) =>
        (!status || assistant.status === status) && (!visibility || assistant.visibility === visibility));
      await fulfillList(route, filtered);
    });
    await page.goto('/admin/assistants');
    await expectCollectionShell(page);
    await page.getByLabel('Status').selectOption('active');
    await page.getByLabel('Visibility').selectOption('public');
    await expect(page.getByRole('button', { name: 'Actions for Customer support' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Actions for Legal review' })).toHaveCount(0);
    await expect(page.getByText('1 result')).toBeVisible();
    await expect(page).toHaveScreenshot('assistants-filtered-desktop-linux.png', { fullPage: true });
  });

  test('renders the unfiltered empty collection @visual', async ({ page }) => {
    await page.route('**/admin/assistants?**', (route) => fulfillList(route, []));
    await page.goto('/admin/assistants');
    await expectCollectionShell(page);
    await expect(page.getByRole('heading', { name: 'No assistants yet' })).toBeVisible();
    await expect(page.getByRole('region', { name: 'Collection summary' })).toContainText('no assistants loaded');
    await expect(page).toHaveScreenshot('assistants-empty-desktop-linux.png', { fullPage: true });
  });

  test('renders the stable loading collection @visual', async ({ page }) => {
    let pendingRoute: Route | undefined;
    await page.route('**/admin/assistants?**', async (route) => {
      pendingRoute = route;
      await new Promise(() => undefined);
    });
    await page.goto('/admin/assistants');
    await expect(page.getByRole('heading', { level: 1, name: 'Assistants' })).toBeVisible();
    await expect(page.getByRole('status')).toHaveText('Loading assistants…');
    await expect(page).toHaveScreenshot('assistants-loading-desktop-linux.png', { fullPage: true });
    await pendingRoute?.abort();
  });

  test('renders a safe collection error @visual', async ({ page }) => {
    await page.route('**/admin/assistants?**', (route) => route.fulfill({
      status: 500,
      contentType: 'application/json',
      json: { code: 'internal_error', message: 'sensitive backend detail' },
    }));
    await page.goto('/admin/assistants');
    await expect(page.getByRole('heading', { name: 'Unable to load assistants' })).toBeVisible();
    await expect(page.getByRole('alert')).toContainText('The server could not complete the request. Try again.');
    await expect(page.getByText('sensitive backend detail')).toHaveCount(0);
    await expect(page).toHaveScreenshot('assistants-error-desktop-linux.png', { fullPage: true });
  });

  test('keeps the populated collection usable without narrow overflow @visual', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.route('**/admin/assistants?**', (route) => fulfillList(route));
    await page.goto('/admin/assistants');
    await expectCollectionShell(page);
    await expect(page.getByRole('button', { name: 'Actions for Customer support' })).toBeVisible();
    await expect(page.getByText('customer-support')).toBeVisible();
    await expect(page.getByRole('cell', { name: /Updated 8 Aug 2026, 13:30/ })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
    await page.getByRole('button', { name: 'Actions for Customer support' }).click();
    await expect(page.getByRole('menu', { name: 'Actions for Customer support' })).toBeVisible();
    await expect(page).toHaveScreenshot('assistants-populated-mobile-linux.png', { fullPage: true });
  });
});
