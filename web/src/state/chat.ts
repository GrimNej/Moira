// The Ask conversation (§4.3.7). Kept per session; follow-ups use the conversation id.

import { signal } from '@preact/signals';

import { ask as askApi } from '../api/client';
import type { AnswerData, AskEvent, Clues } from '../api/types';

export interface Turn {
  id: number;
  question: string;
  clues: Clues | null;
  status: string | null;
  answer: AnswerData | null;
  error: string | null;
  fallback: string[];
  feedback: 'found' | 'not_it' | null;
  savedNote?: string;
}

export const turns = signal<Turn[]>([]);
export const conversationId = signal<string | null>(null);
let seq = 0;

function patch(id: number, f: (t: Turn) => Partial<Turn>): void {
  turns.value = turns.value.map((t) => (t.id === id ? { ...t, ...f(t) } : t));
}

export function addSavedNote(text: string): void {
  turns.value = [
    ...turns.value,
    {
      id: ++seq,
      question: text,
      clues: null,
      status: null,
      answer: null,
      error: null,
      fallback: [],
      feedback: null,
      savedNote: 'Saved',
    },
  ];
}

export async function ask(
  question: string,
  hooks: {
    onLit?: (ids: string[], top: string | null) => void;
    onAnswer?: (a: AnswerData) => void;
    onError?: (fallback: string[]) => void;
  } = {},
): Promise<void> {
  const id = ++seq;
  turns.value = [
    ...turns.value,
    {
      id,
      question,
      clues: null,
      status: null,
      answer: null,
      error: null,
      fallback: [],
      feedback: null,
    },
  ];
  await askApi(question, conversationId.value, (e: AskEvent) => {
    switch (e.event) {
      case 'clues':
        patch(id, () => ({ clues: e.data }));
        break;
      case 'lit':
        hooks.onLit?.(e.data.ids, e.data.top);
        break;
      case 'status':
        patch(id, () => ({ status: e.data.text }));
        break;
      case 'error':
        patch(id, () => ({ error: e.data.message, fallback: e.data.fallback_ids }));
        hooks.onError?.(e.data.fallback_ids);
        break;
      case 'answer':
        if (e.data.conversation_id) conversationId.value = e.data.conversation_id;
        patch(id, () => ({ answer: e.data, status: null }));
        hooks.onAnswer?.(e.data);
        break;
      default:
        break;
    }
  }).catch(() => {
    patch(id, () => ({
      error: 'I can’t reach your sky right now. Check the connection.',
      status: null,
    }));
  });
}

export function setFeedback(id: number, value: 'found' | 'not_it'): void {
  patch(id, () => ({ feedback: value }));
}
