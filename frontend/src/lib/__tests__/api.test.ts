import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { api, isErrorBodyWithDetail } from "@/lib/api";

describe("isErrorBodyWithDetail", () => {
  it("retourne true si body.detail === expected", () => {
    expect(
      isErrorBodyWithDetail({ detail: "rerank_not_configured" }, "rerank_not_configured"),
    ).toBe(true);
  });

  it("retourne false si body.detail !== expected", () => {
    expect(isErrorBodyWithDetail({ detail: "workspace_not_found" }, "rerank_not_configured")).toBe(
      false,
    );
  });

  it("retourne false si body n'a pas de champ detail", () => {
    expect(isErrorBodyWithDetail({ message: "boom" }, "rerank_not_configured")).toBe(false);
  });

  it("retourne false si body est null", () => {
    expect(isErrorBodyWithDetail(null, "rerank_not_configured")).toBe(false);
  });

  it("retourne false si body est une string", () => {
    expect(isErrorBodyWithDetail("oops", "rerank_not_configured")).toBe(false);
  });

  it("retourne false si body.detail n'est pas une string", () => {
    expect(isErrorBodyWithDetail({ detail: 42 }, "rerank_not_configured")).toBe(false);
  });
});

describe("api.put", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ ok: true }),
      }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("appelle fetch avec method PUT et Content-Type JSON", async () => {
    const result = await api.put("/x", { a: 1 });
    expect(fetch).toHaveBeenCalledWith("/x", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ a: 1 }),
      credentials: "include",
    });
    expect(result).toEqual({ ok: true });
  });
});

describe("refresh de session sur 401", () => {
  afterEach(() => vi.unstubAllGlobals());

  function jsonResp(status: number, body: unknown) {
    return { ok: status < 400, status, json: async () => body } as Response;
  }

  it("401 → POST /auth/refresh réussi → la requête est rejouée une fois", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResp(401, { detail: "oidc_session_expired" }))
      .mockResolvedValueOnce(jsonResp(200, { ok: true })) // /auth/refresh
      .mockResolvedValueOnce(jsonResp(200, { value: 42 })); // retry
    vi.stubGlobal("fetch", fetchMock);

    const out = await api.get<{ value: number }>("/api/x");

    expect(out).toEqual({ value: 42 });
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(fetchMock.mock.calls[1]?.[0]).toBe("/auth/refresh");
  });

  it("401 → refresh en échec → l'ApiError 401 originale remonte", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResp(401, { detail: "oidc_session_expired" }))
      .mockResolvedValueOnce(jsonResp(401, { detail: "oidc_session_missing" }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(api.get("/api/x")).rejects.toMatchObject({ status: 401 });
    expect(fetchMock).toHaveBeenCalledTimes(2); // pas de retry, pas de boucle
  });

  it("deux 401 simultanés ne déclenchent qu'UN refresh (single-flight)", async () => {
    const fetchMock = vi.fn((url: string) => {
      if (url === "/auth/refresh") return Promise.resolve(jsonResp(200, { ok: true }));
      if (fetchMock.mock.calls.filter((c) => c[0] !== "/auth/refresh").length <= 2) {
        return Promise.resolve(jsonResp(401, {}));
      }
      return Promise.resolve(jsonResp(200, { ok: true }));
    });
    vi.stubGlobal("fetch", fetchMock);

    await Promise.all([api.get("/api/a"), api.get("/api/b")]);

    const refreshCalls = fetchMock.mock.calls.filter((c) => c[0] === "/auth/refresh");
    expect(refreshCalls).toHaveLength(1);
  });

  it("les 4xx non-401 ne déclenchent pas de refresh", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResp(404, { detail: "not_found" }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(api.get("/api/x")).rejects.toMatchObject({ status: 404 });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
