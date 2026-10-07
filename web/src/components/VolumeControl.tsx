import type { Speaker } from "../voice/useSpeaker";

function SpeakerIcon({ muted }: { muted: boolean }) {
  return (
    <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
      <path d="M4 9h4l5-4v14l-5-4H4z" fill="currentColor" />
      {muted ? (
        <path d="M16 9l5 6M21 9l-5 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      ) : (
        <path
          d="M16 8.5a5 5 0 0 1 0 7M18.5 6a8.5 8.5 0 0 1 0 12"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
        />
      )}
    </svg>
  );
}

/** Top-right of the masthead: mute toggle and volume for read-aloud replies. */
export function VolumeControl({ speaker }: { speaker: Speaker }) {
  if (!speaker.supported) return null;
  const silent = speaker.muted || speaker.volume === 0;
  return (
    <div className="volume">
      <button
        type="button"
        className="volume-toggle"
        onClick={speaker.toggleMute}
        aria-pressed={silent}
        aria-label={silent ? "Turn on read-aloud" : "Mute read-aloud"}
        title={silent ? "Turn on read-aloud" : "Mute read-aloud"}
      >
        <SpeakerIcon muted={silent} />
      </button>
      <label htmlFor="volume" className="sr-only">
        Read-aloud volume
      </label>
      <input
        id="volume"
        type="range"
        min={0}
        max={100}
        step={5}
        value={silent ? 0 : Math.round(speaker.volume * 100)}
        onChange={(event) => speaker.setVolume(Number(event.target.value) / 100)}
      />
    </div>
  );
}
