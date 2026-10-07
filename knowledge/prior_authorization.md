---
title: Prior Authorization
category: front_end
source_basis: ASC X12 278 implementation guide; CMS Interoperability and Prior Authorization Final Rule (CMS-0057-F); AMA prior authorization guidance
---

# Prior Authorization

## What is prior authorization?

Prior authorization (also called preauthorization, precertification or prior approval) is the requirement that a provider obtain approval from the patient's health plan before delivering a specific service, procedure, medication or item, for the plan to cover it. The payer reviews medical necessity and coverage against its policies and issues an approval with an authorization number, a denial, or a request for more information. Common examples include advanced imaging (MRI, CT, PET), elective surgery, inpatient admissions, specialty drugs, durable medical equipment and some therapies.

## Why prior authorization matters to the revenue cycle

Services delivered without a required authorization are typically denied (CARC 197 precertification/authorization absent, or CARC 15 authorization number missing or invalid) and are often unrecoverable, because many payers do not allow retroactive authorization. Missing authorizations are one of the most common preventable causes of denials.

## Prior authorization workflow

1. Check whether the payer requires authorization for the CPT/HCPCS code, diagnosis and site of service.
2. Gather clinical documentation supporting medical necessity.
3. Submit the request through the payer portal, by phone or fax, or electronically using the X12 278 transaction or the payer's prior authorization API.
4. Track the request until a decision; respond to requests for additional information.
5. Record the authorization number, approved units and validity dates on the patient account.
6. Put the authorization number on the claim and verify the service delivered matches what was approved (codes, units, dates, provider and location).

## Referral versus prior authorization

A referral is an order from the primary care physician sending the patient to a specialist, required by some HMO plans. Prior authorization is the payer's approval for a specific service. A visit can require both.

## Regulatory timelines

Under the CMS Interoperability and Prior Authorization Final Rule (CMS-0057-F), impacted payers (Medicare Advantage, Medicaid, CHIP and qualified health plans on the federal exchanges) must, beginning in 2026, send prior authorization decisions within 72 hours for expedited (urgent) requests and within 7 calendar days for standard requests, and must give a specific reason when they deny a request.
