// Types mirroring the FastAPI response schemas.

export type Unit = "count" | "usd" | "pct" | "days";

export interface KpiCard {
  key: string;
  label: string;
  unit: Unit;
  better: "up" | "down" | "neutral";
  formula: string;
  value: number | null;
  previous: number | null;
  change: number | null;
  change_kind: "points" | "percent";
}

export interface Period {
  start: string;
  end: string;
}

export interface MonthlyClaims {
  month: string;
  claims: number;
  billed: number;
  adjudicated: number;
  denied: number;
  rejected: number;
  denial_rate: number | null;
  clean_claim_rate: number | null;
  first_pass_resolution_rate: number | null;
}

export interface MonthlyPayments {
  month: string;
  payer_paid: number;
  patient_paid: number;
  total_paid: number;
  payments: number;
}

export interface MonthlyAR {
  month: string;
  as_of: string;
  outstanding_ar: number;
  days_in_ar: number | null;
}

export interface StatusRow {
  status: string;
  count: number;
  billed: number;
  balance: number;
  share_pct: number;
}

export interface DenialReason {
  carc_code: string;
  group_code: string;
  description: string;
  category: string;
  count: number;
  denied_amount: number;
  share_pct: number;
  preventable: boolean;
  appeals_decided: number;
  overturn_rate: number | null;
}

export interface EntityPerformance {
  id: string;
  name: string;
  claims: number;
  billed: number;
  collected: number;
  adjudicated: number;
  denied: number;
  denial_rate: number | null;
  clean_claim_rate: number | null;
  first_pass_resolution_rate: number | null;
  outstanding_ar: number;
  pending_claims: number;
  payment_rate: number | null;
  avg_days_to_adjudicate: number | null;
}

export interface Overview {
  period: Period;
  previous_period: Period;
  kpis: KpiCard[];
  claims_over_time: MonthlyClaims[];
  payments_over_time: MonthlyPayments[];
  ar_over_time: MonthlyAR[];
  status_distribution: StatusRow[];
  top_denial_reasons: DenialReason[];
  payers: EntityPerformance[];
}

export interface DenialsAnalytics {
  period: Period;
  reasons: DenialReason[];
  categories: { category: string; count: number; denied_amount: number; share_pct: number }[];
  over_time: { month: string; denials: number; denied_amount: number; preventable: number; denial_rate: number | null }[];
  by_payer: { id: string; name: string; adjudicated: number; denied: number; denial_rate: number | null }[];
  by_provider: { id: string; name: string; adjudicated: number; denied: number; denial_rate: number | null }[];
}

export interface FilterOptions {
  payers: { id: string; name: string; type: string }[];
  providers: { id: string; name: string; specialty: string }[];
  statuses: string[];
  date_range: { min: string | null; max: string | null };
  as_of: string;
  data_notice: string | null;
}

export interface ClaimSummary {
  claim_id: string;
  patient_id: string;
  provider_id: string;
  provider: string;
  payer_id: string;
  payer: string;
  claim_date: string;
  service_date: string;
  cpt_code: string;
  billed_amount: number;
  allowed_amount: number;
  paid_amount: number;
  balance: number;
  status: string;
  denial_reason_code: string | null;
  denial_category: string | null;
  days_in_ar: number;
}

export interface ClaimList {
  items: ClaimSummary[];
  total: number;
  page: number;
  page_size: number;
  as_of: string;
}

export interface ClaimDetail {
  claim_id: string;
  patient: { patient_id: string; age_band: string; sex: string; state: string; synthetic: boolean };
  provider_id: string;
  provider: string;
  provider_specialty: string;
  payer_id: string;
  payer: string;
  payer_type: string;
  claim_type: string;
  claim_date: string;
  service_date: string;
  adjudication_date: string | null;
  closed_date: string | null;
  cpt_code: string;
  cpt_description: string;
  modifier: string | null;
  units: number;
  icd10_code: string;
  icd10_description: string;
  place_of_service: string;
  requires_authorization: boolean;
  authorization_number: string | null;
  billed_amount: number;
  allowed_amount: number;
  paid_amount: number;
  patient_responsibility: number;
  patient_paid_amount: number;
  contractual_adjustment: number;
  writeoff_amount: number;
  adjustment_total: number;
  balance: number;
  status: string;
  denial_reason_code: string | null;
  denial_reason: string | null;
  denial_category: string | null;
  rejection_reason: string | null;
  submission_count: number;
  was_rejected: boolean;
  was_denied: boolean;
  first_pass_paid: boolean;
  days_in_ar: number;
  timely_filing_days: number;
  days_until_timely_filing: number;
  payments: { source: string; amount: number; payment_date: string; method: string; trace_number: string | null }[];
  denials: {
    carc_code: string; group_code: string; rarc_code: string | null; description: string; category: string;
    denied_amount: number; denial_date: string; preventable: boolean; appeal_status: string;
    appeal_date: string | null; resolution_date: string | null;
  }[];
  history: { status: string; status_date: string; note: string | null }[];
  as_of: string;
}

export interface Source {
  ref: number;
  title: string;
  document: string;
  section: string | null;
  score: number;
  snippet: string;
}

export interface ValidationIssue {
  code: string;
  severity: "info" | "warning" | "error";
  message: string;
}

export interface Validation {
  passed: boolean;
  regenerated: boolean;
  issues: ValidationIssue[];
}

export interface IntentInfo {
  intent: string;
  confidence: number;
  terms: string[];
  entities: Record<string, string[]>;
}

export interface ClaimAnalysis {
  claim_id: string;
  summary: string;
  status: string;
  issues: { severity: "high" | "medium" | "low" | "info"; title: string; detail: string }[];
  recommended_actions: string[];
  confidence: number;
  confidence_label: "high" | "medium" | "low";
  narrative: string;
  narrative_source: "llm" | "rule_based_fallback";
  sources: Source[];
  validation: Validation;
  model: string;
  usage: { prompt_tokens: number; completion_tokens: number };
  timings_ms: { total: number };
}

export interface Health {
  status: "ok" | "degraded";
  app: string;
  components: { llm: { ready: boolean; provider: string }; rag: { ready: boolean } };
}

export interface ModelInfo {
  provider: string;
  name: string;
  loaded: boolean;
  details: Record<string, string | number | boolean | null>;
}

export interface KnowledgeIndex {
  ready: boolean;
  embedding_model: string | null;
  reranker_model: string | null;
  built_at: string | null;
  n_documents: number;
  n_chunks: number;
  documents: { file: string; title: string; category: string | null; source_basis: string | null; chunks: number }[];
}

export interface RagHit {
  chunk_id: string;
  document: string;
  title: string;
  section: string | null;
  text: string;
  score: number;
  dense_score: number;
  lexical_score: number;
}

export interface Filters {
  start_date?: string;
  end_date?: string;
  payer_id?: string[];
  provider_id?: string[];
  status?: string[];
}
