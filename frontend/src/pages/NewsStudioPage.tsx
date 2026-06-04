import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { 
  Plus, 
  Image as ImageIcon, 
  Save, 
  Zap,
  RefreshCw,
  Clock,
  Settings,
  GitBranch,
  Book,
  ArrowRight
} from 'lucide-react';
import { 
  ReactFlow, 
  MiniMap, 
  Controls, 
  Background, 
  MarkerType,
  Handle,
  Position,
  useNodesState,
  useEdgesState,
} from '@xyflow/react';
import type { Connection, Node, Edge } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { Api } from '../api';
import { useAppSession } from '../app/context';

interface NewsCard {
  card_id: string;
  kind: string;
  publisher_id: string | null;
  created_at: string;
  published_at: string | null;
  text: string | null;
  image_uri: string | null;
  image_anchor_id: string | null;
  preset_id: string | null;
  symbols: string[];
  tags: string[];
  truth_payload: Record<string, any>;
  parent_card_id: string | null;
  activation_prob: number;
  scheduled_at: string | null;
  success_criteria: Record<string, any>;
  failure_outcome: Record<string, any>;
  scenario_id: string | null;
}

interface Scenario {
  id: string;
  name: string;
}

// 1. 自定义节点组件（符合游戏赛博/终端美术设计风格）
const CyberNewsNode = ({ data, selected }: any) => {
  const card = data.card;
  const isSelected = selected;
  
  const kindColors: Record<string, string> = {
    EARNINGS: '#4ade80',
    MILITARY: '#f87171',
    DEFAULT: '#60a5fa'
  };
  const color = kindColors[card.kind] || kindColors.DEFAULT;

  return (
    <div style={{
      padding: '14px',
      borderRadius: '8px',
      background: isSelected ? 'rgba(34, 211, 238, 0.16)' : 'rgba(10, 15, 30, 0.85)',
      border: `2px solid ${isSelected ? '#22d3ee' : 'rgba(59, 130, 246, 0.25)'}`,
      boxShadow: isSelected ? '0 0 25px rgba(34, 211, 238, 0.4)' : '0 4px 12px rgba(0,0,0,0.5)',
      color: '#fff',
      width: '180px',
      fontFamily: 'monospace',
      backdropFilter: 'blur(8px)',
      position: 'relative'
    }}>
      <Handle type="target" position={Position.Left} style={{ background: '#22d3ee', width: 8, height: 8 }} />
      
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
        <span style={{
          fontSize: '8px',
          padding: '2px 6px',
          borderRadius: '3px',
          background: `${color}20`,
          border: `1px solid ${color}50`,
          color: color,
          fontWeight: 'bold',
          textTransform: 'uppercase'
        }}>
          {card.kind}
        </span>
        <span style={{ fontSize: '10px', color: '#475569' }}>
          T+{data.offsetSeconds}s
        </span>
      </div>
      
      <div style={{ 
        fontSize: '12px', 
        fontWeight: '900', 
        overflow: 'hidden', 
        textOverflow: 'ellipsis', 
        whiteSpace: 'nowrap', 
        marginBottom: '4px',
        color: '#fff',
        letterSpacing: '0.5px'
      }}>
        {card.text || `BLOCK_${card.card_id.split('-')[0].toUpperCase()}`}
      </div>
      
      <div style={{ fontSize: '10px', color: '#64748b', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {card.symbols?.join(', ') || 'NO_SYMBOLS'}
      </div>

      <Handle type="source" position={Position.Right} style={{ background: '#22d3ee', width: 8, height: 8 }} />
    </div>
  );
};

const nodeTypes = {
  cybernews: CyberNewsNode
};

const NewsStudioPage: React.FC = () => {
  const nav = useNavigate();
  const { playerId } = useAppSession();
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [selectedScenarioId, setSelectedScenarioId] = useState<string | null>(null);
  const [cards, setCards] = useState<NewsCard[]>([]);
  const [selectedCardId, setSelectedCardId] = useState<string | null>(null);
  const [presets, setPresets] = useState<Record<string, string[]>>({});
  const [loading, setLoading] = useState(false);
  const [scenarioFilter, setScenarioFilter] = useState('');
  
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  
  // 缩放滑块：控制 X 轴事件之间时间触发间隔的拉伸/压缩
  const [timeScale, setTimeScale] = useState<number>(2.0); // 默认 1px = 0.5s，即 1s = 2px

  const [editCard, setEditCard] = useState<Partial<NewsCard>>({
    kind: 'EARNINGS',
    symbols: [],
    tags: [],
    truth_payload: { impact: 0.1, direction: 'UP', intensity: 0.5, ttl_seconds: 3600 },
    activation_prob: 1.0,
    success_criteria: {},
    failure_outcome: {}
  });

  const [variants, setVariants] = useState<any[]>([]);

  // 局外持久化节点 Y 坐标，因为数据库没有提供 layout 的 Y 字段
  const [nodePositions, setNodePositions] = useState<Record<string, { x: number; y: number }>>(() => {
    try {
      const saved = localStorage.getItem('studio_node_positions_v2');
      return saved ? JSON.parse(saved) : {};
    } catch { return {}; }
  });

  useEffect(() => {
    loadScenarios();
    loadPresets();
  }, []);

  useEffect(() => {
    if (selectedScenarioId) {
      loadScenarioCards(selectedScenarioId);
    } else {
      loadAllCards();
    }
    setSelectedCardId(null);
  }, [selectedScenarioId]);

  useEffect(() => {
    if (selectedCardId) {
      const card = cards.find(c => c.card_id === selectedCardId);
      if (card) setEditCard(card);
      loadVariants(selectedCardId);
    } else {
      setVariants([]);
    }
  }, [selectedCardId, cards]);

  const loadVariants = async (cardId: string) => {
    try {
      const data = await Api.globalStudioNewsVariants(cardId);
      setVariants(data);
    } catch (err) { console.error('Failed to load variants:', err); }
  };

  const handleEmitVariant = async (text: string) => {
    if (!selectedCardId) return;
    try {
      setLoading(true);
      await Api.globalStudioNewsEmitVariant({
        card_id: selectedCardId,
        author_id: playerId || 'system',
        text: text,
      });
      loadVariants(selectedCardId);
    } catch (err) { alert('发布变体失败: ' + err); } 
    finally { setLoading(false); }
  };

  const loadScenarios = async () => {
    try {
      const data = await Api.globalStudioNewsScenarios();
      setScenarios(data);
    } catch (err) { console.error('Failed to load scenarios:', err); }
  };

  const loadAllCards = async () => {
    setLoading(true);
    try {
      setCards([]);
    } catch (err) { console.error('Failed to load cards:', err); }
    finally { setLoading(false); }
  };

  const loadScenarioCards = async (id: string) => {
    setLoading(true);
    try {
      const data = await Api.globalStudioNewsScenarioCards(id);
      setCards(data as NewsCard[]);
    } catch (err) { console.error('Failed to load scenario cards:', err); }
    finally { setLoading(false); }
  };

  const loadPresets = async () => {
    try {
      const data = await Api.studioNewsPresets(playerId || 'author');
      setPresets(data);
    } catch (err) { console.error('Failed to load presets:', err); }
  };

  // 保存（创建/修改）节点
  const handleSaveCard = async () => {
    try {
      setLoading(true);
      const payload = {
        ...editCard,
        actor_id: playerId || 'author',
        scenario_id: selectedScenarioId || editCard.scenario_id
      };
      const resp = await Api.globalStudioNewsCreateCard(payload as any);
      setSelectedCardId(resp.card_id);
      if (selectedScenarioId) loadScenarioCards(selectedScenarioId);
      alert('保存成功');
    } catch (err) { alert('保存失败: ' + err); }
    finally { setLoading(false); }
  };

  // 创建一个全新的根事件/独立事件
  const handleCreateNewNode = async () => {
    if (!selectedScenarioId) {
      alert('请先选择一个剧本归档，或者创建一个新剧本归档');
      return;
    }
    try {
      setLoading(true);
      const nowTime = new Date().toISOString();
      const payload = {
        kind: 'EARNINGS',
        symbols: [],
        tags: [],
        truth_payload: { impact: 0.1, direction: 'UP', intensity: 0.5, ttl_seconds: 3600 },
        activation_prob: 1.0,
        actor_id: playerId || 'author',
        scenario_id: selectedScenarioId,
        scheduled_at: nowTime,
        parent_card_id: null
      };
      const resp = await Api.globalStudioNewsCreateCard(payload as any);
      setSelectedCardId(resp.card_id);
      loadScenarioCards(selectedScenarioId);
    } catch (err) {
      alert('创建事件节点失败: ' + err);
    } finally {
      setLoading(false);
    }
  };

  // 当节点被点击选中时
  const onNodeClick = useCallback((_event: React.MouseEvent, node: any) => {
    setSelectedCardId(node.id);
  }, []);

  useEffect(() => {
    const referenceTime = cards.length > 0 
      ? new Date(Math.min(...cards.map(c => c.scheduled_at ? new Date(c.scheduled_at).getTime() : Date.now())))
      : new Date();

    const newNodes = cards.map((card, index) => {
      const offsetMs = card.scheduled_at ? new Date(card.scheduled_at).getTime() - referenceTime.getTime() : 0;
      const offsetSeconds = Math.max(0, Math.floor(offsetMs / 1000));
      
      const savedPos = nodePositions[card.card_id];
      const defaultX = offsetSeconds * timeScale + 50;
      const defaultY = savedPos ? savedPos.y : (index % 5) * 130 + 80;

      return {
        id: card.card_id,
        type: 'cybernews',
        position: { x: savedPos ? offsetSeconds * timeScale + 50 : defaultX, y: defaultY },
        data: { 
          card, 
          offsetSeconds 
        }
      };
    });
    setNodes(newNodes as Node[]);

    const newEdges = cards
      .filter(c => c.parent_card_id && cards.some(p => p.card_id === c.parent_card_id))
      .map(c => ({
        id: `edge-${c.parent_card_id}-${c.card_id}`,
        source: c.parent_card_id!,
        target: c.card_id,
        animated: true,
        style: { stroke: '#22d3ee', strokeWidth: 2 },
        markerEnd: { type: MarkerType.ArrowClosed, color: '#22d3ee' }
      }));
    setEdges(newEdges as Edge[]);
  }, [cards, timeScale, nodePositions, setNodes, setEdges]);

  const onNodeDragStop = useCallback(async (_event: any, node: any) => {
    const card = cards.find(c => c.card_id === node.id);
    if (!card) return;

    const referenceTime = cards.length > 0 
      ? new Date(Math.min(...cards.map(c => c.scheduled_at ? new Date(c.scheduled_at).getTime() : Date.now())))
      : new Date();

    // 根据新的 X 计算时间差偏移
    const currentOffsetSeconds = Math.max(0, Math.floor((node.position.x - 50) / timeScale));
    const newScheduledTime = new Date(referenceTime.getTime() + currentOffsetSeconds * 1000).toISOString();

    // 更新局外 Y 坐标
    const updatedPos = {
      ...nodePositions,
      [node.id]: { x: node.position.x, y: node.position.y }
    };
    setNodePositions(updatedPos);
    localStorage.setItem('studio_node_positions_v2', JSON.stringify(updatedPos));

    try {
      await Api.globalStudioNewsCreateCard({
        ...card,
        scheduled_at: newScheduledTime,
        actor_id: playerId || 'author',
      } as any);
      if (selectedScenarioId) {
        loadScenarioCards(selectedScenarioId);
      }
    } catch (err) {
      console.error('Failed to update scheduled position:', err);
    }
  }, [cards, timeScale, nodePositions, selectedScenarioId, playerId]);

  // 连线建立：A 连接 B，表示 B 依赖于 A （B.parent_card_id = A.card_id）
  const onConnect = useCallback(async (params: Connection) => {
    const sourceId = params.source;
    const targetId = params.target;
    if (!sourceId || !targetId) return;

    const targetCard = cards.find(c => c.card_id === targetId);
    if (targetCard) {
      try {
        await Api.globalStudioNewsCreateCard({
          ...targetCard,
          parent_card_id: sourceId,
          actor_id: playerId || 'author'
        } as any);
        if (selectedScenarioId) {
          loadScenarioCards(selectedScenarioId);
        }
      } catch (err) {
        alert('连接依赖失败: ' + err);
      }
    }
  }, [cards, selectedScenarioId, playerId]);

  // 解除父依赖
  const handleRemoveParent = async () => {
    const card = cards.find(c => c.card_id === selectedCardId);
    if (card) {
      try {
        await Api.globalStudioNewsCreateCard({
          ...card,
          parent_card_id: null,
          actor_id: playerId || 'author'
        } as any);
        if (selectedScenarioId) {
          loadScenarioCards(selectedScenarioId);
        }
      } catch (err) {
        alert('解除依赖失败: ' + err);
      }
    }
  };

  return (
    <div style={{ display: 'flex', width: '100vw', height: '100vh', background: '#020617', color: '#cbd5e1', overflow: 'hidden', fontFamily: 'Inter, sans-serif' }}>
      
      {/* 1. 剧本库 (Scenario Library) */}
      <div style={{ width: '300px', borderRight: '1px solid rgba(255,255,255,0.05)', display: 'flex', flexDirection: 'column', background: '#0a0f1e', flexShrink: 0 }}>
        <div style={{ padding: '40px 24px', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
          <button 
            onClick={() => nav('/')}
            style={{ 
              width: '100%', 
              padding: '14px', 
              background: 'rgba(59, 130, 246, 0.06)', 
              border: '1px solid rgba(59, 130, 246, 0.25)', 
              borderRadius: '8px', 
              color: '#60a5fa', 
              fontSize: '12px', 
              fontWeight: '900', 
              letterSpacing: '3px',
              cursor: 'pointer',
              marginBottom: '40px',
              transition: 'all 0.3s ease',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '10px',
              textTransform: 'uppercase'
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = 'rgba(59, 130, 246, 0.15)';
              e.currentTarget.style.borderColor = 'rgba(59, 130, 246, 0.5)';
              e.currentTarget.style.color = '#fff';
              e.currentTarget.style.boxShadow = '0 0 20px rgba(59, 130, 246, 0.2)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = 'rgba(59, 130, 246, 0.06)';
              e.currentTarget.style.borderColor = 'rgba(59, 130, 246, 0.25)';
              e.currentTarget.style.color = '#60a5fa';
              e.currentTarget.style.boxShadow = 'none';
            }}
          >
            <ArrowRight size={16} style={{ transform: 'rotate(180deg)' }} /> EXIT_TO_SYSTEM
          </button>

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <div style={{ fontSize: '11px', color: '#818cf8', fontWeight: '900', letterSpacing: '3px', marginBottom: '6px', fontFamily: 'monospace' }}>DATA_ARCHIVE</div>
              <h2 style={{ fontSize: '20px', fontWeight: '900', display: 'flex', alignItems: 'center', gap: '12px', color: '#fff', margin: 0, letterSpacing: '-0.5px' }}>
                <Book size={24} style={{ color: '#818cf8' }} /> SCENARIOS
              </h2>
            </div>
            <button 
              onClick={() => {
                const name = prompt('NEW SCENARIO IDENTIFIER:');
                if (name) setSelectedScenarioId(name.toUpperCase());
              }}
              style={{ background: 'rgba(129, 140, 248, 0.15)', border: '1px solid rgba(129, 140, 248, 0.3)', borderRadius: '8px', padding: '10px', color: '#818cf8', cursor: 'pointer', transition: 'all 0.2s' }}
              onMouseEnter={(e) => e.currentTarget.style.background = 'rgba(129, 140, 248, 0.25)'}
              onMouseLeave={(e) => e.currentTarget.style.background = 'rgba(129, 140, 248, 0.15)'}
            >
              <Plus size={20} />
            </button>
          </div>
        </div>

        <div style={{ padding: '24px' }}>
          <div style={{ position: 'relative', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '8px', overflow: 'hidden' }}>
            <div style={{ position: 'absolute', right: '14px', top: '14px', color: '#334155' }}>
              <RefreshCw size={14} />
            </div>
            <input 
              type="text" placeholder="FILTER_DB_BLUEPRINTS..." 
              style={{ width: '100%', background: 'rgba(0,0,0,0.5)', border: 'none', padding: '14px 18px', fontSize: '12px', outline: 'none', color: '#fff', fontFamily: 'monospace' }}
              value={scenarioFilter}
              onChange={(e) => setScenarioFilter(e.target.value)}
            />
          </div>
        </div>

        <div style={{ flex: 1, overflowY: 'auto', padding: '0 24px 32px 24px', scrollbarWidth: 'none' }}>
          <div 
            onClick={() => setSelectedScenarioId(null)}
            style={{
              padding: '16px 20px',
              borderRadius: '10px',
              cursor: 'pointer',
              fontSize: '13px',
              fontWeight: '900',
              marginBottom: '12px',
              transition: 'all 0.2s',
              background: selectedScenarioId === null ? 'rgba(129, 140, 248, 0.15)' : 'transparent',
              border: `1px solid ${selectedScenarioId === null ? 'rgba(129, 140, 248, 0.5)' : 'transparent'}`,
              color: selectedScenarioId === null ? '#fff' : '#475569',
              letterSpacing: '1px'
            }}
          >
            {'>'} UNLINKED_RECORDS
          </div>
          
          <div style={{ margin: '40px 0 20px 0', fontSize: '11px', color: '#1e293b', fontWeight: '900', textTransform: 'uppercase', letterSpacing: '4px', paddingLeft: '10px', borderLeft: '2px solid #1e293b' }}>Archives</div>
          
          {scenarios.filter(s => s.name.toLowerCase().includes(scenarioFilter.toLowerCase())).map(s => (
            <div 
              key={s.id}
              onClick={() => setSelectedScenarioId(s.id)}
              style={{
                padding: '16px 20px',
                borderRadius: '10px',
                cursor: 'pointer',
                fontSize: '13px',
                fontWeight: 'bold',
                marginBottom: '8px',
                transition: 'all 0.2s',
                background: selectedScenarioId === s.id ? 'rgba(129, 140, 248, 0.15)' : 'rgba(255,255,255,0.02)',
                border: `1px solid ${selectedScenarioId === s.id ? 'rgba(129, 140, 248, 0.5)' : 'transparent'}`,
                color: selectedScenarioId === s.id ? '#fff' : '#94a3b8',
                letterSpacing: '0.5px'
              }}
            >
              {s.name}
            </div>
          ))}
        </div>
      </div>

      {/* 2. 蓝图逻辑树 (Node Blueprint Editor Workspace) */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: '#020617', position: 'relative' }}>
        
        {/* 工具栏：控制缩放拉伸，以及快速添加节点 */}
        <div style={{ height: '70px', borderBottom: '1px solid rgba(255,255,255,0.05)', background: '#070a13', display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 32px', zIndex: 10 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '24px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <GitBranch size={20} style={{ color: '#22d3ee' }} />
              <span style={{ fontSize: '14px', fontWeight: '900', color: '#fff', letterSpacing: '1px' }}>SCENARIO_BLUEPRINT</span>
            </div>
            
            {/* 横轴时间缩放滑块 */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', background: 'rgba(255,255,255,0.02)', padding: '6px 16px', borderRadius: '6px', border: '1px solid rgba(255,255,255,0.05)' }}>
              <span style={{ fontSize: '10px', color: '#64748b', fontFamily: 'monospace' }}>TIMELINE_ZOOM:</span>
              <input 
                type="range" min="0.5" max="8.0" step="0.1"
                style={{ width: '120px', accentColor: '#22d3ee' }}
                value={timeScale}
                onChange={e => setTimeScale(parseFloat(e.target.value))}
              />
              <span style={{ fontSize: '10px', color: '#22d3ee', fontWeight: 'bold', width: '35px', fontFamily: 'monospace' }}>x{Number(timeScale || 0).toFixed(1)}</span>
            </div>
          </div>

          <div style={{ display: 'flex', gap: '16px' }}>
            <button
              onClick={handleCreateNewNode}
              style={{
                background: 'rgba(34, 211, 238, 0.1)',
                border: '1px solid rgba(34, 211, 238, 0.3)',
                color: '#22d3ee',
                padding: '10px 20px',
                borderRadius: '6px',
                fontSize: '12px',
                fontWeight: '900',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                transition: 'all 0.2s'
              }}
              onMouseEnter={(e) => e.currentTarget.style.background = 'rgba(34, 211, 238, 0.2)'}
              onMouseLeave={(e) => e.currentTarget.style.background = 'rgba(34, 211, 238, 0.1)'}
            >
              <Plus size={16} /> + INITIALIZE_NEW_BLOCK
            </button>
          </div>
        </div>

        {/* 蓝图可视画板 */}
        <div style={{ flex: 1, position: 'relative' }}>
          {cards.length === 0 ? (
            <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', zIndex: 1 }}>
              <div style={{ width: '80px', height: '80px', borderRadius: '50%', background: 'rgba(255,255,255,0.02)', border: '2px dashed rgba(255,255,255,0.05)', display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: '24px' }}>
                <GitBranch size={40} style={{ color: '#1e293b' }} />
              </div>
              <p style={{ fontSize: '12px', color: '#475569', textTransform: 'uppercase', letterSpacing: '2px', textAlign: 'center', lineHeight: '2' }}>
                {selectedScenarioId ? `Sequence [${selectedScenarioId}] is void.` : "Select or create a scenario archive."}
                <br /><span style={{ color: '#22d3ee' }}>Click 'INITIALIZE_NEW_BLOCK' to deploy the root node.</span>
              </p>
            </div>
          ) : (
            <ReactFlow
              nodes={nodes}
              edges={edges}
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
              onNodeClick={onNodeClick}
              onNodeDragStop={onNodeDragStop}
              onConnect={onConnect}
              nodeTypes={nodeTypes}
              fitView
              attributionPosition="bottom-left"
            >
              <Background color="#0f172a" gap={24} size={1} />
              <Controls />
              <MiniMap style={{ background: '#0a0f1e' }} nodeColor={() => '#1e293b'} />
            </ReactFlow>
          )}
        </div>
      </div>

      {/* 3. 核心节点参数编辑器 (Node Inspector Sidebar) */}
      <div style={{ width: '420px', borderLeft: '1px solid rgba(255,255,255,0.05)', background: '#0a0f1e', display: 'flex', flexDirection: 'column', flexShrink: 0 }}>
        {!selectedCardId ? (
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '32px' }}>
            <div style={{ width: '80px', height: '80px', borderRadius: '24px', background: 'rgba(255,255,255,0.01)', border: '1px solid rgba(255,255,255,0.03)', display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: '24px' }}>
              <Zap size={32} style={{ color: '#1e293b' }} />
            </div>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: '12px', fontWeight: '900', letterSpacing: '4px', color: '#1e293b', textTransform: 'uppercase', marginBottom: '8px' }}>NO_NODE_SELECTED</div>
              <div style={{ fontSize: '10px', color: '#334155', letterSpacing: '1px', textTransform: 'uppercase' }}>Select a blueprint node to access protected parameters</div>
            </div>
          </div>
        ) : (
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
            
            {/* Inspector Header */}
            <div style={{ padding: '32px 24px', borderBottom: '1px solid rgba(255,255,255,0.05)', background: 'rgba(15, 23, 42, 0.4)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
                <div style={{ width: '8px', height: '8px', borderRadius: '2px', background: '#22d3ee', boxShadow: '0 0 10px rgba(34, 211, 238, 0.6)', transform: 'rotate(45deg)' }} />
                <span style={{ fontSize: '10px', color: 'rgba(34, 211, 238, 0.8)', fontWeight: '900', letterSpacing: '2px', fontFamily: 'monospace' }}>NODE_INSPECTOR</span>
              </div>
              <h1 style={{ fontSize: '24px', fontWeight: '900', color: '#fff', margin: 0, letterSpacing: '-0.5px' }}>
                EDIT_PARAMETERS
              </h1>
              <div style={{ display: 'flex', gap: '12px', marginTop: '16px' }}>
                <div style={{ padding: '4px 10px', background: 'rgba(0,0,0,0.5)', border: '1px solid rgba(255,255,255,0.05)', borderRadius: '4px', fontSize: '10px', fontFamily: 'monospace', color: '#64748b' }}>
                  UID: <span style={{ color: '#94a3b8' }}>{editCard.card_id?.split('-')[0].toUpperCase()}</span>
                </div>
              </div>
            </div>

            {/* Inspector Body (Scrollable) */}
            <div style={{ flex: 1, overflowY: 'auto', padding: '24px', display: 'flex', flexDirection: 'column', gap: '32px' }}>
              
              {/* 1. Core Config */}
              <div style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)', padding: '24px', borderRadius: '12px' }}>
                <h3 style={{ fontSize: '10px', fontWeight: '900', color: '#475569', letterSpacing: '2px', marginBottom: '20px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                   <Settings size={14} /> 01_CORE_ATTRIBUTES
                </h3>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    <label style={{ fontSize: '10px', color: '#818cf8', fontWeight: '900' }}>INTERNAL_BLOCK_LABEL</label>
                    <input 
                      type="text" placeholder="EX: MAJOR_BREAKTHROUGH"
                      style={{ width: '100%', background: '#000', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '6px', padding: '10px', color: '#fff', fontSize: '13px', outline: 'none', fontFamily: 'monospace' }}
                      value={editCard.text || ''}
                      onChange={e => setEditCard({...editCard, text: e.target.value})}
                    />
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    <label style={{ fontSize: '10px', color: '#818cf8', fontWeight: '900' }}>EVENT_CLASSIFICATION</label>
                    <select 
                      style={{ width: '100%', background: '#000', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '6px', padding: '10px', color: '#fff', fontSize: '13px', outline: 'none' }}
                      value={editCard.kind}
                      onChange={e => setEditCard({...editCard, kind: e.target.value})}
                    >
                      {Object.keys(presets).map(k => <option key={k} value={k}>{k}</option>)}
                    </select>
                  </div>
                  
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    <label style={{ fontSize: '10px', color: '#818cf8', fontWeight: '900' }}>TARGET_VECTORS (SYMBOLS)</label>
                    <input 
                      type="text" placeholder="EX: CIVILBANK, NEURALINK"
                      style={{ width: '100%', background: '#000', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '6px', padding: '10px', color: '#fff', fontSize: '13px', outline: 'none', fontFamily: 'monospace' }}
                      value={editCard.symbols?.join(', ')}
                      onChange={e => setEditCard({...editCard, symbols: e.target.value.split(',').map(s => s.trim()).filter(Boolean)})}
                    />
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    <label style={{ fontSize: '10px', color: '#818cf8', fontWeight: '900' }}>IMAGE_RESOURCE_URI</label>
                    <div style={{ position: 'relative' }}>
                      <ImageIcon size={14} style={{ position: 'absolute', left: '10px', top: '12px', color: '#334155' }} />
                      <input 
                        type="text" placeholder="HTTPS://ASSETS.FRONTIER.AI/HASH_ID..."
                        style={{ width: '100%', background: '#000', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '6px', padding: '10px 10px 10px 32px', color: '#fff', fontSize: '13px', outline: 'none', fontFamily: 'monospace' }}
                        value={editCard.image_uri || ''}
                        onChange={e => setEditCard({...editCard, image_uri: e.target.value})}
                      />
                    </div>
                  </div>
                </div>
              </div>

              {/* 2. Timing and Dependency */}
              <div style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)', padding: '24px', borderRadius: '12px' }}>
                <h3 style={{ fontSize: '10px', fontWeight: '900', color: '#475569', letterSpacing: '2px', marginBottom: '20px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                   <Clock size={14} /> 02_TIMING_AND_DEPENDENCY
                </h3>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    <label style={{ fontSize: '10px', color: '#818cf8', fontWeight: '900' }}>SCHEDULED_PATCH_TIME</label>
                    <input 
                      type="datetime-local"
                      style={{ width: '100%', background: '#000', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '6px', padding: '10px', color: '#fff', fontSize: '13px', outline: 'none', fontFamily: 'monospace' }}
                      value={editCard.scheduled_at?.slice(0, 16) || ''}
                      onChange={e => setEditCard({...editCard, scheduled_at: e.target.value ? new Date(e.target.value).toISOString() : null})}
                    />
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    <label style={{ fontSize: '10px', color: '#818cf8', fontWeight: '900' }}>ACTIVATION_PROBABILITY</label>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px', background: 'rgba(0,0,0,0.4)', padding: '8px 12px', borderRadius: '6px' }}>
                      <input 
                        type="range" min="0" max="1" step="0.1"
                        style={{ flex: 1, accentColor: '#818cf8' }}
                        value={editCard.activation_prob || 0}
                        onChange={e => setEditCard({...editCard, activation_prob: parseFloat(e.target.value)})}
                      />
                      <span style={{ fontSize: '14px', fontWeight: '900', color: '#818cf8', fontFamily: 'monospace' }}>{Math.round((editCard.activation_prob || 0) * 100)}%</span>
                    </div>
                  </div>

                  {editCard.parent_card_id && (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                      <label style={{ fontSize: '10px', color: '#818cf8', fontWeight: '900' }}>DEPENDS_ON_PARENT_BLOCK</label>
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: 'rgba(34, 211, 238, 0.05)', border: '1px solid rgba(34, 211, 238, 0.15)', padding: '10px', borderRadius: '6px' }}>
                        <span style={{ fontSize: '11px', fontFamily: 'monospace', color: '#22d3ee' }}>
                          BLOCK: {editCard.parent_card_id.split('-')[0].toUpperCase()}
                        </span>
                        <button 
                          onClick={handleRemoveParent}
                          style={{ background: 'transparent', border: 'none', color: '#ef4444', fontSize: '11px', cursor: 'pointer', fontFamily: 'monospace' }}
                        >
                          [UNLINK]
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              </div>

              {/* 3. Market Payload */}
              <div style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)', padding: '24px', borderRadius: '12px' }}>
                <h3 style={{ fontSize: '10px', fontWeight: '900', color: '#475569', letterSpacing: '2px', marginBottom: '20px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                   <Zap size={14} /> 03_MARKET_IMPACT_PAYLOAD
                </h3>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginBottom: '16px' }}>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    <label style={{ fontSize: '10px', color: '#22d3ee', fontWeight: '900' }}>IMPACT_MAGNITUDE</label>
                    <input 
                      type="range" step="0.01" min="-1" max="1"
                      style={{ width: '100%', accentColor: '#22d3ee' }}
                      value={editCard.truth_payload?.impact || 0}
                      onChange={e => setEditCard({...editCard, truth_payload: {...editCard.truth_payload, impact: parseFloat(e.target.value)}})}
                    />
                    <div style={{ fontSize: '14px', fontWeight: '900', color: '#fff', fontFamily: 'monospace', textAlign: 'center' }}>
                      {Number(editCard.truth_payload?.impact || 0).toFixed(2)}
                    </div>
                  </div>
                  
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    <label style={{ fontSize: '10px', color: '#22d3ee', fontWeight: '900' }}>SIGNAL_INTENSITY</label>
                    <input 
                      type="range" step="0.1" min="0" max="1"
                      style={{ width: '100%', accentColor: '#22d3ee' }}
                      value={editCard.truth_payload?.intensity || 0.5}
                      onChange={e => setEditCard({...editCard, truth_payload: {...editCard.truth_payload, intensity: parseFloat(e.target.value)}})}
                    />
                    <div style={{ fontSize: '14px', fontWeight: '900', color: '#fff', fontFamily: 'monospace', textAlign: 'center' }}>
                      {Number(editCard.truth_payload?.intensity || 0.5).toFixed(1)}
                    </div>
                  </div>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  <label style={{ fontSize: '10px', color: '#22d3ee', fontWeight: '900' }}>BIAS_DIRECTION</label>
                  <select 
                    style={{ width: '100%', background: '#000', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '6px', padding: '10px', color: '#fff', fontSize: '13px', outline: 'none' }}
                    value={editCard.truth_payload?.direction || 'STABLE'}
                    onChange={e => setEditCard({...editCard, truth_payload: {...editCard.truth_payload, direction: e.target.value}})}
                  >
                    <option value="UP">BULLISH (▲)</option>
                    <option value="DOWN">BEARISH (▼)</option>
                    <option value="STABLE">STABLE (—)</option>
                  </select>
                </div>
              </div>

              {/* 4. Text Variant Area */}
              <div style={{ background: 'rgba(10, 17, 34, 0.8)', border: '1px solid rgba(255,255,255,0.06)', padding: '24px', borderRadius: '12px', display: 'flex', flexDirection: 'column' }}>
                <h3 style={{ fontSize: '10px', fontWeight: '900', color: '#22d3ee', letterSpacing: '2px', marginBottom: '20px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                   <Book size={14} /> 04_SIGNAL_VARIANTS
                </h3>
                <div style={{ position: 'relative', marginBottom: '20px' }}>
                   <textarea 
                      id="new-variant-text"
                      placeholder="ENTER_NEW_SIGNAL_TEXT..."
                      style={{ width: '100%', background: '#000', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px', padding: '12px', color: '#fff', fontSize: '13px', outline: 'none', minHeight: '100px', resize: 'none', lineHeight: '1.5' }}
                    />
                    <button 
                      onClick={() => {
                        const area = document.getElementById('new-variant-text') as HTMLTextAreaElement;
                        if (area && area.value) {
                          handleEmitVariant(area.value);
                          area.value = '';
                        }
                      }}
                      style={{ position: 'absolute', bottom: '12px', right: '12px', padding: '6px 14px', background: 'rgba(34, 211, 238, 0.1)', border: '1px solid rgba(34, 211, 238, 0.3)', borderRadius: '4px', color: '#22d3ee', fontWeight: '900', fontSize: '10px', cursor: 'pointer', letterSpacing: '1px' }}
                    >
                      + DEPLOY
                    </button>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', maxHeight: '300px', overflowY: 'auto', scrollbarWidth: 'none' }}>
                  {variants.map((v, i) => (
                    <div key={v.variant_id} style={{ background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.04)', padding: '12px', borderRadius: '8px' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                         <span style={{ fontSize: '9px', color: '#22d3ee', fontWeight: '900' }}>SIGNAL_#{variants.length - i}</span>
                         <span style={{ fontSize: '9px', color: '#334155', fontFamily: 'monospace' }}>ID: {v.variant_id.split('-')[0].toUpperCase()}</span>
                      </div>
                      <p style={{ fontSize: '13px', color: '#cbd5e1', margin: 0, lineHeight: '1.5', fontStyle: 'italic' }}>"{v.text}"</p>
                    </div>
                  ))}
                  {variants.length === 0 && (
                    <div style={{ textAlign: 'center', padding: '40px', color: '#1e293b', fontSize: '10px', border: '1px dashed rgba(255,255,255,0.03)', borderRadius: '8px' }}>
                      NO_SIGNAL_VARIANTS_INITIALIZED
                    </div>
                  )}
                </div>
              </div>

            </div>

            {/* Inspector Commit Actions */}
            <div style={{ padding: '20px 24px', borderTop: '1px solid rgba(255,255,255,0.05)', display: 'flex', gap: '12px', background: '#070a13' }}>
              <button 
                onClick={handleSaveCard}
                disabled={loading}
                style={{
                  flex: 1,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '8px',
                  background: '#4f46e5',
                  border: '1px solid rgba(129, 140, 248, 0.4)',
                  color: '#fff',
                  padding: '12px',
                  borderRadius: '6px',
                  fontSize: '12px',
                  fontWeight: '900',
                  cursor: 'pointer',
                  transition: 'all 0.2s',
                  letterSpacing: '1px'
                }}
                onMouseEnter={(e) => e.currentTarget.style.background = '#6366f1'}
                onMouseLeave={(e) => e.currentTarget.style.background = '#4f46e5'}
              >
                {loading ? <RefreshCw size={14} style={{ animation: 'spin 2s linear infinite' }} /> : <Save size={14} />}
                COMMIT_TO_STREAMS
              </button>
            </div>

          </div>
        )}
      </div>

    </div>
  );
};

export default NewsStudioPage;
