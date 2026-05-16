import { describe, it, expect } from "vitest";
import { workspaceCreateSchema } from "@/lib/validators";

describe("workspaceCreateSchema", () => {
  it("accepts valid openai workspace", () => {
    const result = workspaceCreateSchema.safeParse({
      name: "harpocrate",
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
      indexer: { provider: "openai", model: "x", api_key_ref: "k" },
    });
    expect(result.success).toBe(false);
  });

  it("rejects uppercase name", () => {
    const result = workspaceCreateSchema.safeParse({
      name: "BadName",
      indexer: { provider: "openai", model: "x", api_key_ref: "k" },
    });
    expect(result.success).toBe(false);
  });

  it("rejects name longer than 64 chars", () => {
    const result = workspaceCreateSchema.safeParse({
      name: "a".repeat(65),
      indexer: { provider: "openai", model: "x", api_key_ref: "k" },
    });
    expect(result.success).toBe(false);
  });

  it("rejects unknown provider", () => {
    const result = workspaceCreateSchema.safeParse({
      name: "ws",
      indexer: { provider: "nope", model: "x", api_key_ref: "k" },
    });
    expect(result.success).toBe(false);
  });

  it("rejects openai without api_key_ref", () => {
    const result = workspaceCreateSchema.safeParse({
      name: "ws",
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
      indexer: { provider: "ollama", model: "x" },
    });
    expect(result.success).toBe(true);
  });
});
