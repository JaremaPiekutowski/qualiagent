import type {
  AnalysisRun,
  AnalysisRunDetail,
  Section,
  SourceSummary,
  Study,
  StudyCreate,
  StudyUpdate,
} from "./types";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

async function parseError(response: Response): Promise<string> {
  try {
    const payload = await response.json();
    if (typeof payload.detail === "string") {
      return payload.detail;
    }
    return JSON.stringify(payload.detail ?? payload);
  } catch {
    return response.statusText || `HTTP ${response.status}`;
  }
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, init);
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export async function listStudies(): Promise<Study[]> {
  return requestJson<Study[]>("/studies");
}

export async function createStudy(payload: StudyCreate): Promise<Study> {
  return requestJson<Study>("/studies", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function updateStudy(
  studyId: string,
  payload: StudyUpdate,
): Promise<Study> {
  return requestJson<Study>(`/studies/${studyId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function listSources(studyId: string): Promise<SourceSummary[]> {
  return requestJson<SourceSummary[]>(`/studies/${studyId}/sources`);
}

export async function uploadSources(
  studyId: string,
  files: File[],
  respondentLabels: string[],
): Promise<SourceSummary[]> {
  const formData = new FormData();
  for (const file of files) {
    formData.append("files", file);
  }
  for (const label of respondentLabels) {
    formData.append("respondent_labels", label);
  }

  const response = await fetch(`${API_BASE_URL}/studies/${studyId}/sources`, {
    method: "POST",
    body: formData,
  });
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return (await response.json()) as SourceSummary[];
}

export async function listAnalysisRuns(studyId: string): Promise<AnalysisRun[]> {
  return requestJson<AnalysisRun[]>(`/studies/${studyId}/analysis-runs`);
}

export async function getAnalysisRun(
  analysisRunId: string,
): Promise<AnalysisRunDetail> {
  return requestJson<AnalysisRunDetail>(`/analysis-runs/${analysisRunId}`);
}

export async function startAnalysisRun(
  studyId: string,
): Promise<AnalysisRunDetail> {
  return requestJson<AnalysisRunDetail>(`/studies/${studyId}/analysis-runs`, {
    method: "POST",
  });
}

export async function resumeAnalysisRun(
  analysisRunId: string,
  action: "approve" | "revise",
  subqueries?: string[],
): Promise<AnalysisRunDetail> {
  return requestJson<AnalysisRunDetail>(
    `/analysis-runs/${analysisRunId}/resume`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action, subqueries }),
    },
  );
}

export async function listSections(analysisRunId: string): Promise<Section[]> {
  return requestJson<Section[]>(`/analysis-runs/${analysisRunId}/sections`);
}

export function reportDownloadUrl(analysisRunId: string): string {
  return `${API_BASE_URL}/analysis-runs/${analysisRunId}/report.docx`;
}

export async function streamAnalysisRun(
  studyId: string,
  onEvent: (event: Record<string, unknown>) => void,
): Promise<string | null> {
  const response = await fetch(
    `${API_BASE_URL}/studies/${studyId}/analysis-runs/stream`,
    { method: "POST" },
  );
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  if (!response.body) {
    throw new Error("Brak strumienia odpowiedzi");
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let analysisRunId: string | null = null;
  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() ?? "";
    for (const part of parts) {
      const line = part
        .split("\n")
        .find((entry) => entry.startsWith("data: "));
      if (!line) {
        continue;
      }
      const event = JSON.parse(line.slice(6)) as Record<string, unknown>;
      if (typeof event.analysis_run_id === "string") {
        analysisRunId = event.analysis_run_id;
      }
      onEvent(event);
    }
  }
  return analysisRunId;
}
