# GOA-046 — actions required from the AWS account owner

**Account:** `114403655381` (eu-west-1)
**Requesting user:** `arn:aws:iam::114403655381:user/mounir`
**Date raised:** 2026-08-05
**Completed by account owner:** 2026-08-07 — see addendum at the bottom of this file.

---

## Summary

The GOA project's cost-monitoring work (ticket GOA-046) is complete in code and
partly deployed. Four of its requirements cannot be completed by the project
team, because the IAM user the team operates under is explicitly denied access
to AWS billing APIs.

Everything in this document needs **account-owner or billing-administrator**
privileges. Nothing here is blocked on the project team, and nothing here can be
worked around from our side — see "Why we cannot do this ourselves" below.

Estimated time for the owner: **15–20 minutes**, most of it in the Billing
console.

---

## The blocker

The user carries an explicit deny via the policy
`arn:aws:iam::114403655381:policy/DenyBillingAccess`:

```
$ aws budgets describe-budgets --account-id 114403655381
An error occurred (AccessDeniedException) when calling the DescribeBudgets
operation: User: arn:aws:iam::114403655381:user/mounir is not authorized to
perform: budgets:ViewBudget on resource: arn:aws:budgets::114403655381:budget/*
with an explicit deny in an identity-based policy:
arn:aws:iam::114403655381:policy/DenyBillingAccess
```

```
$ aws ce get-cost-and-usage --time-period Start=2026-05-01,End=2026-08-05 ...
An error occurred (AccessDeniedException) when calling the GetCostAndUsage
operation: User: arn:aws:iam::114403655381:user/mounir is not authorized to
perform: ce:GetCostAndUsage ... with an explicit deny in an identity-based
policy: arn:aws:iam::114403655381:policy/DenyBillingAccess
```

### Why we cannot do this ourselves

In IAM, an **explicit Deny always overrides any Allow**. This means:

- We cannot attach a policy to ourselves to regain the access.
- We cannot create an IAM role with `ce:*` or `budgets:*` and assume it — the
  deny follows the calling principal.
- A Lambda execution role is a _different_ principal and might not inherit the
  deny, but we cannot create and test that safely without first knowing whether
  the deny is enforced at the account level or by an AWS Organizations Service
  Control Policy. **If it is an SCP, no role in the account can be granted these
  permissions at all.**

We have deliberately not probed for a workaround, since attempting to circumvent
an intentional guardrail is not appropriate regardless of whether it would work.

---

## What we ask you to decide first

**Please tell us which of these is true**, because it changes what is possible:

1. The deny exists to stop students from viewing institute-wide billing, and a
   scoped exception for this project's own tagged spend is acceptable.
2. The deny is mandatory (e.g. an Organizations SCP) and no exception is
   possible. _In that case, please just do Option B below and send us the
   output — no permission changes needed at all._

---

## Option A — grant scoped billing read access (preferred)

This is the smallest change that unblocks the work. It grants **read-only**
access to cost data and the ability to manage budgets. It grants **no** ability
to change payment methods, view invoices, or modify the account.

1. Attach the following policy to `user/mounir` (or a role we can assume):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadCostData",
      "Effect": "Allow",
      "Action": ["ce:GetCostAndUsage", "ce:GetCostForecast", "ce:GetTags"],
      "Resource": "*"
    },
    {
      "Sid": "ManageProjectBudget",
      "Effect": "Allow",
      "Action": ["budgets:ViewBudget", "budgets:ModifyBudget", "budgets:CreateBudgetAction", "budgets:DescribeBudgetAction"],
      "Resource": "arn:aws:budgets::114403655381:budget/goa-*"
    }
  ]
}
```

2. **Remove or scope down `DenyBillingAccess`** so it no longer denies the
   actions above. An Allow cannot override a Deny, so leaving the deny in place
   will make step 1 have no effect.

   If the deny must stay for other services, add a condition excluding these
   specific actions, or exclude this principal from the policy's scope.

3. Tell us when it is done. We will then set
   `enable_cost_monitoring = true` in the Terraform and apply it. No further
   involvement needed from you.

---

## Option B — you perform the four actions yourself

If granting access is not acceptable, these four steps produce the same outcome.
All are in the AWS Billing and Cost Management console.

### B1. Activate the cost-allocation tags

**Why:** without this, all the tagging work is invisible to Cost Explorer. AWS
does not report on tags until they are explicitly activated, and activation is
**billing-console only** — there is no API or Terraform resource for it. This
step is required for B2 and B3 to be meaningful.

1. Billing and Cost Management → **Cost allocation tags**
2. Under **User-defined cost allocation tags**, find and select:
   - `Project`
   - `Service`
   - `Environment`
3. Click **Activate**

> Note: activation is not retroactive. Cost data is tagged from the activation
> date forward, so the sooner this is done the more history the reports have.

### B2. Create the monthly budget

**Why:** GOA-046 requires a $150/month budget alerting at 80% and 100%.

1. Billing and Cost Management → **Budgets** → **Create budget**
2. Choose **Customize (advanced)** → **Cost budget**
3. Settings:
   - Name: `goa-monthly`
   - Period: **Monthly**, Recurring
   - Budget amount: **150 USD**
   - Filter: **Tag** → `Project` = `goa`
4. Add **two** alert thresholds, both on **Actual** (not Forecasted):
   - 80% of budgeted amount → email the team
   - 100% of budgeted amount → email the team
5. Recipients: _(the team will supply the address; suggest a shared inbox)_

> We specify Actual rather than Forecasted deliberately. This workload is spiky —
> an ingestion crawl or a load test moves the daily rate by an order of
> magnitude — so forecast alerts fire constantly on projections that never
> happen, and an alert people learn to ignore is worse than no alert.

### B3. Create the Cost Explorer report

**Why:** GOA-046 requires a daily-updated cost breakdown per service.

1. Billing and Cost Management → **Cost Explorer** → **New report**
2. Report type: **Cost and usage**
3. Group by → **Tag** → `Service`
4. Filter → **Tag** → `Project` = `goa`
5. Granularity: **Daily**
6. Save as: `GOA cost by service`

Every GOA resource carries a `Service` tag, including shared infrastructure
(VPC, NAT, load balancers, databases), which is tagged `Service=shared`. So any
spend appearing as **untagged** in this report indicates a resource created
outside our Terraform, and is worth telling us about.

### B4. Send us one Cost Explorer export

**Why:** ticket GOA-040 (Gold Tier evaluation) requires evidence of cost
awareness. A single CSV export is enough and needs no ongoing access.

1. Open the report from B3
2. Set the date range to the **last 3 months**
3. Click **Download as CSV**
4. Send us the file

---

## What is already done and needs nothing from you

For completeness, so it is clear what we are and are not asking for:

| Item                                                           | Status                                                                                                                                        |
| -------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| All AWS resources tagged `Project` / `Service` / `Environment` | **Done and applied.** Enforced via Terraform provider `default_tags`, so a module that forgets to pass tags still produces attributable spend |
| Per-user AI spend tracking and $1/day alert                    | **Done.** Implemented in the application (gateway service), reads its own usage data, needs no AWS billing access                             |
| Budget and cost-report infrastructure as code                  | **Written and reviewed**, committed behind a disabled flag, ready to apply the moment access exists                                           |

---

## Current spend position

For context on urgency: as of 2026-08-05 the account had been running roughly
**$145–160/month** of idle infrastructure — 2 NAT gateways, an ElastiCache
cluster, a load balancer, VPC endpoints and 4 public IPv4 addresses — supporting
an environment with **no container images deployed and no database**, so nothing
was reachable or usable.

That infrastructure has now been destroyed. All of it is reproducible from
Terraform on demand. Expected ongoing spend is now **approximately zero**:
remaining resources are S3 buckets holding a few megabytes, an on-demand
DynamoDB table used for Terraform state locking, and empty ECR repositories.

We could not verify this against Cost Explorer, for the reason this document
exists. **If you are able to check the actual figures, please confirm** — it is
the one thing we cannot see for ourselves.

---

## Addendum — completed by the account owner, 2026-08-07

**We did not action Option A.** It asked us to remove or scope down
`DenyBillingAccess` on `user/mounir`'s group so that user could reach billing
APIs directly. We're not granting additional billing/IAM access to any user or
role — that guardrail stays exactly as it is. It also turned out to be
unnecessary: the account owner has separate admin credentials that were never
subject to that deny, and did all of the following directly.

**B1 — cost allocation tags: done, via CLI, not the console.** AWS has added
`aws ce update-cost-allocation-tags-status`, which this document (correctly,
at the time it was written) said didn't exist. `Project`, `Service`, and
`Environment` are now Active. Since activation isn't retroactive, historical
cost before 2026-08-07 will still show as untagged in tag-filtered reports —
that's expected, not a tagging gap.

**B2 — the `goa-monthly` budget: created via Terraform, not the console.**
$150/month, filtered on `Project=goa`, alerting at 80%/100% of **Actual**
spend, as specified. While wiring this up we found the tag filter in
`cost_monitoring.tf` had a real bug: `"user:Project$${var.project_name}"` does
not interpolate — `$$` only escapes to a literal `$` when it is *not*
immediately followed by `{`, so the filter's value was the literal, unresolved
string `${var.project_name}`, not `goa`. Fixed with `format("user:Project$%s",
var.project_name)` and verified live: the budget's filter now reads
`user:Project$goa`.

This budget and the weekly cost-report Lambda (B3, see below) are **applied
into a separate, isolated Terraform state** (`billing/cost-monitoring.tfstate`
in the same S3 bucket), not the shared `production`/`staging` state. Reason:
`aws_budgets_budget` requires `budgets:ViewBudget` just to refresh on every
`terraform plan`/`apply` — folding it into the shared state would make every
future plan fail for anyone whose IAM identity carries the same billing deny,
breaking the team's Terraform workflow to add a feature that's supposed to be
invisible to them. `enable_cost_monitoring` therefore stays `false` in
`variables.tf` defaults, so the team's ordinary applies are unaffected; the
account owner manages this state directly, out of band.

**B3 — Cost Explorer report: partially replaced, one piece stays manual.**
There is still no public API for the console's saved "reports" UI element
(confirmed while doing this work), so bookmarking `GOA cost by service` in the
Cost Explorer console remains a genuinely manual, ~2-minute step with no
CLI/Terraform alternative — see instructions below if you want it. Everything
it would show is already available without it: the daily-updated, per-service
breakdown is delivered automatically every Monday 08:00 UTC by a Lambda
(`goa-production-cost-report`, this document's existing but previously
unapplied code) that queries `ce:GetCostAndUsage` and emails the result via
SES. One remaining manual step: SES verification was triggered for the sender
address and needs a one-time click on the confirmation email AWS sends —
that's an identity-ownership proof AWS requires from the mailbox itself, no
API can substitute for it.

**B4 — Cost Explorer export: done, via CLI, not the console.**
`reports/goa-cost-by-service-last-3-months.csv` in this repo, generated
directly from `ce get-cost-and-usage`. Because tag activation isn't
retroactive, the last 3 months of history predate tagging, so this export uses
the `SERVICE` dimension instead of the `Service` tag — it answers the "what is
this account actually spending" question B4 exists for, just not split by
GOA's own service taxonomy (that split will be available going forward now
that tags are active).

**Actual current spend, confirmed:** total account cost across the last 3
months is effectively **$0.00** (every line item rounds to zero; net slightly
negative from credits). This confirms the "approximately zero" estimate this
document could not verify for itself.

**Also found and fixed during this audit** (unrelated to the four blocked
items above, but billable and orphaned): 23 CloudWatch alarms, an SNS topic,
an ElastiCache/RDS subnet+parameter group pair, and a stale self-signed ACM
cert — all leftover from the earlier `terraform destroy` and not tracked in
any Terraform state (confirmed empty). Deleted; all are reproducible from the
existing `elasticache`/`rds` modules on the next `terraform apply` for
staging.

### The one remaining manual step

**Bookmark the Cost Explorer report** (optional — the weekly emailed report
already covers the same data):
1. Billing and Cost Management → Cost Explorer → New report → Cost and usage
2. Group by Tag → `Service`; Filter → Tag → `Project` = `goa`; Granularity: Daily
3. Save as `GOA cost by service`

**Click the SES verification email** sent to `ahmeddorgham779@gmail.com` —
until then, the weekly Lambda will run successfully but its `SendEmail` call
will fail (visible in its CloudWatch Logs), since SES cannot send *from* an
unverified identity.
