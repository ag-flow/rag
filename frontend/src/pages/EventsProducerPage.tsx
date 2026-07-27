import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { LoadingSpinner } from "@/components/LoadingSpinner";
import { ApiError } from "@/lib/api";
import { isProducerNotConfigured, unknownEventsFromError } from "@/lib/events-producer";
import type { EventsProducerSpec, TestConnectionResult } from "@/lib/events-producer.types";
import {
  useEventsProducerConfig,
  useSaveEventsProducer,
  useTestEventsProducerConnection,
} from "@/hooks/useEventsProducer";
import { useToast } from "@/hooks/useToast";

const EMPTY: EventsProducerSpec = {
  enabled: false,
  workflow_base_url: "",
  source_id: "",
  secret_ref: "",
  source_uri: "urn:yoops:rag",
  events: [],
};

type TestState = { ok: boolean; status_code: number; detail: string } | { notConfigured: true } | null;

export function EventsProducerPage() {
  const { t } = useTranslation("events_producer");
  const { toast } = useToast();
  const { data, isLoading } = useEventsProducerConfig();
  const save = useSaveEventsProducer();
  const test = useTestEventsProducerConnection();

  const [form, setForm] = useState<EventsProducerSpec>(EMPTY);
  const [unknownEvents, setUnknownEvents] = useState<string[] | null>(null);
  const [testResult, setTestResult] = useState<TestState>(null);

  useEffect(() => {
    if (!data) return;
    setForm({
      enabled: data.enabled,
      workflow_base_url: data.workflow_base_url,
      source_id: data.source_id,
      secret_ref: data.secret_ref,
      source_uri: data.source_uri,
      events: data.events,
    });
  }, [data]);

  const knownEvents = data?.known_events ?? [];

  const setField = <K extends keyof EventsProducerSpec>(key: K, value: EventsProducerSpec[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const toggleEvent = (code: string, checked: boolean) => {
    setForm((prev) => ({
      ...prev,
      events: checked ? [...prev.events, code] : prev.events.filter((e) => e !== code),
    }));
  };

  const handleSave = () => {
    setUnknownEvents(null);
    save.mutate(form, {
      onSuccess: () => toast({ title: t("save.success") }),
      onError: (err) => {
        const rejected = err instanceof ApiError ? unknownEventsFromError(err.body) : null;
        if (rejected) {
          setUnknownEvents(rejected);
          return;
        }
        toast({ title: t("save.error"), variant: "destructive" });
      },
    });
  };

  const handleTest = () => {
    setTestResult(null);
    test.mutate(undefined, {
      onSuccess: (res: TestConnectionResult) => setTestResult(res),
      onError: (err) => {
        if (err instanceof ApiError && isProducerNotConfigured(err.body)) {
          setTestResult({ notConfigured: true });
          return;
        }
        toast({ title: t("test.error"), variant: "destructive" });
      },
    });
  };

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <LoadingSpinner />
      </div>
    );
  }

  return (
    <div className="p-6 max-w-2xl mx-auto">
      <h1 className="text-xl font-semibold text-slate-900">{t("title")}</h1>
      <p className="text-sm text-slate-500 mt-1">{t("subtitle")}</p>

      <div className="mt-4 flex items-start gap-2 rounded-md border border-sky-200 bg-sky-50 px-4 py-3">
        <ShieldCheck className="h-4 w-4 text-sky-600 mt-0.5 flex-shrink-0" />
        <p className="text-sm text-sky-900">{t("intro")}</p>
      </div>

      <section className="mt-6 space-y-4 rounded-md border bg-white p-6">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h2 className="text-sm font-semibold text-slate-900">{t("fields.enabled")}</h2>
            <p className="mt-1 text-sm text-slate-600">{t("fields.enabled_help")}</p>
          </div>
          <Switch
            checked={form.enabled}
            onCheckedChange={(v) => setField("enabled", v)}
            aria-label={t("fields.enabled")}
          />
        </div>

        <div>
          <label className="text-sm font-medium text-slate-700">{t("fields.workflow_base_url")}</label>
          <Input
            value={form.workflow_base_url}
            onChange={(e) => setField("workflow_base_url", e.target.value)}
            placeholder="https://workflow.example.com/ingest"
            className="mt-1 font-mono"
          />
        </div>

        <div>
          <label className="text-sm font-medium text-slate-700">{t("fields.source_id")}</label>
          <Input
            value={form.source_id}
            onChange={(e) => setField("source_id", e.target.value)}
            placeholder="00000000-0000-0000-0000-000000000000"
            className="mt-1 font-mono"
          />
          <p className="mt-1 text-xs text-slate-500">{t("fields.source_id_help")}</p>
        </div>

        <div>
          <label className="text-sm font-medium text-slate-700">{t("fields.secret_ref")}</label>
          <Input
            value={form.secret_ref}
            onChange={(e) => setField("secret_ref", e.target.value)}
            placeholder="${vault://rag:workflow-hmac}"
            className="mt-1 font-mono"
          />
          <p className="mt-1 text-xs text-slate-500">{t("fields.secret_ref_help")}</p>
        </div>

        <div>
          <label className="text-sm font-medium text-slate-700">{t("fields.source_uri")}</label>
          <Input
            value={form.source_uri}
            onChange={(e) => setField("source_uri", e.target.value)}
            placeholder="urn:yoops:rag"
            className="mt-1 font-mono"
          />
        </div>
      </section>

      <section className="mt-6 rounded-md border bg-white p-6">
        <h2 className="text-sm font-semibold text-slate-900">{t("events.title")}</h2>
        <p className="mt-1 text-xs text-slate-500">{t("events.help")}</p>
        <div className="mt-3 space-y-2">
          {knownEvents.length === 0 ? (
            <p className="text-sm text-slate-500">{t("events.empty")}</p>
          ) : (
            knownEvents.map((code) => (
              <label key={code} className="flex items-center gap-2 text-sm text-slate-800">
                <input
                  type="checkbox"
                  checked={form.events.includes(code)}
                  onChange={(e) => toggleEvent(code, e.target.checked)}
                  className="h-4 w-4 rounded border-slate-300 text-sky-600 focus:ring-sky-500"
                  aria-label={code}
                />
                <span className="font-mono">{code}</span>
              </label>
            ))
          )}
        </div>
        {unknownEvents && (
          <p className="mt-3 text-xs text-red-600">
            {t("save.unknown_events", { events: unknownEvents.join(", ") })}
          </p>
        )}
      </section>

      <div className="mt-6 flex items-center gap-2">
        <Button type="button" onClick={handleSave} disabled={save.isPending}>
          {t("actions.save")}
        </Button>
        <Button type="button" variant="ghost" onClick={handleTest} disabled={test.isPending}>
          {t("actions.test")}
        </Button>
      </div>

      {testResult && (
        <div
          role="status"
          className={
            "mt-4 rounded-md border px-4 py-3 text-sm " +
            ("notConfigured" in testResult
              ? "border-amber-200 bg-amber-50 text-amber-900"
              : testResult.ok
                ? "border-emerald-200 bg-emerald-50 text-emerald-800"
                : "border-red-200 bg-red-50 text-red-700")
          }
        >
          {"notConfigured" in testResult
            ? t("test.not_configured")
            : testResult.ok
              ? t("test.ok", { status: testResult.status_code })
              : t("test.failed", { status: testResult.status_code, detail: testResult.detail })}
        </div>
      )}
    </div>
  );
}
