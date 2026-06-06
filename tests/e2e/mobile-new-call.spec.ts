import { expect, test } from "@playwright/test";

async function mockMayaRelayApi(page: import("@playwright/test").Page) {
  const conversation = {
    id: "conversation-1",
    code: "C0001",
    status: "open",
    channel: "sms",
    customer: {
      phone: "+15550000001",
      displayName: null,
      lookupName: null,
      name: "Test Customer",
    },
    lastMessage: {
      body: "Hello",
      direction: "customer_to_employee",
      deliveryStatus: "delivered",
      deliveryErrorCode: null,
      createdAt: "2026-06-06T14:00:00Z",
      hasAttachments: false,
    },
    updatedAt: "2026-06-06T14:00:00Z",
  };
  const requestCounts = {
    conversations: 0,
    detail: 0,
    me: 0,
    quickResponses: 0,
  };

  await page.route("**/api/me", async (route) => {
    requestCounts.me += 1;
    await route.fulfill({
      contentType: "application/json",
      json: {
        authenticated: true,
        app: { name: "Maya Relay", environment: "test" },
      },
    });
  });

  await page.route("**/api/conversations", async (route) => {
    requestCounts.conversations += 1;
    await route.fulfill({
      contentType: "application/json",
      json: {
        metrics: { open: 1, failed: 0, recent: 1, withAttachments: 0 },
        conversations: [conversation],
      },
    });
  });

  await page.route("**/api/conversations/conversation-1", async (route) => {
    requestCounts.detail += 1;
    await route.fulfill({
      contentType: "application/json",
      json: {
        conversation: {
          ...conversation,
          assignedEmployee: "+15551234567",
          createdAt: "2026-06-06T14:00:00Z",
        },
        messages: [
          {
            id: "message-1",
            conversationId: "conversation-1",
            direction: "customer_to_employee",
            body: "Hello",
            fromPhone: "+15550000001",
            toPhone: "+13852208404",
            twilioMessageSid: "SMfake",
            deliveryStatus: "delivered",
            deliveryErrorCode: null,
            deliveryErrorMessage: null,
            clientRequestId: null,
            createdAt: "2026-06-06T14:00:00Z",
            attachments: [],
          },
        ],
        suggestedReply: "",
      },
    });
  });

  await page.route("**/api/quick-responses", async (route) => {
    requestCounts.quickResponses += 1;
    await route.fulfill({
      contentType: "application/json",
      json: { quickResponses: [] },
    });
  });

  return requestCounts;
}

async function expectNoHorizontalOverflow(page: import("@playwright/test").Page) {
  const overflow = await page.evaluate(() => ({
    bodyScrollWidth: document.body.scrollWidth,
    documentScrollWidth: document.documentElement.scrollWidth,
    viewportWidth: window.innerWidth,
  }));

  expect(overflow.bodyScrollWidth).toBeLessThanOrEqual(overflow.viewportWidth);
  expect(overflow.documentScrollWidth).toBeLessThanOrEqual(overflow.viewportWidth);
}

async function expectNoIosInputZoomRisk(locator: import("@playwright/test").Locator) {
  const fontSize = await locator.evaluate((element) => Number.parseFloat(window.getComputedStyle(element).fontSize));
  expect(fontSize).toBeGreaterThanOrEqual(16);
}

async function expectInsideViewport(locator: import("@playwright/test").Locator) {
  const box = await locator.boundingBox();
  expect(box).not.toBeNull();
  expect(box!.x).toBeGreaterThanOrEqual(0);
  expect(box!.x + box!.width).toBeLessThanOrEqual(locator.page().viewportSize()!.width);
}

test("New Call drawer stays inside the mobile viewport", async ({ page }) => {
  await mockMayaRelayApi(page);
  await page.goto("/app/");

  await page.getByRole("button", { name: /new call/i }).click();
  await expect(page.getByRole("dialog", { name: "New call" })).toBeVisible();
  await expectNoHorizontalOverflow(page);

  const phoneInput = page.getByLabel("Customer phone");
  await phoneInput.focus();
  await phoneInput.fill("+1 555 000 0000");
  await expectNoIosInputZoomRisk(phoneInput);
  await expectNoHorizontalOverflow(page);

  for (const control of [
    page.getByRole("button", { name: "Cancel" }),
    page.getByRole("button", { name: /start call/i }),
    phoneInput,
  ]) {
    await expectInsideViewport(control);
  }
});

test("authenticated boot loads each initial resource once", async ({ page }) => {
  const requestCounts = await mockMayaRelayApi(page);

  await page.goto("/app/");
  await expect(page.getByRole("button", { name: /Test Customer/ })).toBeVisible();
  await expect(page.getByRole("article").getByText("Hello")).toBeVisible();

  await expect.poll(() => requestCounts.conversations).toBe(1);
  await expect.poll(() => requestCounts.detail).toBe(1);
  await expect.poll(() => requestCounts.quickResponses).toBe(1);
  expect(requestCounts.me).toBeGreaterThanOrEqual(1);
  expect(requestCounts.me).toBeLessThanOrEqual(2);
});

test("login input focus does not create mobile zoom risk", async ({ page }) => {
  await page.route("**/api/me", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      status: 401,
      json: { detail: "Unauthorized" },
    });
  });

  await page.goto("/app/");
  const passwordInput = page.getByLabel("Password");
  await passwordInput.focus();
  await expectNoIosInputZoomRisk(passwordInput);
  await expectNoHorizontalOverflow(page);

  await expectInsideViewport(page.locator(".login-panel"));
  await expectInsideViewport(passwordInput);
  await expectInsideViewport(page.getByRole("button", { name: "Sign in" }));
});
