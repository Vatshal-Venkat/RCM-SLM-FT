---
title: Payment Posting and Reconciliation
category: payment_posting
source_basis: ASC X12 835 implementation guide; HFMA cash posting best practices; CAQH CORE ERA/EFT operating rules
---

# Payment Posting and Reconciliation

## What is payment posting?

Payment posting is the revenue cycle step in which payments and adjustments received from payers and patients are recorded against the correct patient accounts and claim lines in the practice management or billing system. Each payment is posted with the paid amount, contractual adjustments, patient responsibility (deductible, coinsurance, copay) and any denial codes, so that account balances are accurate and the next action (secondary billing, patient statement, denial follow-up) can start.

## Auto-posting versus manual posting

Auto-posting (electronic posting) loads ERA (835) files directly into the billing system and posts payments and adjustments automatically using the CARC and group codes. Manual posting is used for paper EOBs, patient payments, lockbox checks and exceptions that the auto-posting rules cannot handle. Auto-posting is faster and more accurate but needs exception queues for unmatched claims, takebacks and unusual adjustments.

## Steps in payment posting

1. Receive the remittance (ERA or paper EOB) and the payment (EFT, check or card).
2. Reconcile the deposit to the remittance (EFT-to-ERA reassociation using the trace number).
3. Post payments and contractual adjustments to each claim line.
4. Transfer remaining patient responsibility to the patient balance.
5. Post denials with zero payment and route them to the denial work queue.
6. Bill secondary or tertiary insurance where coverage exists.
7. Identify underpayments by comparing the paid amount with the contracted rate.
8. Balance the daily batch to the bank deposit.

## Posting balance check

For a fully processed claim line: billed amount = paid amount + contractual adjustment + patient responsibility + other adjustments. If the line does not balance, an adjustment or payment is missing or posted incorrectly.

## Why accurate payment posting matters

Posting errors make AR balances wrong, cause incorrect patient statements, hide denials and underpayments, and distort KPIs such as days in AR and net collection rate. Unposted cash delays secondary billing and patient collections.

## Credit balances, recoupments and refunds

A credit balance arises when payments exceed the amount owed, for example a duplicate payment or an overpayment. Overpayments must be refunded to the payer or patient; Medicare requires identified overpayments to be reported and returned within 60 days. A recoupment (takeback) is a payer recovering a prior payment by offsetting it against a later remittance; it must be posted against the original claim.
