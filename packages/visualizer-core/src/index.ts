export { VisualizerPanel } from "./components/VisualizerPanel";
export { CodePane } from "./components/CodePane";
export { ControlBar } from "./components/ControlBar";
export { CallStack } from "./components/CallStack";
export { HeapView } from "./components/HeapView";
export { RecursionTreeView } from "./components/RecursionTreeView";
export { Explainer } from "./components/Explainer";

export { ArrayView } from "./components/structures/ArrayView";
export { LinkedListView } from "./components/structures/LinkedListView";
export { TreeView } from "./components/structures/TreeView";
export { GraphView } from "./components/structures/GraphView";
export { StackView } from "./components/structures/StackView";
export { QueueView } from "./components/structures/QueueView";
export { HeapTreeView } from "./components/structures/HeapTreeView";

export { detectStructure } from "./lib/detectStructure";
export { buildRecursionTree, findActiveCall, countCalls } from "./lib/recursionTree";
export type { CallNode } from "./lib/recursionTree";
export { detectPatterns, activePatternHit } from "./lib/patterns";
export type { PatternHit, PatternKind } from "./lib/patterns";
export { diffTraces } from "./lib/diffTraces";
export type { TraceDiff, TraceDivergence } from "./lib/diffTraces";
export { usePlayback } from "./hooks/usePlayback";
export { useTrace } from "./hooks/useTrace";
export { traceClient } from "./lib/traceClient";
