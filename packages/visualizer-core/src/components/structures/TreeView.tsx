import React, { useMemo } from "react";
import { hierarchy, tree as d3tree, type HierarchyPointNode } from "d3-hierarchy";
import type { HeapObject, Value } from "@dsa-viz/trace-schema";

export interface TreeViewProps {
  rootId: string;
  heap: Record<string, HeapObject>;
  /** comma-separated list of child field names (default: "left,right") */
  childFields?: string;
  width?: number;
  height?: number;
}

interface TreeNode {
  id: string;
  val: Value;
  children: TreeNode[];
}

/**
 * Lays out a tree using d3-hierarchy. Each node is a circle labeled with the
 * `val` field; edges connect parents to children. Handles binary trees
 * (`left`/`right`) by default; pass `childFields="children"` for n-ary trees,
 * or a custom list like `"first,second,third"`.
 */
export const TreeView: React.FC<TreeViewProps> = ({
  rootId,
  heap,
  childFields = "left,right",
  width = 480,
  height = 280,
}) => {
  const fields = childFields.split(",").map((s) => s.trim());
  const root = useMemo(() => buildTree(rootId, heap, fields, new Set()), [
    rootId,
    heap,
    childFields,
  ]);
  if (!root) return <em>(not tree-like)</em>;

  const layout = useMemo(() => {
    const h = hierarchy<TreeNode>(root, (d) => d.children);
    return d3tree<TreeNode>().size([width - 40, height - 40])(h);
  }, [root, width, height]);

  const nodes = layout.descendants();
  const links = layout.links();

  return (
    <svg className="dsa-viz-treeview" width={width} height={height}>
      <g transform="translate(20,20)">
        {links.map((l, i) => (
          <line
            key={i}
            x1={l.source.x}
            y1={l.source.y}
            x2={l.target.x}
            y2={l.target.y}
            className="dsa-viz-tree-edge"
            stroke="#888"
          />
        ))}
        {nodes.map((n: HierarchyPointNode<TreeNode>) => (
          <g key={n.data.id} transform={`translate(${n.x},${n.y})`}>
            <circle r={16} className="dsa-viz-tree-node" fill="#eef" stroke="#446" />
            <text textAnchor="middle" dy="0.35em" className="dsa-viz-tree-label">
              {labelValue(n.data.val)}
            </text>
          </g>
        ))}
      </g>
    </svg>
  );
};

function buildTree(
  id: string,
  heap: Record<string, HeapObject>,
  fields: string[],
  visiting: Set<string>,
): TreeNode | null {
  if (visiting.has(id)) return null; // cycle guard
  const obj = heap[id];
  if (!obj || obj.kind !== "object") return null;
  visiting.add(id);
  const childRefs: { id: string }[] = [];

  // generic children field
  if (obj.fields.children?.kind === "ref") {
    const cobj = heap[obj.fields.children.id];
    if (cobj?.kind === "list") {
      for (const v of cobj.items) {
        if (v.kind === "ref") childRefs.push({ id: v.id });
      }
    }
  }
  for (const f of fields) {
    const v = obj.fields[f];
    if (v?.kind === "ref") childRefs.push({ id: v.id });
  }

  const children: TreeNode[] = [];
  for (const r of childRefs) {
    const c = buildTree(r.id, heap, fields, visiting);
    if (c) children.push(c);
  }
  visiting.delete(id);

  return {
    id,
    val: obj.fields.val ?? obj.fields.value ?? obj.fields.data ?? { kind: "none" },
    children,
  };
}

function labelValue(v: Value): string {
  if (v.kind === "int" || v.kind === "float" || v.kind === "str" || v.kind === "bool")
    return String((v as { v: unknown }).v);
  if (v.kind === "none") return "·";
  return "→";
}
