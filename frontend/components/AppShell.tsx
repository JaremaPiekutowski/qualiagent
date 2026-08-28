"use client";

import { useCallback, useEffect, useState } from "react";

import { AnalysisPanel } from "@/components/AnalysisPanel";
import { MaterialsPanel } from "@/components/MaterialsPanel";
import { ReportPanel } from "@/components/ReportPanel";
import { StudyPanel } from "@/components/StudyPanel";
import { createStudy, listStudies } from "@/lib/api";
import type { Study, TabId } from "@/lib/types";

const TABS: { id: TabId; label: string }[] = [
  { id: "study", label: "Badanie" },
  { id: "materials", label: "Materiały" },
  { id: "analysis", label: "Analiza" },
  { id: "report", label: "Raport" },
];

export function AppShell() {
  const [studies, setStudies] = useState<Study[]>([]);
  const [selectedStudyId, setSelectedStudyId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<TabId>("study");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const selectedStudy =
    studies.find((study) => study.id === selectedStudyId) ?? null;

  const refreshStudies = useCallback(async (preferStudyId?: string) => {
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const loaded = await listStudies();
      setStudies(loaded);
      setSelectedStudyId((current) => {
        if (preferStudyId && loaded.some((study) => study.id === preferStudyId)) {
          return preferStudyId;
        }
        if (current && loaded.some((study) => study.id === current)) {
          return current;
        }
        return loaded[0]?.id ?? null;
      });
    } catch (error) {
      setErrorMessage(
        error instanceof Error ? error.message : "Nie udało się pobrać badań",
      );
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshStudies();
  }, [refreshStudies]);

  async function handleCreateStudy() {
    setErrorMessage(null);
    try {
      const created = await createStudy({
        name: "Nowe badanie",
        research_questions: [""],
        web_search_enabled: false,
      });
      await refreshStudies(created.id);
      setActiveTab("study");
    } catch (error) {
      setErrorMessage(
        error instanceof Error ? error.message : "Nie udało się utworzyć badania",
      );
    }
  }

  return (
    <div className="mx-auto flex min-h-screen w-full max-w-5xl flex-col px-4 py-8 sm:px-8">
      <header className="mb-8 border-b border-line pb-6">
        <p className="mb-2 text-sm font-medium tracking-[0.18em] text-blue uppercase">
          Analiza jakościowa
        </p>
        <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h1 className="text-4xl font-semibold tracking-tight text-navy sm:text-5xl">
              QualiAgent
            </h1>
            <p className="mt-2 max-w-xl text-base text-muted">
              Badanie, materiały i raport z cytatami zakotwiczonymi w źródłach.
            </p>
          </div>
          <div className="flex flex-col gap-2 sm:items-end">
            <label className="text-sm text-muted" htmlFor="study-select">
              Aktywne badanie
            </label>
            <div className="flex flex-wrap gap-2">
              <select
                id="study-select"
                className="min-w-56 rounded-md border border-line bg-surface px-3 py-2 shadow-[var(--shadow)]"
                value={selectedStudyId ?? ""}
                onChange={(event) => setSelectedStudyId(event.target.value || null)}
                disabled={isLoading || studies.length === 0}
              >
                {studies.length === 0 ? (
                  <option value="">Brak badań</option>
                ) : (
                  studies.map((study) => (
                    <option key={study.id} value={study.id}>
                      {study.name}
                    </option>
                  ))
                )}
              </select>
              <button
                type="button"
                onClick={() => void handleCreateStudy()}
                className="rounded-md bg-blue px-4 py-2 font-medium text-white transition hover:bg-navy"
              >
                Nowe badanie
              </button>
            </div>
          </div>
        </div>
      </header>

      <nav className="mb-6 flex flex-wrap gap-2" aria-label="Zakładki">
        {TABS.map((tab) => {
          const isActive = tab.id === activeTab;
          return (
            <button
              key={tab.id}
              type="button"
              onClick={() => setActiveTab(tab.id)}
              className={
                isActive
                  ? "rounded-md bg-navy px-4 py-2 font-medium text-white"
                  : "rounded-md border border-line bg-surface px-4 py-2 text-navy transition hover:bg-accent-soft"
              }
            >
              {tab.label}
            </button>
          );
        })}
      </nav>

      {errorMessage ? (
        <p className="mb-4 rounded-md border border-danger/30 bg-surface px-4 py-3 text-danger">
          {errorMessage}
        </p>
      ) : null}

      <main className="rounded-xl border border-line bg-surface p-5 shadow-[var(--shadow)] sm:p-8">
        {isLoading ? <p className="text-muted">Ładowanie…</p> : null}

        {!isLoading && activeTab === "study" ? (
          <StudyPanel
            study={selectedStudy}
            onStudySaved={(study) => {
              setStudies((current) =>
                current.map((item) => (item.id === study.id ? study : item)),
              );
            }}
            onError={setErrorMessage}
          />
        ) : null}

        {!isLoading && activeTab === "materials" ? (
          <MaterialsPanel study={selectedStudy} onError={setErrorMessage} />
        ) : null}

        {!isLoading && activeTab === "analysis" ? (
          <AnalysisPanel study={selectedStudy} onError={setErrorMessage} />
        ) : null}

        {!isLoading && activeTab === "report" ? (
          <ReportPanel study={selectedStudy} onError={setErrorMessage} />
        ) : null}
      </main>
    </div>
  );
}
