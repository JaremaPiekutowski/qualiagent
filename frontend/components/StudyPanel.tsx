"use client";

import { useEffect, useState } from "react";

import { updateStudy } from "@/lib/api";
import type { Study } from "@/lib/types";

type StudyPanelProps = {
  study: Study | null;
  onStudySaved: (study: Study) => void;
  onError: (message: string | null) => void;
};

export function StudyPanel({ study, onStudySaved, onError }: StudyPanelProps) {
  const [name, setName] = useState("");
  const [researchQuestions, setResearchQuestions] = useState<string[]>([""]);
  const [webSearchEnabled, setWebSearchEnabled] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!study) {
      setName("");
      setResearchQuestions([""]);
      setWebSearchEnabled(false);
      return;
    }
    setName(study.name);
    setResearchQuestions(
      study.research_questions.length > 0 ? study.research_questions : [""],
    );
    setWebSearchEnabled(study.web_search_enabled);
  }, [study]);

  if (!study) {
    return (
      <div>
        <h2 className="text-2xl font-semibold text-navy">Badanie</h2>
        <p className="mt-3 text-muted">
          Utwórz nowe badanie, żeby edytować nazwę, pytania i web search.
        </p>
      </div>
    );
  }

  async function handleSave() {
    if (!study) {
      return;
    }
    onError(null);
    setStatusMessage(null);
    setIsSaving(true);
    try {
      const cleanedQuestions = researchQuestions
        .map((question) => question.trim())
        .filter((question) => question.length > 0);
      const saved = await updateStudy(study.id, {
        name: name.trim() || study.name,
        research_questions: cleanedQuestions,
        web_search_enabled: webSearchEnabled,
      });
      onStudySaved(saved);
      setStatusMessage("Zapisano zmiany badania.");
    } catch (error) {
      onError(error instanceof Error ? error.message : "Nie udało się zapisać badania");
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h2 className="text-2xl font-semibold text-navy">Badanie</h2>
        <p className="mt-2 text-muted">
          Nazwa, pytania badawcze i przełącznik wyszukiwania w sieci.
        </p>
      </div>

      <label className="flex flex-col gap-2">
        <span className="text-sm text-muted">Nazwa</span>
        <input
          className="rounded-md border border-line bg-background px-3 py-2"
          value={name}
          onChange={(event) => setName(event.target.value)}
        />
      </label>

      <div className="flex flex-col gap-3">
        <div className="flex items-center justify-between gap-3">
          <span className="text-sm text-muted">Pytania badawcze</span>
          <button
            type="button"
            className="rounded-md border border-line px-3 py-1.5 text-sm hover:bg-accent-soft"
            onClick={() => setResearchQuestions((current) => [...current, ""])}
          >
            Dodaj pytanie
          </button>
        </div>
        {researchQuestions.map((question, index) => (
          <div key={`question-${index}`} className="flex gap-2">
            <textarea
              className="min-h-20 flex-1 rounded-md border border-line bg-background px-3 py-2"
              value={question}
              onChange={(event) => {
                const value = event.target.value;
                setResearchQuestions((current) =>
                  current.map((item, itemIndex) =>
                    itemIndex === index ? value : item,
                  ),
                );
              }}
              placeholder={`Pytanie ${index + 1}`}
            />
            <button
              type="button"
              className="rounded-md border border-line px-3 py-2 text-sm text-muted hover:text-danger"
              onClick={() =>
                setResearchQuestions((current) =>
                  current.length === 1
                    ? [""]
                    : current.filter((_, itemIndex) => itemIndex !== index),
                )
              }
            >
              Usuń
            </button>
          </div>
        ))}
      </div>

      <label className="flex items-center gap-3">
        <input
          type="checkbox"
          checked={webSearchEnabled}
          onChange={(event) => setWebSearchEnabled(event.target.checked)}
        />
        <span>Włącz web search przy braku materiału</span>
      </label>

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          disabled={isSaving}
          onClick={() => void handleSave()}
          className="rounded-md bg-blue px-4 py-2 font-medium text-white disabled:opacity-60"
        >
          {isSaving ? "Zapisywanie…" : "Zapisz badanie"}
        </button>
        {statusMessage ? <span className="text-sm text-blue">{statusMessage}</span> : null}
      </div>
    </div>
  );
}
