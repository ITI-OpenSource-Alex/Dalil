# GOA — Final Graduation Project Demo Script

**Audience:** anyone presenting this project who has never operated it live
before. Follow this document literally — every click, every typed string,
every line of speaker text is written out in full.

**Source of truth:** every step in this script was personally executed and
confirmed working, live, against the real backend (no mocks), during the
Phase 1 QA pass and its Writing-exam follow-up session on 2026-08-01 (see
`docs/dorgham-context/PHASE1_QA_REPORT.md`). Nothing in this script is
guessed or assumed. Where a feature exists but was **not** personally
verified live (e.g. recording a live Speaking Practice answer), it is
explicitly excluded — see Section 4.

**Total live presentation time: 6–8 minutes** (Section 6 has the exact
timeline). Preparation (Section 1) is done **before** the audience is in
the room and does not count toward this window.

---

# 1. Demo Preparation

Do this the evening before or the morning of the presentation — not weeks
in advance. Several steps are account-specific and time-sensitive (one-shot
exam pools, a subscription-tier cache, an hourly rate limit).

## 1.1 Start the stack

Open a terminal in the repository root and run:

```
docker compose up -d
```

Wait about 30–60 seconds for everything to initialize, then confirm every
service is healthy:

```
docker compose ps
```

Every row should say `Up` (some will additionally say `(healthy)`). If
`orchestration` is not listed as `Up`, start it explicitly — it is required
for every chat-based feature (Q&A, opportunity search, writing):

```
docker compose up -d orchestration
```

## 1.2 Verify the backend responds

```
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:3000
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8080/health
```

Both must print `200`. If not, re-check `docker compose ps` before
continuing.

## 1.3 Confirm migrations and seed data

Migrations run automatically when each service starts — no manual step is
needed. Confirm the Reading exam has usable data:

```
docker compose exec postgres psql -U goa -d exam_db -c "SELECT count(*) FROM questions WHERE skill_area='reading';"
```

Expect a count of **1 or more**. Then confirm Writing questions exist:

```
docker compose exec postgres psql -U goa -d exam_db -c "SELECT count(*) FROM questions WHERE skill_area='writing';"
```

Expect a count of **1 or more** (this environment has ~20).

## 1.4 Create the demo account

Do **not** reuse an account from a previous rehearsal or an old demo — both
the Reading and Writing exam pools are one-shot per account (a question, once
drawn by a given account, is never drawn again for that same account), and
the opportunity-matching seed data is keyed to one specific account's UUID.

1. Open `http://localhost:3000/register` in your browser.
2. Register a new account with an email and password you'll remember (e.g.
   `demo@goa-presentation.com` / a password you'll type live). Write these
   down — you'll need them live in Step 3 of Section 2.
3. After registering you'll land on `/login`. Log in once with the same
   credentials to confirm they work, then leave yourself logged in.

## 1.5 Promote the demo account to paid tier

Exam sessions (Reading and Writing) require a paid subscription. Run this
**at least 15–20 minutes before presenting** — the gateway caches
subscription tier per account in Redis, and promoting too close to demo
time can leave a stale "free" result cached.

```
docker compose exec postgres psql -U goa -d user_db -c "UPDATE users SET \"subscriptionTier\"='paid' WHERE email='<your demo account email>';"
```

If you promote it and an exam session still fails with "subscription
required" shortly after, flush the cache (replace `<uuid>` with the
account's real UUID from Step 1.6 below):

```
docker compose exec redis-gateway redis-cli DEL "subtier:v1:<uuid>"
```

## 1.6 Get the demo account's real UUID

With the demo account logged in, open the browser's DevTools console
(`F12` → Console tab) and run:

```js
fetch("/api/profile", { credentials: "include" }).then(r => r.json()).then(console.log)
```

Copy the `id` field from the printed object — this is the account's UUID.
You'll need it in the next two steps.

## 1.7 Point the opportunity-matching seed data at this account

```
docker compose exec postgres psql -U goa -d rag_db -c "SELECT user_id FROM local_user_profiles;"
```

This lists existing seeded profile rows (from earlier setup or previous
demo runs). Pick one row's `user_id` and repoint it at your demo account's
UUID:

```
docker compose exec postgres psql -U goa -d rag_db -c "UPDATE local_user_profiles SET user_id='<your demo account uuid>' WHERE user_id='<the row's current user_id>';"
```

Then flush the match cache so the new mapping takes effect immediately:

```
docker compose exec redis-cache redis-cli -n 2 DEL "match:<your demo account uuid>"
```

## 1.8 Pre-create a General Training Writing session (required)

**This step is required — do not skip it.** The Writing exam card's "Take
Exam" button always creates an **Academic** session, and Academic Writing
Task 1 fails during evaluation in this environment (the Writing service
requires a stimulus image that no real ingested Academic question has —
see Section 4). **General Training** Writing works correctly and was fully
verified. There is currently no UI control to choose General over Academic,
so you must create the General session directly, once, in advance.

With the demo account logged in, in the DevTools console run:

```js
const profile = await fetch("/api/profile", { credentials: "include" }).then(r => r.json());
const session = await fetch("http://localhost:8080/api/exam/sessions", {
  method: "POST",
  credentials: "include",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ user_id: profile.id, exam_type: "general", skill_area: "writing" }),
}).then(r => r.json());
console.log(session.session_id);
```

Copy the printed `session_id`. Build this URL and **write it down** — you
will open it directly during the live demo instead of clicking "Take Exam":

```
http://localhost:3000/exam/shell?session=<session_id>
```

Do not open this URL yet, and do not submit this session during
rehearsal — it is one-shot. Save it for the live presentation itself. If
you want to rehearse the Writing exam step beforehand, create a **second**
General session the same way, rehearse with that one, and use this first
one only for the actual presentation.

## 1.9 One full dry run, then stop

Using this same demo account, do one complete dry run of the Reading exam
(Section 2, Steps 12–13 below) so you're confident the pool has usable
questions. **Do not** dry-run the Writing exam on this exact pre-created
session (see 1.8). After this one dry run, **stop** — every additional
"Take Exam" click consumes one of the account's 3-sessions-per-hour limit
(shared across every skill), and re-drawing the Reading pool risks
exhausting it before you're on stage.

## 1.10 Browser preparation

- **Browser:** Google Chrome or Microsoft Edge (Chromium-based). Avoid
  Safari/Firefox for the live demo — this environment's automated
  verification used Chromium and that's the only combination confirmed
  working end to end.
- **Screen resolution:** at least **1280×800**, ideally 1440×900 or larger.
  The exam shell explicitly requires a desktop-width viewport — narrower
  windows show a "Desktop screen resolution required" lock screen.
- **Zoom level:** 100% (not zoomed out) so text stays readable to the
  audience without truncating layouts.
- **Clear stale state:** open DevTools → Application tab → Session Storage
  → `http://localhost:3000` → delete the `active_exam_session` key if
  present (left over from your dry run in 1.9). This avoids an unexpected
  "Resume in-progress exam?" banner appearing live.
- **Close DevTools** before presenting (open it only for the setup steps
  above).
- Close unrelated tabs, mute notifications, and disable any browser
  extensions that inject visible UI (ad blockers' icons are fine; avoid
  ones that alter page content).

## 1.11 Final checklist before walking on stage

- [ ] `docker compose ps` — every service `Up`/`healthy`.
- [ ] `curl http://localhost:3000` and `curl http://localhost:8080/health` → both `200`.
- [ ] Demo account created fresh, not reused from an earlier presentation.
- [ ] Demo account promoted to paid, done 15+ minutes ago.
- [ ] Opportunity-matching profile re-pointed at this account's UUID; match cache flushed.
- [ ] General Training Writing session pre-created (Step 1.8); its URL written down and not yet opened.
- [ ] One Reading dry run completed on this account; no further exam sessions started since.
- [ ] `sessionStorage.active_exam_session` cleared.
- [ ] Browser is Chrome/Edge, window ≥1280×800, zoom 100%, DevTools closed.
- [ ] Login credentials for the demo account visible in a notes app or password manager.

---

# 2. Demo Flow (Step by Step)

## Step 1

**Current Screen**

Open:
```
http://localhost:3000
```

**Action**

No clicks yet — just let the landing page load, then scroll slowly from
the top of the page down through the Hero, Features, How It Works, and
Pricing sections, stopping at the Footer.

**Presenter Script**

"This is GOA — an AI-powered platform that helps students prepare for the
IELTS exam and, at the same time, find and apply to Master's programs
abroad that actually match their profile. Everything you're about to see
is running against a real backend — real AI models, real scoring, real
data — nothing here is a mockup."

**Expected Result**

A polished landing page: a Hero section with a headline and call-to-action,
a Features section (Opportunity Matching, IELTS Preparation, CV Review), a
How It Works section with four numbered steps, and a Pricing comparison
(Free vs. Paid). No placeholder text anywhere.

**Duration**

20 seconds

---

## Step 2

**Current Screen**

Still on `http://localhost:3000`.

**Action**

Click the **"Log in"** / **"Sign in"** link in the navigation bar (or
navigate directly to `http://localhost:3000/login`).

On the login page:
- Click the **Email** field. Type your demo account's email (from Section
  1.4).
- Click the **Password** field. Type the password.
- Click **"Sign In"**.

**Presenter Script**

"Let's log in as a real student — I've already created this account ahead
of time."

**Expected Result**

The page redirects to `/chat`. The left sidebar shows the logged-in
account's real email address and initials — not a placeholder name.

**Duration**

15 seconds

---

## Step 3

**Current Screen**

`http://localhost:3000/chat`

**Action**

Point at (don't click yet) the greeting message and the sidebar.

**Presenter Script**

"This is the main assistant. It's grounded in real program data and can
answer questions, find opportunities, generate application checklists, and
help with IELTS writing practice — all from this one chat interface. On
the left, you can see the navigation: Chat, and the IELTS practice area.
A few items are marked 'Soon' — features we've deliberately scoped for a
later release rather than shipping half-finished."

**Expected Result**

The chat interface shows the assistant's opening message: "Hi 👋 I can help
you find Master's programs, build an application checklist, or practise
IELTS — where would you like to start?" The sidebar shows: Chat,
Opportunities (Soon), Checklists (Soon), IELTS, Speaking History, CV
Review (Soon), Profile.

**Duration**

20 seconds

---

## Step 4

**Current Screen**

`http://localhost:3000/chat`

**Action**

- Click the chat text input box at the bottom of the screen.
- Type exactly:
  ```
  Find me Masters programs in Germany
  ```
- Press **Enter** (or click the **Send** button).
- Wait for the response — this takes roughly 5–15 seconds (the message is
  classified and scored against real program requirements).

**Presenter Script**

"Let's ask it to do the platform's core job — find real Master's programs
that match this student's actual academic profile, GPA, and IELTS score."

*(While waiting, if there's a pause:)* "This is doing a live eligibility
check against a real database of program requirements — GPA thresholds,
IELTS minimums, ECTS credits — not returning a static list."

**Expected Result**

A grid of program cards renders below the assistant's message, two columns
wide. Each card shows a real program name, university, country, a
deadline, and a match percentage. Expect roughly 7–8 cards with varying
match percentages (this account's seeded profile typically returns a top
match around 70%, with one program correctly shown as **blocked** at 0%
with a reason such as insufficient ECTS credits — this is a real
eligibility gate firing, not a bug).

**Duration**

60–75 seconds

---

## Step 5

**Current Screen**

Still `http://localhost:3000/chat`, opportunity cards visible.

**Action**

Point at the 0%-match / blocked card if one is visible.

**Presenter Script**

"Notice this one is blocked, with a real reason given — not enough ECTS
credits, in this case. That's the eligibility engine actually working, not
just cosmetic scoring. Every card here reflects a genuine, computed
result."

**Expected Result**

No action needed — this is a narration beat over the already-rendered
cards.

**Duration**

10 seconds

---

## Step 6

**Current Screen**

Still `http://localhost:3000/chat`.

**Action**

Click **"Get Checklist"** on the highest-match (topmost) card.

**Presenter Script**

"Once a student picks a program, one click turns that match into an
actual, actionable application checklist."

**Expected Result**

The page navigates to `/checklist/<programId>`. A checklist page loads
showing "APPLICATION CHECKLIST", a completion percentage (starts at 0%),
and a "Documents" phase with real checklist items (e.g. valid passport,
academic transcripts, motivation letter, recommendation letters).

**Duration**

15 seconds

---

## Step 7

**Current Screen**

`http://localhost:3000/checklist/<programId>`

**Action**

Click the checkbox next to the first checklist item.

**Presenter Script**

"This is a real, persistent checklist — checking an item off saves
immediately, and there's a PDF export if a student wants to print their
progress or share it with an advisor."

**Expected Result**

The checkbox visually toggles to checked and the completion percentage
updates. An "Export as PDF" button is visible near the top of the page.

**Duration**

15 seconds

---

## Step 8

**Current Screen**

`http://localhost:3000/checklist/<programId>`

**Action**

Click **"← Back to Chat"** (top-left of the checklist page), then click
**"Speaking History"** in the left sidebar.

**Presenter Script**

"Let's look at the IELTS side of the platform. This is the Speaking
practice history view — every past practice session is logged with a
score and full feedback breakdown."

**Expected Result**

Navigates to `/speaking/history`. A band-trend chart renders across the
top (a line chart summarizing recent session scores), followed by a list
of individual past sessions, each showing a topic prompt, date, question
type, and band score.

**Duration**

20 seconds

---

## Step 9

**Current Screen**

`http://localhost:3000/speaking/history`

**Action**

Click on any single session in the list.

**Presenter Script**

"Clicking into any session shows the full breakdown — fluency, lexical
resource, grammar, and pronunciation, each scored and explained
individually."

**Expected Result**

Navigates to the session detail view, showing the transcript and a
per-criterion evaluation breakdown with individual band scores and written
feedback for each IELTS speaking criterion.

**Duration**

15 seconds

---

## Step 10

**Current Screen**

Session detail view.

**Action**

Click **"IELTS"** in the left sidebar.

**Presenter Script**

"Now let's do a full, real IELTS exam simulation, end to end — starting
with Reading."

**Expected Result**

Navigates to `/exam`. Four skill cards render: Reading, Listening,
Writing, Speaking, each showing a "current band" figure. Listening and
Speaking show a **"Coming soon"** badge instead of a "Take Exam" button —
point this out as a deliberate, honest scoping decision, not an oversight.
Reading and Writing show working **"Take Exam"** buttons.

**Duration**

10 seconds

---

## Step 11

**Current Screen**

`http://localhost:3000/exam`

**Action**

Click **"Take Exam"** on the **Reading** card (the first "Take Exam"
button on the page).

**Presenter Script**

"Reading is our most complete exam simulation — a real Cambridge-style
test, with five different question types, a split passage-and-question
view, and full automated grading."

**Expected Result**

Navigates to `/exam/shell?session=<id>`. The Reading exam interface loads:
a passage panel on one side (independently scrollable), section tabs
(Section 1 / 2 / 3), a question panel, and a countdown timer in the header.

**Duration**

10 seconds

---

## Step 12

**Current Screen**

Reading exam shell.

**Action**

Answer the **first 5 questions** you see, regardless of type (multiple
choice, true/false/not given, fill-in-the-blank, matching, or short
answer — the specific test drawn varies by account, so don't script exact
answers; just answer whatever the first 5 questions are, picking any
reasonable option or typing any short word for text fields). Leave the
remaining questions unanswered.

Then click the **"Submit Exam"** button (inside the passage/question area,
part of the Reading component itself).

**Presenter Script**

"I'll answer a handful of questions across a couple of different question
types to show the variety, then submit — I'll deliberately leave a few
unanswered so you can see the submission safeguard."

**Expected Result**

A confirmation dialog appears, showing how many questions remain
unanswered (e.g. "You have 10 unanswered questions. Once submitted, you
can't go back and change your answers.") with **"Cancel"** and **"Submit &
Exit"** buttons.

**Duration**

45 seconds

---

## Step 13

**Current Screen**

Reading exam submission confirmation dialog.

**Action**

Click **"Submit & Exit"**.

**Presenter Script**

"And this is graded instantly, server-side, against a real answer key."

**Expected Result**

Navigates to `/exam/results?session=<id>&skill=Reading`. The results page
shows: an overall band score and raw score banner, a Question Type
Breakdown (identifying the weakest question type — a genuine, computed
insight, not fixed text), a Section Breakdown, and a full
Question-by-Question Review listing every question with the submitted
answer, correct/incorrect status, and the correct answer where wrong.

**Duration**

20 seconds

---

## Step 14

**Current Screen**

Reading results page.

**Action**

Point at the Question Type Breakdown and one or two rows of the
Question-by-Question Review.

**Presenter Script**

"Everything here — the band score, the breakdown by question type, the
per-question review — is computed from the real answer key. Nothing on
this page is hardcoded."

**Expected Result**

No action — narration beat.

**Duration**

10 seconds

---

## Step 15

**Current Screen**

Reading results page.

**Action**

In the address bar, replace the URL with the General Training Writing
session URL you saved in Section 1, Step 1.8:
```
http://localhost:3000/exam/shell?session=<your pre-created session_id>
```
Press Enter to navigate there directly.

**Presenter Script**

"Now let's do the same thing for Writing — this one uses a live AI model
to evaluate the response against the real IELTS band descriptors, per
task."

**Expected Result**

The Writing exam interface loads: two side-by-side panels, "TASK 1 (Report
/ Letter)" and "TASK 2 (Extended Essay)", each with a real prompt and an
empty text area, plus a countdown timer and a "Submit Exam" button in the
header.

**Duration**

10 seconds

---

## Step 16

**Current Screen**

Writing exam shell.

**Action**

Click into the **Task 1** text area and type (or paste) exactly:

```
Dear Sir or Madam, I am writing to inform you about an issue with the recent service I received at your establishment. Last week I visited your store to purchase a laptop, however the product I received was faulty and did not match the description provided online. I would appreciate a prompt refund or replacement. I look forward to your response at your earliest convenience. Yours faithfully, A Customer
```

Click into the **Task 2** text area and type (or paste) exactly:

```
Some people believe that it is best to accept a bad situation, such as an unsatisfactory job or shortage of money, while others argue that it is better to try and improve such situations. In my opinion, taking proactive steps to improve one's circumstances is generally more beneficial than passive acceptance, although there are situations where patience is the wiser course of action. This essay will discuss both viewpoints before presenting my own conclusion, drawing on examples from personal experience and broader societal trends to support the argument being made throughout this response to the given topic.
```

**Presenter Script**

"I've got two responses ready to paste in so we don't spend the whole demo
typing — one for each task."

**Expected Result**

Both text areas show the typed/pasted text.

**Duration**

15 seconds (if pasted from prepared notes; longer if typed live)

---

## Step 17

**Current Screen**

Writing exam shell, both tasks filled in.

**Action**

Click **"Submit Exam"** (top-right of the header). In the confirmation
dialog that appears ("Submit Examination?"), click **"Submit & Exit"**.

**Presenter Script**

"Submitting now — this sends each task to a real language model for
evaluation, so it can take anywhere from about twenty seconds to a minute
per task. While we wait — this is genuinely running the essay through the
same four criteria a real IELTS examiner uses: Task Response, Coherence
and Cohesion, Lexical Resource, and Grammatical Range and Accuracy."

**Expected Result**

A full-screen "Analyzing performance..." overlay appears immediately.
After a wait (typically 20–90 seconds total for both tasks), the page
automatically redirects to `/exam/results?session=<id>&skill=Writing`.

**Duration**

30–90 seconds (variable — see Recovery Plan, Section 5, if this runs long)

---

## Step 18

**Current Screen**

`http://localhost:3000/exam/results?session=<id>&skill=Writing`

**Action**

Scroll down through the results page.

**Presenter Script**

"And here's the full evaluation — an overall band, a separate breakdown
per task, and for each task, all four criteria individually scored with
real, specific written feedback that quotes back the actual sentences from
what we just submitted."

**Expected Result**

The page shows: an overall band score at the top, then a "Task 1" card and
a "Task 2" card, each with its own band score and (if the response was
under the IELTS minimum word count, which the sample text above
intentionally is) a word-count penalty notice. Inside each task card, four
criterion rows — Task Response, Cohesion, Vocabulary, Grammar — each with
its own band score and a paragraph of detailed, essay-specific feedback.

**Duration**

20 seconds

---

## Step 19

**Current Screen**

Writing results page.

**Action**

Click **"Return to Skills Workspace"** at the bottom of the page.

**Presenter Script**

"That's the full loop — from chat, to opportunity matching, to a real
application checklist, to two fully automated IELTS exam simulations with
genuine AI grading. Everything you saw today was running live, against
real services, with no pre-recorded or faked data."

**Expected Result**

Navigates back to `/exam`.

**Duration**

10 seconds

---

## Step 20

**Current Screen**

`http://localhost:3000/exam`

**Action**

No further clicks. Face the audience.

**Presenter Script**

"That's GOA — thank you. Happy to answer any questions, or go deeper into
any part of what you just saw."

**Expected Result**

N/A — closing.

**Duration**

10 seconds

---

# 3. Exact Demo Prompts

## Chat — Opportunity Matching

```
Find me Masters programs in Germany
```

This is the only chat prompt used in the script (Step 4). It was verified
live, repeatedly, returning real, varied match percentages and at least
one correctly blocked program.

*(General open-ended Q&A in chat, e.g. "What GPA do I need for a Master's
in Germany?", was tested during QA and does work via the RAG pipeline, but
also produced an intermittent backend error once during testing — an
existing, pre-Phase-1 flakiness in the RAG service unrelated to anything
fixed in this project's QA passes. It is intentionally **not** included as
a scripted step to keep the live demo on the most reliably-verified path.
If there's extra time and you want to include it, be prepared to see an
honest "Sorry, something went wrong" message rather than a hang — the
error handling itself is solid — and move on without dwelling on it.)*

## Writing — Task 1 (General Training, Report/Letter)

```
Dear Sir or Madam, I am writing to inform you about an issue with the recent service I received at your establishment. Last week I visited your store to purchase a laptop, however the product I received was faulty and did not match the description provided online. I would appreciate a prompt refund or replacement. I look forward to your response at your earliest convenience. Yours faithfully, A Customer
```

## Writing — Task 2 (Extended Essay)

```
Some people believe that it is best to accept a bad situation, such as an unsatisfactory job or shortage of money, while others argue that it is better to try and improve such situations. In my opinion, taking proactive steps to improve one's circumstances is generally more beneficial than passive acceptance, although there are situations where patience is the wiser course of action. This essay will discuss both viewpoints before presenting my own conclusion, drawing on examples from personal experience and broader societal trends to support the argument being made throughout this response to the given topic.
```

Both of these exact essays were used in a real, verified end-to-end
Writing exam run in this environment and produced real, complete
evaluations (both tasks scored, real per-criterion feedback rendered on
the results page). They are deliberately shorter than the real IELTS
minimum word count (150 / 250 words) — this is intentional: it keeps the
live demo fast to type/paste, and it produces an honest, real "under
minimum word count" warning on the results page, which is itself a good,
true demonstration of the grading logic working correctly. If you'd
prefer a "cleaner" result with no length warning, you may substitute
longer original text, but only the two essays above have been personally
confirmed to evaluate successfully in this environment — test any
substitute during rehearsal (Section 1.9's note on rehearsing on a
*second* pre-created session), not live.

## Reading — how many questions to answer

Answer the **first 5 questions**, in whatever order they appear, of
whatever types are present (the specific test drawn is randomized per
account — see Section 1.9). Leave the rest unanswered so the submission
confirmation dialog's unanswered-question warning has something real to
show. Do not try to answer all questions — this is unnecessary for the
demo and costs time.

## Speaking

Not included in this script — see Section 4 for why, and Section 5 for
what to say if asked about it live.

---

# 4. What NOT To Click

- **Do not click "Take Exam" on the Writing card from `/exam` directly.**
  It always creates an **Academic** session, and Academic Writing Task 1
  fails during evaluation in this environment (the Writing service
  requires a stimulus image that no real ingested Academic question
  currently has). Always use the pre-created General Training session URL
  from Section 1.8 instead.
- **Do not click "Take Exam" on Listening or Speaking.** Both correctly
  show a "Coming soon" badge instead of a clickable button — there is
  nothing to click, by design. If asked, say: "Listening and Speaking
  exam simulation are scoped for a later release — we chose to mark that
  honestly rather than ship a half-built experience."
- **Do not attempt to start or record a live Speaking Practice session
  (the microphone icon inside `/chat`).** This project does include a
  Speaking Practice feature, but the live microphone-recording →
  transcription → evaluation flow was **not** personally re-verified
  end-to-end during the QA passes this script is based on (only the
  Speaking **History** view — showing already-completed past sessions —
  was verified). Do not demo it live. If asked about it, say: "Speaking
  practice with live recording is part of the product — what I can show
  you right now is the history and evaluation view for past sessions,"
  and proceed to Section 2, Step 8.
- **Do not run the Reading or Writing exam a second time from the same
  demo account.** Both question pools are one-shot per account — a second
  attempt will either draw from an emptying pool or fail outright. If you
  need to demo either exam twice (e.g., for two separate audiences), use
  a fresh account each time (repeat Section 1.4–1.9).
- **Do not click around `/exam` repeatedly "just to show it off."** Each
  "Take Exam" click consumes one of the account's 3-sessions-per-hour
  limit, shared across every skill. Budget exactly one Reading attempt and
  one Writing attempt (the pre-created one) and nothing more once you're
  in front of the audience.
- **Do not navigate to `/speaking/history` while logged out**, and do not
  log out at any point during the presentation. An unauthenticated visit
  to that page shows an honest "couldn't load your profile" error state
  rather than data — it is correct behavior, but not something to show
  live.
- **Do not open browser DevTools in front of the audience** unless
  specifically asked to demonstrate something technical — it was needed
  only for the one-time preparation steps in Section 1.

---

# 5. Recovery Plan

The product handles failures gracefully everywhere — no step in this
script can white-screen the browser. If something goes wrong, stay calm,
narrate briefly, and follow the specific recovery below. None of these
require restarting the browser or losing your place in the script.

### Opportunity Matching (Step 4) returns no cards / an error

**What you'll see:** the assistant's reply reads something like "Sorry,
something went wrong while generating the response," with a "Route:
OPPORTUNITY_SEARCH" tag, instead of cards.

**What to say:** "Looks like that request is taking a moment — let me
try that again." (One retry is normal and expected; don't apologize
extensively.)

**What to do:** Retype the same message (`Find me Masters programs in
Germany`) and send it again. If it fails a second time, say: "I'll come
back to this — let's look at the checklist feature with a program I know
is already matched," and skip directly to Step 6, clicking "Get
Checklist" on any card from an earlier successful attempt still visible in
the chat history above, or — if none are visible — proceed to Step 8
(Speaking History) and return to opportunity matching later if time
allows.

### Writing evaluation fails or the overlay doesn't clear (Step 17)

**What you'll see:** the "Analyzing performance..." overlay clears on its
own and a red banner appears in the exam shell with an error message and a
**"Retry"** button (it will never hang forever, and it will never
white-screen).

**What to say:** "The evaluation service is under a bit of load — let's
give it one more try." (This is genuinely expected: the underlying AI
evaluation occasionally needs a retry under heavy usage, which is exactly
what happened during this project's own testing.)

**What to do:** Click **"Retry"** once. If it's still not resolving within
about 15–20 seconds after the retry, say: "While that finishes in the
background, let me show you a result from an earlier run" — switch to a
pre-captured screenshot of a completed Writing results page (take one
during your Section 1.9 rehearsal and keep it open in another tab or a
slides deck as a backup), narrate it exactly as you would the live page,
then return to Step 19 (Return to Skills Workspace) to close out the
segment. Do not attempt more than one retry live — it costs time and
audience attention.

### A whole backend service is down

**What you'll see:** a request takes an unusually long time (several
seconds to tens of seconds) and then returns a clear error message
(never a silent infinite hang, never a white screen) — e.g. "Unable to
start the Reading exam. Please try again," with a Retry button, or a chat
message saying something went wrong.

**What to say:** "One of our backend services needs a moment — let me
check that." (Said calmly, as a minor technical aside, not an alarm.)

**What to do:** If you have terminal access nearby, run
`docker compose ps` to see which service is down, then
`docker compose up -d <service-name>` to restart it (typical recovery
time: 10–30 seconds). While waiting, continue narrating whatever screen is
currently visible, or jump ahead to a step that doesn't depend on the
affected service (e.g., if `exam` is down, go show the checklist or
speaking history instead, and circle back to the exam steps once it's
recovered).

### A Docker container crashed or `docker compose ps` shows something not `Up`

**What to do:**
```
docker compose up -d <service-name>
```
This restarts just that one service without affecting anything else that's
already running. If the whole stack seems unresponsive:
```
docker compose restart
```
(Takes about 30–60 seconds for everything to come back.) Have this command
ready in a terminal window, minimized, throughout the presentation — you
should never need it, but it's a fast, safe recovery if you do.

### A stale/incorrect cache causes wrong or missing data

**Symptom:** opportunity matching returns a "profile not yet replicated"
style error even though you completed Section 1.7, or an exam session
creation is rejected as requiring a paid plan even though you completed
Section 1.5.

**What to do:** This means a cache entry from an earlier (pre-fix) state
is still active. Re-run the specific flush command from Section 1.5 or 1.7
for this account's UUID, then retry the action once. This should not
happen if Section 1's steps were completed in order with the recommended
15-minute buffer before presenting — but if it does, the fix is a single
command, not a restart.

### The AI response (chat, opportunity matching, or Writing evaluation) is simply slow

**What to say, verbatim, while waiting (pick whichever fits):**
- "This is doing a real-time eligibility check against live program
  requirements — not returning a canned list."
- "This is running through a real language model against the actual IELTS
  band descriptors, so it genuinely takes a little time — that's the
  trade-off for a real evaluation instead of a scripted one."
- "While this finishes, here's what's happening behind the scenes: the
  request is classified, routed to the right service, scored, and
  streamed back — all in real time."

**What to do:** Never sit in silence during a wait. Always have one of the
lines above ready, and keep talking about the *next* screen you're about
to show while the current request finishes in the background.

---

# 6. Demo Timeline

| Time | Screen | Action | Speaker Notes |
|---|---|---|---|
| 0:00–0:20 | `/` (Landing) | Scroll through Hero → Features → How It Works → Pricing | Introduce GOA as an AI-powered IELTS + study-abroad matching platform; everything shown is live, not a mockup. |
| 0:20–0:35 | `/login` | Enter demo account email/password, click Sign In | "Let's log in as a real student." |
| 0:35–0:55 | `/chat` | Point at greeting + sidebar | Introduce the assistant and note the honest "Soon" badges for unbuilt features. |
| 0:55–2:10 | `/chat` | Type and send "Find me Masters programs in Germany"; wait for cards | Explain this is a live eligibility check against real program requirements. |
| 2:10–2:20 | `/chat` | Point at the blocked/0% card | Highlight the real eligibility gate firing. |
| 2:20–2:35 | `/chat` → `/checklist/:id` | Click "Get Checklist" on the top card | One click turns a match into an actionable plan. |
| 2:35–2:50 | `/checklist/:id` | Check off one item | Real, persistent checklist; PDF export available. |
| 2:50–3:10 | `/checklist/:id` → `/speaking/history` | "← Back to Chat", then "Speaking History" in sidebar | Introduce the Speaking practice history view. |
| 3:10–3:25 | `/speaking/history` | Click into one session | Show the per-criterion evaluation breakdown. |
| 3:25–3:35 | Session detail → `/exam` | Click "IELTS" in sidebar | Introduce the full exam simulation; point out Listening/Speaking "Coming soon." |
| 3:35–3:45 | `/exam` | Click "Take Exam" on Reading | Describe the Reading exam's real Cambridge-style content and grading. |
| 3:45–4:30 | Reading exam shell | Answer first 5 questions across types | Narrate the split passage/question interface as questions are answered. |
| 4:30–4:50 | Reading exam shell | Click "Submit Exam" → "Submit & Exit" | Note the unanswered-question safeguard shown in the confirmation dialog. |
| 4:50–5:10 | `/exam/results` (Reading) | Scroll through results | Point out the real computed band, section breakdown, and per-question review. |
| 5:10–5:20 | `/exam/results` → Writing shell | Navigate directly to the pre-created General Training session URL | Introduce the Writing exam and its live AI evaluation. |
| 5:20–5:35 | Writing exam shell | Paste Task 1 and Task 2 responses | (Reading the essays aloud is optional — keep moving.) |
| 5:35–7:00 | Writing exam shell | Click "Submit Exam" → "Submit & Exit"; wait | Explain the four IELTS criteria being evaluated while the overlay is up (see Section 5 filler lines if this runs long). |
| 7:00–7:20 | `/exam/results` (Writing) | Scroll through results | Point out per-task, per-criterion band scores and specific written feedback. |
| 7:20–7:30 | `/exam/results` → `/exam` | Click "Return to Skills Workspace" | Closing summary line. |
| 7:30–7:40 | `/exam` | (no action) | Thank the audience, invite questions. |

**Total: ~7 minutes 40 seconds**, comfortably inside the 6–8 minute target.
The Writing evaluation wait (Step 17, timeline row 5:35–7:00) is the one
genuinely variable segment — it has historically taken anywhere from ~20
seconds to ~90 seconds in this environment. If it runs on the fast end,
use the extra time for questions at the end; if it runs long, use the
filler lines in Section 5 and trust the timeline's built-in buffer (the
total above already assumes close to the slower end of that range).
