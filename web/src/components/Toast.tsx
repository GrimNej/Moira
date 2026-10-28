// One toast above the timeline; role="status" so screen readers hear it (§4.3.13).

import { hideToast, toast } from '../state/ui';

export function Toast() {
  const t = toast.value;
  return (
    <div
      class={`toast${t ? ' on' : ''}${t?.action ? '' : ' nobtn'}`}
      role="status"
      aria-live="polite"
    >
      <span>{t?.text ?? ''}</span>
      {t?.action && (
        <button
          type="button"
          class="press"
          onClick={() => {
            const a = t.action;
            hideToast();
            a?.run();
          }}
        >
          {t.action.label}
        </button>
      )}
    </div>
  );
}
