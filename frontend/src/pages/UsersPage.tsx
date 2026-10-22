import { useTranslation } from "react-i18next";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { LoadingSpinner } from "@/components/LoadingSpinner";
import { useSetUserRole, useUsers } from "@/hooks/useUsers";
import { useToast } from "@/hooks/useToast";
import { ApiError } from "@/lib/api";
import type { UserAccount, UserRole } from "@/lib/users";

/** Valeur du <select> pour « aucun rôle » (accès retiré). */
const NO_ROLE = "none";

/**
 * Configuration → Utilisateurs (admin) : les comptes et leur rôle. Le rôle vit
 * en base et se relit à chaque requête : un changement s'applique à la requête
 * suivante de l'utilisateur concerné, sans reconnexion.
 */
export function UsersPage() {
  const { t } = useTranslation("users");
  const { data: users = [], isLoading } = useUsers();

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <LoadingSpinner />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">{t("page_title")}</h1>
        <p className="mt-1 text-sm text-slate-500">{t("description")}</p>
      </div>
      <div className="overflow-hidden rounded border border-slate-200">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t("col_username")}</TableHead>
              <TableHead>{t("col_email")}</TableHead>
              <TableHead>{t("col_type")}</TableHead>
              <TableHead>{t("col_role")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {users.map((user) => (
              <UserRow key={user.id} user={user} />
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}

interface UserRowProps {
  user: UserAccount;
}

function UserRow({ user }: UserRowProps) {
  const { t } = useTranslation("users");
  const { toast } = useToast();
  const setRole = useSetUserRole();

  async function handleChange(value: string) {
    const role: UserRole = value === NO_ROLE ? null : (value as UserRole);
    try {
      await setRole.mutateAsync({ userId: user.id, role });
      toast({ title: t("role_changed", { username: user.username }) });
    } catch (err) {
      const lastAdmin = err instanceof ApiError && err.status === 409;
      toast({
        title: t(lastAdmin ? "error_last_admin" : "error_generic"),
        variant: "destructive",
      });
    }
  }

  return (
    <TableRow>
      <TableCell className="font-mono text-sm">{user.username}</TableCell>
      <TableCell className="text-sm text-slate-600">{user.email}</TableCell>
      <TableCell className="text-xs text-slate-600">
        {user.oidc_issuer ? (
          <span title={user.oidc_issuer}>{t("type_oidc")}</span>
        ) : user.has_local_password ? (
          t("type_local")
        ) : (
          t("type_pending")
        )}
      </TableCell>
      <TableCell>
        <select
          aria-label={t("role_select_label", { username: user.username })}
          value={user.role ?? NO_ROLE}
          disabled={setRole.isPending}
          onChange={(e) => void handleChange(e.target.value)}
          className="rounded border border-slate-300 bg-white px-2 py-1 text-sm"
        >
          <option value="rag-admin">{t("role_admin")}</option>
          <option value="rag-viewer">{t("role_viewer")}</option>
          <option value={NO_ROLE}>{t("role_none")}</option>
        </select>
      </TableCell>
    </TableRow>
  );
}
