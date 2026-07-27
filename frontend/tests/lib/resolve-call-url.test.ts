import { describe, it, expect } from "vitest";
import { resolveCallUrl } from "@/lib/models";
import type { ProviderUrlTemplates } from "@/lib/models.types";

const TEMPLATES: ProviderUrlTemplates = {
  "azure-openai": {
    embeddings: {
      template: "{base_url}/openai/deployments/{model}/embeddings?api-version=2024-02-01",
      default_base_url: null,
    },
  },
  openai: {
    embeddings: { template: "{base_url}/embeddings", default_base_url: "https://api.openai.com/v1" },
  },
};

describe("resolveCallUrl", () => {
  it("azure-openai : racine de ressource + modèle → URL de déploiement complète", () => {
    expect(
      resolveCallUrl(TEMPLATES, "embeddings", {
        provider: "azure-openai",
        model: "text-embedding-3-large",
        baseUrl: "https://rag-agflow.openai.azure.com",
      }),
    ).toBe(
      "https://rag-agflow.openai.azure.com/openai/deployments/text-embedding-3-large/embeddings?api-version=2024-02-01",
    );
  });

  it("base par défaut du provider quand le champ est vide", () => {
    expect(
      resolveCallUrl(TEMPLATES, "embeddings", { provider: "openai", model: "m", baseUrl: "" }),
    ).toBe("https://api.openai.com/v1/embeddings");
  });

  it("le template du modèle prime et accepte l'alias {url}", () => {
    expect(
      resolveCallUrl(TEMPLATES, "embeddings", {
        provider: "azure-openai",
        model: "x",
        baseUrl: "https://r.openai.azure.com/",
        template: "{url}/openai/deployments/mon-deploiement/embeddings?api-version=2024-02-01",
      }),
    ).toBe(
      "https://r.openai.azure.com/openai/deployments/mon-deploiement/embeddings?api-version=2024-02-01",
    );
  });

  it("base requise absente → null ; capacité inconnue → null", () => {
    expect(
      resolveCallUrl(TEMPLATES, "embeddings", { provider: "azure-openai", model: "m", baseUrl: "" }),
    ).toBeNull();
    expect(resolveCallUrl(TEMPLATES, "rerank", { provider: "openai", model: "m" })).toBeNull();
  });
});
