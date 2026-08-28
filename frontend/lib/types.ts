export type Study = {
  id: string;
  name: string;
  research_questions: string[];
  web_search_enabled: boolean;
  created_at: string;
};

export type StudyCreate = {
  name: string;
  research_questions: string[];
  web_search_enabled: boolean;
};

export type StudyUpdate = {
  name?: string;
  research_questions?: string[];
  web_search_enabled?: boolean;
};

export type SourceSummary = {
  id: string;
  study_id: string;
  source_code: string;
  filename: string;
  kind: string;
  respondent_label: string | null;
  status: string;
  error: string | null;
};

export type AnalysisRun = {
  id: string;
  study_id: string;
  thread_id: string;
  status: string;
  created_at: string;
  finished_at: string | null;
  error: string | null;
};

export type RetrievedChunkSummary = {
  chunk_id: string;
  source_code: string;
  respondent_label: string | null;
  position: number;
  text_preview: string;
  score: number;
};

export type AnalysisApprovalPreview = {
  research_question: string;
  subqueries: string[];
  coverage: string | null;
  coverage_note: string;
  respondents_covered: number;
  respondents_total: number;
  missing_dimensions: string[];
  retrieved: Record<string, RetrievedChunkSummary[]>;
};

export type AnalysisRunDetail = AnalysisRun & {
  section_count: number;
  report_path: string | null;
  approval_preview: AnalysisApprovalPreview | null;
};

export type Citation = {
  id: string;
  section_id: string;
  marker: string;
  source_id: string;
  chunk_id: string;
  quoted_text: string;
  verified: boolean;
  verification_note: string | null;
};

export type Section = {
  id: string;
  analysis_run_id: string;
  research_question: string;
  position: number;
  body: string;
  coverage: string;
  coverage_note: string;
  respondents_covered: number;
  respondents_total: number;
  citations: Citation[];
};

export type TabId = "study" | "materials" | "analysis" | "report";
