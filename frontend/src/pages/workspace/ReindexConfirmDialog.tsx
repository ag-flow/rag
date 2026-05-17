import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";

interface Props {
  name: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ReindexConfirmDialog({ open, onOpenChange }: Props) {
  if (!open) return null;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Reindex (T10)</DialogTitle>
        </DialogHeader>
        <Button variant="outline" onClick={() => onOpenChange(false)}>
          Fermer
        </Button>
      </DialogContent>
    </Dialog>
  );
}
