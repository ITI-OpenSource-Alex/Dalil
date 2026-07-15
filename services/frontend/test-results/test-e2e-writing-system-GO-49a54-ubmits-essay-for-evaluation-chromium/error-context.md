# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: test\e2e\writing-system.spec.ts >> GOA Writing Practice >> submits essay for evaluation
- Location: test\e2e\writing-system.spec.ts:14:7

# Error details

```
Error: expect(locator).toBeVisible() failed

Locator: getByText('Estimated Overall Band')
Expected: visible
Timeout: 5000ms
Error: element(s) not found

Call log:
  - Expect "toBeVisible" with timeout 5000ms
  - waiting for getByText('Estimated Overall Band')

```

```yaml
- complementary:
  - text: G goa
  - navigation:
    - link "Chat":
      - /url: /chat
      - img
      - text: Chat
    - link "Opportunities":
      - /url: "#"
      - img
      - text: Opportunities
    - link "Checklists":
      - /url: "#"
      - img
      - text: Checklists
    - link "IELTS":
      - /url: /exam
      - img
      - text: IELTS
    - link "CV Review":
      - /url: "#"
      - img
      - text: CV Review
    - link "Profile":
      - /url: "#"
      - img
      - text: Profile
  - img
  - text: Free plan
  - heading "Unlock GOA Pro" [level=4]
  - paragraph: Unlimited AI, CV review, IELTS scoring.
  - button "Upgrade →"
  - text: LA
  - paragraph: Lina Ahmadi
  - paragraph: lina.ahmadi@goa.app
- main:
  - heading "GOA Assistant" [level=1]
  - paragraph: Lina Ahmadi • CGPA 3.45 • IELTS 6
  - text: Sync Ready G
  - paragraph: Hi Lina 👋 I've loaded your profile (CGPA 3.45, IELTS 6). Where would you like to start?
  - paragraph: Technology has changed education significantly.
  - text: LA G
  - paragraph
  - heading "IELTS Writing Practice" [level=3]
  - paragraph: Paste or write your essay below.
  - textbox "Write your IELTS essay here...": Technology has changed education significantly.
  - text: 47 characters
  - button "Cancel"
  - button "Submitting..." [disabled]
  - heading "IELTS Writing Evaluation" [level=3]
  - text: Grammatical Range & Accuracy Band 7.0
  - paragraph: Good grammar
  - text: Evaluating essay... GOA can make mistakes. Verify university requirements before applying.
- alert
```

# Test source

```ts
  1  | import { test, expect } from "@playwright/test";
  2  | 
  3  | test.describe("GOA Writing Practice", () => {
  4  |   test.beforeEach(async ({ page }) => {
  5  |     await page.goto("/chat");
  6  |   });
  7  | 
  8  |   test("opens writing mode", async ({ page }) => {
  9  |     await page.getByTitle("Writing Practice").click();
  10 | 
  11 |     await expect(page.getByTestId("essay-input")).toBeVisible();
  12 |   });
  13 | 
  14 |   test("submits essay for evaluation", async ({ page }) => {
  15 |     // Mock the chat endpoint
  16 |     await page.route("**/api/chat", async (route) => {
  17 |       await route.fulfill({
  18 |         status: 200,
  19 |         headers: {
  20 |           "Content-Type": "text/event-stream",
  21 |         },
  22 |         body: [
  23 |           'data: {"type":"writing_url","essayId":"1","sseUrl":"/api/writing/test"}',
  24 |           "",
  25 |           "",
  26 |         ].join("\n"),
  27 |       });
  28 |     });
  29 | 
  30 |     // Mock the writing evaluation stream
  31 |     await page.route("**/api/writing/test", async (route) => {
  32 |       console.log("Writing SSE endpoint hit");
  33 |       await route.fulfill({
  34 |         status: 200,
  35 |         headers: {
  36 |           "Content-Type": "text/event-stream",
  37 |         },
  38 |         body: [
  39 |           'data: {"type":"criterion","criterion":"grammar","band":7,"feedback":"Good grammar"}',
  40 |           "",
  41 |           'data: {"type":"complete","essay_id":"1","overall_band":7,"evaluations":{"grammar":{"band":7,"feedback":"Good grammar"}}}',
  42 |           "",
  43 |         ].join("\n"),
  44 |       });
  45 |     });
  46 | 
  47 |     await page.getByTitle("Writing Practice").click();
  48 | 
  49 |     await page
  50 |       .getByTestId("essay-input")
  51 |       .fill("Technology has changed education significantly.");
  52 | 
  53 |     await page.getByTestId("submit-essay-button").click();
  54 | 
  55 |     // Verify the evaluation panel updates
> 56 |     await expect(page.getByText("Estimated Overall Band")).toBeVisible();
     |                                                            ^ Error: expect(locator).toBeVisible() failed
  57 | 
  58 |     await expect(page.getByText("7.0")).toBeVisible();
  59 | 
  60 |     await expect(page.getByText("Good grammar")).toBeVisible();
  61 | 
  62 |     await expect(page.getByText("Band 7.0")).toBeVisible();
  63 |   });
  64 | });
  65 | 
```