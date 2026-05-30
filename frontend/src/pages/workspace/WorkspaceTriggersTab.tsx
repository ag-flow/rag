import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Trash2, ChevronDown, ChevronRight, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  useTriggers, usePatchTrigger, useDeleteTrigger,
  useTriggerPrompts, useCreateTriggerPrompt, useDeleteTriggerPrompt,
  usePrompts,
} from "@/hooks/useEnrichments";
import { useLlmConfigs } from "@/hooks/usePlayground";
import { useToast } from "@/hooks/useToast";
import { AddTriggerDialog } from "./AddTriggerDialog";
import type { Trigger } from "@/lib/enrichments.types";

interface TriggerPromptsPanelProps {
  trigger: Trigger;
  workspaceName: string;
}

function TriggerPromptsPanel({ trigger, workspaceName }: TriggerPromptsPanelProps) {
  const { t } = useTranslation("triggers");
  const { data: triggerPrompts = [] } = useTriggerPrompts(workspaceName, trigger.id);
  const { data: allPrompts = [] } = usePrompts();
  const { data: llmConfigs = [] } = useLlmConfigs(workspaceName);
  const addPrompt = useCreateTriggerPrompt(workspaceName, trigger.id);
  const deletePrompt = useDeleteTriggerPrompt(workspaceName, trigger.id);

  const [selectedTemplate, setSelectedTemplate] = useState("");
  const [selectedLlm, setSelectedLlm] = useState("");
  const [addOpen, setAddOpen] = useState(false);

  const nextOrder = triggerPrompts.length + 1;

  async function handleAddPrompt() {
    if (!selectedTemplate || !selectedLlm) return;
    await addPrompt.mutateAsync({
      template_id: selectedTemplate,
      llm_id: selectedLlm,
      order_index: nextOrder,
    });
    setSelectedTemplate("");
    setSelectedLlm("");
    setAddOpen(false);
  }

  return (
    <div className="border-t bg-slate-50 p-3 space-y-2">
      <p className="text-xs font-semibold text-slate-600">{t("prompts_title")}</p>
      {triggerPrompts.length === 0 ? (
        <p className="text-xs text-slate-400">{t("prompts_empty")}</p>
      ) : (
        <div className="space-y-1">
          {triggerPrompts.map((tp) => (
            <div key={tp.id} className="flex items-center gap-2 rounded bg-white border border-slate-200 px-3 py-1.5 text-xs">
              <span className="text-slate-400 w-5">{tp.order_index}.</span>
              <span className="font-medium text-slate-700 flex-1">{tp.template_name}</span>
              <span className="text-slate-400">{tp.llm_provider}/{tp.llm_model}</span>
              <Button
                variant="ghost"
                size="sm"
                className="h-6 px-1 text-rose-500 hover:text-rose-700"
                onClick={() => deletePrompt.mutate(tp.id)}
              >
                <Trash2 className="h-3 w-3" />
              </Button>
            </div>
          ))}
        </div>
      )}

      {!addOpen ? (
        <Button variant="outline" size="sm" onClick={() => setAddOpen(true)} className="text-xs">
          <Plus className="h-3 w-3 mr-1" />
          {t("add_prompt_btn")}
        </Button>
      ) : (
        <div className="space-y-2 rounded border border-slate-200 bg-white p-3">
          <p className="text-xs font-medium text-slate-600">{t("add_prompt_dialog_title")}</p>
          <Select value={selectedTemplate} onValueChange={setSelectedTemplate}>
            <SelectTrigger className="h-8 text-xs">
              <SelectValue placeholder={t("field_template")} />
            </SelectTrigger>
            <SelectContent>
              {allPrompts.map((p) => (
                <SelectItem key={p.id} value={p.id} className="text-xs">
                  {p.name} <span className="text-slate-400">({p.language})</span>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={selectedLlm} onValueChange={setSelectedLlm}>
            <SelectTrigger className="h-8 text-xs">
              <SelectValue placeholder={t("field_llm")} />
            </SelectTrigger>
            <SelectContent>
              {llmConfigs.filter((l) => l.enabled).map((l) => (
                <SelectItem key={l.id} value={l.id} className="text-xs font-mono">
                  {l.provider}/{l.model}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <div className="flex gap-2">
            <Button size="sm" className="text-xs h-7" onClick={handleAddPrompt}
              disabled={!selectedTemplate || !selectedLlm || addPrompt.isPending}>
              {t("prompt_add_save")}
            </Button>
            <Button variant="ghost" size="sm" className="text-xs h-7" onClick={() => setAddOpen(false)}>
              {t("cancel")}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

interface Props {
  workspaceName: string;
}

export function WorkspaceTriggersTab({ workspaceName }: Props) {
  const { t } = useTranslation("triggers");
  const { toast } = useToast();
  const { data: triggers = [], isLoading } = useTriggers(workspaceName);
  const patchMutation = usePatchTrigger(workspaceName);
  const deleteMutation = useDeleteTrigger(workspaceName);
  const [addOpen, setAddOpen] = useState(false);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [toDelete, setToDelete] = useState<Trigger | null>(null);

  function toggleExpand(id: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }

  async function handleDelete() {
    if (!toDelete) return;
    try {
      await deleteMutation.mutateAsync(toDelete.id);
      toast({ title: t("deleted_toast") });
    } catch {
      toast({ title: t("error_toast"), variant: "destructive" });
    } finally {
      setToDelete(null);
    }
  }

  return (
    <div className="space-y-4 pt-4">
      <div className="flex justify-end">
        <Button size="sm" onClick={() => setAddOpen(true)}>
          {t("add_btn")}
        </Button>
      </div>

      {!isLoading && triggers.length === 0 ? (
        <div className="rounded border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500">
          {t("empty")}
        </div>
      ) : (
        <div className="rounded border border-slate-200 overflow-hidden divide-y divide-slate-200">
          {triggers.map((trigger) => (
            <div key={trigger.id}>
              <div className="flex items-center gap-3 px-4 py-3 bg-white">
                <button
                  type="button"
                  className="text-slate-400 hover:text-slate-600"
                  onClick={() => toggleExpand(trigger.id)}
                >
                  {expanded.has(trigger.id)
                    ? <ChevronDown className="h-4 w-4" />
                    : <ChevronRight className="h-4 w-4" />}
                </button>
                <span className="font-mono text-sm font-semibold text-slate-700 flex-1">
                  {trigger.extension}
                </span>
                <Switch
                  checked={trigger.enabled}
                  onCheckedChange={(enabled) =>
                    patchMutation.mutate({ triggerId: trigger.id, payload: { enabled } })
                  }
                />
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setToDelete(trigger)}
                  className="text-rose-600 hover:text-rose-700"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </div>
              {expanded.has(trigger.id) && (
                <TriggerPromptsPanel trigger={trigger} workspaceName={workspaceName} />
              )}
            </div>
          ))}
        </div>
      )}

      <AddTriggerDialog
        workspaceName={workspaceName}
        open={addOpen}
        onOpenChange={setAddOpen}
      />

      <AlertDialog open={!!toDelete} onOpenChange={(o) => { if (!o) setToDelete(null); }}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("delete_confirm_title")}</AlertDialogTitle>
            <AlertDialogDescription>{t("delete_confirm_body")}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("cancel")}</AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete} className="bg-rose-600 hover:bg-rose-700">
              {t("delete_btn")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
