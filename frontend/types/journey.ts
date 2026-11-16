// Types for the patient-journey API (/api/encounters).

export type Speaker = "doctor" | "patient" | "unknown";
export interface Utterance { speaker: Speaker; text: string }

export type Attention = "eligibility" | "consultation" | "sign_off" | "scrub" | "denial" | "patient_payment" | null;
export type CoverageStatus = "covered" | "prior_auth_required" | "not_covered" | "medical_necessity_risk";
export type BillingDecision = "bill_insurance" | "bill_with_abn" | "self_pay" | "do_not_perform";

export interface DoctorOption { id: string; name: string; specialty: string; provider_id: string; provider: string; primary_care: boolean }
export interface PlanOption {
  payer_id: string; payer: string; payer_type: string; plan_name: string; member_id_example: string;
  copay_pcp: number; copay_specialist: number; deductible: number; coinsurance_pct: number;
}
export interface SampleVisit {
  id: string; title: string; summary: string; provider_id: string; doctor_id: string; payer_id: string;
  visit_reason: string; new_patient: boolean; birth_year: number; sex: "F" | "M"; transcript: Utterance[];
}
export interface StageInfo { stage: string; step: number; label: string }
export interface JourneyOptions { doctors: DoctorOption[]; plans: PlanOption[]; samples: SampleVisit[]; stages: StageInfo[] }

export interface Slots { doctor_id: string; day: string; weekend: boolean; slots: { time: string; available: boolean }[] }

export interface EncounterSummary {
  id: string; patient_name: string; doctor: string; specialty: string; provider: string; payer: string; payer_id: string;
  scheduled_at: string; visit_reason: string; stage: string; step: number; attention: Attention; attention_detail: string | null;
  claim_status: string; total_charge: number; payer_paid: number; patient_paid: number; balance: number; sim_day: number;
}

export interface Scorecard {
  encounters: number; closed: number; needs_attention: number; clean_claim_rate: number | null; denial_rate: number | null;
  days_to_cash: number | null; net_collection_rate: number | null; first_pass_resolution: number | null;
  automated_steps: number; human_actions: number; collected: number;
}
export interface EncounterList { items: EncounterSummary[]; scorecard: Scorecard }

export interface Eligibility {
  transaction: string; trace_number: string; payer: string; payer_type: string; member_id: string; service_date: string;
  active: boolean; error_code?: string; error?: string; message: string; plan_name?: string; copay?: number; copay_type?: string;
  deductible?: number; deductible_met?: number; deductible_remaining?: number; coinsurance_pct?: number; oop_max?: number;
}

export interface Diagnosis {
  code: string; description: string; confidence: number; evidence: string | null; rationale: string; kind: string; primary: boolean;
}

export interface SoapNote {
  chief_complaint: string;
  subjective: { hpi: string[]; pertinent_negatives: string[] };
  objective: { vitals: Record<string, string>; exam: string[] };
  assessment: { code: string; description: string }[];
  plan: { orders: string[]; prescriptions: string[]; otc: string[]; instructions: string[]; follow_up: string | null };
  not_coded: { finding: string; reason: string; quote: string }[];
  evidence: { tag: string; label: string; quote: string }[];
  generated_by: string;
}

export interface MdmPart { level: string; why: string }
export interface Coding {
  diagnoses: Diagnosis[];
  em: { problems: MdmPart; data: MdmPart; risk: MdmPart; mdm: string; new_patient: boolean; code?: string; preventive_code?: string };
  warnings: string[];
  evidence: Record<string, string>;
  estimate?: { charge: number; allowed: number; payer: number; patient: number; deductible_applied: number; copay: number; coinsurance: number };
}

export interface CostShare { deductible: number; copay: number; coinsurance: number; self_pay?: number; abn_liability?: number }

export interface ServiceLine {
  line_no: number; code: string; code_system: string; description: string; category: string; modifier: string | null; units: number;
  dx_codes: string[]; charge: number; source: string; confidence: number; evidence: string | null; rationale: string | null;
  coverage_status: CoverageStatus; coverage_reason: string | null; auth_status: string | null; auth_number: string | null;
  billing_decision: BillingDecision; est_payer: number; est_patient: number; line_status: string; allowed: number;
  payer_paid: number; patient_resp: number; adjustment: number; carc: string | null; claim_id: string | null;
  cost_share: CostShare | null;
}

export interface CheckResult { check: string; status: "pass" | "fixed" | "warn" | "fail"; detail: string }
export interface Scrub {
  clean: boolean; checks: CheckResult[]; claim_form: string | null; transaction: string | null; auto_fixes: number;
  billed_lines: number; total_billed: number; note?: string;
}

export interface Submission {
  attempt: number; claim_ref: string; clearinghouse: string;
  steps: { step: string; status: "pass" | "fail"; detail: string }[];
  ack_999: { status: string; detail: string };
  ack_277ca: { status: "accepted" | "rejected"; category_code: string; detail: string; payer_icn?: string; auto_fix?: string };
  x12_837: string;
}

export interface Adjudication {
  outcome?: "paid" | "partially_paid" | "denied"; gates?: { gate: string; status: "pass" | "fail"; detail: string }[];
  denied_lines?: string[]; paid_lines?: string[]; adjudication_date?: string; pended?: boolean; pend_reason?: string; records_sent?: boolean;
}

export interface EraLine {
  line_no: number; code: string; modifier: string | null; billed: number; allowed: number; paid: number; patient_resp: number;
  status: string; adjustments: { code: string; amount: number; text: string }[];
}
export interface Remittance {
  kind: "original" | "appeal"; payment_date: string; eft_trace: string; method: string; total_paid: number; lines: EraLine[];
  x12_835: string; reconciliation: { expected: number; paid: number; variance: number; status: string };
}

export interface Appeal {
  line_no?: number; code?: string; carc?: string; status?: "drafted" | "overturned" | "upheld" | "accepted"; letter?: string;
  assessment?: { recommend: boolean; likelihood: string; found: string[]; reason: string };
  resolutions?: Record<string, { code: string; carc: string; resolution: string }>;
}

export interface Statement {
  statement_date: string; due_date: string; items: { code: string; description: string; amount: number; why: string }[];
  total_patient_responsibility: number; paid_to_date: number; balance_due: number; credit: number;
  payment_options: string[]; portal: string; aging_bucket: string;
}

export interface JourneyEvent {
  id: number; step: number; actor: string; title: string; detail: string | null; level: "info" | "success" | "warning" | "error";
  automated: boolean; sim_day: number; at: string | null;
}

export interface EncounterDetail extends EncounterSummary {
  patient: { name: string; patient_id: string; birth_year: number; sex: string; state: string; new_patient: boolean };
  insurance: { payer_id: string; payer: string; payer_type: string; plan_name: string; member_id: string; member_id_example: string };
  doctor_info: { id: string; name: string; specialty: string; npi: string; primary_care: boolean };
  signed: boolean; submission_count: number;
  eligibility: Eligibility | null;
  checkin: { planned_auth?: { required: boolean; services: string[]; message: string }; checked_in_at?: string; copay_collected?: number } | null;
  transcript: Utterance[]; note: SoapNote | null; coding: Coding | null; scrub: Scrub | null; clearinghouse: Submission[];
  adjudication: Adjudication | null; remittance: Remittance[]; appeal: Appeal | null;
  billing: { statement?: Statement; payments?: { date: string; amount: number; method: string; note: string }[] } | null;
  lines: ServiceLine[];
  totals: { total_charge: number; payer_paid: number; patient_responsibility: number; patient_paid: number; adjustments: number; balance: number };
  metrics: { human_actions: number; automated_steps: number; sim_day: number };
  events: JourneyEvent[];
  result?: { advanced?: boolean; message?: string | null; steps?: string[]; stopped_for?: Attention };
}

export interface CodeSearch {
  services: { code: string; system: string; description: string; charge: number; category: string }[];
  diagnoses: { code: string; description: string }[];
}
