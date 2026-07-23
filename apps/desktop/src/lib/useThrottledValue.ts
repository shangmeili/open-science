import { useEffect, useRef, useState } from "react";

/** Keep streaming UI responsive by committing at most one trailing value per window. */
export function useThrottledValue<T>(value: T, ms: number): T {
  const [shown, setShown] = useState(value);
  const lastCommit = useRef(0);

  useEffect(() => {
    if (value === shown) return;
    const elapsed = Date.now() - lastCommit.current;
    if (elapsed >= ms) {
      lastCommit.current = Date.now();
      setShown(value);
      return;
    }
    const id = window.setTimeout(() => {
      lastCommit.current = Date.now();
      setShown(value);
    }, ms - elapsed);
    return () => window.clearTimeout(id);
  }, [value, shown, ms]);

  return shown;
}
