import { useEffect, useRef } from "react";
import type { ReactNode } from "react";

export type ModalProps = {
  children?: ReactNode;
  onClose: () => void;
  className?: string;
};

function Modal({ children, onClose, className = "" }: ModalProps) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    ref.current?.showModal();
    return () => {
      if (ref.current?.open) ref.current.close();
    };
  }, []);
  return (
    <dialog ref={ref} className={className} onCancel={(event) => { event.preventDefault(); onClose(); }} onClose={onClose}>
      {children}
    </dialog>
  );
}

export { Modal };
