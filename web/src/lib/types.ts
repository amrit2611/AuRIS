/**
 * TypeScript types mirroring the FastAPI response shapes in
 * src/auris/api.py. Kept intentionally hand-authored (no OpenAPI
 * codegen yet) to keep the frontend build simple; if the backend
 * models change, update both sides.
 */

export interface HealthResponse {
  status: string;
  api_version: string;
}

export interface PerCheckCounts {
  duplicates: number;
  anomalies: number;
  missing: number;
  high_frequency: number;
  amount_deviation: number;
}

export interface AnalysisMetrics {
  total_transactions: number;
  unique_vendors: number;
  flagged_pool_unique: number;
  priority_queue_count: number;
  total_flagged_amount: number;
  top_score: number;
  median_score: number;
}

export interface ColumnMappingInfo {
  used: boolean;
  mapping: Record<string, string | null>;
}

export interface ScoredRow {
  invoice_id: string | number;
  vendor: string;
  amount: number | null;
  date: string;
  risk_score: number;
  reasons: string; // serialised "A; B; C" from FastAPI
  [key: string]: unknown;
}

export interface ReportRow {
  invoice_id: string | number;
  vendor: string;
  amount: number | null;
  date: string;
  risk_type: string;
  [key: string]: unknown;
}

export interface AnalysisResponse {
  metrics: AnalysisMetrics;
  per_check_counts: PerCheckCounts;
  column_mapping: ColumnMappingInfo;
  scored_rows: ScoredRow[];
  report_rows: ReportRow[];
}

export interface SummarizeRequest {
  report_rows: ReportRow[];
  scored_rows?: ScoredRow[] | null;
}

export interface SummarizeResponse {
  summary_markdown: string;
}

export interface AurisConfig {
  anomaly_quantile: number;
  vendor_frequency_quantile: number;
  deviation_low_multiplier: number;
  deviation_high_multiplier: number;
  ml_contamination: number;
  ml_n_estimators: number;
  ml_random_state: number;
  summary_model: string;
  summary_max_tokens: number;
  duplicate_weight: number;
  anomaly_weight: number;
  deviation_weight: number;
  missing_weight: number;
  frequency_weight: number;
  ml_weight: number;
}
