---
title: Claims Processing Lifecycle
category: claims
source_basis: ASC X12 837P/837I, 999, 277CA, 276/277 implementation guides; CMS Medicare Claims Processing Manual; NUCC CMS-1500 and NUBC UB-04 manuals
---

# Claims Processing Lifecycle

## What is a healthcare claim?

A claim is the provider's request to a payer for payment for services delivered to a covered patient. It lists the patient and insured, the rendering and billing providers (NPI and tax ID), dates of service, diagnosis codes (ICD-10-CM), procedure codes (CPT/HCPCS) with modifiers and units, place of service, charges and any authorization number.

## Claim forms and transactions

Professional claims (physicians and other practitioners) use the CMS-1500 paper form or its electronic equivalent, the X12 837P. Institutional claims (hospitals, skilled nursing facilities and other facilities) use the UB-04 (CMS-1450) form or the X12 837I. HIPAA requires electronic submission for most providers billing Medicare.

## Claim lifecycle steps

1. Charge capture and coding: services are documented and coded.
2. Claim creation and scrubbing: the billing system builds the claim and a claim scrubber checks it against edits (required fields, code validity, NCCI edits, payer rules).
3. Submission: the claim is sent, usually through a clearinghouse, as an 837 transaction.
4. Acknowledgment: the clearinghouse and payer return a 999 (syntax acknowledgment) and a 277CA (claim acknowledgment) reporting acceptance or rejection.
5. Adjudication: the payer checks eligibility, benefits, authorization, coding, medical necessity and pricing, then decides to pay, deny or pend the claim.
6. Remittance: the payer sends payment (EFT or check) with an ERA (835) or EOB.
7. Posting and follow-up: the payment is posted; denials, underpayments and unpaid claims are worked; patient responsibility is billed.

## What is a clean claim?

A clean claim is a claim that has no errors or missing information and can be processed by the payer without investigation or requests for additional information. Clean claims are paid faster; Medicare must pay clean claims within 30 days of receipt or owe interest.

## What is a clearinghouse?

A clearinghouse is an intermediary that receives claims from providers, validates and scrubs them, converts them to the payer's required format, routes them to the correct payer, and returns acknowledgments, claim status and ERAs to the provider.

## Claim status inquiry

Providers check the status of a submitted claim with the X12 276 claim status request and 277 response, or through payer portals. Status checks are part of AR follow-up for claims with no response.

## Timely filing limits

Every payer sets a deadline for submitting a claim after the date of service. Medicare requires claims to be filed within 12 months (one calendar year) of the date of service. Commercial and Medicaid limits vary, often 90 to 365 days. Claims filed late are denied (CARC 29) and generally cannot be recovered.

## Adjudication outcomes

A claim can be paid in full, partially paid, denied, or pended (held for more information). Partial payments and denials are explained with CARC and RARC codes on the remittance.
