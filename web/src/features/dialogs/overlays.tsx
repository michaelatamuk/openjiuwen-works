import { Modal } from "../../ui/Modal";

export type LightboxImage = {
  url: string;
  alt?: string;
};

export type LightboxProps = {
  image: LightboxImage | null;
  onClose: () => void;
};

export type DialogEvent = {
  type?: string;
  seq?: number;
  ts?: string;
  at?: string;
  data?: Record<string, unknown>;
};

export type EventDialogProps = {
  event: DialogEvent | null;
  onClose: () => void;
};

export function Lightbox({ image, onClose }: LightboxProps) {
  if (!image) return null;
  return (
    <Modal onClose={onClose}>
      <h2 className="small muted">Artifact</h2>
      <img className="lightbox-image" src={image.url} alt={image.alt || "artifact"} />
      <div className="dialog-actions"><button type="button" className="btn" onClick={onClose}>Close</button></div>
    </Modal>
  );
}

export function EventDialog({ event, onClose }: EventDialogProps) {
  if (!event) return null;
  return (
    <Modal onClose={onClose}>
      <h2>Event</h2>
      <pre className="run-dialog-body">{JSON.stringify(event, null, 2)}</pre>
      <div className="dialog-actions"><button type="button" className="btn" onClick={onClose}>Close</button></div>
    </Modal>
  );
}
