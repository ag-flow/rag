import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Copy, Loader2, Search } from "lucide-react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useVaultSecrets } from "@/hooks/useHarpocrateVaults";
import { useToast } from "@/hooks/useToast";

function useDebouncedValue<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(id);
  }, [value, delay]);
  return debounced;
}

interface VaultSecretsTabProps {
  vaultId: string;
}

export function VaultSecretsTab({ vaultId }: VaultSecretsTabProps) {
  const { t } = useTranslation("harpocrate");
  const { toast } = useToast();

  const [nameInput, setNameInput] = useState("");
  const [pathInput, setPathInput] = useState("");
  const debouncedName = useDebouncedValue(nameInput, 300);

  const filters: { name_contains?: string; path?: string; limit?: number } = {
    limit: 50,
  };
  if (debouncedName) filters.name_contains = debouncedName;
  if (pathInput) filters.path = pathInput;

  const { data, isLoading, isError, refetch, isRefetching } = useVaultSecrets(
    vaultId,
    filters,
    true,
  );

  async function handleCopy(name: string) {
    try {
      await navigator.clipboard.writeText(name);
    } catch {
      // clipboard peut échouer (permission refusée, contexte non-secure) :
      // on notifie quand même l'utilisateur via le toast standard.
    }
    toast({ title: t("secrets.copied_toast", { name }) });
  }

  if (isError) {
    return (
      <div className="rounded border border-rose-200 bg-rose-50 p-4">
        <h4 className="mb-1 font-semibold text-rose-800">{t("secrets.loading_error_title")}</h4>
        <p className="mb-3 text-sm text-rose-700">{t("secrets.loading_error_body")}</p>
        <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isRefetching}>
          {t("secrets.retry")}
        </Button>
      </div>
    );
  }

  const secrets = data?.secrets ?? [];

  return (
    <div className="space-y-4">
      {/* Filtres */}
      <div className="flex items-center gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-slate-400" />
          <Input
            value={nameInput}
            onChange={(e) => setNameInput(e.target.value)}
            placeholder={t("secrets.filter_name_placeholder")}
            className="pl-9"
          />
        </div>
        <Input
          value={pathInput}
          onChange={(e) => setPathInput(e.target.value)}
          placeholder={t("secrets.filter_path_placeholder")}
          className="w-36"
        />
        {/* Tag select : pas implémenté tant que le backend ne fournit pas la liste
            distincte des tags. Pour M5cd, on laisse un placeholder désactivé. */}
        <Input
          value=""
          readOnly
          disabled
          placeholder={t("secrets.filter_tag_all")}
          className="w-36 bg-slate-50"
        />
      </div>

      {/* Table */}
      {isLoading ? (
        <div className="flex justify-center py-6">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </div>
      ) : secrets.length === 0 ? (
        <div className="rounded border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500">
          {t("secrets.empty")}
        </div>
      ) : (
        <div className="overflow-hidden rounded border border-slate-200">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("secrets.col_name")}</TableHead>
                <TableHead>{t("secrets.col_description")}</TableHead>
                <TableHead className="w-24">{t("secrets.col_type")}</TableHead>
                <TableHead className="w-20" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {secrets.map((s) => (
                <TableRow key={s.id}>
                  <TableCell className="font-mono text-sm">{s.name}</TableCell>
                  <TableCell className="text-sm text-slate-600">
                    {s.description ?? (
                      <span className="italic text-slate-400">{t("secrets.no_description")}</span>
                    )}
                  </TableCell>
                  <TableCell>
                    {s.is_placeholder ? (
                      <Badge
                        variant="secondary"
                        className="bg-amber-100 text-amber-800 hover:bg-amber-100"
                      >
                        {t("secrets.type_placeholder")}
                      </Badge>
                    ) : (
                      <Badge
                        variant="secondary"
                        className="bg-sky-100 text-sky-800 hover:bg-sky-100"
                      >
                        {t("secrets.type_secret")}
                      </Badge>
                    )}
                  </TableCell>
                  <TableCell>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleCopy(s.name)}
                      aria-label={t("secrets.copy_aria")}
                    >
                      <Copy className="mr-1 h-3.5 w-3.5" />
                      {t("secrets.copy")}
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      {/* Footer */}
      <div className="flex items-center justify-between text-xs text-slate-500">
        <span>{t("secrets.count", { count: secrets.length })}</span>
        {data?.next_cursor && (
          <span className="italic text-slate-400">{t("secrets.has_more")}</span>
        )}
      </div>
    </div>
  );
}
