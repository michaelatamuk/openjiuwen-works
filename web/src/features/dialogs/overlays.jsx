import { Modal } from "../../ui/Modal.jsx";

export function Lightbox({ image, onClose }) {
  if (!image) return null;
  return (
    <Modal onClose={onClose}>
      <h2 className="small muted">Artifact</h2>
      <img className="lightbox-image" src={image.url} alt={image.alt || "artifact"} />
      <div className="dialog-actions"><button type="button" className="btn" onClick={onClose}>Close</button></div>
    </Modal>
  );
}

export function EventDialog({ event, onClose }) {
  if (!event) return null;
  return (
    <Modal onClose={onClose}>
      <h2>Event</h2>
      <pre className="run-dialog-body">{JSON.stringify(event, null, 2)}</pre>
      <div className="dialog-actions"><button type="button" className="btn" onClick={onClose}>Close</button></div>
    </Modal>
  );
}
