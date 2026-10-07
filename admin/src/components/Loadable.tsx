import type { ReactNode } from "react";

import type { ApiState } from "../lib/useApi";
import { ErrorState } from "./ErrorState";
import { LoadingState } from "./LoadingState";

interface Props<T> {
  state: ApiState<T>;
  children: (data: T) => ReactNode;
}

/** Shows the loading and error states, then renders the loaded data. */
export function Loadable<T>({ state, children }: Props<T>) {
  if (state.error) return <ErrorState message={state.error} onRetry={state.reload} />;
  if (state.data === undefined) return <LoadingState />;
  return <>{children(state.data)}</>;
}
