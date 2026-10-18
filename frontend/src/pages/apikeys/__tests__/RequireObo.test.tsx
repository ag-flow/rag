import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { I18nextProvider, initReactI18next } from "react-i18next";
import i18next from "i18next";
import type { ReactNode } from "react";

import frApikeys from "@/i18n/fr/apikeys.json";
import { CreateUserApiKeyDialog } from "@/pages/apikeys/CreateUserApiKeyDialog";
import { EditScopeDialog } from "@/pages/apikeys/EditScopeDialog";
import { ApiKeysPage } from "@/pages/ApiKeysPage";
import type { UserApiKey } from "@/lib/user-api-keys.types";

const createMock = vi.fn();
const scopeMock = vi.fn();
const oboMock = vi.fn();
let listed: UserApiKey[] = [];

vi.mock("@/hooks/useUserApiKeys", () => ({
  useUserApiKeys: () => ({ data: listed, isLoading: false }),
  useCreateUserApiKey: () => ({ mutateAsync: createMock, isPending: false }),
  useSetUserApiKeyScope: () => ({ mutateAsync: scopeMock, isPending: false }),
  useSetUserApiKeyRequireObo: () => ({ mutateAsync: oboMock, isPending: false }),
  useRotateUserApiKey: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useRevokeUserApiKey: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

const testI18n = i18next.createInstance();
void testI18n.use(initReactI18next).init({
  lng: "fr",
  ns: ["apikeys"],
  defaultNS: "apikeys",
  resources: { fr: { apikeys: frApikeys } },
  interpolation: { escapeValue: false },
});

function wrap(node: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <I18nextProvider i18n={testI18n}>
      <QueryClientProvider client={qc}>
        <MemoryRouter>{node}</MemoryRouter>
      </QueryClientProvider>
    </I18nextProvider>,
  );
}

const KEY: UserApiKey = {
  id: "k1",
  name: "agent",
  fingerprint_preview: "abcd1234",
  status: "active",
  created_at: "2026-10-18T00:00:00Z",
  revoked_at: null,
  rotated_at: null,
  scope: "read",
  require_obo: false,
};

beforeEach(() => {
  createMock.mockReset().mockResolvedValue({ api_key: "secret-value" });
  scopeMock.mockReset().mockResolvedValue(undefined);
  oboMock.mockReset().mockResolvedValue(undefined);
  listed = [];
});

describe("CreateUserApiKeyDialog — OBO obligatoire", () => {
  it("envoie require_obo=true quand la bascule est activée", async () => {
    wrap(<CreateUserApiKeyDialog open onOpenChange={() => {}} />);
    fireEvent.change(screen.getByPlaceholderText(frApikeys.field_name_placeholder), {
      target: { value: "ci" },
    });
    fireEvent.click(screen.getByRole("switch", { name: frApikeys.obo.title }));
    fireEvent.click(screen.getByRole("button", { name: frApikeys.create_save }));

    await waitFor(() =>
      expect(createMock).toHaveBeenCalledWith({ name: "ci", scope: "read", require_obo: true }),
    );
  });

  it("envoie require_obo=false par défaut", async () => {
    wrap(<CreateUserApiKeyDialog open onOpenChange={() => {}} />);
    fireEvent.change(screen.getByPlaceholderText(frApikeys.field_name_placeholder), {
      target: { value: "ci" },
    });
    fireEvent.click(screen.getByRole("button", { name: frApikeys.create_save }));

    await waitFor(() =>
      expect(createMock).toHaveBeenCalledWith({ name: "ci", scope: "read", require_obo: false }),
    );
  });
});

describe("EditScopeDialog — OBO obligatoire", () => {
  it("n'appelle que la route OBO quand seul le flag change", async () => {
    wrap(<EditScopeDialog apiKey={KEY} onOpenChange={() => {}} />);
    fireEvent.click(screen.getByRole("switch", { name: frApikeys.obo.title }));
    fireEvent.click(screen.getByRole("button", { name: frApikeys.scope.save }));

    await waitFor(() => expect(oboMock).toHaveBeenCalledWith({ keyId: "k1", requireObo: true }));
    expect(scopeMock).not.toHaveBeenCalled();
  });

  it("pré-remplit la bascule depuis la clé", () => {
    wrap(<EditScopeDialog apiKey={{ ...KEY, require_obo: true }} onOpenChange={() => {}} />);
    expect(screen.getByRole("switch", { name: frApikeys.obo.title })).toHaveAttribute(
      "data-state",
      "checked",
    );
  });
});

describe("ApiKeysPage — badge OBO", () => {
  it("affiche le badge seulement pour une clé OBO obligatoire", () => {
    listed = [KEY, { ...KEY, id: "k2", name: "portail", require_obo: true }];
    wrap(<ApiKeysPage />);
    expect(screen.getAllByText(frApikeys.obo.badge)).toHaveLength(1);
  });
});
