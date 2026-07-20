import { useTranslation } from "react-i18next";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { McpClientPanel } from "./McpClientPanel";
import type { UserApiKey } from "@/lib/user-api-keys.types";

interface Props {
  apiKey: UserApiKey | null;
  onOpenChange: (open: boolean) => void;
}

/**
 * Fiche de connexion MCP d'une clé existante. La valeur de la clé étant
 * show-once, on affiche un placeholder — l'utilisateur y colle sa propre clé.
 */
export function McpConnectionDialog({ apiKey, onOpenChange }: Props) {
  const { t } = useTranslation("apikeys");

  return (
    <Dialog open={apiKey !== null} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[640px]">
        <DialogHeader>
          <DialogTitle>{t("mcp.dialog_title", { name: apiKey?.name ?? "" })}</DialogTitle>
          <DialogDescription>{t("mcp.dialog_desc")}</DialogDescription>
        </DialogHeader>
        {apiKey && <McpClientPanel grants={apiKey.workspaces} />}
      </DialogContent>
    </Dialog>
  );
}
