"use client";

import { useCallback, useEffect, useState } from "react";

import { listSources, uploadSources } from "@/lib/api";
import type { SourceSummary, Study } from "@/lib/types";

type PendingFile = {
  file: File;
  respondentLabel: string;
};

type MaterialsPanelProps = {
  study: Study | null;
  onError: (message: string | null) => void;
};

export function MaterialsPanel({ study, onError }: MaterialsPanelProps) {
  const [sources, setSources] = useState<SourceSummary[]>([]);
  const [pendingFiles, setPendingFiles] = useState<PendingFile[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  const refreshSources = useCallback(async () => {
    if (!study) {
      setSources([]);
      return;
    }
    setIsLoading(true);
    onError(null);
    try {
      setSources(await listSources(study.id));
    } catch (error) {
      onError(
        error instanceof Error ? error.message : "Nie udało się pobrać materiałów",
      );
    } finally {
      setIsLoading(false);
    }
  }, [onError, study]);

  useEffect(() => {
    void refreshSources();
  }, [refreshSources]);

  if (!study) {
    return (
      <div>
        <h2 className="text-2xl font-semibold text-navy">Materiały</h2>
        <p className="mt-3 text-muted">Najpierw wybierz lub utwórz badanie.</p>
      </div>
    );
  }

  function handleFileSelection(fileList: FileList | null) {
    if (!fileList) {
      return;
    }
    const next = Array.from(fileList).map((file) => ({
      file,
      respondentLabel: "",
    }));
    setPendingFiles(next);
    setStatusMessage(null);
  }

  async function handleUpload() {
    if (!study) {
      return;
    }
    if (pendingFiles.length === 0) {
      onError("Wybierz co najmniej jeden plik.");
      return;
    }
    onError(null);
    setStatusMessage(null);
    setIsUploading(true);
    try {
      const uploaded = await uploadSources(
        study.id,
        pendingFiles.map((item) => item.file),
        pendingFiles.map((item) => item.respondentLabel.trim()),
      );
      setPendingFiles([]);
      await refreshSources();
      setStatusMessage(`Wgrano i zindeksowano ${uploaded.length} plik(ów).`);
    } catch (error) {
      onError(error instanceof Error ? error.message : "Upload nie powiódł się");
    } finally {
      setIsUploading(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h2 className="text-2xl font-semibold text-navy">Materiały</h2>
        <p className="mt-2 text-muted">
          Upload TXT / PDF / DOCX z etykietą respondenta i podgląd statusów indeksowania.
        </p>
      </div>

      <label className="flex flex-col gap-2">
        <span className="text-sm text-muted">Pliki</span>
        <input
          type="file"
          multiple
          accept=".txt,.pdf,.docx,.mp3,.wav,.m4a,.mp4,.mov,.webm"
          onChange={(event) => handleFileSelection(event.target.files)}
        />
      </label>

      {pendingFiles.length > 0 ? (
        <div className="flex flex-col gap-3">
          <h3 className="text-sm tracking-wide text-muted uppercase">
            Etykiety przed uploadem
          </h3>
          {pendingFiles.map((item, index) => (
            <div
              key={`${item.file.name}-${index}`}
              className="grid gap-2 border-b border-line pb-3 sm:grid-cols-[1fr_12rem]"
            >
              <span className="truncate">{item.file.name}</span>
              <input
                className="rounded-md border border-line bg-background px-3 py-2"
                placeholder="np. R01"
                value={item.respondentLabel}
                onChange={(event) => {
                  const value = event.target.value;
                  setPendingFiles((current) =>
                    current.map((entry, entryIndex) =>
                      entryIndex === index
                        ? { ...entry, respondentLabel: value }
                        : entry,
                    ),
                  );
                }}
              />
            </div>
          ))}
          <button
            type="button"
            disabled={isUploading}
            onClick={() => void handleUpload()}
            className="w-fit rounded-md bg-blue px-4 py-2 font-medium text-white disabled:opacity-60"
          >
            {isUploading ? "Indeksowanie…" : "Wgraj i zindeksuj"}
          </button>
        </div>
      ) : null}

      {statusMessage ? <p className="text-sm text-blue">{statusMessage}</p> : null}

      <div>
        <div className="mb-3 flex items-center justify-between gap-3">
          <h3 className="text-sm tracking-wide text-muted uppercase">Statusy źródeł</h3>
          <button
            type="button"
            className="rounded-md border border-line px-3 py-1.5 text-sm hover:bg-accent-soft"
            onClick={() => void refreshSources()}
          >
            Odśwież
          </button>
        </div>
        {isLoading ? <p className="text-muted">Ładowanie źródeł…</p> : null}
        {!isLoading && sources.length === 0 ? (
          <p className="text-muted">Brak wgranych materiałów.</p>
        ) : null}
        {!isLoading && sources.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="min-w-full border-collapse text-left text-sm">
              <thead>
                <tr className="border-b border-line text-muted">
                  <th className="py-2 pr-4 font-medium">Kod</th>
                  <th className="py-2 pr-4 font-medium">Plik</th>
                  <th className="py-2 pr-4 font-medium">Respondent</th>
                  <th className="py-2 pr-4 font-medium">Status</th>
                  <th className="py-2 font-medium">Błąd</th>
                </tr>
              </thead>
              <tbody>
                {sources.map((source) => (
                  <tr key={source.id} className="border-b border-line/70">
                    <td className="py-2 pr-4">{source.source_code}</td>
                    <td className="py-2 pr-4">{source.filename}</td>
                    <td className="py-2 pr-4">{source.respondent_label ?? "—"}</td>
                    <td className="py-2 pr-4">{source.status}</td>
                    <td className="py-2 text-danger">{source.error ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </div>
    </div>
  );
}
