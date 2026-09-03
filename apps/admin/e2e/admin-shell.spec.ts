import { expect, test, type Page } from '@playwright/test';

const administrator = {
  user: {
    id: 'admin-visual-regression',
    email: 'admin@example.test',
    role: 'administrator',
  },
};

const operationsSummary = {
  generated_at: '2026-08-25T10:00:00Z',
  health: 'healthy',
  maintenance: false,
  cache: { regions: 3 },
  jobs: { running: 1, failed: 0 },
  audit: { today: 4 },
  assistants: { total: 2, published: 1 },
  knowledge_sources: { total: 5, enabled: 4, failed: null },
  ingestion: {
    queued: 2,
    running: 1,
    recoverable: 0,
    failed: 0,
    oldest_queued_age_seconds: 4320,
    workers_observed: 2,
  },
};

async function arrangeAuthenticatedDashboard(page: Page) {
  await page.route('**/admin/auth/me', async (route) => {
    expect(route.request().method()).toBe('GET');
    await route.fulfill({ status: 200, contentType: 'application/json', json: administrator });
  });
  await page.route('**/admin/operations/summary', async (route) => {
    expect(route.request().method()).toBe('GET');
    await route.fulfill({ status: 200, contentType: 'application/json', json: operationsSummary });
  });
}

async function expectUsableDashboard(page: Page) {
  await expect(page.getByRole('main')).toBeVisible();
  await expect(page.getByRole('heading', { level: 1, name: 'Dashboard' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Service status' })).toBeVisible();
  await expect(page.getByText('No operational conditions currently require attention.')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Unable to load dashboard' })).toHaveCount(0);
  await expect(page.getByText('The backend returned an invalid response.')).toHaveCount(0);
}

test.describe('authenticated Admin shell', () => {
  test.beforeEach(async ({ page }) => {
    await arrangeAuthenticatedDashboard(page);
  });

  test('renders the desktop Dashboard and its active navigation @visual', async ({ page }) => {
    await page.goto('/admin');
    await expectUsableDashboard(page);

    const navigation = page.getByRole('navigation', { name: 'Primary' });
    await expect(navigation).toBeVisible();
    await expect(navigation.getByRole('link', { name: 'Dashboard' })).toHaveAttribute(
      'aria-current',
      'page',
    );
    await expect(page.getByText('admin@example.test')).toBeVisible();

    await expect(page).toHaveScreenshot('dashboard-desktop-linux.png', { fullPage: true });
  });

  test('keeps the narrow Dashboard usable with its navigation open @visual', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/admin');
    await expectUsableDashboard(page);

    const menuButton = page.getByRole('button', { name: 'Open navigation' });
    await expect(menuButton).toBeVisible();
    await expect(menuButton).toHaveAttribute('aria-expanded', 'false');
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth),
    ).toBe(true);

    await menuButton.click();
    const navigation = page.getByRole('navigation', { name: 'Primary' });
    await expect(page.getByRole('button', { name: 'Close navigation', exact: true })).toHaveAttribute(
      'aria-expanded',
      'true',
    );
    await expect(navigation).toBeVisible();
    await expect(navigation.getByRole('link', { name: 'Dashboard' })).toHaveAttribute(
      'aria-current',
      'page',
    );
    await expect(page.getByRole('main')).toHaveAttribute('inert', '');

    await expect(page).toHaveScreenshot('dashboard-mobile-navigation-open-linux.png');
  });
});
