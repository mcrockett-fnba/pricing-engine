<template>
  <div class="segmentation-tree">
    <div class="tree-controls">
      <button @click="expandAll = !expandAll">
        {{ expandAll ? 'Collapse' : 'Expand All' }}
      </button>
      <span class="tree-info">Click a leaf to see details</span>
    </div>
    <div class="tree-scroll">
      <svg :width="svgWidth" :height="svgHeight" class="tree-svg">
        <g :transform="`translate(${margin.left}, ${margin.top})`">
          <!-- Edges -->
          <line
            v-for="edge in edges"
            :key="edge.id"
            :x1="edge.x1" :y1="edge.y1"
            :x2="edge.x2" :y2="edge.y2"
            stroke="#ccc"
            stroke-width="1"
          />
          <!-- Nodes -->
          <g
            v-for="node in visibleNodes"
            :key="node.id"
            :transform="`translate(${node.x}, ${node.y})`"
            @click="onNodeClick(node)"
            class="tree-node"
          >
            <!-- Leaf node -->
            <template v-if="node.type === 'leaf'">
              <rect
                :x="-nodeW/2" :y="-nodeH/2"
                :width="nodeW" :height="nodeH"
                :fill="leafColor(node.mean_time)"
                :stroke="node.leaf_id === selectedLeafId ? '#1a1a2e' : '#999'"
                :stroke-width="node.leaf_id === selectedLeafId ? 3 : 1"
                rx="4"
              />
              <text dy="0" text-anchor="middle" font-size="10" fill="#fff" font-weight="600">
                #{{ node.leaf_id }}
              </text>
              <text dy="12" text-anchor="middle" font-size="9" fill="#fff" opacity="0.85">
                {{ node.samples?.toLocaleString() }}
              </text>
            </template>
            <!-- Internal node -->
            <template v-else>
              <circle
                r="14"
                fill="#f8f9fa"
                stroke="#adb5bd"
                stroke-width="1"
              />
              <text dy="3" text-anchor="middle" font-size="8" fill="#333">
                {{ shortFeature(node.feature) }}
              </text>
              <text :dy="-18" text-anchor="middle" font-size="8" fill="#999">
                {{ node.threshold?.toFixed(1) }}
              </text>
            </template>
          </g>
        </g>
      </svg>
    </div>

    <!-- Color legend -->
    <div class="legend">
      <span class="legend-label">Payoff speed:</span>
      <div class="legend-gradient"></div>
      <span class="legend-fast">Fast</span>
      <span class="legend-slow">Slow</span>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'

const props = defineProps({
  treeData: { type: Object, required: true },
  selectedLeafId: { type: Number, default: null },
})

const emit = defineEmits(['selectLeaf'])

const expandAll = ref(false)
const collapsedNodes = ref(new Set())

const nodeW = 54
const nodeH = 30
const levelH = 60
const leafSpacing = 60
const margin = { top: 20, right: 20, bottom: 20, left: 20 }

// Layout the tree using a simple recursive algorithm
function layoutTree(node, depth = 0) {
  if (!node) return { nodes: [], width: 0 }

  if (node.type === 'leaf') {
    return {
      nodes: [{ ...node, depth, x: 0, y: depth * levelH, id: `node-${node.node_id}` }],
      width: leafSpacing,
    }
  }

  // Collapse deep nodes unless expandAll
  const maxDepth = expandAll.value ? 20 : 4
  if (depth >= maxDepth) {
    // Treat as pseudo-leaf showing subtree count
    return {
      nodes: [{
        ...node,
        type: 'leaf',
        depth,
        x: 0,
        y: depth * levelH,
        id: `node-${node.node_id}`,
        leaf_id: null,
        mean_time: node.left?.mean_time || 0,
      }],
      width: leafSpacing,
    }
  }

  const left = layoutTree(node.left, depth + 1)
  const right = layoutTree(node.right, depth + 1)

  const totalWidth = left.width + right.width
  const leftOffset = -totalWidth / 2 + left.width / 2
  const rightOffset = totalWidth / 2 - right.width / 2

  // Offset child positions
  const leftNodes = left.nodes.map(n => ({ ...n, x: n.x + leftOffset }))
  const rightNodes = right.nodes.map(n => ({ ...n, x: n.x + rightOffset }))

  const thisNode = {
    ...node,
    depth,
    x: 0,
    y: depth * levelH,
    id: `node-${node.node_id}`,
    leftCenter: leftOffset,
    rightCenter: rightOffset,
  }

  return {
    nodes: [thisNode, ...leftNodes, ...rightNodes],
    width: totalWidth,
  }
}

const layout = computed(() => {
  if (!props.treeData?.nested_tree) return { nodes: [], width: 0 }
  return layoutTree(props.treeData.nested_tree)
})

const visibleNodes = computed(() => layout.value.nodes)

const edges = computed(() => {
  const edgeList = []
  const nodeMap = new Map()
  for (const n of visibleNodes.value) {
    nodeMap.set(n.node_id, n)
  }

  for (const n of visibleNodes.value) {
    if (n.type !== 'leaf' && n.leftCenter !== undefined) {
      // Find direct children
      const leftChild = visibleNodes.value.find(
        c => c.depth === n.depth + 1 && Math.abs(c.x - (n.x + n.leftCenter)) < 1
      )
      const rightChild = visibleNodes.value.find(
        c => c.depth === n.depth + 1 && Math.abs(c.x - (n.x + n.rightCenter)) < 1
      )
      if (leftChild) {
        edgeList.push({
          id: `e-${n.node_id}-l`,
          x1: n.x, y1: n.y + 14,
          x2: leftChild.x, y2: leftChild.y - (leftChild.type === 'leaf' ? nodeH/2 : 14),
        })
      }
      if (rightChild) {
        edgeList.push({
          id: `e-${n.node_id}-r`,
          x1: n.x, y1: n.y + 14,
          x2: rightChild.x, y2: rightChild.y - (rightChild.type === 'leaf' ? nodeH/2 : 14),
        })
      }
    }
  }
  return edgeList
})

const svgWidth = computed(() => layout.value.width + margin.left + margin.right)
const svgHeight = computed(() => {
  const maxDepth = visibleNodes.value.reduce((m, n) => Math.max(m, n.depth), 0)
  return (maxDepth + 1) * levelH + margin.top + margin.bottom
})

function leafColor(meanTime) {
  // Green (fast payoff) → Blue (slow payoff)
  // Normalize: 0-120 months range
  const t = Math.min(Math.max((meanTime || 0) / 120, 0), 1)
  const r = Math.round(37 * (1 - t) + 30 * t)
  const g = Math.round(99 * (1 - t) + 58 * t)
  const b = Math.round(89 * (1 - t) + 138 * t)
  return `rgb(${r},${g},${b})`
}

function shortFeature(name) {
  const map = {
    noteDateYear: 'year',
    creditScore: 'credit',
    interestRate: 'rate',
    loanSize: 'size',
    stateGroup: 'region',
    origCustAmortMonth: 'term',
  }
  return map[name] || name
}

function onNodeClick(node) {
  if (node.type === 'leaf' && node.leaf_id) {
    emit('selectLeaf', node.leaf_id)
  }
}
</script>

<style scoped>
.segmentation-tree { overflow: hidden; }

.tree-controls {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-bottom: 0.5rem;
}
.tree-controls button {
  padding: 0.3rem 0.75rem;
  border: 1px solid #dee2e6;
  background: #fff;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.8rem;
}
.tree-info { font-size: 0.8rem; color: #999; }

.tree-scroll {
  overflow: auto;
  max-height: 60vh;
  border: 1px solid #eee;
  border-radius: 6px;
  background: #fafbfc;
}

.tree-node { cursor: pointer; }
.tree-node:hover rect { opacity: 0.85; }
.tree-node:hover circle { fill: #e9ecef; }

.legend {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-top: 0.5rem;
  font-size: 0.8rem;
  color: #666;
}
.legend-gradient {
  width: 100px;
  height: 12px;
  background: linear-gradient(to right, rgb(37,99,89), rgb(30,58,138));
  border-radius: 2px;
}
.legend-fast { color: rgb(37,99,89); }
.legend-slow { color: rgb(30,58,138); }
</style>
