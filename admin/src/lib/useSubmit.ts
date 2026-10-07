import { useCallback, useState } from "react";

import { describeError } from "./errors";

interface SubmitState {
  busy: boolean;
  error: string | null;
  success: string | null;
}

const IDLE: SubmitState = { busy: false, error: null, success: null };

export interface Submitter extends SubmitState {
  /** Runs the action; a string it returns becomes the success message. */
  run: (action: () => Promise<unknown>) => Promise<void>;
  fail: (message: string) => void;
  clear: () => void;
}

/** Busy, error and success state for one form. */
export function useSubmit(): Submitter {
  const [state, setState] = useState<SubmitState>(IDLE);

  const run = useCallback(async (action: () => Promise<unknown>) => {
    setState({ busy: true, error: null, success: null });
    try {
      const message = await action();
      setState({ busy: false, error: null, success: typeof message === "string" ? message : null });
    } catch (error) {
      setState({ busy: false, error: describeError(error), success: null });
    }
  }, []);

  const fail = useCallback((message: string) => {
    setState({ busy: false, error: message, success: null });
  }, []);

  const clear = useCallback(() => setState(IDLE), []);

  return { ...state, run, fail, clear };
}
