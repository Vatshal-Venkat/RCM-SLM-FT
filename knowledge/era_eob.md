---
title: ERA and EOB - Remittance Documents
category: remittance
source_basis: ASC X12 005010X221A1 (835) implementation guide; CMS Medicare remittance advice guidance; CAQH CORE EFT/ERA operating rules
---

# ERA and EOB - Remittance Documents

## What is an ERA (Electronic Remittance Advice)?

An ERA (Electronic Remittance Advice) is the electronic explanation of payment that a health plan (payer) sends to a provider after adjudicating a claim. It is transmitted as the HIPAA-standard ASC X12 835 Health Care Claim Payment/Advice transaction. For every claim and service line it reports the billed amount, allowed amount, paid amount, patient responsibility (deductible, coinsurance, copay) and every adjustment, each explained with a Claim Adjustment Reason Code (CARC), an adjustment group code, and where needed a Remittance Advice Remark Code (RARC).

Providers use ERAs to auto-post payments and adjustments to patient accounts, identify denials, and reconcile deposits. The ERA is the electronic counterpart of the paper remittance advice (for Medicare, the Standard Paper Remittance).

## What is an EOB (Explanation of Benefits)?

An EOB (Explanation of Benefits) is a statement from a health plan explaining how a claim was processed: the services billed, the amount the plan allowed, what the plan paid, and the amount the member may owe. EOBs are sent primarily to the patient (the insured member). An EOB is not a bill. Providers may also receive paper EOBs from payers that do not send ERAs, and they are used for manual payment posting and for billing secondary insurance. Medicare beneficiaries receive a Medicare Summary Notice (MSN) instead of an EOB.

## Difference between an ERA and an EOB

- Audience: an ERA is sent to the provider (or its billing agent); an EOB is sent mainly to the patient.
- Format: an ERA is an electronic X12 835 transaction; an EOB is usually a paper or PDF document.
- Content: an ERA can batch many claims for one payment and carries machine-readable CARC/RARC codes; an EOB describes one member's claim in plain language.
- Use: providers auto-post ERAs into the practice management system; patients use EOBs to understand coverage and what they owe.
- Both explain the same adjudication result: billed, allowed, paid, adjusted and patient-responsibility amounts.

## ERA structure and key segments

An 835 file contains: the payment header with the payment method and amount (BPR segment) and a trace number (TRN) used to match the ERA to its EFT deposit; one CLP segment per claim with the claim status code, charge, payment and patient responsibility; CAS segments with adjustment group codes and CARCs; SVC segments for service-line detail; and LQ segments for RARCs. Claim status code 1 means processed as primary, 2 processed as secondary, 4 denied, and 22 a reversal of a previous payment.

## ERA and EFT reassociation

Payments usually arrive by Electronic Funds Transfer (EFT, the CCD+ ACH format) separately from the ERA. Reassociation matches each deposit to its ERA using the trace number (TRN02 in the 835, carried in the EFT addenda record). Unmatched EFTs or ERAs delay posting and distort cash reporting. CAQH CORE operating rules require payers to make ERA and EFT available so they can be reassociated.

## Enrolling for ERA

Providers enroll with each payer (often through the clearinghouse) to receive ERAs. Until enrollment is complete, remittances arrive on paper and must be posted manually, which is slower and more error-prone.
