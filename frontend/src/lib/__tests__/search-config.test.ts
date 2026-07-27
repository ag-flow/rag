import { describe, it, expect, vi, beforeEach } from "vitest";
import { searchConfigApi, isLexicalEngineUnavailable } from "@/lib/search-config";
import { api, ApiError } from "@/lib/api";
import type { HybridConfig } from "@/lib/search-config.types";

const baseConfig: HybridConfig = {
  workspace_id: "ws-1",
  enabled: true,
  rrf_k: 60,
  weight_lexical: 0.5,
  weight_vector: 0.5,
  lexical_engine: "fts",
  rebuild_job_id: null,
  created_at: "2026-07-01T10:00:00Z",
  updated_at: "2026-07-01T10:00:00Z",
};

describe("searchConfigApi.get", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("retourne null sur 404 (pas encore de config = vectoriel pur)", async () => {
    vi.spyOn(api, "get").mockRejectedValue(new ApiError(404, { detail: "not_found" }));
    await expect(searchConfigApi.get("ws-1")).resolves.toBeNull();
  });

  it("retourne la config sur 200", async () => {
    vi.spyOn(api, "get").mockResolvedValue(baseConfig);
    await expect(searchConfigApi.get("ws-1")).resolves.toEqual(baseConfig);
  });

  it("appelle la bonne URL", async () => {
    const spy = vi.spyOn(api, "get").mockResolvedValue(baseConfig);
    await searchConfigApi.get("ws-1");
    expect(spy).toHaveBeenCalledWith("/api/admin/workspaces/ws-1/hybrid-config");
  });

  it("propage les erreurs non-404", async () => {
    vi.spyOn(api, "get").mockRejectedValue(new ApiError(500, null));
    await expect(searchConfigApi.get("ws-1")).rejects.toMatchObject({ status: 500 });
  });
});

describe("isLexicalEngineUnavailable", () => {
  it("renvoie true sur le shape 422 du backend", () => {
    expect(
      isLexicalEngineUnavailable({
        detail: {
          error: "lexical_engine_unavailable",
          engine: "bm25",
          hint: "CREATE EXTENSION pg_search;",
        },
      }),
    ).toBe(true);
  });

  it("renvoie false sur un detail string (422 pydantic classique)", () => {
    expect(isLexicalEngineUnavailable({ detail: "validation error" })).toBe(false);
  });

  it("renvoie false sur une autre erreur structurée", () => {
    expect(isLexicalEngineUnavailable({ detail: { error: "workspace_not_found" } })).toBe(false);
  });

  it("renvoie false sur null/non-objet", () => {
    expect(isLexicalEngineUnavailable(null)).toBe(false);
    expect(isLexicalEngineUnavailable(undefined)).toBe(false);
    expect(isLexicalEngineUnavailable("string")).toBe(false);
  });
});
