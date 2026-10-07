import { afterEach, describe, expect, it } from "vitest";

import { DEFAULT_SPEAKER, loadSpeaker, saveSpeaker } from "./speaker";

describe("speaker settings", () => {
  afterEach(() => localStorage.clear());

  it("defaults to on, and remembers mute and volume", () => {
    expect(loadSpeaker()).toEqual(DEFAULT_SPEAKER);
    saveSpeaker({ muted: true, volume: 0.4 });
    expect(loadSpeaker()).toEqual({ muted: true, volume: 0.4 });
  });

  it("ignores bad stored values", () => {
    localStorage.setItem("citycare.speaker", "{not json");
    expect(loadSpeaker()).toEqual(DEFAULT_SPEAKER);
    localStorage.setItem("citycare.speaker", JSON.stringify({ muted: "yes", volume: 7 }));
    expect(loadSpeaker()).toEqual({ muted: false, volume: 1 });
  });
});
