interface Props {
  name: string;
}

export function WorkspaceDetailPanel({ name }: Props) {
  return (
    <div className="flex-1 p-8 text-slate-500">
      Détail workspace : {name} (en construction)
    </div>
  );
}
