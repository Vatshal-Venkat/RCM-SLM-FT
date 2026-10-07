---
title: Claim Denials and Rejections
category: denial_management
source_basis: X12 Claim Adjustment Reason Code (CARC) and RARC code lists; CMS Medicare Claims Processing Manual Ch. 29 (appeals); HFMA denial management guidance
---

# Claim Denials and Rejections

## What is a claim denial?

A claim denial occurs when a payer has received and adjudicated (processed) a claim and refuses to pay all or part of it. Denials are reported on the remittance (ERA/835 or EOB) with a Claim Adjustment Reason Code (CARC) explaining why. A denied claim exists in the payer's system, so it is resolved by correcting and resubmitting it (a corrected claim) or by filing an appeal, within the payer's deadlines.

## What is a claim rejection?

A claim rejection occurs when a claim fails front-end edits at the clearinghouse or payer and is never accepted into the payer's adjudication system. Typical causes are formatting errors, an invalid or missing member ID, an invalid NPI, missing required fields, or an invalid code. Rejections are reported on acknowledgment transactions (the 999 for syntax errors and the 277CA claim acknowledgment) rather than on a remittance. Because the claim was never processed, a rejected claim is fixed and resubmitted as a new original claim, not appealed.

## Difference between a claim rejection and a denial

- Timing: a rejection happens before adjudication; a denial happens after adjudication.
- Where it is reported: rejections appear on clearinghouse/payer acknowledgments (999, 277CA); denials appear on the ERA (835) or EOB with CARC codes.
- Status: a rejected claim was never accepted by the payer; a denied claim was received and processed.
- Fix: correct and resubmit a rejection as a new claim; correct and resubmit (corrected claim) or appeal a denial.
- Timely filing: a rejected claim does not stop the timely filing clock, so rejections must be worked quickly.

## Hard denials versus soft denials

A soft denial is temporary and can be resolved by supplying missing information, documentation or a corrected claim (for example, CARC 16 claim lacks information). A hard denial is a final determination that results in lost revenue unless a formal appeal succeeds (for example, CARC 29 timely filing expired, or a non-covered service).

## Why might a claim be denied? Common denial reasons

- Eligibility and coverage problems: coverage terminated (CARC 27), patient not identified as an insured (CARC 31), service not covered by this payer (CARC 109).
- Missing or invalid prior authorization: CARC 197 (precertification/authorization absent) and CARC 15 (authorization number missing or invalid).
- Medical necessity: CARC 50 (not deemed a medical necessity by the payer).
- Coding errors: diagnosis inconsistent with procedure (CARC 11), procedure inconsistent with modifier (CARC 4), bundled service (CARC 97).
- Missing information or billing errors: CARC 16.
- Duplicate claim: CARC 18.
- Coordination of benefits: CARC 22 (care may be covered by another payer).
- Timely filing limit expired: CARC 29.
- Documentation required: CARC 252 (an attachment or other documentation is required).

## Claim adjustment group codes

Every adjustment on a remittance carries a group code: CO (Contractual Obligation, the provider must write it off and may not bill the patient), PR (Patient Responsibility, such as deductible PR-1, coinsurance PR-2, copay PR-3), OA (Other Adjustment), and PI (Payer Initiated reduction). CARC 45 (charge exceeds the fee schedule) with group CO is a normal contractual adjustment, not a denial.

## Denial management strategies

1. Capture and categorise every denial by CARC, payer, provider, service and root cause (front-end, coding, clinical, billing).
2. Measure denial rate by payer and reason and trend it monthly to find the largest drivers.
3. Prevent at the front end: real-time eligibility verification, authorization tracking, and complete registration.
4. Strengthen claim scrubbing: add edits for recurring denial causes before submission.
5. Prioritise denial work queues by dollar value and appeal or timely-filing deadline.
6. Appeal with complete documentation (medical records, authorization proof, coding rationale) and track overturn rates.
7. Close the loop: share root-cause findings with registration, coding and clinical documentation teams and with payer contracting.

## Medicare appeal levels

Medicare Part A and B appeals have five levels: (1) redetermination by the Medicare Administrative Contractor, requested within 120 days of receiving the initial determination; (2) reconsideration by a Qualified Independent Contractor, within 180 days; (3) Administrative Law Judge hearing; (4) Medicare Appeals Council review; (5) judicial review in federal district court. Commercial payers set their own appeal deadlines in provider contracts.
