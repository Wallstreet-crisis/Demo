import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { 
  Plus, 
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

// 1. 自定义节点组件（符合游戏整体 Slate/Blue 风格）
const CyberNewsNode = ({ data, selected }: any) => {
  const card = data.card;
  const isSelected = selected;
  
  const kindColors: Record<string, string> = {
    EARNINGS: '#10b981', // green
    MILITARY: '#ef4444', // red
    DEFAULT: '#3b82f6'  // blue
  };
  const color = kindColors[card.kind] || kindColors.DEFAULT;

  return (
    <div style={{
      padding: '12px',
      borderRadius: '2px',
      background: isSelected ? '#1e293b' : '#0f172a',
      border: `1px solid ${isSelected ? '#3b82f6' : '#334155'}`,
      boxShadow: isSelected ? '0 0 10px rgba(59, 130, 246, 0.3)' : 'none',
      color: '#f1f5f9',
      width: '180px',
      fontFamily: 'inherit',
      position: 'relative'
    }}>
      <Handle type="target" position={Position.Left} style={{ background: '#3b82f6', width: 6, height: 6, borderRadius: 0 }} />
      
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
        <span style={{
          fontSize: '9px',
          padding: '1px 4px',
          borderRadius: '1px',
          background: 'rgba(0,0,0,0.3)',
          border: `1px solid ${color}`,
          color: color,
          fontWeight: 'bold',
          textTransform: 'uppercase'
        }}>
          {card.kind}
        </span>
        <span style={{ fontSize: '10px', color: '#64748b' }}>
          T+{data.offsetSeconds}s
        </span>
      </div>
      
      <div style={{ 
        fontSize: '12px', 
        fontWeight: '600', 
        overflow: 'hidden', 
        textOverflow: 'ellipsis', 
        whiteSpace: 'nowrap', 
        marginBottom: '4px',
        color: '#f1f5f9'
      }}>
        {card.text || `BLOCK_${card.card_id.split('-')[0].toUpperCase()}`}
      </div>
      
      <div style={{ fontSize: '10px', color: '#64748b', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {card.symbols?.join(', ') || 'NO_SYMBOLS'}
      </div>

      <Handle type="source" position={Position.Right} style={{ background: '#3b82f6', width: 6, height: 6, borderRadius: 0 }} />
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
    <div style={{ display: 'flex', width: '100vw', height: '100vh', background: '#0f172a', color: '#e2e8f0', overflow: 'hidden' }}>
      
      {/* 1. 剧本库 (Scenario Library) */}
      <div style={{ width: '280px', borderRight: '1px solid #334155', display: 'flex', flexDirection: 'column', background: '#1e293b', flexShrink: 0 }}>
        <div style={{ padding: '24px', borderBottom: '1px solid #334155' }}>
          <button 
            onClick={() => nav('/')}
            className="cyber-button"
            style={{ 
              width: '100%', 
              padding: '8px', 
              marginBottom: '24px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '8px'
            }}
          >
            <ArrowRight size={14} style={{ transform: 'rotate(180deg)' }} /> EXIT_TO_SYSTEM
          </button>

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <div style={{ fontSize: '10px', color: '#64748b', fontWeight: 'bold', marginBottom: '4px' }}>DATA ARCHIVE</div>
              <h2 style={{ fontSize: '18px', fontWeight: 'bold', display: 'flex', alignItems: 'center', gap: '8px', color: '#f1f5f9', margin: 0 }}>
                <Book size={20} style={{ color: '#3b82f6' }} /> Scenarios
              </h2>
            </div>
            <button 
              onClick={() => {
                const name = prompt('NEW SCENARIO IDENTIFIER:');
                if (name) setSelectedScenarioId(name.toUpperCase());
              }}
              className="cyber-button"
              style={{ padding: '6px' }}
            >
              <Plus size={18} />
            </button>
          </div>
        </div>

        <div style={{ padding: '16px' }}>
          <div style={{ position: 'relative' }}>
            <input 
              type="text" placeholder="Filter scenarios..." 
              className="cyber-input"
              style={{ width: '100%', paddingRight: '32px' }}
              value={scenarioFilter}
              onChange={(e) => setScenarioFilter(e.target.value)}
            />
            <div style={{ position: 'absolute', right: '10px', top: '7px', color: '#475569' }}>
              <RefreshCw size={14} />
            </div>
          </div>
        </div>

        <div style={{ flex: 1, overflowY: 'auto', padding: '0 16px 24px 16px', scrollbarWidth: 'none' }}>
          <div 
            onClick={() => setSelectedScenarioId(null)}
            style={{
              padding: '10px 12px',
              borderRadius: '2px',
              cursor: 'pointer',
              fontSize: '13px',
              marginBottom: '8px',
              transition: 'all 0.1s',
              background: selectedScenarioId === null ? '#334155' : 'transparent',
              border: `1px solid ${selectedScenarioId === null ? '#3b82f6' : 'transparent'}`,
              color: selectedScenarioId === null ? '#fff' : '#94a3b8'
            }}
          >
            Unlinked Records
          </div>
          
          <div style={{ margin: '24px 0 12px 0', fontSize: '11px', color: '#475569', fontWeight: 'bold', textTransform: 'uppercase', letterSpacing: '1px' }}>Archives</div>
          
          {scenarios.filter(s => s.name.toLowerCase().includes(scenarioFilter.toLowerCase())).map(s => (
            <div 
              key={s.id}
              onClick={() => setSelectedScenarioId(s.id)}
              style={{
                padding: '10px 12px',
                borderRadius: '2px',
                cursor: 'pointer',
                fontSize: '13px',
                marginBottom: '4px',
                transition: 'all 0.1s',
                background: selectedScenarioId === s.id ? '#334155' : 'transparent',
                border: `1px solid ${selectedScenarioId === s.id ? '#3b82f6' : 'transparent'}`,
                color: selectedScenarioId === s.id ? '#fff' : '#94a3b8'
              }}
            >
              {s.name}
            </div>
          ))}
        </div>
      </div>

      {/* 2. 蓝图逻辑树 (Node Blueprint Editor Workspace) */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: '#0f172a', position: 'relative' }}>
        
        {/* 工具栏 */}
        <div style={{ height: '60px', borderBottom: '1px solid #334155', background: '#1e293b', display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 24px', zIndex: 10 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '24px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <GitBranch size={18} style={{ color: '#3b82f6' }} />
              <span style={{ fontSize: '13px', fontWeight: 'bold', color: '#f1f5f9' }}>BLUEPRINT EDITOR</span>
            </div>
            
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <span style={{ fontSize: '11px', color: '#64748b' }}>Zoom:</span>
              <input 
                type="range" min="0.5" max="8.0" step="0.1"
                style={{ width: '100px', accentColor: '#3b82f6' }}
                value={timeScale}
                onChange={e => setTimeScale(parseFloat(e.target.value))}
              />
              <span style={{ fontSize: '11px', color: '#3b82f6', fontWeight: 'bold', width: '30px' }}>x{Number(timeScale || 0).toFixed(1)}</span>
            </div>
          </div>

          <button
            onClick={handleCreateNewNode}
            className="cyber-button active"
            style={{ padding: '6px 16px' }}
          >
            <Plus size={16} /> New Block
          </button>
        </div>

        {/* 蓝图可视画板 */}
        <div style={{ flex: 1, position: 'relative' }}>
          {cards.length === 0 ? (
            <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', zIndex: 1 }}>
              <div style={{ width: '60px', height: '60px', borderRadius: '50%', background: '#1e293b', border: '1px dashed #334155', display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: '16px' }}>
                <GitBranch size={32} style={{ color: '#334155' }} />
              </div>
              <p style={{ fontSize: '13px', color: '#475569', textAlign: 'center' }}>
                {selectedScenarioId ? `Scenario [${selectedScenarioId}] is empty.` : "Select a scenario to begin."}
                <br /><span style={{ color: '#3b82f6' }}>Click 'New Block' to start the sequence.</span>
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
              <Background color="#1e293b" gap={20} size={1} />
              <Controls style={{ background: '#1e293b', border: '1px solid #334155', borderRadius: '2px' }} />
              <MiniMap style={{ background: '#0f172a', border: '1px solid #334155' }} nodeColor={() => '#1e293b'} maskColor="rgba(15, 23, 42, 0.7)" />
            </ReactFlow>
          )}
        </div>
      </div>

      {/* 3. 核心节点参数编辑器 (Node Inspector Sidebar) */}
      <div style={{ width: '400px', borderLeft: '1px solid #334155', background: '#1e293b', display: 'flex', flexDirection: 'column', flexShrink: 0 }}>
        {!selectedCardId ? (
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '32px' }}>
            <Zap size={48} style={{ color: '#0f172a', marginBottom: '16px' }} />
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: '12px', fontWeight: 'bold', color: '#475569', textTransform: 'uppercase', marginBottom: '4px' }}>No Node Selected</div>
              <div style={{ fontSize: '11px', color: '#64748b' }}>Select a node to edit its parameters</div>
            </div>
          </div>
        ) : (
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
            
            {/* Inspector Header */}
            <div style={{ padding: '24px', borderBottom: '1px solid #334155', background: 'rgba(0,0,0,0.1)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                <div style={{ width: '6px', height: '6px', background: '#3b82f6' }} />
                <span style={{ fontSize: '10px', color: '#3b82f6', fontWeight: 'bold', letterSpacing: '1px' }}>INSPECTOR</span>
              </div>
              <h1 style={{ fontSize: '20px', fontWeight: 'bold', color: '#f1f5f9', margin: 0 }}>
                Block Parameters
              </h1>
              <div style={{ marginTop: '12px' }}>
                <span style={{ padding: '2px 6px', background: '#0f172a', border: '1px solid #334155', borderRadius: '2px', fontSize: '10px', color: '#64748b' }}>
                  ID: {editCard.card_id?.split('-')[0].toUpperCase()}
                </span>
              </div>
            </div>

            {/* Inspector Body */}
            <div style={{ flex: 1, overflowY: 'auto', padding: '24px', display: 'flex', flexDirection: 'column', gap: '24px' }}>
              
              {/* 1. Attributes */}
              <div className="cyber-card">
                <h3 style={{ fontSize: '11px', fontWeight: 'bold', color: '#64748b', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                   <Settings size={14} /> CORE ATTRIBUTES
                </h3>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                    <label style={{ fontSize: '11px', color: '#94a3b8' }}>Block Label</label>
                    <input 
                      type="text" placeholder="Internal name..."
                      className="cyber-input"
                      value={editCard.text || ''}
                      onChange={e => setEditCard({...editCard, text: e.target.value})}
                    />
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                    <label style={{ fontSize: '11px', color: '#94a3b8' }}>Classification</label>
                    <select 
                      className="cyber-input"
                      value={editCard.kind}
                      onChange={e => setEditCard({...editCard, kind: e.target.value})}
                    >
                      {Object.keys(presets).map(k => <option key={k} value={k}>{k}</option>)}
                    </select>
                  </div>
                  
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                    <label style={{ fontSize: '11px', color: '#94a3b8' }}>Symbols</label>
                    <input 
                      type="text" placeholder="CIVILBANK, NEURALINK..."
                      className="cyber-input"
                      value={editCard.symbols?.join(', ')}
                      onChange={e => setEditCard({...editCard, symbols: e.target.value.split(',').map(s => s.trim()).filter(Boolean)})}
                    />
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                    <label style={{ fontSize: '11px', color: '#94a3b8' }}>Image URI</label>
                    <input 
                      type="text" placeholder="https://..."
                      className="cyber-input"
                      value={editCard.image_uri || ''}
                      onChange={e => setEditCard({...editCard, image_uri: e.target.value})}
                    />
                  </div>
                </div>
              </div>

              {/* 2. Timing */}
              <div className="cyber-card">
                <h3 style={{ fontSize: '11px', fontWeight: 'bold', color: '#64748b', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                   <Clock size={14} /> TRIGGER LOGIC
                </h3>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                    <label style={{ fontSize: '11px', color: '#94a3b8' }}>Scheduled Time</label>
                    <input 
                      type="datetime-local"
                      className="cyber-input"
                      style={{ colorScheme: 'dark' }}
                      value={editCard.scheduled_at?.slice(0, 16) || ''}
                      onChange={e => setEditCard({...editCard, scheduled_at: e.target.value ? new Date(e.target.value).toISOString() : null})}
                    />
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                    <label style={{ fontSize: '11px', color: '#94a3b8' }}>Probability ({Math.round((editCard.activation_prob || 0) * 100)}%)</label>
                    <input 
                      type="range" min="0" max="1" step="0.1"
                      style={{ width: '100%', accentColor: '#3b82f6' }}
                      value={editCard.activation_prob || 0}
                      onChange={e => setEditCard({...editCard, activation_prob: parseFloat(e.target.value)})}
                    />
                  </div>

                  {editCard.parent_card_id && (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                      <label style={{ fontSize: '11px', color: '#94a3b8' }}>Parent Block</label>
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: '#0f172a', padding: '6px 10px', border: '1px solid #334155' }}>
                        <span style={{ fontSize: '11px', color: '#3b82f6' }}>
                          ID: {editCard.parent_card_id.split('-')[0].toUpperCase()}
                        </span>
                        <button 
                          onClick={handleRemoveParent}
                          style={{ background: 'transparent', border: 'none', color: '#ef4444', fontSize: '10px', cursor: 'pointer' }}
                        >
                          UNLINK
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              </div>

              {/* 3. Market Impact */}
              <div className="cyber-card">
                <h3 style={{ fontSize: '11px', fontWeight: 'bold', color: '#64748b', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                   <Zap size={14} /> MARKET PAYLOAD
                </h3>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginBottom: '16px' }}>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                    <label style={{ fontSize: '11px', color: '#94a3b8' }}>Impact ({Number(editCard.truth_payload?.impact || 0).toFixed(2)})</label>
                    <input 
                      type="range" step="0.01" min="-1" max="1"
                      style={{ width: '100%', accentColor: '#3b82f6' }}
                      value={editCard.truth_payload?.impact || 0}
                      onChange={e => setEditCard({...editCard, truth_payload: {...editCard.truth_payload, impact: parseFloat(e.target.value)}})}
                    />
                  </div>
                  
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                    <label style={{ fontSize: '11px', color: '#94a3b8' }}>Intensity ({Number(editCard.truth_payload?.intensity || 0.5).toFixed(1)})</label>
                    <input 
                      type="range" step="0.1" min="0" max="1"
                      style={{ width: '100%', accentColor: '#3b82f6' }}
                      value={editCard.truth_payload?.intensity || 0.5}
                      onChange={e => setEditCard({...editCard, truth_payload: {...editCard.truth_payload, intensity: parseFloat(e.target.value)}})}
                    />
                  </div>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                  <label style={{ fontSize: '11px', color: '#94a3b8' }}>Bias Direction</label>
                  <select 
                    className="cyber-input"
                    value={editCard.truth_payload?.direction || 'STABLE'}
                    onChange={e => setEditCard({...editCard, truth_payload: {...editCard.truth_payload, direction: e.target.value}})}
                  >
                    <option value="UP">BULLISH (▲)</option>
                    <option value="DOWN">BEARISH (▼)</option>
                    <option value="STABLE">STABLE (—)</option>
                  </select>
                </div>
              </div>

              {/* 4. Variants */}
              <div className="cyber-card">
                <h3 style={{ fontSize: '11px', fontWeight: 'bold', color: '#64748b', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                   <Book size={14} /> SIGNAL VARIANTS
                </h3>
                <div style={{ position: 'relative', marginBottom: '16px' }}>
                   <textarea 
                      id="new-variant-text"
                      placeholder="Enter variant text..."
                      className="cyber-input"
                      style={{ width: '100%', minHeight: '80px', resize: 'none' }}
                    />
                    <button 
                      onClick={() => {
                        const area = document.getElementById('new-variant-text') as HTMLTextAreaElement;
                        if (area && area.value) {
                          handleEmitVariant(area.value);
                          area.value = '';
                        }
                      }}
                      className="cyber-button"
                      style={{ position: 'absolute', bottom: '8px', right: '8px' }}
                    >
                      + Add
                    </button>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', maxHeight: '200px', overflowY: 'auto' }}>
                  {variants.map((v, i) => (
                    <div key={v.variant_id} style={{ background: '#0f172a', border: '1px solid #334155', padding: '10px', borderRadius: '2px' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                         <span style={{ fontSize: '9px', color: '#3b82f6', fontWeight: 'bold' }}>Variant #{variants.length - i}</span>
                         <span style={{ fontSize: '9px', color: '#475569' }}>{v.variant_id.split('-')[0]}</span>
                      </div>
                      <p style={{ fontSize: '12px', color: '#cbd5e1', margin: 0, lineHeight: '1.4' }}>{v.text}</p>
                    </div>
                  ))}
                  {variants.length === 0 && (
                    <div style={{ textAlign: 'center', padding: '20px', color: '#475569', fontSize: '11px' }}>
                      No variants defined.
                    </div>
                  )}
                </div>
              </div>

            </div>

            {/* Commit Actions */}
            <div style={{ padding: '16px 24px', borderTop: '1px solid #334155', background: '#1e293b' }}>
              <button 
                onClick={handleSaveCard}
                disabled={loading}
                className="cyber-button active"
                style={{
                  width: '100%',
                  padding: '10px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '8px',
                  fontSize: '13px'
                }}
              >
                {loading ? <RefreshCw size={14} className="animate-spin" /> : <Save size={16} />}
                SAVE CHANGES
              </button>
            </div>

          </div>
        )}
      </div>

    </div>
  );
};

export default NewsStudioPage;
