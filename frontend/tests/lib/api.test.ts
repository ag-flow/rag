import { describe, it, expect, vi, beforeEach } from "vitest";
import { api, ApiError, isUnauthorized } from "@/lib/api";

describe("api", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  describe("api.get", () => {
    it("returns parsed JSON on 200", async () => {
      const fetchMock = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ name: "ws_a" }),
      });
      vi.stubGlobal("fetch", fetchMock);

      const result = await api.get<{ name: string }>("/api/admin/workspaces/ws_a");
      expect(result).toEqual({ name: "ws_a" });
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/admin/workspaces/ws_a",
        expect.objectContaining({ credentials: "include" }),
      );
    });

    it("throws ApiError on 401", async () => {
      vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
        json: async () => ({ error: "oidc_session_missing" }),
      }));

      await expect(api.get("/me")).rejects.toMatchObject({
        name: "ApiError",
        status: 401,
      });
    });

    it("throws ApiError on 404 with body parsed", async () => {
      vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
        ok: false,
        status: 404,
        json: async () => ({ error: "workspace_not_found", name: "ghost" }),
      }));

      try {
        await api.get("/api/admin/workspaces/ghost");
        throw new Error("should have thrown");
      } catch (e) {
        expect(e).toBeInstanceOf(ApiError);
        expect((e as ApiError).status).toBe(404);
        expect((e as ApiError).body).toEqual({ error: "workspace_not_found", name: "ghost" });
      }
    });
  });

  describe("api.post", () => {
    it("sends body as JSON with credentials", async () => {
      const fetchMock = vi.fn().mockResolvedValue({
        ok: true,
        status: 201,
        json: async () => ({ name: "ws_a" }),
      });
      vi.stubGlobal("fetch", fetchMock);

      await api.post("/api/admin/workspaces", { name: "ws_a" });

      expect(fetchMock).toHaveBeenCalledWith(
        "/api/admin/workspaces",
        expect.objectContaining({
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name: "ws_a" }),
        }),
      );
    });
  });

  describe("api.delete", () => {
    it("sends DELETE with no body", async () => {
      const fetchMock = vi.fn().mockResolvedValue({
        ok: true,
        status: 204,
        json: async () => ({}),
      });
      vi.stubGlobal("fetch", fetchMock);

      await api.delete("/api/admin/workspaces/ws_a");

      expect(fetchMock).toHaveBeenCalledWith(
        "/api/admin/workspaces/ws_a",
        expect.objectContaining({ method: "DELETE", credentials: "include" }),
      );
    });
  });

  describe("isUnauthorized", () => {
    it("returns true for ApiError with status 401", () => {
      const err = new ApiError(401, { error: "x" });
      expect(isUnauthorized(err)).toBe(true);
    });

    it("returns false for non-401 ApiError", () => {
      const err = new ApiError(403, { error: "x" });
      expect(isUnauthorized(err)).toBe(false);
    });

    it("returns false for non-ApiError", () => {
      expect(isUnauthorized(new Error("oops"))).toBe(false);
    });
  });
});
