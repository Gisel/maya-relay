import { expect, test } from "@playwright/test";

async function mockMayaRelayApi(
  page: import("@playwright/test").Page,
  options: { holdSecondDetailRequest?: boolean } = {},
) {
  let conversationStatus: "open" | "closed" = "open";
  const conversation = {
    id: "conversation-1",
    code: "C0001",
    status: conversationStatus,
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
  const olderConversation = {
    ...conversation,
    id: "conversation-2",
    code: "C0002",
    channel: "whatsapp",
    customer: {
      phone: "+15550000002",
      displayName: "Older Customer",
      lookupName: null,
      name: "Older Customer",
    },
    lastMessage: {
      ...conversation.lastMessage,
      body: "Older hello",
      direction: "employee_to_customer",
      createdAt: "2026-06-05T14:00:00Z",
    },
    updatedAt: "2026-06-05T14:00:00Z",
  };
  let startedConversation: typeof conversation | null = null;
  let startedMessage: {
    id: string;
    conversationId: string;
    direction: string;
    body: string;
    fromPhone: string;
    toPhone: string;
    twilioMessageSid: string;
    deliveryStatus: string;
    deliveryErrorCode: null;
    deliveryErrorMessage: null;
    clientRequestId: string | null;
    createdAt: string;
    attachments: never[];
  } | null = null;
  let contact = {
    id: "contact-1",
    phone: "+15550000001",
    displayName: null as string | null,
    lookupName: null as string | null,
    name: "Test Customer",
    notes: "Prefers proof approvals by text.",
    lastActivityAt: "2026-06-06T14:05:00Z",
    openConversationId: "conversation-1",
    lastConversationId: "conversation-1",
    latestCallId: "call-existing",
  };
  const requestCounts = {
    conversations: 0,
    detail: 0,
    me: 0,
    callStarts: 0,
    callLists: 0,
    callUpdates: 0,
    statusUpdates: 0,
    quickResponses: 0,
    contacts: 0,
    contactUpdates: 0,
    contactImports: 0,
    operationalStatus: 0,
    suggestedReplies: 0,
    conversationStarts: 0,
  };
  const startConversationPayloads: unknown[] = [];
  const calls = [
    {
      id: "call-existing",
      conversationId: "conversation-1",
      direction: "outbound",
      callType: "conversation_call",
      customerPhone: "+15550000001",
      employeePhone: "+15551234567",
      twilioCallSid: "CAexisting",
      status: "completed",
      outcome: null,
      notes: null,
      followUpStatus: "none",
      recap: null,
      transcription: null,
      startedAt: "2026-06-06T14:05:00Z",
      answeredAt: "2026-06-06T14:05:04Z",
      completedAt: "2026-06-06T14:05:49Z",
      createdAt: "2026-06-06T14:05:00Z",
      updatedAt: "2026-06-06T14:05:49Z",
    },
  ];
  let releaseHeldDetailRequest: (() => void) | null = null;

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

  await page.route(/\/api\/conversations(?:\?.*)?$/, async (route) => {
    const url = new URL(route.request().url());
    const query = (url.searchParams.get("q") || "").toLowerCase();
    const status = url.searchParams.get("status");
    const offset = Number(url.searchParams.get("offset") || "0");
    const currentConversation = { ...conversation, status: conversationStatus };
    const candidates = [currentConversation, olderConversation].filter((item) => !status || item.status === status);
    if (startedConversation && (!status || startedConversation.status === status)) {
      candidates.unshift(startedConversation);
    }
    const pageConversations = query
      ? candidates.filter((item) =>
        [item.customer.name, item.customer.phone, item.lastMessage.body].join(" ").toLowerCase().includes(query),
      )
      : offset > 0 ? candidates.filter((item) => item.id === "conversation-2") : candidates.filter((item) => item.id === "conversation-1");
    requestCounts.conversations += 1;
    await route.fulfill({
      contentType: "application/json",
      json: {
        metrics: { open: 1, failed: 0, recent: 1, withAttachments: 0 },
        conversations: pageConversations,
        pagination: {
          limit: 50,
          offset,
          nextOffset: query || offset > 0 ? null : 1,
          hasMore: !query && offset === 0,
        },
      },
    });
  });

  await page.route("**/api/conversations/conversation-1", async (route) => {
    if (route.request().method() === "PATCH") {
      requestCounts.statusUpdates += 1;
      const payload = JSON.parse(route.request().postData() || "{}") as { status?: "open" | "closed" };
      conversationStatus = payload.status || conversationStatus;
      await route.fulfill({
        contentType: "application/json",
        json: {
          conversation: {
            ...conversation,
            status: conversationStatus,
            assignedEmployee: "+15551234567",
            createdAt: "2026-06-06T14:00:00Z",
          },
        },
      });
      return;
    }

    requestCounts.detail += 1;
    if (options.holdSecondDetailRequest && requestCounts.detail === 2) {
      await new Promise<void>((resolve) => {
        releaseHeldDetailRequest = resolve;
      });
    }
    const messages = [
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
      {
        id: "message-2",
        conversationId: "conversation-1",
        direction: "system",
        body: "From Test Customer [#C0001]:\nHello\nReply with #C0001 your message",
        fromPhone: "+13852208404",
        toPhone: "+15551234567",
        twilioMessageSid: "SMforward",
        deliveryStatus: "delivered",
        deliveryErrorCode: null,
        deliveryErrorMessage: null,
        clientRequestId: null,
        createdAt: "2026-06-06T14:00:01Z",
        attachments: [],
      },
      {
        id: "message-3",
        conversationId: "conversation-1",
        direction: "system",
        body: "#C0001 Please send size and deadline.",
        fromPhone: "+13852208404",
        toPhone: "+15551234567",
        twilioMessageSid: "SMsuggestion",
        deliveryStatus: "delivered",
        deliveryErrorCode: null,
        deliveryErrorMessage: null,
        clientRequestId: null,
        createdAt: "2026-06-06T14:00:02Z",
        attachments: [],
      },
      {
        id: "message-attachment",
        conversationId: "conversation-1",
        direction: "customer_to_employee",
        body: "Please see attached\nAttachment 1 (image/png): https://files.example/proof.png",
        fromPhone: "+15550000001",
        toPhone: "+13852208404",
        twilioMessageSid: "SMattachment",
        deliveryStatus: "delivered",
        deliveryErrorCode: null,
        deliveryErrorMessage: null,
        clientRequestId: null,
        createdAt: "2026-06-06T14:00:02Z",
        attachments: [
          {
            url: "https://files.example/proof.png",
            contentType: "image/png",
            kind: "image",
          },
        ],
      },
    ];
    if (requestCounts.detail > 1) {
      messages.push({
        id: "message-4",
        conversationId: "conversation-1",
        direction: "customer_to_employee",
        body: "New automatic customer message",
        fromPhone: "+15550000001",
        toPhone: "+13852208404",
        twilioMessageSid: "SMnew",
        deliveryStatus: "delivered",
        deliveryErrorCode: null,
        deliveryErrorMessage: null,
        clientRequestId: null,
        createdAt: "2026-06-06T14:00:03Z",
        attachments: [],
      });
    }
    await route.fulfill({
      contentType: "application/json",
      json: {
        conversation: {
          ...conversation,
          status: conversationStatus,
          assignedEmployee: "+15551234567",
          createdAt: "2026-06-06T14:00:00Z",
        },
        messages,
        calls,
        suggestedReply: "Please send size and deadline.",
      },
    });
  });

  await page.route("**/api/conversations/conversation-2", async (route) => {
    requestCounts.detail += 1;
    await route.fulfill({
      contentType: "application/json",
      json: {
        conversation: {
          ...olderConversation,
          assignedEmployee: "+15551234567",
          createdAt: "2026-06-05T14:00:00Z",
        },
        messages: [
          {
            id: "message-whatsapp-1",
            conversationId: "conversation-2",
            direction: "customer_to_employee",
            body: "Can you follow up on my quote?",
            fromPhone: "+15550000002",
            toPhone: "+13852208404",
            twilioMessageSid: "SMwhatsapp",
            deliveryStatus: "delivered",
            deliveryErrorCode: null,
            deliveryErrorMessage: null,
            clientRequestId: null,
            createdAt: "2026-06-05T14:00:00Z",
            attachments: [],
          },
        ],
        calls: [],
        suggestedReply: "",
      },
    });
  });

  await page.route("**/api/conversations/conversation-started", async (route) => {
    requestCounts.detail += 1;
    await route.fulfill({
      contentType: "application/json",
      json: {
        conversation: {
          ...(startedConversation || conversation),
          assignedEmployee: "+15551234567",
          createdAt: "2026-06-06T14:07:00Z",
        },
        messages: startedMessage ? [startedMessage] : [],
        calls: [],
        suggestedReply: "",
      },
    });
  });

  await page.route("**/api/conversations/start", async (route) => {
    requestCounts.conversationStarts += 1;
    const payload = JSON.parse(route.request().postData() || "{}") as {
      body?: string;
      channel?: "sms" | "whatsapp";
      display_name?: string;
      phone_number?: string;
      client_request_id?: string;
    };
    startConversationPayloads.push(payload);
    startedConversation = {
      ...conversation,
      id: "conversation-started",
      code: "C0003",
      channel: payload.channel || "sms",
      customer: {
        phone: payload.phone_number || "+15550000001",
        displayName: payload.display_name || null,
        lookupName: null,
        name: payload.display_name || "Test Customer",
      },
      lastMessage: {
        ...conversation.lastMessage,
        body: payload.body || "Started conversation",
        direction: "employee_to_customer",
        createdAt: "2026-06-06T14:07:00Z",
      },
      updatedAt: "2026-06-06T14:07:00Z",
    };
    startedMessage = {
      id: "message-started",
      conversationId: "conversation-started",
      direction: "employee_to_customer",
      body: payload.body || "Started conversation",
      fromPhone: "+13852208404",
      toPhone: payload.phone_number || "+15550000001",
      twilioMessageSid: "SMstarted",
      deliveryStatus: "queued",
      deliveryErrorCode: null,
      deliveryErrorMessage: null,
      clientRequestId: payload.client_request_id || null,
      createdAt: "2026-06-06T14:07:00Z",
      attachments: [],
    };
    await route.fulfill({
      contentType: "application/json",
      json: {
        status: "sent",
        sendMode: "freeform",
        templateKey: null,
        contentSid: null,
        conversation: {
          ...startedConversation,
          assignedEmployee: "+15551234567",
          createdAt: "2026-06-06T14:07:00Z",
        },
        message: startedMessage,
      },
    });
  });

  await page.route("**/api/conversations/conversation-1/suggested-reply", async (route) => {
    requestCounts.suggestedReplies += 1;
    await route.fulfill({
      contentType: "application/json",
      json: { suggestedReply: "Fresh generated reply from the latest customer message." },
    });
  });

  await page.route("**/api/conversations/conversation-2/suggested-reply", async (route) => {
    requestCounts.suggestedReplies += 1;
    await route.fulfill({
      contentType: "application/json",
      json: { suggestedReply: "Fresh WhatsApp quote follow-up suggestion." },
    });
  });

  await page.route("**/api/conversations/conversation-1/call", async (route) => {
    requestCounts.callStarts += 1;
    calls.unshift({
      id: "call-new",
      conversationId: "conversation-1",
      direction: "outbound",
      callType: "conversation_call",
      customerPhone: "+15550000001",
      employeePhone: "+15551234567",
      twilioCallSid: "CAnew",
      status: "initiated",
      outcome: null,
      notes: null,
      followUpStatus: "none",
      recap: null,
      transcription: null,
      startedAt: "2026-06-06T14:06:00Z",
      answeredAt: null,
      completedAt: null,
      createdAt: "2026-06-06T14:06:00Z",
      updatedAt: "2026-06-06T14:06:00Z",
    });
    await route.fulfill({
      contentType: "application/json",
      json: {
        status: "calling",
        callSid: "CAnew",
        to: "+15550000001",
        employeePhone: "+15551234567",
      },
    });
  });

  await page.route(/\/api\/calls(?:\?.*)?$/, async (route) => {
    requestCounts.callLists += 1;
    const url = new URL(route.request().url());
    const query = (url.searchParams.get("q") || "").toLowerCase();
    const direction = url.searchParams.get("direction") || "all";
    const offset = Number(url.searchParams.get("offset") || "0");
    const directionMatches = direction === "all" || direction === "outgoing"
      ? (call: typeof calls[number]) => call.direction === "outbound"
      : (call: typeof calls[number]) => call.direction === "inbound";
    const matchingCalls = calls.filter(directionMatches);
    const row = matchingCalls.length
      ? {
        id: "conversation-1",
        conversation: {
          id: "conversation-1",
          code: "C0001",
          status: conversationStatus,
          channel: "sms",
          assignedEmployee: "+15551234567",
          createdAt: "2026-06-06T14:00:00Z",
          updatedAt: "2026-06-06T14:00:00Z",
        },
        customer: conversation.customer,
        latestCall: matchingCalls[0],
        callCount: matchingCalls.length,
        workflowStatus: matchingCalls[0].outcome || matchingCalls[0].followUpStatus === "done" ? "done" : "pending_follow_up",
      }
      : null;
    const rows = row && [row.customer.name, row.customer.phone, row.conversation.code]
      .join(" ")
      .toLowerCase()
      .includes(query)
      ? [row]
      : [];
    await route.fulfill({
      contentType: "application/json",
      json: {
        calls: rows.slice(offset, offset + 50),
        pagination: {
          limit: 50,
          offset,
          nextOffset: null,
          hasMore: false,
        },
      },
    });
  });

  await page.route("**/api/calls/*", async (route) => {
    requestCounts.callUpdates += 1;
    const callId = route.request().url().split("/api/calls/")[1];
    const payload = JSON.parse(route.request().postData() || "{}") as {
      outcome: string | null;
      follow_up_status: string;
      notes: string | null;
      recap: string | null;
      transcription: string | null;
    };
    const callIndex = calls.findIndex((call) => call.id === callId);
    const updatedCall = {
      ...calls[callIndex],
      outcome: payload.outcome,
      followUpStatus: payload.follow_up_status,
      notes: payload.notes,
      recap: payload.recap,
      transcription: payload.transcription,
    };
    calls[callIndex] = updatedCall;
    await route.fulfill({
      contentType: "application/json",
      json: { call: updatedCall },
    });
  });

  await page.route("**/api/quick-responses", async (route) => {
    requestCounts.quickResponses += 1;
    await route.fulfill({
      contentType: "application/json",
      json: {
        quickResponses: [
          {
            id: "missing_job_specs",
            label: "Request missing job specs",
            body: "Please send size and deadline.",
            group: "quick_response",
            channels: ["sms", "whatsapp"],
          },
          {
            id: "shop_hours",
            label: "Shop hours",
            body: "Maya hours\nM-F: 9:00am - 5:30pm | SAT: By Appointment",
            group: "quick_response",
            channels: ["sms", "whatsapp"],
          },
          {
            id: "maya_quote_follow_up",
            label: "Quote follow-up",
            body: "Hi there, following up on your quote request. Reply here with any questions or updates.",
            bodyTemplate: "Hi {customer_name}, following up on your quote request. Reply here with any questions or updates.",
            group: "template_response",
            channels: ["sms", "whatsapp"],
            templateKey: "quote_follow_up",
            variables: [
              {
                key: "customer_name",
                label: "Customer name",
                placeholder: "Customer name",
                required: true,
                defaultValue: "there",
                defaultSource: "customer_name",
              },
            ],
          },
        ],
      },
    });
  });

  await page.route("**/api/operations/status*", async (route) => {
    requestCounts.operationalStatus += 1;
    await route.fulfill({
      contentType: "application/json",
      json: {
        summary: {
          messageFailures: 1,
          callAttention: 1,
          total: 2,
        },
        messageFailures: [
          {
            id: "message-failed",
            conversationId: "conversation-1",
            conversationCode: "C0001",
            customerName: "Test Customer",
            customerPhone: "+15550000001",
            channel: "sms",
            direction: "employee_to_customer",
            bodyPreview: "Your proof is ready.",
            twilioMessageSid: "SMfailed",
            deliveryStatus: "undelivered",
            deliveryErrorCode: "30007",
            deliveryErrorMessage: "Carrier violation",
            createdAt: "2026-06-06T14:00:00Z",
            hint: "Carrier filtering. Check message wording, sender registration, and recent repeated sends.",
          },
        ],
        callAttention: [
          {
            id: "call-existing",
            kind: "recording_missing",
            conversationId: "conversation-1",
            conversationCode: "C0001",
            customerName: "Test Customer",
            customerPhone: "+15550000001",
            direction: "outbound",
            callType: "conversation_call",
            twilioCallSid: "CAexisting",
            status: "completed",
            recordingStatus: null,
            recordingSid: null,
            startedAt: "2026-06-06T14:05:00Z",
            completedAt: "2026-06-06T14:05:49Z",
            createdAt: "2026-06-06T14:05:00Z",
            hint: "The call completed but no recording is attached yet. Confirm recording callbacks and Studio recording settings.",
          },
        ],
      },
    });
  });

  await page.route("**/api/contacts/import", async (route) => {
    requestCounts.contactImports += 1;
    await route.fulfill({
      contentType: "application/json",
      json: {
        created: 1,
        updated: 1,
        skipped: 0,
        invalidRows: [],
      },
    });
  });

  await page.route("**/api/contacts/contact-1", async (route) => {
    requestCounts.contactUpdates += 1;
    const payload = JSON.parse(route.request().postData() || "{}") as {
      displayName?: string | null;
      notes?: string | null;
    };
    contact = {
      ...contact,
      displayName: payload.displayName ?? contact.displayName,
      name: payload.displayName || contact.lookupName || contact.phone,
      notes: payload.notes ?? contact.notes,
    };
    conversation.customer.displayName = contact.displayName;
    conversation.customer.name = contact.name;
    await route.fulfill({
      contentType: "application/json",
      json: {
        contact: {
          id: contact.id,
          phone: contact.phone,
          displayName: contact.displayName,
          lookupName: contact.lookupName,
          name: contact.name,
          notes: contact.notes,
        },
      },
    });
  });

  await page.route(/\/api\/contacts(?:\?.*)?$/, async (route) => {
    requestCounts.contacts += 1;
    const url = new URL(route.request().url());
    const query = (url.searchParams.get("q") || "").toLowerCase();
    const haystack = [contact.name, contact.displayName, contact.lookupName, contact.phone, contact.notes]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
    const items = !query || haystack.includes(query) ? [contact] : [];
    await route.fulfill({
      contentType: "application/json",
      json: {
        items,
        pagination: {
          limit: Number(url.searchParams.get("limit") || "25"),
          offset: Number(url.searchParams.get("offset") || "0"),
          nextOffset: null,
          hasMore: false,
        },
      },
    });
  });

  return {
    ...requestCounts,
    get conversations() {
      return requestCounts.conversations;
    },
    get detail() {
      return requestCounts.detail;
    },
    get me() {
      return requestCounts.me;
    },
    get callStarts() {
      return requestCounts.callStarts;
    },
    get callLists() {
      return requestCounts.callLists;
    },
    get callUpdates() {
      return requestCounts.callUpdates;
    },
    get statusUpdates() {
      return requestCounts.statusUpdates;
    },
    get quickResponses() {
      return requestCounts.quickResponses;
    },
    get contacts() {
      return requestCounts.contacts;
    },
    get contactUpdates() {
      return requestCounts.contactUpdates;
    },
    get contactImports() {
      return requestCounts.contactImports;
    },
    get operationalStatus() {
      return requestCounts.operationalStatus;
    },
    get conversationStarts() {
      return requestCounts.conversationStarts;
    },
    get startConversationPayloads() {
      return startConversationPayloads;
    },
    releaseHeldDetailRequest() {
      releaseHeldDetailRequest?.();
    },
  };
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

test("operator can start a new SMS conversation from a saved customer", async ({ page }) => {
  const requestCounts = await mockMayaRelayApi(page);

  await page.goto("/app/");
  await expect(page.getByRole("article").getByText("Hello")).toBeVisible();

  await page.getByRole("button", { name: /new message/i }).click();
  const drawer = page.getByRole("dialog", { name: "New message" });
  await expect(drawer).toBeVisible();

  await drawer.getByLabel("Find customer").fill("Test");
  const customerResult = drawer.locator(".contact-picker-result", { hasText: "Test Customer" });
  await expect(customerResult).toBeVisible();
  await customerResult.click();

  await expect(drawer.getByLabel("Customer phone")).toHaveValue("+15550000001");
  await expect(drawer.getByLabel("Customer name")).toHaveValue("Test Customer");
  await drawer.getByLabel("Customer phone").fill("+15550000009");
  await expect(drawer.getByLabel("Customer name")).toHaveValue("");
  await drawer.getByLabel("Find customer").fill("Test");
  await expect(customerResult).toBeVisible();
  await customerResult.click();
  await expect(drawer.getByLabel("Customer phone")).toHaveValue("+15550000001");
  await expect(drawer.getByLabel("Customer name")).toHaveValue("Test Customer");
  await drawer.getByRole("textbox", { name: "Message", exact: true }).fill("Hi Test Customer, we can help with your order.");
  await drawer.getByRole("button", { name: /send message/i }).click();

  await expect.poll(() => requestCounts.conversationStarts).toBe(1);
  expect(requestCounts.startConversationPayloads[0]).toMatchObject({
    body: "Hi Test Customer, we can help with your order.",
    channel: "sms",
    display_name: "Test Customer",
    phone_number: "+15550000001",
  });
  await expect(drawer).toBeHidden();
  await expect(page.getByRole("article").getByText("Hi Test Customer, we can help with your order.")).toBeVisible();
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

test("customer profile edits happen from the right-panel pencil without hiding messages", async ({ page }) => {
  const requestCounts = await mockMayaRelayApi(page);

  await page.goto("/app/");
  await expect(page.getByRole("article").getByText("Hello")).toBeVisible();
  await page.getByRole("button", { name: "Details" }).click();

  const editButton = page.getByRole("button", { name: "Edit customer profile" });
  await expect(editButton).toBeEnabled();
  await editButton.click();

  const editor = page.getByRole("dialog", { name: "Edit customer profile" });
  await expect(editor).toBeVisible();
  await editor.getByLabel("Name").fill("Priority Test Customer");
  await editor.getByLabel("Notes").fill("Needs a printed proof before pickup.");
  await editor.getByRole("button", { name: "Save profile" }).click();

  await expect.poll(() => requestCounts.contactUpdates).toBe(1);
  await expect(editor.getByText("Saved customer profile.")).toBeVisible();
  await page.getByRole("button", { name: "Close customer profile editor" }).click();

  await expect(page.getByRole("article").getByText("Hello")).toBeVisible();
  await expect(page.locator(".customer-profile-summary").getByText("Priority Test Customer")).toBeVisible();
  await page.getByRole("button", { name: "View customer notes" }).click();
  await expect(page.getByRole("dialog", { name: "Customer notes" }).getByText("Needs a printed proof before pickup.")).toBeVisible();
  await page.getByRole("button", { name: "Close customer notes" }).click();
});

test("template-aware quick responses appear in the single quick responses list", async ({ page }) => {
  await mockMayaRelayApi(page);

  await page.goto("/app/");
  await expect(page.getByRole("article").getByText("Hello")).toBeVisible();
  await page.getByRole("button", { name: "Details" }).click();

  await expect(page.getByRole("tab", { name: "Quick Responses" })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("button", { name: /Request missing job specs/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /Shop hours/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /Quote follow-up/ })).toBeVisible();
  await page.getByRole("button", { name: /Request missing job specs/ }).click();
  await expect(page.getByLabel("Reply message")).toHaveValue("Please send size and deadline.");
  await page.getByRole("button", { name: "Close details panel" }).click();

  await page.getByRole("button", { name: "Load more" }).click();
  await page.getByRole("button", { name: /Older Customer/ }).click();
  await expect(page.getByRole("article").getByText("Can you follow up on my quote?")).toBeVisible();
  await page.getByRole("button", { name: "Details" }).click();

  await expect(page.getByRole("tab", { name: "Quick Responses" })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("heading", { name: "WhatsApp Drafts" })).toHaveCount(0);
  await page.getByRole("button", { name: /Quote follow-up/ }).click();

  await expect(page.getByRole("dialog", { name: "Quote follow-up" })).toBeVisible();
  await expect(page.getByLabel("Customer name")).toHaveValue("Older Customer");
  await expect(page.getByText("Hi Older Customer, following up on your quote request. Reply here with any questions or updates.")).toBeVisible();
});

test("unified inbox search keeps conversation search and adds contact matches", async ({ page }) => {
  const requestCounts = await mockMayaRelayApi(page);

  await page.goto("/app/");
  await expect(page.getByRole("article").getByText("Hello")).toBeVisible();

  const searchInput = page.getByPlaceholder("Search conversations or contacts...");
  await expect(page.locator(".inbox-panel input[type='search']")).toHaveCount(1);
  await searchInput.fill("proof approvals");

  await expect(page.locator(".contact-search-results", { hasText: "Contacts" })).toBeVisible();
  await expect(page.locator(".contact-result-row", { hasText: "Test Customer" })).toBeVisible();
  await expect(page.locator(".conversation-list > *").first()).toHaveClass(/contact-search-results/);
  await expect.poll(() => requestCounts.contacts).toBeGreaterThan(1);

  await page.locator(".contact-result-row", { hasText: "Test Customer" }).click();

  await expect(page.getByRole("article").getByText("Hello")).toBeVisible();
  await expect(page.getByRole("button", { name: "Call", exact: true })).toBeVisible();
});

test("settings CSV import gives import feedback without moving profile controls into the inbox", async ({ page }) => {
  const requestCounts = await mockMayaRelayApi(page);

  await page.goto("/app/");
  await expect(page.getByRole("article").getByText("Hello")).toBeVisible();

  await page.getByRole("button", { name: "Settings" }).click();
  const settings = page.getByRole("dialog", { name: "Settings" });
  await expect(settings).toBeVisible();
  await expect(settings.getByRole("heading", { name: "Operational status" })).toBeVisible();
  await expect(settings.getByText("Failed Twilio sends")).toBeVisible();
  await expect(settings.getByText("Carrier filtering")).toBeVisible();
  await expect(settings.getByText("Recording missing")).toBeVisible();
  await expect(settings.locator(".status-issue-scroll")).toBeVisible();
  await expect.poll(() => requestCounts.operationalStatus).toBeGreaterThan(0);
  await expect(settings.getByRole("heading", { name: "CSV Import" })).toBeVisible();

  await settings.getByLabel("Contact CSV").setInputFiles({
    name: "contacts.csv",
    mimeType: "text/csv",
    buffer: Buffer.from("phone_number,display_name\n+15550000003,CSV Customer\n"),
  });
  await settings.getByRole("button", { name: "Import contacts" }).click();

  await expect.poll(() => requestCounts.contactImports).toBe(1);
  await expect(settings.getByText("Created 1")).toBeVisible();
  await expect(settings.getByText("Updated 1")).toBeVisible();
  await expect(settings.getByText("Skipped 0")).toBeVisible();
  await expect(page.getByRole("article").getByText("Hello")).toBeVisible();
});

test("calls tab shows grouped call activity and refreshes after starting a call", async ({ page }) => {
  const requestCounts = await mockMayaRelayApi(page);

  await page.goto("/app/");
  await page.getByRole("tab", { name: "Calls" }).click();

  await expect(page.getByPlaceholder("Search calls...")).toBeVisible();
  await expect(page.getByRole("group", { name: "Call direction filter" }).getByRole("button", { name: "outgoing" })).toBeVisible();
  await expect(page.locator(".call-activity-row", { hasText: "Test Customer" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Latest call summary" })).toBeHidden();
  await expect(page.getByRole("heading", { name: "Call timeline" })).toBeVisible();
  await expect(page.locator(".call-timeline-item").first().getByText("45s")).toBeVisible();

  await page.getByRole("tab", { name: "Text" }).click();
  await page.getByRole("button", { name: "Call", exact: true }).click();

  await expect.poll(() => requestCounts.callStarts).toBe(1);
  await expect(page.getByText("Calling Francisco first, then +15550000001.")).toBeVisible();
  await page.getByRole("tab", { name: "Calls" }).click();
  await expect(page.locator(".call-activity-row", { hasText: "initiated" })).toBeVisible();
});

test("calls workspace saves outcome follow-up notes recap and transcription", async ({ page }) => {
  const requestCounts = await mockMayaRelayApi(page);

  await page.goto("/app/");
  await page.getByRole("tab", { name: "Calls" }).click();

  const workspace = page.locator(".call-workspace");
  await expect(workspace.getByRole("heading", { name: "Call details" })).toBeVisible();
  await workspace.getByLabel("Outcome").selectOption("connected");
  await workspace.getByLabel("Follow-up status").selectOption("needed");
  await workspace.getByLabel("Notes").fill("Customer asked for pricing.");
  await workspace.getByLabel("Recap").fill("Reviewed timing and next steps.");
  await workspace.getByLabel("Transcription").fill("Placeholder transcript.");
  await workspace.getByRole("button", { name: "Save call" }).click();

  await expect.poll(() => requestCounts.callUpdates).toBe(1);
  await expect(workspace.getByLabel("Outcome")).toHaveValue("connected");
  await expect(workspace.getByLabel("Follow-up status")).toHaveValue("needed");
});

test("customer messages mark conversations as needing reply", async ({ page }) => {
  await mockMayaRelayApi(page);

  await page.goto("/app/");
  await expect(page.getByRole("button", { name: /Test Customer/ })).toHaveClass(/needs-reply/);

  await page.getByRole("button", { name: "Load more" }).click();

  await expect(page.getByRole("button", { name: /Older Customer/ })).not.toHaveClass(/needs-reply/);
});

test("system relay and AI suggestion messages stay out of the chat timeline", async ({ page }) => {
  await mockMayaRelayApi(page);

  await page.goto("/app/");

  await expect(page.getByRole("article").getByText("Hello")).toBeVisible();
  await expect(page.getByRole("article").getByText("Please send size and deadline.")).toHaveCount(0);
  await expect(page.getByRole("article").getByText(/Reply with #C0001/)).toHaveCount(0);
  await expect(page.getByRole("article").getByText(/https:\/\/files\.example\/proof\.png/)).toHaveCount(0);
  await page.getByRole("button", { name: "Details" }).click();
  await expect(page.getByText("Fresh generated reply from the latest customer message.")).toBeVisible();

  await page.getByRole("button", { name: "Use suggested reply" }).click();
  await expect(page.getByLabel("Reply message")).toHaveValue("Fresh generated reply from the latest customer message.");
  await expect(page.getByText("No AI suggestion is available for this conversation yet.")).toBeVisible();
});

test("selected conversation refreshes new messages automatically", async ({ page }) => {
  await page.addInitScript(() => {
    const originalSetInterval = window.setInterval;
    window.setInterval = ((handler: TimerHandler, timeout?: number, ...args: unknown[]) =>
      originalSetInterval(handler, timeout === 15000 ? 100 : timeout, ...args)) as typeof window.setInterval;
  });
  const requestCounts = await mockMayaRelayApi(page);

  await page.goto("/app/");
  await expect(page.getByRole("article").getByText("Hello")).toBeVisible();
  await expect(page.getByRole("article").getByText("New automatic customer message")).toBeVisible();
  await expect.poll(() => requestCounts.detail).toBeGreaterThan(1);
});

test("message thread scrolls to the newest message", async ({ page }) => {
  const requestCounts = await mockMayaRelayApi(page);

  await page.goto("/app/");
  await page.addStyleTag({ content: ".message-thread { max-height: 160px !important; }" });
  await page.getByRole("button", { name: "Refresh inbox" }).click();
  await expect(page.getByRole("article").getByText("New automatic customer message")).toBeVisible();

  await expect
    .poll(() =>
      page.locator(".message-thread").evaluate((element) => (
        element.scrollTop + element.clientHeight >= element.scrollHeight - 2
      )),
    )
    .toBe(true);
  expect(requestCounts.detail).toBeGreaterThan(1);
});

test("manual inbox refresh pulls new selected messages", async ({ page }) => {
  const requestCounts = await mockMayaRelayApi(page);

  await page.goto("/app/");
  await expect(page.getByRole("article").getByText("Hello")).toBeVisible();
  await page.getByRole("button", { name: "Refresh inbox" }).click();

  await expect(page.getByRole("article").getByText("New automatic customer message")).toBeVisible();
  await expect.poll(() => requestCounts.detail).toBeGreaterThan(1);
});

test("manual inbox refresh forces a fresh detail request while polling is already running", async ({ page }) => {
  await page.addInitScript(() => {
    const originalSetInterval = window.setInterval;
    window.setInterval = ((handler: TimerHandler, timeout?: number, ...args: unknown[]) =>
      originalSetInterval(handler, timeout === 15000 ? 100 : timeout, ...args)) as typeof window.setInterval;
  });
  const requestCounts = await mockMayaRelayApi(page, { holdSecondDetailRequest: true });

  await page.goto("/app/");
  await expect(page.getByRole("article").getByText("Hello")).toBeVisible();
  await expect.poll(() => requestCounts.detail).toBe(2);

  await page.getByRole("button", { name: "Refresh inbox" }).click();

  await expect.poll(() => requestCounts.detail).toBeGreaterThan(2);
  requestCounts.releaseHeldDetailRequest();
});

test("composer accepts dropped files and sends them as reply attachments", async ({ page }) => {
  await mockMayaRelayApi(page);
  let replyRequestBody = "";
  await page.route("**/api/conversations/conversation-1/reply", async (route) => {
    replyRequestBody = route.request().postData() || "";
    await route.fulfill({
      contentType: "application/json",
      json: {
        status: "sent",
        message: {
          id: "message-dropped-file",
          conversationId: "conversation-1",
          direction: "employee_to_customer",
          body: "Uploaded from drag and drop",
          fromPhone: "+13852208404",
          toPhone: "+15550000001",
          twilioMessageSid: "SMdropped",
          deliveryStatus: "pending",
          deliveryErrorCode: null,
          deliveryErrorMessage: null,
          clientRequestId: "drag-drop-request",
          createdAt: "2026-06-06T14:01:00Z",
          attachments: [
            {
              url: "https://files.example/dropped-proof.png",
              contentType: "image/png",
              kind: "image",
            },
          ],
        },
      },
    });
  });

  await page.goto("/app/");
  await expect(page.getByRole("article").getByText("Hello")).toBeVisible();
  await page.locator(".composer").evaluate((element) => {
    const dataTransfer = new DataTransfer();
    dataTransfer.items.add(new File(["fake image"], "dropped-proof.png", { type: "image/png" }));
    element.dispatchEvent(new DragEvent("drop", { bubbles: true, dataTransfer }));
  });

  await expect(page.getByText("dropped-proof.png")).toBeVisible();
  await page.getByRole("button", { name: "Send message" }).click();

  await expect.poll(() => replyRequestBody).toContain("dropped-proof.png");
});

test("closing a conversation requires confirmation and can be undone", async ({ page }) => {
  const requestCounts = await mockMayaRelayApi(page);

  await page.goto("/app/");
  await expect(page.getByRole("article").getByText("Hello")).toBeVisible();
  await expect.poll(() => requestCounts.statusUpdates).toBe(0);

  await page.getByLabel("Close conversation").click();
  const closeDialog = page.getByRole("dialog", { name: "Are you sure you want to close this conversation?" });
  await expect(closeDialog).toBeVisible();
  await page.getByRole("button", { name: "Cancel" }).click();

  await expect.poll(() => requestCounts.statusUpdates).toBe(0);
  await expect(page.getByLabel("Reply message")).toBeEnabled();

  await page.getByLabel("Close conversation").click();
  await closeDialog.getByRole("button", { name: "Close conversation" }).click();

  await expect.poll(() => requestCounts.statusUpdates).toBe(1);
  await expect(page.getByText("Test Customer was closed.")).toBeVisible();
  await expect(page.getByText("This conversation is closed. Reopen it to send a reply.")).toBeVisible();
  await expect(page.getByLabel("Reply message")).toBeDisabled();
  await expect(page.locator(".conversation-list").getByRole("button", { name: /Test Customer/ })).toHaveCount(0);

  await page.getByRole("button", { name: "Undo" }).click();

  await expect.poll(() => requestCounts.statusUpdates).toBe(2);
  await expect(page.getByText("Test Customer was closed.")).toHaveCount(0);
  await expect(page.getByLabel("Reply message")).toBeEnabled();
  await expect(page.locator(".conversation-list").getByRole("button", { name: /Test Customer/ })).toBeVisible();
});

test("closed conversation filter reveals closed rows", async ({ page }) => {
  await mockMayaRelayApi(page);

  await page.goto("/app/");
  await expect(page.getByRole("article").getByText("Hello")).toBeVisible();

  await page.getByLabel("Close conversation").click();
  await page
    .getByRole("dialog", { name: "Are you sure you want to close this conversation?" })
    .getByRole("button", { name: "Close conversation" })
    .click();
  await expect(page.locator(".conversation-list").getByRole("button", { name: /Test Customer/ })).toHaveCount(0);

  await page.getByRole("button", { name: "closed" }).click();

  await expect(page.locator(".conversation-row.status-closed", { hasText: "Test Customer" })).toBeVisible();
});

test("Load more appends the next conversation page", async ({ page }) => {
  const requestCounts = await mockMayaRelayApi(page);

  await page.goto("/app/");
  await expect(page.getByRole("button", { name: /Test Customer/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /Older Customer/ })).toHaveCount(0);

  await page.getByRole("button", { name: "Load more" }).click();

  await expect(page.getByRole("button", { name: /Test Customer/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /Older Customer/ })).toBeVisible();
  await expect.poll(() => requestCounts.conversations).toBe(2);
});

test("conversation search filters loaded rows before server results", async ({ page }) => {
  const requestCounts = await mockMayaRelayApi(page);

  await page.goto("/app/");
  await page.getByRole("button", { name: "Load more" }).click();
  await expect(page.getByRole("button", { name: /Older Customer/ })).toBeVisible();

  await page.getByPlaceholder("Search conversations or contacts...").fill("Older");

  await expect(page.getByRole("button", { name: /Older Customer/ })).toBeVisible({ timeout: 100 });
  await expect(page.getByRole("button", { name: /Test Customer/ })).toHaveCount(0);
  expect(requestCounts.conversations).toBe(2);
});

test("conversation search includes unloaded server matches", async ({ page }) => {
  const requestCounts = await mockMayaRelayApi(page);

  await page.goto("/app/");
  await expect(page.getByRole("button", { name: /Test Customer/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /Older Customer/ })).toHaveCount(0);

  await page.getByPlaceholder("Search conversations or contacts...").fill("Older");

  await expect(page.getByRole("button", { name: /Older Customer/ })).toBeVisible();
  await expect.poll(() => requestCounts.conversations).toBe(2);
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
