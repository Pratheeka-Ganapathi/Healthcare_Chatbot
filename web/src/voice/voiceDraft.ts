/** The message box while listening: what was typed before, finished phrases, live words. */
export interface VoiceDraft {
  base: string;
  finals: string[];
  interim: string;
}

export const MAX_DRAFT_CHARS = 500;

export function startDraft(base: string): VoiceDraft {
  return { base, finals: [], interim: "" };
}

export function withTranscript(draft: VoiceDraft, text: string, final: boolean): VoiceDraft {
  return final
    ? { ...draft, finals: [...draft.finals, text], interim: "" }
    : { ...draft, interim: text };
}

export function draftText(draft: VoiceDraft): string {
  return [draft.base, ...draft.finals, draft.interim]
    .map((part) => part.trim())
    .filter(Boolean)
    .join(" ")
    .slice(0, MAX_DRAFT_CHARS);
}
