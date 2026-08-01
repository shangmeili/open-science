/** Encode application-owned identifiers as one URL segment before handing the
 * path to React Router. This keeps imported or corrupted identifiers from being
 * interpreted as an external destination, path, query, or fragment. */
const routeSegment = (value: string): string => encodeURIComponent(value);

export const heorTaskPath = (sessionId: string): string =>
  `/heor/${routeSegment(sessionId)}`;

export const legacyTaskPath = (sessionId: string): string =>
  `/live/${routeSegment(sessionId)}`;

export const runRecordPath = (runId: string): string =>
  `/runs?run=${routeSegment(runId)}`;
