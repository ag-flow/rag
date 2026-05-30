import { useRef, useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { Send, RotateCcw, ChevronDown, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { useLlmConfigs, usePlaygroundChat } from "@/hooks/usePlayground";
import { useToast } from "@/hooks/useToast";
import type { ChatMessage, ChunkResult, PlaygroundChatResponse } from "@/lib/playground.types";

interface ConversationTurn {
  question: string;
  response: PlaygroundChatResponse;
}

interface Props {
  workspaceName: string;
}

function ChunksCollapsible({ chunks }: { chunks: ChunkResult[] }) {
  const { t } = useTranslation("playground");
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-2">
      <button
        type="button"
        className="flex items-center gap-1 text-xs text-slate-500 hover:text-slate-700"
        onClick={() => setOpen(!open)}
      >
        {open ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
        {t("chat.chunks_toggle", { count: chunks.length })}
      </button>
      {open && (
        <div className="mt-2 space-y-2">
          {chunks.map((c, i) => (
            <div key={i} className="rounded bg-slate-50 border border-slate-200 p-2 text-xs">
              <div className="flex justify-between text-slate-500 mb-1">
                <span className="font-mono">{c.path}</span>
                <span className="text-emerald-600 font-medium">score {c.score.toFixed(3)}</span>
              </div>
              <p className="text-slate-700 line-clamp-3">{c.content}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function PlaygroundChatTab({ workspaceName }: Props) {
  const { t } = useTranslation("playground");
  const { toast } = useToast();
  const { data: configs = [] } = useLlmConfigs(workspaceName);
  const chatMutation = usePlaygroundChat(workspaceName);

  const enabledConfigs = configs.filter((c) => c.enabled);

  const [selectedLlm, setSelectedLlm] = useState("");

  // Auto-sélectionner le premier LLM activé à l'ouverture
  useEffect(() => {
    if (!selectedLlm && enabledConfigs.length > 0) {
      const first = enabledConfigs[0];
      if (first) setSelectedLlm(`${first.provider}/${first.model}`);
    }
  }, [enabledConfigs, selectedLlm]);
  const [topK, setTopK] = useState(5);
  const [minScore, setMinScore] = useState(0.7);
  const [input, setInput] = useState("");
  const [history, setHistory] = useState<ChatMessage[]>([]);
  const [turns, setTurns] = useState<ConversationTurn[]>([]);
  const bottomRef = useRef<HTMLDivElement>(null);

  function handleReset() {
    setHistory([]);
    setTurns([]);
    setInput("");
  }

  async function handleSend() {
    if (!input.trim() || !selectedLlm || chatMutation.isPending) return;
    const parts = selectedLlm.split("/");
    const provider = parts[0] ?? "";
    const model = parts.slice(1).join("/");
    const message = input.trim();
    setInput("");

    try {
      const response = await chatMutation.mutateAsync({
        message,
        history,
        llm: { provider, model },
        top_k: topK,
        min_score: minScore,
      });
      setTurns((prev) => [...prev, { question: message, response }]);
      setHistory((prev) => [
        ...prev,
        { role: "user" as const, content: message },
        { role: "assistant" as const, content: response.answer },
      ]);
      setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: "smooth" }), 50);
    } catch {
      toast({ title: t("chat.error_toast"), variant: "destructive" });
    }
  }

  if (enabledConfigs.length === 0) {
    return (
      <div className="rounded border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500">
        {t("chat.no_llm")}
      </div>
    );
  }

  return (
    <div className="flex flex-col h-[600px]">
      <div className="flex items-center gap-3 pb-3 border-b border-slate-200 flex-wrap">
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-500">{t("chat.llm_label")}</span>
          <Select value={selectedLlm} onValueChange={setSelectedLlm}>
            <SelectTrigger className="w-56 h-8 text-xs">
              <SelectValue placeholder="Sélectionner…" />
            </SelectTrigger>
            <SelectContent>
              {enabledConfigs.map((c) => (
                <SelectItem key={c.id} value={`${c.provider}/${c.model}`} className="text-xs font-mono">
                  {c.provider} / {c.model}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="flex items-center gap-1">
          <span className="text-xs text-slate-500">{t("chat.top_k_label")}</span>
          <Input
            type="number"
            min={1}
            max={50}
            value={topK}
            onChange={(e) => setTopK(parseInt(e.target.value, 10) || 5)}
            className="w-16 h-8 text-xs"
          />
        </div>
        <div className="flex items-center gap-1">
          <span className="text-xs text-slate-500">{t("chat.min_score_label")}</span>
          <Input
            type="number"
            min={0}
            max={1}
            step={0.05}
            value={minScore}
            onChange={(e) => setMinScore(parseFloat(e.target.value) || 0.7)}
            className="w-16 h-8 text-xs"
          />
        </div>
        <Button variant="ghost" size="sm" onClick={handleReset} className="ml-auto">
          <RotateCcw className="h-3.5 w-3.5 mr-1" />
          {t("chat.reset")}
        </Button>
      </div>

      <div className="flex-1 overflow-y-auto py-3 space-y-4">
        {turns.map((turn, i) => (
          <div key={i} className="space-y-2">
            <div className="flex justify-end">
              <div className="max-w-[80%] rounded-lg bg-blue-600 text-white px-3 py-2 text-sm">
                {turn.question}
              </div>
            </div>
            <div className="max-w-[85%]">
              <div className="rounded-lg bg-slate-100 px-3 py-2 text-sm whitespace-pre-wrap">
                {turn.response.answer}
              </div>
              <ChunksCollapsible chunks={turn.response.chunks} />
              <p className="text-xs text-slate-400 mt-1">
                {t("chat.tokens", {
                  prompt: turn.response.usage.prompt_tokens,
                  completion: turn.response.usage.completion_tokens,
                })}
              </p>
            </div>
          </div>
        ))}
        {chatMutation.isPending && (
          <div className="flex items-center gap-2 text-sm text-slate-500 italic">
            <span className="animate-pulse">{t("chat.thinking")}</span>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <div className="flex gap-2 pt-3 border-t border-slate-200">
        <Input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={t("chat.placeholder")}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void handleSend();
            }
          }}
          disabled={chatMutation.isPending}
        />
        <Button
          onClick={() => void handleSend()}
          disabled={!input.trim() || !selectedLlm || chatMutation.isPending}
          size="sm"
        >
          <Send className="h-4 w-4 mr-1" />
          {t("chat.send")}
        </Button>
      </div>
    </div>
  );
}
