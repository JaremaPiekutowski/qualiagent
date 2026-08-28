"use client";

import { useCallback, useEffect, useState } from "react";

import {
  getAnalysisRun,
  listAnalysisRuns,
  resumeAnalysisRun,
  streamAnalysisRun,
} from "@/lib/api";
import type { AnalysisRun, AnalysisRunDetail, Study } from "@/lib/types";

type AnalysisPanelProps = {
  study: Study | null;
  onError: (message: string | null) => void;
};

export function AnalysisPanel({ study, onError }: AnalysisPanelProps) {
  const [runs, setRuns] = useState<AnalysisRun[]>([]);
  const [activeRun, setActiveRun] = useState<AnalysisRunDetail | null>(null);
  const [subqueriesText, setSubqueriesText] = useState("");
  const [events, setEvents] = useState<string[]>([]);
  const [isBusy, setIsBusy] = useState(false);

  const refreshRuns = useCallback(async () => {
    if (!study) {
      setRuns([]);
      setActiveRun(null);
      return;
    }
    const loaded = await listAnalysisRuns(study.id);
    setRuns(loaded);
  }, [study]);

  useEffect(() => {
    void refreshRuns().catch((error: unknown) => {
      onError(
        error instanceof Error ? error.message : "Nie udało się pobrać przebiegów",
      );
    });
  }, [onError, refreshRuns]);

  useEffect(() => {
    if (activeRun?.approval_preview) {
      setSubqueriesText(activeRun.approval_preview.subqueries.join("\n"));
    }
  }, [activeRun]);

  if (!study) {
    return (
      <div>
        <h2 className="text-2xl font-semibold text-navy">Analiza</h2>
        <p className="mt-3 text-muted">Najpierw wybierz lub utwórz badanie.</p>
      </div>
    );
  }

  async function handleStart() {
    if (!study) {
      return;
    }
    onError(null);
    setIsBusy(true);
    setEvents([]);
    try {
      const analysisRunId = await streamAnalysisRun(study.id, (event) => {
        if (event.type === "node") {
          setEvents((current) => [...current, `węzeł: ${String(event.node)}`]);
        } else if (event.type === "done") {
          setEvents((current) => [
            ...current,
            `status: ${String(event.status)}`,
          ]);
        } else if (event.type === "error") {
          setEvents((current) => [
            ...current,
            `błąd: ${String(event.detail)}`,
          ]);
        }
      });
      await refreshRuns();
      if (analysisRunId) {
        setActiveRun(await getAnalysisRun(analysisRunId));
      }
    } catch (error) {
      onError(
        error instanceof Error ? error.message : "Nie udało się uruchomić analizy",
      );
    } finally {
      setIsBusy(false);
    }
  }

  async function handleResume(action: "approve" | "revise") {
    if (!activeRun) {
      return;
    }
    onError(null);
    setIsBusy(true);
    try {
      const subqueries =
        action === "revise"
          ? subqueriesText
              .split("\n")
              .map((line) => line.trim())
              .filter(Boolean)
          : undefined;
      const updated = await resumeAnalysisRun(activeRun.id, action, subqueries);
      setActiveRun(updated);
      await refreshRuns();
    } catch (error) {
      onError(
        error instanceof Error ? error.message : "Nie udało się wznowić analizy",
      );
    } finally {
      setIsBusy(false);
    }
  }

  async function handleSelectRun(runId: string) {
    onError(null);
    try {
      setActiveRun(await getAnalysisRun(runId));
    } catch (error) {
      onError(
        error instanceof Error ? error.message : "Nie udało się pobrać przebiegu",
      );
    }
  }

  const preview = activeRun?.approval_preview;

  return (
    <div>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 className="text-2xl font-semibold text-navy">Analiza</h2>
          <p className="mt-2 text-muted">
            Uruchom przebieg, obserwuj postęp i zatwierdź pisanie sekcji.
          </p>
        </div>
        <button
          type="button"
          disabled={isBusy}
          onClick={() => void handleStart()}
          className="rounded-md bg-blue px-4 py-2 font-medium text-white transition hover:bg-navy disabled:opacity-60"
        >
          {isBusy ? "Pracuję…" : "Uruchom analizę"}
        </button>
      </div>

      {events.length > 0 ? (
        <div className="mt-6 rounded-md border border-line bg-cream/40 px-4 py-3 text-sm text-muted">
          <p className="mb-2 font-medium text-navy">Strumień postępu</p>
          <ul className="space-y-1">
            {events.map((event) => (
              <li key={event}>{event}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <div className="mt-6 grid gap-6 lg:grid-cols-[240px_1fr]">
        <div>
          <h3 className="text-sm font-medium tracking-wide text-blue uppercase">
            Przebiegi
          </h3>
          <ul className="mt-3 space-y-2">
            {runs.length === 0 ? (
              <li className="text-muted">Brak przebiegów.</li>
            ) : (
              runs.map((run) => (
                <li key={run.id}>
                  <button
                    type="button"
                    onClick={() => void handleSelectRun(run.id)}
                    className={
                      activeRun?.id === run.id
                        ? "w-full rounded-md bg-navy px-3 py-2 text-left text-sm text-white"
                        : "w-full rounded-md border border-line bg-surface px-3 py-2 text-left text-sm text-navy hover:bg-accent-soft"
                    }
                  >
                    <span className="block font-medium">{run.status}</span>
                    <span className="block text-xs opacity-80">
                      {new Date(run.created_at).toLocaleString()}
                    </span>
                  </button>
                </li>
              ))
            )}
          </ul>
        </div>

        <div>
          {!activeRun ? (
            <p className="text-muted">Wybierz przebieg albo uruchom nowy.</p>
          ) : (
            <div className="space-y-4">
              <p className="text-sm text-muted">
                Status: <span className="font-medium text-navy">{activeRun.status}</span>
                {" · "}
                sekcje: {activeRun.section_count}
              </p>

              {preview ? (
                <div className="space-y-4 rounded-md border border-cyan bg-cream/30 p-4">
                  <div>
                    <h3 className="font-semibold text-navy">Podgląd przed pisaniem</h3>
                    <p className="mt-1 text-sm text-muted">{preview.research_question}</p>
                  </div>
                  <p className="text-sm">
                    Pokrycie: <strong>{preview.coverage}</strong> (
                    {preview.respondents_covered}/{preview.respondents_total}).{" "}
                    {preview.coverage_note}
                  </p>
                  <label className="block text-sm text-muted">
                    Podpytania (możesz poprawić przed wznowieniem)
                    <textarea
                      className="mt-2 min-h-32 w-full rounded-md border border-line bg-surface px-3 py-2 text-navy"
                      value={subqueriesText}
                      onChange={(event) => setSubqueriesText(event.target.value)}
                    />
                  </label>
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      disabled={isBusy}
                      onClick={() => void handleResume("approve")}
                      className="rounded-md bg-navy px-4 py-2 text-white disabled:opacity-60"
                    >
                      Zatwierdź i pisz
                    </button>
                    <button
                      type="button"
                      disabled={isBusy}
                      onClick={() => void handleResume("revise")}
                      className="rounded-md border border-line bg-surface px-4 py-2 text-navy disabled:opacity-60"
                    >
                      Popraw podpytania
                    </button>
                  </div>
                </div>
              ) : null}

              {activeRun.error ? (
                <p className="rounded-md border border-danger/30 px-3 py-2 text-danger">
                  {activeRun.error}
                </p>
              ) : null}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
