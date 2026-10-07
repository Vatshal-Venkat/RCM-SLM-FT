---
title: Revenue Cycle KPI Definitions
category: kpi
source_basis: HFMA MAP Keys (revenue cycle key performance indicators); MGMA practice benchmarks; platform analytics engine definitions
---

# Revenue Cycle KPI Definitions

Each KPI below includes its standard formula and how this platform's analytics engine calculates it from claims data.

## Days in AR (Days in Accounts Receivable)

Days in AR measures the average number of days it takes to collect payment after services are billed.

Formula: Days in AR = Total accounts receivable balance / Average daily gross charges.
Average daily gross charges = total gross charges for a recent period (commonly the last 90 days) / number of days in that period.

Lower is better. Commonly cited targets are under 40 days, with high performers below 30 days. Rising Days in AR signals slower payment, growing denials, posting backlogs or follow-up gaps.

Platform calculation: outstanding AR at the end of the selected period (reconstructed from billed charges, payments, contractual adjustments and write-offs dated on or before that day) divided by average daily billed charges over the 90 days ending that day.

## Denial Rate

Denial rate is the percentage of adjudicated claims that payers deny.

Formula: Denial rate = (Number of denied claims / Total number of claims adjudicated) x 100.
It can also be measured in dollars: denied charges / total charges adjudicated x 100.

Typical denial rates run around 5-10%; best practice is below 5%.

Platform calculation: claims that were denied in full or in part when adjudicated (including denials later overturned on appeal) divided by all adjudicated claims, by count, for claims submitted in the selected period.

## Clean Claim Rate

Clean claim rate is the percentage of claims that pass all edits and are accepted by the clearinghouse and payer on first submission without any correction.

Formula: Clean claim rate = (Claims accepted on first submission without edits or rejections / Total claims submitted) x 100.

Target: 95% or higher (high performers 98%+). It measures front-end billing quality.

Platform calculation: claims accepted on first submission with no front-end (clearinghouse or payer) rejection, divided by all claims submitted in the selected period.

## First-Pass Resolution Rate (FPRR)

First-pass resolution rate is the percentage of claims that are paid in full or otherwise resolved on the first submission, with no rework, resubmission or appeal.

Formula: FPRR = (Claims resolved on first submission / Total claims adjudicated) x 100.

Target: 90% or higher. Clean claim rate measures acceptance at submission, whereas FPRR measures the adjudication outcome: a claim can be clean (accepted) and still be denied, which lowers FPRR.

Platform calculation: adjudicated claims that were paid on the first submission with no denial, rejection or resubmission, divided by all adjudicated claims.

## Net Collection Rate

Net collection rate measures how much of the collectible revenue (after contractual adjustments) was actually collected.

Formula: Net collection rate = (Total payments / (Total charges - Contractual adjustments)) x 100.

Target: 95% or higher. A low rate indicates revenue lost to denials, write-offs, underpayments or uncollected patient balances.

Platform calculation: total payer and patient payments divided by allowed amount (billed charges minus contractual adjustments) for closed claims.

## Gross Collection Rate

Formula: Gross collection rate = (Total payments / Total gross charges) x 100. It depends heavily on the provider's charge master and payer contracts, so it is less useful for comparing organisations than net collection rate.

## Payment Rate

Platform calculation: total paid amount / total billed amount x 100. It shows the share of billed charges converted to cash across all claims.

## AR Over 90 Days

Formula: Percentage of AR over 90 days = (AR balance older than 90 days / Total AR balance) x 100. A common target is below 10-15%. Aged AR is harder to collect and may breach timely filing or appeal limits.

## Average Claim Value

Formula: Average claim value = Total billed amount / Number of claims.

## Charge Lag

Charge lag is the number of days between the date of service and the date the charge is entered or the claim is submitted. Long charge lag delays cash and increases timely filing risk.
