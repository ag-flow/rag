import { useTranslation } from "react-i18next";
import { FolderOpen, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";

interface Props {
  onCreate: () => void;
}

export function WorkspacesEmptyState({ onCreate }: Props) {
  const { t } = useTranslation("workspace");
  return (
    <div className="flex flex-1 items-center justify-center p-8">
      <div className="max-w-md text-center rounded-lg border border-dashed border-slate-300 p-10">
        <FolderOpen className="mx-auto mb-3 h-10 w-10 text-slate-400" />
        <h3 className="text-base font-semibold text-slate-900 mb-1.5">
          {t("empty.title")}
        </h3>
        <p className="text-sm text-slate-500 mb-5">{t("empty.description")}</p>
        <Button onClick={onCreate}>
          <Plus className="h-4 w-4" />
          {t("list.new")}
        </Button>
      </div>
    </div>
  );
}
