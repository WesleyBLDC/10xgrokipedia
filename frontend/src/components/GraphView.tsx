import { useEffect, useRef, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import ForceGraph3D from "react-force-graph-3d";
import { getArticleGraph } from "../api";
import type { ArticleGraph, GraphNode, GraphEdge } from "../api";
// @ts-ignore - three.js types may not be available
import * as THREE from "three";

interface GraphViewProps {
  articleId?: string;
  onClose?: () => void;
  isModal?: boolean;
}

export default function GraphView({ articleId, onClose, isModal = false }: GraphViewProps) {
  const navigate = useNavigate();
  const fgRef = useRef<any>();
  const [graph, setGraph] = useState<ArticleGraph | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [hoveredNode, setHoveredNode] = useState<GraphNode | null>(null);
  const [hoveredEdge, setHoveredEdge] = useState<GraphEdge | null>(null);
  const [highlightNodes, setHighlightNodes] = useState<Set<string>>(new Set());
  const [highlightLinks, setHighlightLinks] = useState<Set<string>>(new Set());

  // Use articleId prop if provided
  const idToUse = articleId;

  useEffect(() => {
    const loadGraph = async () => {
      try {
        setLoading(true);
        setError(null);
        const data = await getArticleGraph(idToUse);
        setGraph(data);
      } catch (err) {
        console.error("Error loading graph:", err);
        const errorMessage = err instanceof Error ? err.message : "Failed to load graph";
        setError(errorMessage);
      } finally {
        setLoading(false);
      }
    };
    loadGraph();
  }, [idToUse]);

  // Highlight nodes and links on hover
  const handleNodeHover = useCallback((node: GraphNode | null) => {
    setHoveredNode(node);
    
    if (!node || !graph) {
      setHighlightNodes(new Set());
      setHighlightLinks(new Set());
      return;
    }

    const highlightNodesSet = new Set([node.id]);
    const highlightLinksSet = new Set<string>();

    // Find all connected nodes and links
    graph.edges.forEach((edge) => {
      if (edge.source === node.id) {
        highlightNodesSet.add(edge.target);
        highlightLinksSet.add(`${edge.source}-${edge.target}`);
      } else if (edge.target === node.id) {
        highlightNodesSet.add(edge.source);
        highlightLinksSet.add(`${edge.source}-${edge.target}`);
      }
    });

    setHighlightNodes(highlightNodesSet);
    setHighlightLinks(highlightLinksSet);
  }, [graph]);

  const handleLinkHover = useCallback((link: any) => {
    // Convert link back to edge format for our state
    if (link && graph) {
      const edge = graph.edges.find(
        e => e.source === link.source?.id && e.target === link.target?.id
      ) || graph.edges.find(
        e => e.source === (typeof link.source === 'string' ? link.source : link.source?.id) && 
             e.target === (typeof link.target === 'string' ? link.target : link.target?.id)
      );
      setHoveredEdge(edge || null);
    } else {
      setHoveredEdge(null);
    }
  }, [graph]);

  const handleNodeClick = useCallback((node: GraphNode) => {
    setSelectedNode(node);
    // node.id is now a UUID, use it directly
    navigate(`/page/${node.id}`);
    // Close modal if in modal mode
    if (isModal && onClose) {
      onClose();
    }
  }, [navigate, isModal, onClose]);

  // Color functions
  const getNodeColor = useCallback((node: GraphNode) => {
    if (selectedNode?.id === node.id) return "#ff6b6b";
    if (hoveredNode?.id === node.id) return "#4ecdc4";
    if (graph?.center_node === node.id) return "#ffe66d";
    if (highlightNodes.has(node.id)) return "#95e1d3";
    return "#a8dadc";
  }, [selectedNode, hoveredNode, highlightNodes, graph?.center_node]);

  const getLinkColor = useCallback((edge: GraphEdge) => {
    if (hoveredEdge && hoveredEdge.source === edge.source && hoveredEdge.target === edge.target) {
      return "#ff6b6b";
    }
    if (highlightLinks.has(`${edge.source}-${edge.target}`)) {
      return "#4ecdc4";
    }
    // Color by edge type
    if (edge.types.includes("shared_exact_citations")) return "#ff6b6b";
    if (edge.types.includes("direct_link")) return "#ffe66d";
    if (edge.types.includes("shared_domains")) return "#4ecdc4";
    return "#95a5a6";
  }, [hoveredEdge, highlightLinks]);

  // Node size based on connections
  const getNodeSize = useCallback((node: GraphNode) => {
    if (!graph) return 3;
    const connections = graph.edges.filter(
      (e) => e.source === node.id || e.target === node.id
    ).length;
    return Math.max(3, Math.min(8, 3 + connections * 0.3));
  }, [graph]);

  if (loading) {
    return (
      <div style={{ 
        display: "flex", 
        justifyContent: "center", 
        alignItems: "center", 
        height: "100vh",
        fontSize: "18px",
        color: "#666"
      }}>
        Loading graph...
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ 
        display: "flex", 
        justifyContent: "center", 
        alignItems: "center", 
        height: "100vh",
        flexDirection: "column",
        gap: "10px"
      }}>
        <div style={{ fontSize: "18px", color: "#e74c3c" }}>Error: {error}</div>
        <button 
          onClick={() => window.location.reload()}
          style={{
            padding: "10px 20px",
            fontSize: "14px",
            backgroundColor: "#3498db",
            color: "white",
            border: "none",
            borderRadius: "5px",
            cursor: "pointer"
          }}
        >
          Retry
        </button>
      </div>
    );
  }

  if (!graph) {
    return null;
  }

  // Transform graph data to match react-force-graph-3d format (links instead of edges)
  const graphData = {
    nodes: graph.nodes,
    links: graph.edges.map(edge => ({
      source: edge.source,
      target: edge.target,
      weight: edge.weight,
      types: edge.types,
      metadata: edge.metadata
    }))
  };

  const containerStyle: React.CSSProperties = isModal 
    ? { position: "relative", width: "100%", height: "100%" }
    : { position: "relative", width: "100vw", height: "100vh" };

  return (
    <div style={containerStyle}>
      {isModal && onClose && (
        <button
          onClick={onClose}
          style={{
            position: "absolute",
            top: "20px",
            right: "20px",
            zIndex: 1001,
            padding: "10px 20px",
            backgroundColor: "#e74c3c",
            color: "white",
            border: "none",
            borderRadius: "5px",
            cursor: "pointer",
            fontSize: "14px",
            fontWeight: "bold",
            boxShadow: "0 2px 8px rgba(0,0,0,0.3)"
          }}
        >
          ✕ Close
        </button>
      )}
      <ForceGraph3D
        ref={fgRef}
        graphData={graphData}
        nodeLabel={(node: GraphNode) => `
          <div style="
            background: rgba(0,0,0,0.8);
            color: white;
            padding: 8px 12px;
            border-radius: 4px;
            font-size: 12px;
            max-width: 200px;
          ">
            <strong>${node.title}</strong><br/>
            Citations: ${node.citation_count}<br/>
            Links: ${node.outgoing_links}
          </div>
        `}
        nodeColor={getNodeColor}
        nodeVal={getNodeSize}
        linkLabel={(link: any) => {
          // Find the corresponding edge to get metadata
          const edge = graph?.edges.find(
            e => (e.source === link.source?.id || e.source === link.source) && 
                 (e.target === link.target?.id || e.target === link.target)
          );
          if (!edge) return '';
          return `
            <div style="
              background: rgba(0,0,0,0.8);
              color: white;
              padding: 8px 12px;
              border-radius: 4px;
              font-size: 12px;
              max-width: 250px;
            ">
              <strong>Weight: ${edge.weight.toFixed(2)}</strong><br/>
              Types: ${edge.types.join(", ")}<br/>
              ${edge.metadata?.shared_domains ? `Domains: ${edge.metadata.shared_domains.length}` : ""}
            </div>
          `;
        }}
        linkColor={(link: any) => {
          const edge = graph?.edges.find(
            e => (e.source === link.source?.id || e.source === link.source) && 
                 (e.target === link.target?.id || e.target === link.target)
          );
          return edge ? getLinkColor(edge) : "#95a5a6";
        }}
        linkWidth={(link: any) => {
          const edge = graph?.edges.find(
            e => (e.source === link.source?.id || e.source === link.source) && 
                 (e.target === link.target?.id || e.target === link.target)
          );
          return edge ? Math.max(1, edge.weight / 5) : 1;
        }}
        linkOpacity={0.6}
        onNodeHover={handleNodeHover}
        onLinkHover={handleLinkHover}
        onNodeClick={handleNodeClick}
        enableNodeDrag={true}
        showNavInfo={true}
        cooldownTicks={100}
        onEngineStop={() => {
          if (fgRef.current && graph.center_node) {
            // Focus on center node if specified
            const centerNode = graph.nodes.find(n => n.id === graph.center_node);
            if (centerNode) {
              // Use a fixed distance for camera positioning
              const distance = 150;
              fgRef.current.cameraPosition(
                { x: distance, y: distance, z: distance },
                { x: 0, y: 0, z: 0 },
                3000
              );
            }
          }
        }}
        nodeThreeObject={(node: GraphNode) => {
          const sprite = new THREE.Sprite(
            new THREE.SpriteMaterial({
              map: (() => {
                const canvas = document.createElement("canvas");
                canvas.width = 64;
                canvas.height = 64;
                const ctx = canvas.getContext("2d")!;
                ctx.fillStyle = getNodeColor(node);
                ctx.beginPath();
                ctx.arc(32, 32, 28, 0, 2 * Math.PI);
                ctx.fill();
                ctx.strokeStyle = "#fff";
                ctx.lineWidth = 3;
                ctx.stroke();
                return new THREE.CanvasTexture(canvas);
              })(),
              transparent: true,
            })
          );
          sprite.scale.set(12, 12, 1);
          return sprite;
        }}
      />
      
      {/* Info Panel */}
      <div style={{
        position: "absolute",
        top: "20px",
        left: "20px",
        background: "rgba(30, 30, 30, 0.95)",
        padding: "20px",
        borderRadius: "8px",
        boxShadow: "0 2px 10px rgba(0,0,0,0.5)",
        maxWidth: "300px",
        zIndex: 1000,
        border: "1px solid #555"
      }}>
        <h2 style={{ margin: "0 0 15px 0", fontSize: "20px", color: "#fff" }}>Article Graph</h2>
        {graph.stats && (
          <div style={{ fontSize: "14px", color: "#ccc", marginBottom: "15px" }}>
            <div><strong style={{ color: "#fff" }}>Nodes:</strong> {graph.stats.total_nodes}</div>
            <div><strong style={{ color: "#fff" }}>Edges:</strong> {graph.stats.total_edges}</div>
          </div>
        )}
        {selectedNode && (
          <div style={{ 
            marginTop: "15px", 
            padding: "10px", 
            background: "rgba(255, 107, 107, 0.2)", 
            borderRadius: "4px",
            fontSize: "12px",
            border: "1px solid #ff6b6b"
          }}>
            <strong style={{ color: "#ff6b6b" }}>Selected:</strong> <span style={{ color: "#fff" }}>{selectedNode.title}</span>
          </div>
        )}
        {hoveredNode && (
          <div style={{ 
            marginTop: "10px", 
            padding: "10px", 
            background: "rgba(78, 205, 196, 0.2)", 
            borderRadius: "4px",
            fontSize: "12px",
            border: "1px solid #4ecdc4"
          }}>
            <strong style={{ color: "#4ecdc4" }}>Hovering:</strong> <span style={{ color: "#fff" }}>{hoveredNode.title}</span>
          </div>
        )}
        {hoveredEdge && (
          <div style={{ 
            marginTop: "10px", 
            padding: "10px", 
            background: "rgba(255, 230, 109, 0.2)", 
            borderRadius: "4px",
            fontSize: "12px",
            border: "1px solid #ffe66d"
          }}>
            <strong style={{ color: "#ffe66d" }}>Edge:</strong> <span style={{ color: "#fff" }}>{hoveredEdge.weight.toFixed(2)}</span><br/>
            <span style={{ fontSize: "11px", color: "#ccc" }}>
              {hoveredEdge.types.join(", ")}
            </span>
          </div>
        )}
        <div style={{ marginTop: "15px", fontSize: "12px", color: "#ccc" }}>
          <div style={{ fontWeight: "bold", marginBottom: "5px", color: "#fff" }}>Controls:</div>
          <div>• Click node to navigate</div>
          <div>• Drag to rotate</div>
          <div>• Scroll to zoom</div>
          <div>• Hover to highlight</div>
        </div>
      </div>

      {/* Legend */}
      <div style={{
        position: "absolute",
        bottom: "20px",
        left: "20px",
        background: "rgba(30, 30, 30, 0.95)",
        padding: "15px",
        borderRadius: "8px",
        boxShadow: "0 2px 10px rgba(0,0,0,0.5)",
        fontSize: "12px",
        zIndex: 1000,
        border: "1px solid #555"
      }}>
        <div style={{ fontWeight: "bold", marginBottom: "8px", color: "#fff" }}>Edge Colors:</div>
        <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <div style={{ width: "20px", height: "3px", background: "#ff6b6b" }}></div>
            <span style={{ color: "#fff" }}>Shared Citations</span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <div style={{ width: "20px", height: "3px", background: "#ffe66d" }}></div>
            <span style={{ color: "#fff" }}>Direct Links</span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <div style={{ width: "20px", height: "3px", background: "#4ecdc4" }}></div>
            <span style={{ color: "#fff" }}>Shared Domains</span>
          </div>
        </div>
      </div>
    </div>
  );
}

