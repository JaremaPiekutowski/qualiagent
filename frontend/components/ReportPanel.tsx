"use client";

import { useCallback, useEffect, useState } from "react";

import {
  listAnalysisRuns,
  listSections,
  reportDownloadUrl,
} from "@/lib/api";
import type { AnalysisRun, Section, Study } from "@/lib/types";

type ReportPanelProps = {
  study: Study | null;
  onError: (message: string | null) => void;
};

export function ReportPanel({ study, onError }: ReportPanelProps) {
  const [runs, setRuns] = useState<AnalysisRun[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [sections, setSections] = useState<Section[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  const refresh = useCallback(async () => {
    if (!study) {
      setRuns([]);
      setSelectedRunId(null);
      setSections([]);
      return;
    }
    setIsLoading(true);
    onError(null);
    try {
      const loaded = await listAnalysisRuns(study.id);
      setRuns(loaded);
      const preferred =
        loaded.find((run) => run.status === "completed")?.id ?? loaded[0]?.id ?? null;
      setSelectedRunId((current) =>
        current && loaded.some((run) => run.id === current) ? current : preferred,
      );
    } catch (error) {
      onError(
        error instanceof Error ? error.message : "Nie udało się pobrać przebiegów",
      );
    } finally {
      setIsLoading(false);
    }
  }, [onError, study]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (!selectedRunId) {
      setSections([]);
      return;
    }
    void listSections(selectedRunId)
      .then(setSections)
      .catch((error: unknown) => {
        onError(
          error instanceof Error ? error.message : "Nie udało się pobrać sekcji",
        );
      });
  }, [onError, selectedRunId]);

  if (!study) {
    return (
      <div>
        <h2 className="text-2xl font-semibold text-navy">Raport</h2>
        <p className="mt-3 text-muted">Najpierw wybierz lub utwórz badanie.</p>
      </div>
    );
  }

  const selectedRun = runs.find((run) => run.id === selectedRunId) ?? null;

  return (
    <div>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 className="text-2xl font-semibold text-navy">Raport</h2>
          <p className="mt-2 text-muted">
            Podgląd sekcji, tabela cytowań i pobieranie DOCX.
          </p>
        </div>
        {selectedRun?.status === "completed" ? (
          <a
            href={reportDownloadUrl(selectedRun.id)}
            className="rounded-md bg-blue px-4 py-2 font-medium text-white transition hover:bg-navy"
          >
            Pobierz DOCX
          </a>
        ) : null}
      </div>

      <label className="mt-6 block text-sm text-muted" htmlFor="report-run">
        Przebieg analizy
        <select
          id="report-run"
          className="mt-2 w-full max-w-md rounded-md border border-line bg-surface px-3 py-2"
          value={selectedRunId ?? ""}
          onChange={(event) => setSelectedRunId(event.target.value || null)}
          disabled={isLoading || runs.length === 0}
        >
          {runs.length === 0 ? (
            <option value="">Brak przebiegów</option>
          ) : (
            runs.map((run) => (
              <option key={run.id} value={run.id}>
                {run.status} · {new Date(run.created_at).toLocaleString()}
              </option>
            ))
          )}
        </select>
      </label>

      <div className="mt-8 space-y-8">
        {sections.length === 0 ? (
          <p className="text-muted">
            {selectedRun
              ? "Ten przebieg nie ma jeszcze zapisanych sekcji."
              : "Wybierz ukończony przebieg."}
          </p>
        ) : (
          sections.map((section) => (
            <article key={section.id} className="border-t border-line pt-6">
              <h3 className="text-xl font-semibold text-navy">
                {section.research_question}
              </h3>
              <p className="mt-1 text-sm text-muted">
                Pokrycie: {section.coverage} · respondenci{" "}
                {section.respondents_covered}/{section.respondents_total}
              </p>
              <p className="mt-4 whitespace-pre-wrap text-navy">{section.body}</p>
              {section.citations.length > 0 ? (
                <div className="mt-4 overflow-x-auto">
                  <table className="min-w-full text-left text-sm">
                    <thead>
                      <tr className="border-b border-line text-muted">
                        <th className="py-2 pr-4 font-medium">Marker</th>
                        <th className="py-2 pr-4 font-medium">Fragment</th>
                        <th className="py-2 font-medium">Weryfikacja</th>
                      </tr>
                    </thead>
                    <tbody>
                      {section.citations.map((citation) => (
                        <tr
                          key={citation.id}
                          className={
                            citation.verified
                              ? "border-b border-line/70"
                              : "border-b border-line/70 bg-cream/50"
                          }
                        >
                          <td className="py-2 pr-4 font-mono text-xs">
                            {citation.marker}
                          </td>
                          <td className="py-2 pr-4">{citation.quoted_text}</td>
                          <td className="py-2">
                            {citation.verified ? "OK" : "niezweryfikowany"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : null}
            </article>
          ))
        )}
      </div>
    </div>
  );
}
