import type { ReactElement } from "react";
import { useTranslation } from "react-i18next";
import type { ChunkingAlgo } from "@/lib/chunking-strategies.types";

// Mini-schémas inline (pas d'asset externe) : document source à gauche,
// résultat du découpage à droite. Couleurs alignées sur la charte slate/sky.

function Doc({ x, lines }: { x: number; lines: number[] }) {
  return (
    <g>
      <rect x={x} y={8} width={52} height={74} rx={4} className="fill-white stroke-slate-300" />
      {lines.map((w, i) => (
        <rect
          key={i}
          x={x + 6}
          y={16 + i * 9}
          width={w}
          height={4}
          rx={2}
          className="fill-slate-300"
        />
      ))}
    </g>
  );
}

function Arrow() {
  return (
    <path d="M70 45h18m0 0-5-5m5 5-5 5" className="stroke-sky-500" strokeWidth={2} fill="none" />
  );
}

function ProseDiagram(): ReactElement {
  return (
    <svg viewBox="0 0 200 90" className="w-full" role="img" aria-hidden>
      <Doc x={12} lines={[40, 30, 36, 24, 38, 28, 34]} />
      <Arrow />
      {/* parent (section) → enfants bornés en tokens */}
      <rect x={96} y={10} width={92} height={70} rx={5} className="fill-sky-50 stroke-sky-300" />
      <rect x={102} y={16} width={44} height={5} rx={2} className="fill-sky-400" />
      {[28, 46, 64].map((y) => (
        <rect
          key={y}
          x={102}
          y={y}
          width={80}
          height={12}
          rx={3}
          className="fill-white stroke-sky-400"
        />
      ))}
    </svg>
  );
}

function TableDiagram(): ReactElement {
  return (
    <svg viewBox="0 0 200 90" className="w-full" role="img" aria-hidden>
      <g>
        <rect x={12} y={12} width={52} height={66} rx={3} className="fill-white stroke-slate-300" />
        {[12, 25, 38, 51, 64].map((y, i) => (
          <rect
            key={y}
            x={12}
            y={y}
            width={52}
            height={i === 0 ? 13 : 12}
            className={i === 0 ? "fill-slate-300" : "fill-transparent stroke-slate-200"}
          />
        ))}
      </g>
      <Arrow />
      {[14, 50].map((y) => (
        <g key={y}>
          <rect x={96} y={y} width={92} height={28} rx={4} className="fill-white stroke-sky-400" />
          <rect x={96} y={y} width={92} height={9} rx={4} className="fill-sky-200" />
        </g>
      ))}
    </svg>
  );
}

function CodeDiagram(): ReactElement {
  return (
    <svg viewBox="0 0 200 90" className="w-full" role="img" aria-hidden>
      <Doc x={12} lines={[36, 26, 40, 20, 34, 30, 22]} />
      <text x={20} y={78} className="fill-slate-400 text-[10px] font-mono">
        {"{ }"}
      </text>
      <Arrow />
      {[
        ["fn", 12],
        ["class", 40],
        ["fn", 68],
      ].map(([label, y]) => (
        <g key={y as number}>
          <rect
            x={96}
            y={y as number}
            width={92}
            height={20}
            rx={4}
            className="fill-white stroke-sky-400"
          />
          <text x={104} y={(y as number) + 13} className="fill-sky-600 text-[9px] font-mono">
            {label}
          </text>
        </g>
      ))}
    </svg>
  );
}

function DataDiagram(): ReactElement {
  return (
    <svg viewBox="0 0 200 90" className="w-full" role="img" aria-hidden>
      <Doc x={12} lines={[30, 38, 24, 36, 28, 40, 26]} />
      <text x={18} y={78} className="fill-slate-400 text-[9px] font-mono">
        key:
      </text>
      <Arrow />
      {["a", "b", "c"].map((k, i) => (
        <g key={k}>
          <rect
            x={96}
            y={12 + i * 24}
            width={92}
            height={18}
            rx={4}
            className="fill-white stroke-sky-400"
          />
          <text x={104} y={24 + i * 24} className="fill-sky-600 text-[9px] font-mono">
            {k}: …
          </text>
        </g>
      ))}
    </svg>
  );
}

const DIAGRAMS: Record<ChunkingAlgo, () => ReactElement> = {
  prose: ProseDiagram,
  markdown: ProseDiagram,
  table: TableDiagram,
  code: CodeDiagram,
  data: DataDiagram,
};

interface Props {
  algo: ChunkingAlgo;
}

export function AlgoInfoPanel({ algo }: Props) {
  const { t } = useTranslation("chunking_strategies");
  const Diagram = DIAGRAMS[algo];
  return (
    <aside className="h-fit rounded-md border border-slate-200 bg-slate-50 p-4 space-y-3">
      <div className="rounded border border-slate-200 bg-white p-2">
        <Diagram />
      </div>
      <h4 className="text-sm font-semibold text-slate-900">{t(`algo_info.${algo}.title`)}</h4>
      <p className="text-sm leading-relaxed text-slate-600">{t(`algo_info.${algo}.description`)}</p>
      <p className="text-xs text-slate-600">
        <span className="font-semibold">{t("algo_info.best_for_label")}</span>{" "}
        {t(`algo_info.${algo}.best_for`)}
      </p>
      <p className="text-xs text-slate-500">💡 {t(`algo_info.${algo}.tip`)}</p>
    </aside>
  );
}
