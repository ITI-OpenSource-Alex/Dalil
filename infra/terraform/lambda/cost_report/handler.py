"""Weekly AWS cost report for the GOA project (GOA-046).

Queries Cost Explorer for the last seven days, groups spend by the ``Service``
cost-allocation tag, and emails a plain-text summary via SES.

Grouping is by tag rather than by AWS service on purpose. "ECS cost $12" tells
you nothing actionable when nine services share one cluster; "rag cost $12"
does. The Terraform in cost_monitoring.tf is what guarantees the tag exists on
every resource — this handler only reads it back.

Resources with no owning service carry ``Service=shared`` (VPC, NAT, ALB, RDS,
Redis). Anything landing in the untagged bucket is therefore a real tagging gap
and is reported separately rather than being folded into "shared", so it stays
visible instead of quietly becoming someone else's line item.
"""

import datetime
import os

import boto3

PROJECT_TAG = os.environ.get("PROJECT_TAG", "goa")
SERVICE_TAG_KEY = os.environ.get("SERVICE_TAG_KEY", "Service")
SENDER = os.environ["REPORT_SENDER_ADDRESS"]
RECIPIENTS = [
    address.strip()
    for address in os.environ["REPORT_RECIPIENTS"].split(",")
    if address.strip()
]
MONTHLY_BUDGET_USD = float(os.environ.get("MONTHLY_BUDGET_USD", "150"))

# Cost Explorer's own label for spend it cannot attribute to a tag value.
UNTAGGED = f"{SERVICE_TAG_KEY}$"


def _week_window(today: datetime.date) -> tuple[str, str]:
    """Return the [start, end) ISO dates for the previous seven days.

    Cost Explorer treats ``End`` as exclusive, so passing today's date gives a
    window ending at the last complete day.
    """
    return (today - datetime.timedelta(days=7)).isoformat(), today.isoformat()


def _month_to_date_window(today: datetime.date) -> tuple[str, str]:
    return today.replace(day=1).isoformat(), today.isoformat()


def _cost_by_service(client, start: str, end: str) -> dict[str, float]:
    costs: dict[str, float] = {}
    next_token = None

    while True:
        request = {
            "TimePeriod": {"Start": start, "End": end},
            "Granularity": "DAILY",
            "Metrics": ["UnblendedCost"],
            "Filter": {
                "Tags": {
                    "Key": "Project",
                    "Values": [PROJECT_TAG],
                }
            },
            "GroupBy": [{"Type": "TAG", "Key": SERVICE_TAG_KEY}],
        }
        if next_token:
            request["NextPageToken"] = next_token

        response = client.get_cost_and_usage(**request)

        for period in response["ResultsByTime"]:
            for group in period["Groups"]:
                raw_key = group["Keys"][0]
                service = raw_key.split("$", 1)[-1] or "UNTAGGED"
                amount = float(group["Metrics"]["UnblendedCost"]["Amount"])
                costs[service] = costs.get(service, 0.0) + amount

        next_token = response.get("NextPageToken")
        if not next_token:
            return costs


def _total(costs: dict[str, float]) -> float:
    return sum(costs.values())


def _format_report(
    weekly: dict[str, float],
    month_to_date: dict[str, float],
    start: str,
    end: str,
) -> str:
    weekly_total = _total(weekly)
    mtd_total = _total(month_to_date)
    remaining = MONTHLY_BUDGET_USD - mtd_total

    lines = [
        f"GOA weekly AWS cost report — {start} to {end}",
        "",
        f"Week total:          ${weekly_total:,.2f}",
        f"Month to date:       ${mtd_total:,.2f}",
        f"Monthly budget:      ${MONTHLY_BUDGET_USD:,.2f}",
        f"Remaining:           ${remaining:,.2f}",
        "",
        "By service (this week):",
    ]

    if not weekly:
        lines.append("  no tagged spend recorded")
    else:
        for service, amount in sorted(
            weekly.items(), key=lambda item: item[1], reverse=True
        ):
            share = (amount / weekly_total * 100) if weekly_total else 0.0
            label = service if service != "UNTAGGED" else "UNTAGGED (tagging gap)"
            lines.append(f"  {label:<28} ${amount:>8,.2f}  {share:5.1f}%")

    if remaining < 0:
        lines += ["", "*** MONTHLY BUDGET EXCEEDED ***"]
    elif mtd_total > MONTHLY_BUDGET_USD * 0.8:
        lines += ["", "*** Over 80% of the monthly budget consumed ***"]

    if "UNTAGGED" in weekly:
        lines += [
            "",
            "Untagged spend is present. Every resource is expected to carry a",
            "Service tag (shared infrastructure included), so this line means a",
            "resource was created outside Terraform or a module dropped its tags.",
        ]

    return "\n".join(lines)


def handler(event, context):  # noqa: ARG001 - Lambda signature
    today = datetime.datetime.now(datetime.timezone.utc).date()
    explorer = boto3.client("ce")

    week_start, week_end = _week_window(today)
    month_start, month_end = _month_to_date_window(today)

    weekly = _cost_by_service(explorer, week_start, week_end)
    month_to_date = _cost_by_service(explorer, month_start, month_end)
    body = _format_report(weekly, month_to_date, week_start, week_end)

    boto3.client("ses").send_email(
        Source=SENDER,
        Destination={"ToAddresses": RECIPIENTS},
        Message={
            "Subject": {"Data": f"GOA AWS cost report — week ending {week_end}"},
            "Body": {"Text": {"Data": body}},
        },
    )

    return {
        "week_total_usd": round(_total(weekly), 2),
        "month_to_date_usd": round(_total(month_to_date), 2),
        "services_reported": len(weekly),
    }
