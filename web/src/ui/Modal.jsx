import { useEffect, useRef } from "react";

function Modal({ children, onClose, className = "" }) {
  const ref = useRef(null);
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
