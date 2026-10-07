import { useCallback, useEffect, useEffectEvent, useState } from "react";

import { describeError } from "./errors";

interface Loaded<T> {
  key: string;
  nonce: number;
  data?: T;
  error?: string;
}

export interface ApiState<T> {
  data: T | undefined;
  error: string | undefined;
  loading: boolean;
  reload: () => void;
  /** Replaces the loaded data, e.g. with what a save returned. */
  replace: (data: T) => void;
}

/**
 * Loads data for `key` and reloads whenever the key changes. During a reload of the same key the
 * previous data stays visible; data from a different key is only shown with `keepPrevious` (for
 * paging, so the screen does not jump while the next page loads).
 */
export function useApi<T>(
  load: () => Promise<T>,
  key: string,
  options: { keepPrevious?: boolean } = {},
): ApiState<T> {
  const [loaded, setLoaded] = useState<Loaded<T> | null>(null);
  const [nonce, setNonce] = useState(0);
  const runLoad = useEffectEvent(load);

  useEffect(() => {
    let active = true;
    runLoad().then(
      (data) => active && setLoaded({ key, nonce, data }),
      (error: unknown) => active && setLoaded({ key, nonce, error: describeError(error) }),
    );
    return () => {
      active = false;
    };
  }, [key, nonce]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);
  const replace = useCallback((data: T) => setLoaded({ key, nonce, data }), [key, nonce]);

  const current = loaded?.key === key ? loaded : null;
  return {
    data: current?.data ?? (options.keepPrevious ? loaded?.data : undefined),
    error: current?.nonce === nonce ? current.error : undefined,
    loading: current === null || current.nonce !== nonce,
    reload,
    replace,
  };
}
