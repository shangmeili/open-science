import {
  ExternalLink,
  FileImage,
  LayoutGrid,
  Loader2,
  MessageSquareText,
  Move,
} from "lucide-react";
import {
  type KeyboardEvent,
  type PointerEvent,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useTranslation } from "react-i18next";
import { openArtifactExternally } from "@/lib/artifactFile";
import {
  type ConceptualModelDiagramAudit,
  type ConceptualModelNodePosition,
  type HeorConceptualModel,
} from "@/lib/heor";
import { formatHeorReviewIssue } from "./reviewIssue";

const WIDTH = 1280;
const HEIGHT = 640;
const MIN_X = 120;
const MAX_X = 1160;
const MIN_Y = 240;
const MAX_Y = 540;
const NODE_WIDTH = 220;
const NODE_HEIGHT = 92;

export type ConceptualModelDiagramState =
  | { kind: "loading" }
  | { kind: "invalid"; message: string }
  | { kind: "ready"; audit: ConceptualModelDiagramAudit };

function clamp(value: number, minimum: number, maximum: number) {
  return Math.max(minimum, Math.min(maximum, Math.round(value)));
}

export function automaticConceptualModelLayout(
  model: HeorConceptualModel,
): ConceptualModelNodePosition[] {
  const states = [
    ...model.states.filter((state) => !state.absorbing),
    ...model.states.filter((state) => state.absorbing),
  ];
  const columns = Math.min(4, Math.max(1, Math.ceil(Math.sqrt(states.length * 1.5))));
  const rows = Math.ceil(states.length / columns);
  return states.map((state, index) => {
    const row = Math.floor(index / columns);
    const firstInRow = row * columns;
    const rowCount = Math.min(columns, states.length - firstInRow);
    const column = index - firstInRow;
    const x = rowCount === 1
      ? (MIN_X + MAX_X) / 2
      : MIN_X + column * ((MAX_X - MIN_X) / (rowCount - 1));
    const y = rows === 1
      ? (MIN_Y + MAX_Y) / 2
      : MIN_Y + row * ((MAX_Y - MIN_Y) / (rows - 1));
    return { stateId: state.id, x: Math.round(x), y: Math.round(y) };
  });
}

function completeLayout(
  model: HeorConceptualModel,
  positions: ConceptualModelNodePosition[],
): boolean {
  return positions.length === model.states.length
    && new Set(positions.map((position) => position.stateId)).size === model.states.length
    && model.states.every((state) => positions.some((position) => position.stateId === state.id));
}

export function ConceptualModelDiagramAssessment({
  model,
  modelComplete,
  state,
  generating,
  desktopAvailable,
  onRequestModel,
  onGenerate,
}: {
  model: HeorConceptualModel;
  modelComplete: boolean;
  state: ConceptualModelDiagramState;
  generating: boolean;
  desktopAvailable: boolean;
  onRequestModel: () => void;
  onGenerate: (positions: ConceptualModelNodePosition[]) => void;
}) {
  const { t } = useTranslation("heor");
  const audit = state.kind === "ready" ? state.audit : null;
  const initial = useMemo(() => automaticConceptualModelLayout(model), [model]);
  const [positions, setPositions] = useState<ConceptualModelNodePosition[]>(initial);
  const svgRef = useRef<SVGSVGElement>(null);
  const dragging = useRef<{ stateId: string; pointerId: number } | null>(null);

  useEffect(() => {
    setPositions(audit && completeLayout(model, audit.positions) ? audit.positions : initial);
  }, [audit, initial, model]);

  const positionById = useMemo(
    () => new Map(positions.map((position) => [position.stateId, position])),
    [positions],
  );
  const ready = modelComplete && audit?.readyToGenerate === true && completeLayout(model, positions);
  const current = audit?.outputsCurrent === true;
  const issues = state.kind === "invalid"
    ? [state.message]
    : [...(audit?.errors ?? []), ...(audit?.warnings ?? [])];

  const moveNode = (stateId: string, x: number, y: number) => {
    setPositions((currentPositions) => currentPositions.map((position) =>
      position.stateId === stateId
        ? { ...position, x: clamp(x, MIN_X, MAX_X), y: clamp(y, MIN_Y, MAX_Y) }
        : position));
  };

  const onPointerMove = (event: PointerEvent<SVGSVGElement>) => {
    const active = dragging.current;
    const svg = svgRef.current;
    if (!active || !svg || active.pointerId !== event.pointerId) return;
    const bounds = svg.getBoundingClientRect();
    moveNode(
      active.stateId,
      ((event.clientX - bounds.left) / bounds.width) * WIDTH,
      ((event.clientY - bounds.top) / bounds.height) * HEIGHT,
    );
  };

  const onNodeKeyDown = (
    event: KeyboardEvent<SVGGElement>,
    position: ConceptualModelNodePosition,
  ) => {
    const step = event.shiftKey ? 25 : 10;
    const delta = {
      ArrowLeft: [-step, 0],
      ArrowRight: [step, 0],
      ArrowUp: [0, -step],
      ArrowDown: [0, step],
    }[event.key];
    if (!delta) return;
    event.preventDefault();
    moveNode(position.stateId, position.x + delta[0], position.y + delta[1]);
  };

  return (
    <section className="border-b border-border px-5 py-4" data-testid="conceptual-model-diagram-assessment">
      <div className="flex items-start gap-2">
        <FileImage size={16} className="mt-0.5 shrink-0 text-accent" />
        <div className="min-w-0 flex-1">
          <div className="text-xs font-semibold uppercase tracking-[0.12em] text-muted">
            {t("conceptualDiagram.title")}
          </div>
          <div className="mt-1 text-sm font-semibold text-text">
            {state.kind === "loading"
              ? t("conceptualDiagram.loading")
              : current
                ? t("conceptualDiagram.current")
                : ready
                  ? t("conceptualDiagram.ready")
                  : t("conceptualDiagram.incomplete")}
          </div>
          <p className="mt-1 text-xs leading-5 text-muted">{t("conceptualDiagram.note")}</p>
        </div>
      </div>

      <div className="mt-3 overflow-hidden rounded-card border border-border bg-[#fbfaf7]">
        <svg
          ref={svgRef}
          viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
          role="img"
          aria-label={t("conceptualDiagram.canvasLabel")}
          className="block h-auto w-full touch-none select-none"
          onPointerMove={onPointerMove}
          onPointerUp={(event) => {
            if (dragging.current?.pointerId === event.pointerId) dragging.current = null;
          }}
          onPointerCancel={() => { dragging.current = null; }}
        >
          <defs>
            <marker id="conceptual-arrow" markerWidth="9" markerHeight="7" refX="8" refY="3.5" orient="auto">
              <path d="M0,0 L9,3.5 L0,7 Z" fill="#365f7a" />
            </marker>
          </defs>
          <rect width={WIDTH} height={HEIGHT} fill="#fbfaf7" />
          <text x="48" y="56" fill="#172033" fontSize="25" fontWeight="700">
            {model.objective.length > 72 ? `${model.objective.slice(0, 71)}…` : model.objective}
          </text>
          <text x="48" y="84" fill="#637080" fontSize="13">
            {t("conceptualDiagram.visualOnly")}
          </text>
          {model.transitions.map((transition) => {
            const from = positionById.get(transition.from);
            const to = positionById.get(transition.to);
            if (!from || !to) return null;
            if (transition.from === transition.to) {
              return (
                <g key={transition.id} data-transition-id={transition.id}>
                  <path
                    d={`M ${from.x - 58} ${from.y - NODE_HEIGHT / 2} C ${from.x - 58} ${from.y - 125}, ${from.x + 58} ${from.y - 125}, ${from.x + 58} ${from.y - NODE_HEIGHT / 2}`}
                    fill="none"
                    stroke="#6b7d8d"
                    strokeWidth="2"
                    markerEnd="url(#conceptual-arrow)"
                  />
                  <text x={from.x} y={from.y - 130} textAnchor="middle" fill="#536474" fontSize="11">
                    {transition.trigger}
                  </text>
                </g>
              );
            }
            const dx = to.x - from.x;
            const dy = to.y - from.y;
            const distance = Math.max(1, Math.sqrt(dx * dx + dy * dy));
            const inset = Math.min(NODE_WIDTH / 2, distance / 3);
            const x1 = from.x + (dx / distance) * inset;
            const y1 = from.y + (dy / distance) * inset;
            const x2 = to.x - (dx / distance) * inset;
            const y2 = to.y - (dy / distance) * inset;
            const longEdge = Math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2) > NODE_WIDTH * 1.8;
            const normal = { x: -(y2 - y1) / distance, y: (x2 - x1) / distance };
            const control = {
              x: (x1 + x2) / 2 + normal.x * 160,
              y: (y1 + y2) / 2 + normal.y * 160,
            };
            const label = longEdge
              ? { x: (x1 + 2 * control.x + x2) / 4, y: (y1 + 2 * control.y + y2) / 4 }
              : { x: (x1 + x2) / 2, y: (y1 + y2) / 2 };
            return (
              <g key={transition.id} data-transition-id={transition.id}>
                {longEdge ? (
                  <path d={`M ${x1} ${y1} Q ${control.x} ${control.y} ${x2} ${y2}`} fill="none" stroke="#365f7a" strokeWidth="2.2" markerEnd="url(#conceptual-arrow)" />
                ) : (
                  <line x1={x1} y1={y1} x2={x2} y2={y2} stroke="#365f7a" strokeWidth="2.2" markerEnd="url(#conceptual-arrow)" />
                )}
                <text x={label.x} y={label.y - 7} textAnchor="middle" fill="#365f7a" fontSize="11">
                  {transition.trigger.length > 20 ? `${transition.trigger.slice(0, 19)}…` : transition.trigger}
                </text>
              </g>
            );
          })}
          {model.states.map((modelState) => {
            const position = positionById.get(modelState.id);
            if (!position) return null;
            return (
              <g
                key={modelState.id}
                data-state-id={modelState.id}
                role="button"
                tabIndex={0}
                aria-label={t("conceptualDiagram.nodeLabel", { state: modelState.label })}
                transform={`translate(${position.x - NODE_WIDTH / 2} ${position.y - NODE_HEIGHT / 2})`}
                className="cursor-move outline-none focus-visible:[&>rect:first-of-type]:stroke-[5]"
                onPointerDown={(event) => {
                  event.currentTarget.setPointerCapture(event.pointerId);
                  dragging.current = { stateId: modelState.id, pointerId: event.pointerId };
                }}
                onKeyDown={(event) => onNodeKeyDown(event, position)}
              >
                <title>{`${modelState.label}: ${modelState.definition}`}</title>
                <rect
                  width={NODE_WIDTH}
                  height={NODE_HEIGHT}
                  rx="14"
                  fill={modelState.absorbing ? "#f4ece9" : "#eef4f7"}
                  stroke="#2f5f78"
                  strokeWidth={modelState.absorbing ? 4 : 2}
                />
                {modelState.absorbing && <rect x="7" y="7" width={NODE_WIDTH - 14} height={NODE_HEIGHT - 14} rx="10" fill="none" stroke="#2f5f78" strokeWidth="1.5" />}
                <text x={NODE_WIDTH / 2} y="38" textAnchor="middle" fill="#172033" fontSize="17" fontWeight="700">
                  {modelState.label.length > 16 ? `${modelState.label.slice(0, 15)}…` : modelState.label}
                </text>
                <text x={NODE_WIDTH / 2} y="67" textAnchor="middle" fill="#596675" fontSize="11">
                  {modelState.definition.length > 24 ? `${modelState.definition.slice(0, 23)}…` : modelState.definition}
                </text>
              </g>
            );
          })}
        </svg>
      </div>

      <div className="mt-2 flex items-center gap-1.5 text-[10px] leading-4 text-muted">
        <Move size={12} className="shrink-0" /> {t("conceptualDiagram.editHint")}
      </div>

      {issues.length > 0 && (
        <ul className="mt-3 space-y-1 text-[10px] leading-4 text-warn">
          {issues.slice(0, 5).map((issue) => (
            <li key={issue}>• {formatHeorReviewIssue(issue, t("panel.artifactPending"))}</li>
          ))}
        </ul>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={() => setPositions(initial)}
          className="inline-flex items-center gap-1.5 text-xs font-medium text-link hover:underline"
        >
          <LayoutGrid size={13} /> {t("conceptualDiagram.autoLayout")}
        </button>
        {!modelComplete && (
          <button type="button" onClick={onRequestModel} className="inline-flex items-center gap-1.5 text-xs font-medium text-link hover:underline">
            <MessageSquareText size={13} /> {t("conceptualDiagram.askModel")}
          </button>
        )}
        {ready && desktopAvailable && (
          <button
            type="button"
            onClick={() => onGenerate(positions)}
            disabled={generating}
            className="inline-flex items-center gap-1.5 rounded-md bg-accent px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-50"
          >
            {generating ? <Loader2 size={13} className="animate-spin" /> : <FileImage size={13} />}
            {generating ? t("conceptualDiagram.generating") : t("conceptualDiagram.generate")}
          </button>
        )}
        {current && audit && (
          <>
            <button type="button" onClick={() => void openArtifactExternally(audit.svgPath)} className="inline-flex items-center gap-1.5 text-xs font-medium text-link hover:underline">
              <ExternalLink size={13} /> {t("conceptualDiagram.openSvg")}
            </button>
            <button type="button" onClick={() => void openArtifactExternally(audit.graphmlPath)} className="inline-flex items-center gap-1.5 text-xs font-medium text-link hover:underline">
              <ExternalLink size={13} /> {t("conceptualDiagram.openGraphml")}
            </button>
          </>
        )}
      </div>
      <div className="mt-2 truncate font-mono text-[10px] text-muted">
        {audit?.conceptualModelSha256 ? `${audit.modelPath} · ${audit.conceptualModelSha256.slice(0, 12)}…` : audit?.modelPath}
      </div>
    </section>
  );
}
