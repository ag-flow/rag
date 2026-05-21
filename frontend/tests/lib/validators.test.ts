import { describe, it, expect } from "vitest";
import { workspaceCreateSchema } from "@/lib/validators";

describe("workspaceCreateSchema", () => {
  it("accepts valid openai workspace", () => {
    const result = workspaceCreateSchema.safeParse({
      name: "harpocrate",
      api_key_vault: "vault-main",
      indexer: {
        provider: "openai",
        model: "text-embedding-3-small",
        api_key_ref: "openai_key",
      },
    });
    expect(result.success).toBe(true);
  });

  it("accepts valid ollama workspace without api_key_ref", () => {
    const result = workspaceCreateSchema.safeParse({
      name: "ws_ollama",
      api_key_vault: "vault-main",
      indexer: {
        provider: "ollama",
        model: "nomic-embed-text",
        base_url: "http://192.168.10.80:11434",
      },
    });
    expect(result.success).toBe(true);
  });

  it("rejects empty name", () => {
    const result = workspaceCreateSchema.safeParse({
      name: "",
      api_key_vault: "vault-main",
      indexer: { provider: "openai", model: "x", api_key_ref: "k" },
    });
    expect(result.success).toBe(false);
  });

  it("rejects uppercase name", () => {
    const result = workspaceCreateSchema.safeParse({
      name: "BadName",
      api_key_vault: "vault-main",
      indexer: { provider: "openai", model: "x", api_key_ref: "k" },
    });
    expect(result.success).toBe(false);
  });

  it("rejects name longer than 64 chars", () => {
    const result = workspaceCreateSchema.safeParse({
      name: "a".repeat(65),
      api_key_vault: "vault-main",
      indexer: { provider: "openai", model: "x", api_key_ref: "k" },
    });
    expect(result.success).toBe(false);
  });

  it("rejects unknown provider", () => {
    const result = workspaceCreateSchema.safeParse({
      name: "ws",
      api_key_vault: "vault-main",
      indexer: { provider: "nope", model: "x", api_key_ref: "k" },
    });
    expect(result.success).toBe(false);
  });

  it("rejects openai without api_key_ref", () => {
    const result = workspaceCreateSchema.safeParse({
      name: "ws",
      api_key_vault: "vault-main",
      indexer: { provider: "openai", model: "x" },
    });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(JSON.stringify(result.error.issues)).toContain("api_key_ref");
    }
  });

  it("accepts ollama without api_key_ref", () => {
    const result = workspaceCreateSchema.safeParse({
      name: "ws",
      api_key_vault: "vault-main",
      indexer: { provider: "ollama", model: "x" },
    });
    expect(result.success).toBe(true);
  });

  it("rejects missing api_key_vault", () => {
    const result = workspaceCreateSchema.safeParse({
      name: "ws",
      indexer: { provider: "ollama", model: "x" },
    });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(JSON.stringify(result.error.issues)).toContain("api_key_vault");
    }
  });

  it("rejects empty api_key_vault", () => {
    const result = workspaceCreateSchema.safeParse({
      name: "ws",
      api_key_vault: "",
      indexer: { provider: "ollama", model: "x" },
    });
    expect(result.success).toBe(false);
  });
});
