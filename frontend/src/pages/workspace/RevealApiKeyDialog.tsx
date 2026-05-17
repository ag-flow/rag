import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";

interface Props {
  name: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function RevealApiKeyDialog({ open, onOpenChange }: Props) {
  if (!open) return null;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Reveal API Key (T9)</DialogTitle>
        </DialogHeader>
        <Button variant="outline" onClick={() => onOpenChange(false)}>
          Fermer
        </Button>
      </DialogContent>
    </Dialog>
  );
}
