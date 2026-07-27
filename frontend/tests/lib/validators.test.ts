import { describe, it, expect } from "vitest";
import { vaultCreateSchema, vaultUpdateSchema } from "@/lib/validators";

// workspaceCreateSchema a été retiré : la création de workspace passe par le
// sélecteur d'endpoint (préréglage du coffre), plus par un formulaire zod.

describe("vaultCreateSchema", () => {
  const valid = {
    name: "coffre-principal",
    label: "Coffre principal",
    base_url: "https://harpocrate.example",
    api_key_id: "k-001",
    api_key: "hrpv_1_supersecret",
  };

  it("accepts a valid vault", () => {
    const result = vaultCreateSchema.safeParse(valid);
    expect(result.success).toBe(true);
  });

  it("defaults probe_path and is_default", () => {
    const result = vaultCreateSchema.parse(valid);
    expect(result.probe_path).toBe("");
    expect(result.is_default).toBe(true);
  });

  it("rejects uppercase name", () => {
    expect(vaultCreateSchema.safeParse({ ...valid, name: "Coffre" }).success).toBe(false);
  });

  it("rejects non-http base_url", () => {
    expect(
      vaultCreateSchema.safeParse({ ...valid, base_url: "ftp://harpocrate" }).success,
    ).toBe(false);
  });

  it("rejects short api_key", () => {
    expect(vaultCreateSchema.safeParse({ ...valid, api_key: "court" }).success).toBe(false);
  });

  it("rejects invalid probe_path characters", () => {
    expect(
      vaultCreateSchema.safeParse({ ...valid, probe_path: "santé?!" }).success,
    ).toBe(false);
  });
});

describe("vaultUpdateSchema", () => {
  it("accepts label + base_url + probe_path", () => {
    const result = vaultUpdateSchema.safeParse({
      label: "Nouveau libellé",
      base_url: "https://harpocrate.example",
      probe_path: "health",
    });
    expect(result.success).toBe(true);
  });

  it("rejects empty label", () => {
    expect(
      vaultUpdateSchema.safeParse({
        label: "",
        base_url: "https://harpocrate.example",
        probe_path: "",
      }).success,
    ).toBe(false);
  });
});
