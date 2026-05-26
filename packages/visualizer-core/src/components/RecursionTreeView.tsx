import React, { useMemo } from "react";
import { hierarchy, tree as d3tree } from "d3-hierarchy";
import type { Trace } from "@dsa-viz/trace-schema";
import {
  buildRecursionTree,
  countCalls,
  findActiveCall,
  formatArgs,
  formatArgsVerbose,
  type CallNode,
} from "../lib/recursionTree";

export interface RecursionTreeViewProps {
  trace: Trace;
  t: number;
  /** Max call nodes to render before collapsing to a placeholder. */
  maxNodes?: number;
}

const NODE_W = 150;
const NODE_H = 36;

export const RecursionTreeView: React.FC<RecursionTreeViewProps> = ({
  trace,
  t,
  maxNodes = 500,
}) => {
  const root = useMemo(
    () => buildRecursionTree(trace.events, { maxNodes }),
    [trace.events, maxNodes],
  );
  const total = countCalls(root);

  const lastEvent = Math.max(0, trace.events.length - 1);
  const activeId = useMemo(
    () => findActiveCall(root, t, lastEvent)?.id ?? null,
    [root, t, lastEvent],
  );

  const layout = useMemo(() => {
    const h = hierarchy<CallNode>(root);
    return d3tree<CallNode>().nodeSize([NODE_W + 20, NODE_H + 50])(h);
  }, [root]);

  if (total === 0) {
    return <em className="dsa-viz-recursion-empty">(no calls recorded)</em>;
  }

  const nodes = layout.descendants().filter((n) => n.depth > 0);
  const links = layout.links().filter((l) => l.source.depth > 0);

  const xs = nodes.map((n) => n.x);
  const ys = nodes.map((n) => n.y);
  const padX = NODE_W / 2 + 12;
  const padY = NODE_H / 2 + 12;
  const minX = Math.min(...xs) - padX;
  const maxX = Math.max(...xs) + padX;
  const minY = Math.min(...ys) - padY;
  const maxY = Math.max(...ys) + padY;

  return (
    <svg
      className="dsa-viz-recursion"
      viewBox={`${minX} ${minY} ${maxX - minX} ${maxY - minY}`}
      preserveAspectRatio="xMidYMid meet"
    >
      {links.map((link, i) => (
        <line
          key={i}
          x1={link.source.x}
          y1={link.source.y}
          x2={link.target.x}
          y2={link.target.y}
          className="dsa-viz-recursion-edge"
        />
      ))}
      {nodes.map((node) => {
        const isActive = node.data.id === activeId;
        const argsLabel = formatArgs(node.data.args);
        const tooltip = `${node.data.func}(${formatArgsVerbose(node.data.args)})`;
        return (
          <g
            key={node.data.id}
            transform={`translate(${node.x}, ${node.y})`}
            className={`dsa-viz-recursion-node${isActive ? " is-active" : ""}`}
          >
            {/* Native browser tooltip — hovering a node reveals the full
                args including self= and full pointer ids. */}
            <title>{tooltip}</title>
            <rect x={-NODE_W / 2} y={-NODE_H / 2} width={NODE_W} height={NODE_H} rx={6} />
            <text className="dsa-viz-recursion-func" textAnchor="middle" y={-2}>
              {node.data.func}
            </text>
            <text className="dsa-viz-recursion-args" textAnchor="middle" y={13}>
              {argsLabel}
            </text>
          </g>
        );
      })}
    </svg>
  );
};
