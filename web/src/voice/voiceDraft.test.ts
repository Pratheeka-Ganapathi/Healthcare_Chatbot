import { describe, expect, it } from "vitest";

import { draftText, MAX_DRAFT_CHARS, startDraft, withTranscript } from "./voiceDraft";

describe("voice draft", () => {
  it("keeps typed text and replaces live words until a phrase is final", () => {
    let draft = startDraft("Hi,");
    draft = withTranscript(draft, "I need", false);
    expect(draftText(draft)).toBe("Hi, I need");
    draft = withTranscript(draft, "I need an appointment", false);
    expect(draftText(draft)).toBe("Hi, I need an appointment");
    draft = withTranscript(draft, "I need an appointment.", true);
    draft = withTranscript(draft, "Tomorrow", false);
    expect(draftText(draft)).toBe("Hi, I need an appointment. Tomorrow");
  });

  it("starts empty and never exceeds the message limit", () => {
    expect(draftText(startDraft("  "))).toBe("");
    const long = withTranscript(startDraft(""), "a".repeat(MAX_DRAFT_CHARS + 50), true);
    expect(draftText(long)).toHaveLength(MAX_DRAFT_CHARS);
  });
});
