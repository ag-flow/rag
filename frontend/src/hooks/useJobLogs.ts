import { useState, useEffect } from "react";

type WsEvent =
  | { type: "log"; level: string; msg: string; ts: string }
  | { type: "done"; status: string; files_changed: number; files_skipped: number }
  | { type: "ping" };

export type JobLogLine = { type: "log"; level: string; msg: string; ts: string };
export type JobStatus = "idle" | "running" | "done" | "error";

export function useJobLogs(jobId: string | null): { lines: JobLogLine[]; jobStatus: JobStatus } {
  const [lines, setLines] = useState<JobLogLine[]>([]);
  const [jobStatus, setJobStatus] = useState<JobStatus>("idle");

  useEffect(() => {
    if (!jobId) {
      setLines([]);
      setJobStatus("idle");
      return;
    }

    setLines([]);
    setJobStatus("running");

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const ws = new WebSocket(`${protocol}//${window.location.host}/ws/jobs/${jobId}/logs`);

    ws.onmessage = (e: MessageEvent) => {
      const event: WsEvent = JSON.parse(e.data as string);
      if (event.type === "log") {
        setLines((prev) => [...prev, event]);
      } else if (event.type === "done") {
        setJobStatus(event.status === "done" ? "done" : "error");
      }
    };

    ws.onerror = () => setJobStatus("error");

    return () => ws.close();
  }, [jobId]);

  return { lines, jobStatus };
}
