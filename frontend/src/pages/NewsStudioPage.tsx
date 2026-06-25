import React, { useState, useEffect, useCallback, useRef } from 'react';
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
  ArrowRight,
  Download,
  Upload,
  Trash2,
  Sparkles,
  Store
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

type NewsStoreChainTreeNode = {
  node_id: string;
  kind: string;
  text: string;
  scheduled_delay_seconds: number;
  activation_prob: number;
  symbols: string[];
  tags: string[];
  truth_payload: Record<string, any>;
  parent_node_id: string | null;
};

type NewsStoreItemConfig = {
  kind: string;
  price_cash: number;
  description: string;
  requires_symbols: boolean;
  trigger_mode: 'IMMEDIATE' | 'MANUAL' | 'AUTO_CHAIN';
  tags: string[];
  rarity: string;
  chain_kind: string | null;
  chain_defaults: Record<string, any>;
  chain_tree: NewsStoreChainTreeNode[];
  enabled: boolean;
};

type ScenarioWorldviewConfig = {
  featured_symbols: string[];
  market_open_note: string;
  market_close_note: string;
  holiday_note: string;
  overview_note: string;
};

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

const createDefaultScenarioWorldview = (): ScenarioWorldviewConfig => ({
  featured_symbols: [],
  market_open_note: '',
  market_close_note: '',
  holiday_note: '',
  overview_note: '',
});

const cloneScenarioWorldview = (worldview?: Partial<ScenarioWorldviewConfig> | null): ScenarioWorldviewConfig => ({
  featured_symbols: [...(worldview?.featured_symbols || [])],
  market_open_note: worldview?.market_open_note || '',
  market_close_note: worldview?.market_close_note || '',
  holiday_note: worldview?.holiday_note || '',
  overview_note: worldview?.overview_note || '',
});

const createDefaultScenarioStoreItems = (): NewsStoreItemConfig[] => ([
  {
    kind: 'RUMOR',
    price_cash: 2000,
    description: '来源不明的非官方消息，传播力强但可信度存疑。',
    requires_symbols: false,
    trigger_mode: 'IMMEDIATE',
    tags: ['news', 'base'],
    rarity: 'COMMON',
    chain_kind: null,
    chain_defaults: {},
    chain_tree: [],
    enabled: true,
  },
  {
    kind: 'LEAK',
    price_cash: 15000,
    description: '内部流出的机密文件，极具杀伤力。',
    requires_symbols: true,
    trigger_mode: 'IMMEDIATE',
    tags: ['news', 'base'],
    rarity: 'RARE',
    chain_kind: null,
    chain_defaults: {},
    chain_tree: [],
    enabled: true,
  },
  {
    kind: 'REPORT',
    price_cash: 8000,
    description: '机构发布的专业分析，对市场预期有显著引导。',
    requires_symbols: true,
    trigger_mode: 'IMMEDIATE',
    tags: ['news', 'base'],
    rarity: 'UNCOMMON',
    chain_kind: null,
    chain_defaults: {},
    chain_tree: [],
    enabled: true,
  },
  {
    kind: 'MAJOR_EVENT',
    price_cash: 100000,
    description: '足以改变行业格局的重大突发事件。',
    requires_symbols: true,
    trigger_mode: 'AUTO_CHAIN',
    tags: ['news', 'chain'],
    rarity: 'EPIC',
    chain_kind: 'MAJOR_EVENT',
    chain_defaults: { t0_seconds: 60, omen_interval_seconds: 10, abort_probability: 0.3, grant_count: 2, seed: 1 },
    chain_tree: [],
    enabled: true,
  },
  {
    kind: 'WORLD_EVENT',
    price_cash: 500000,
    description: '影响所有参与者的宏观系统性事件。',
    requires_symbols: false,
    trigger_mode: 'AUTO_CHAIN',
    tags: ['news', 'chain'],
    rarity: 'LEGENDARY',
    chain_kind: 'WORLD_EVENT',
    chain_defaults: { t0_seconds: 15, omen_interval_seconds: 10, abort_probability: 0.3, grant_count: 2, seed: 1 },
    chain_tree: [],
    enabled: true,
  },
]);

const cloneScenarioStoreItems = (items?: NewsStoreItemConfig[] | null): NewsStoreItemConfig[] => {
  if (!items || items.length === 0) return createDefaultScenarioStoreItems();
  return items.map((item) => ({
    ...item,
    tags: [...(item.tags || [])],
    chain_defaults: { ...(item.chain_defaults || {}) },
    chain_tree: (item.chain_tree || []).map((n) => ({ ...n, symbols: [...(n.symbols || [])], tags: [...(n.tags || [])], truth_payload: { ...(n.truth_payload || {}) } })),
  }));
};

const toNewsStoreItem = (item: NewsStoreItemConfig) => ({
  ...item,
  price_cash: Number(item.price_cash || 0),
  requires_symbols: !!item.requires_symbols,
  chain_tree: (item.chain_tree || []).map((n) => ({
    node_id: n.node_id,
    kind: n.kind,
    text: n.text || '',
    scheduled_delay_seconds: Number(n.scheduled_delay_seconds || 0),
    activation_prob: Number(n.activation_prob ?? 1.0),
    symbols: [...(n.symbols || [])],
    tags: [...(n.tags || [])],
    truth_payload: { ...(n.truth_payload || {}) },
    parent_node_id: n.parent_node_id || null,
  })),
  chain_kind: item.chain_kind || null,
  enabled: item.enabled !== false,
});

// 1. 自定义节点组件（符合游戏整体 Slate/Blue 风格）
const CyberNewsNode = ({ data, selected }: any) => {
  const card = data.card;
  const isSelected = selected;
  
  const kindColors: Record<string, string> = {
    RUMOR: '#64748b',      // slate
    LEAK: '#ef4444',       // red
    REPORT: '#f59e0b',     // amber
    MAJOR_EVENT: '#a855f7', // purple
    WORLD_EVENT: '#ec4899', // pink
    EARNINGS: '#10b981',   // green
    MILITARY: '#ef4444',   // red
    DEFAULT: '#3b82f6'     // blue
  };
  const color = kindColors[card.kind] || kindColors.DEFAULT;

  const prob = card.activation_prob ?? 1.0;
  const isProbabilistic = prob < 1.0;
  const displayText = card.text || `[${card.kind}] ${card.card_id.slice(0, 8)}`;

  return (
    <div style={{
      padding: '10px 12px 10px 14px',
      borderRadius: '4px',
      background: isSelected ? '#1e293b' : '#0f172a',
      border: `1px solid ${isSelected ? '#3b82f6' : '#334155'}`,
      borderLeft: `3px solid ${color}`,
      boxShadow: isSelected ? '0 0 12px rgba(59, 130, 246, 0.35)' : 'none',
      color: '#f1f5f9',
      width: '220px',
      fontFamily: 'inherit',
      position: 'relative'
    }}>
      <Handle type="target" position={Position.Left} style={{ background: color, width: 8, height: 8, borderRadius: '50%' }} />

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px', gap: '4px' }}>
        <span style={{
          fontSize: '9px',
          padding: '1px 5px',
          borderRadius: '2px',
          background: `${color}22`,
          border: `1px solid ${color}`,
          color: color,
          fontWeight: 'bold',
          textTransform: 'uppercase',
          flexShrink: 0
        }}>
          {card.kind}
        </span>
        <div style={{ display: 'flex', alignItems: 'center', gap: '4px', flexShrink: 0 }}>
          {isProbabilistic && (
            <span style={{ 
              fontSize: '9px', 
              padding: '1px 4px', 
              borderRadius: '2px',
              background: 'rgba(251,191,36,0.15)', 
              border: '1px solid #fbbf24',
              color: '#fbbf24', 
              fontWeight: 'bold' 
            }}>
              {Math.round(prob * 100)}%
            </span>
          )}
          <span style={{ fontSize: '10px', color: '#64748b' }}>
            T+{data.offsetSeconds}s
          </span>
        </div>
      </div>
      
      <div style={{ 
        fontSize: '11px', 
        fontWeight: '600', 
        overflow: 'hidden',
        display: '-webkit-box',
        WebkitLineClamp: 2,
        WebkitBoxOrient: 'vertical',
        lineHeight: '1.4',
        marginBottom: '4px',
        color: card.text ? '#f1f5f9' : '#64748b'
      }}>
        {displayText}
      </div>
      
      <div style={{ fontSize: '10px', color: '#64748b', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {card.symbols?.length ? card.symbols.join(', ') : 'NO_SYMBOLS'}
      </div>

      <Handle type="source" position={Position.Right} style={{ background: color, width: 8, height: 8, borderRadius: '50%' }} />
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
  const [activeTab, setActiveTab] = useState<'worldview' | 'store' | 'tree'>('tree');
  const [cards, setCards] = useState<NewsCard[]>([]);
  const [selectedCardId, setSelectedCardId] = useState<string | null>(null);
  const [presets, setPresets] = useState<Record<string, string[]>>({});
  const [loading, setLoading] = useState(false);
  const importFileRef = useRef<HTMLInputElement>(null);
  const [scenarioFilter, setScenarioFilter] = useState('');
  const [scenarioBackgroundStory, setScenarioBackgroundStory] = useState('');
  const [scenarioWorldview, setScenarioWorldview] = useState<ScenarioWorldviewConfig>(() => createDefaultScenarioWorldview());
  const [scenarioStoreItems, setScenarioStoreItems] = useState<NewsStoreItemConfig[]>(() => createDefaultScenarioStoreItems());
  
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

  useEffect(() => {
    loadScenarios(true);
    loadPresets();
  }, []);

  useEffect(() => {
    if (selectedScenarioId) {
      loadScenarioCards(selectedScenarioId);
      loadScenarioMeta(selectedScenarioId);
    } else {
      loadAllCards();
      setScenarioBackgroundStory('');
      setScenarioStoreItems(createDefaultScenarioStoreItems());
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

  const loadScenarios = async (autoSeed = false) => {
    try {
      const data = await Api.globalStudioNewsScenarios();
      setScenarios(data);
      if (autoSeed && data.length === 0) {
        await seedDefaultScenario();
      }
    } catch (err) { console.error('Failed to load scenarios:', err); }
  };

  const seedDefaultScenario = async () => {
    try {
      setLoading(true);
      const template = await Api.globalStudioNewsDefaultTemplate();
      const scenarioId = 'DEFAULT_STORYLINE';
      await Api.globalStudioNewsImportPackage(scenarioId, {
        actor_id: 'author',
        package: { ...template, scenario_id: scenarioId },
      });
      const data = await Api.globalStudioNewsScenarios();
      setScenarios(data);
      setSelectedScenarioId(scenarioId);
    } catch (err) {
      console.error('Failed to seed default scenario:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteScenario = async (scenarioId: string) => {
    if (!confirm(`确定要删除场景 "${scenarioId}" 吗？此操作不可撤销，将删除该场景下所有卡片和元数据。`)) return;
    try {
      setLoading(true);
      await Api.globalStudioNewsDeleteScenario(scenarioId);
      if (selectedScenarioId === scenarioId) {
        setSelectedScenarioId(null);
      }
      await loadScenarios();
    } catch (err) {
      alert('删除场景失败: ' + err);
    } finally {
      setLoading(false);
    }
  };

  const loadScenarioMeta = async (scenarioId: string) => {
    try {
      const meta = await Api.globalStudioNewsScenarioMeta(scenarioId);
      setScenarioBackgroundStory(meta.background_story || '');
      setScenarioWorldview(cloneScenarioWorldview(meta.worldview as any));
      setScenarioStoreItems(cloneScenarioStoreItems(meta.news_store_items as any));
    } catch (err) {
      console.error('Failed to load scenario meta:', err);
      setScenarioBackgroundStory('');
      setScenarioWorldview(createDefaultScenarioWorldview());
      setScenarioStoreItems(createDefaultScenarioStoreItems());
    }
  };

  const updateScenarioWorldview = (patch: Partial<ScenarioWorldviewConfig>) => {
    setScenarioWorldview((prev) => ({
      ...prev,
      ...patch,
      featured_symbols: patch.featured_symbols ? [...patch.featured_symbols] : prev.featured_symbols,
    }));
  };

  const updateScenarioStoreItem = (index: number, patch: Partial<NewsStoreItemConfig>) => {
    setScenarioStoreItems((items: NewsStoreItemConfig[]) => items.map((item: NewsStoreItemConfig, idx: number) => (idx === index ? { ...item, ...patch } : item)));
  };

  const updateScenarioStoreItemChainDefault = (index: number, key: string, value: string | number | boolean) => {
    setScenarioStoreItems((items: NewsStoreItemConfig[]) => items.map((item: NewsStoreItemConfig, idx: number) => {
      if (idx !== index) return item;
      return {
        ...item,
        chain_defaults: {
          ...(item.chain_defaults || {}),
          [key]: value,
        },
      };
    }));
  };

  const generateNodeId = () => `node_${Math.random().toString(36).slice(2, 9)}_${Date.now().toString(36)}`;

  const addChainTreeNode = (itemIndex: number, parentNodeId: string | null = null) => {
    setScenarioStoreItems((items: NewsStoreItemConfig[]) => items.map((item: NewsStoreItemConfig, idx: number) => {
      if (idx !== itemIndex) return item;
      const newNode: NewsStoreChainTreeNode = {
        node_id: generateNodeId(),
        kind: item.kind || 'RUMOR',
        text: '',
        scheduled_delay_seconds: 60,
        activation_prob: 1.0,
        symbols: [],
        tags: [],
        truth_payload: {},
        parent_node_id: parentNodeId,
      };
      return { ...item, chain_tree: [...(item.chain_tree || []), newNode] };
    }));
  };

  const removeChainTreeNode = (itemIndex: number, nodeId: string) => {
    setScenarioStoreItems((items: NewsStoreItemConfig[]) => items.map((item: NewsStoreItemConfig, idx: number) => {
      if (idx !== itemIndex) return item;
      const remaining = (item.chain_tree || []).filter((n) => n.node_id !== nodeId);
      // also clear references to removed node as parent
      const cleaned = remaining.map((n) => (n.parent_node_id === nodeId ? { ...n, parent_node_id: null } : n));
      return { ...item, chain_tree: cleaned };
    }));
  };

  const updateChainTreeNode = (itemIndex: number, nodeId: string, patch: Partial<NewsStoreChainTreeNode>) => {
    setScenarioStoreItems((items: NewsStoreItemConfig[]) => items.map((item: NewsStoreItemConfig, idx: number) => {
      if (idx !== itemIndex) return item;
      return {
        ...item,
        chain_tree: (item.chain_tree || []).map((n) => (n.node_id === nodeId ? { ...n, ...patch } : n)),
      };
    }));
  };

  const addScenarioStoreItem = () => {
    setScenarioStoreItems((items: NewsStoreItemConfig[]) => ([
      ...items,
      {
        kind: 'RUMOR',
        price_cash: 0,
        description: '',
        requires_symbols: false,
        trigger_mode: 'IMMEDIATE',
        tags: [],
        rarity: 'COMMON',
        chain_kind: null,
        chain_defaults: {},
        chain_tree: [],
        enabled: true,
      },
    ]));
  };

  const removeScenarioStoreItem = (index: number) => {
    setScenarioStoreItems((items: NewsStoreItemConfig[]) => items.filter((_: NewsStoreItemConfig, idx: number) => idx !== index));
  };

  const handleSaveScenarioMeta = async () => {
    if (!selectedScenarioId) return;
    try {
      setLoading(true);
      await Api.globalStudioNewsUpdateScenarioMeta(selectedScenarioId, {
        actor_id: 'author',
        background_story: scenarioBackgroundStory,
        worldview: scenarioWorldview,
        news_store_items: scenarioStoreItems.map(toNewsStoreItem),
      });
      alert('Scenario settings saved');
    } catch (err) {
      alert('保存场景元数据失败: ' + err);
    } finally {
      setLoading(false);
    }
  };

  const handleExportPackage = async () => {
    if (!selectedScenarioId) return;
    try {
      setLoading(true);
      const pkg = await Api.globalStudioNewsExportPackage(selectedScenarioId);
      const blob = new Blob([JSON.stringify(pkg, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${pkg.scenario_id || selectedScenarioId}_world.json`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      alert('导出世界包失败: ' + err);
    } finally {
      setLoading(false);
    }
  };

  const handleImportPackage = async (file: File) => {
    if (!selectedScenarioId) return;
    try {
      setLoading(true);
      const text = await file.text();
      const pkg = JSON.parse(text);
      await Api.globalStudioNewsImportPackage(selectedScenarioId, {
        actor_id: 'author',
        package: pkg,
      });
      await loadScenarioMeta(selectedScenarioId);
      await loadScenarioCards(selectedScenarioId);
      alert('世界包导入成功');
    } catch (err) {
      alert('导入世界包失败: ' + err);
    } finally {
      setLoading(false);
    }
  };

  const handleCreateScenarioFromTemplate = async () => {
    const name = prompt('NEW SCENARIO IDENTIFIER:');
    if (!name) return;
    const scenarioId = name.toUpperCase().trim();
    if (!scenarioId) return;

    try {
      setLoading(true);
      const template = await Api.globalStudioNewsDefaultTemplate();
      await Api.globalStudioNewsImportPackage(scenarioId, {
        actor_id: 'author',
        package: {
          ...template,
          scenario_id: scenarioId,
        },
      });
      await loadScenarios();
      setSelectedScenarioId(scenarioId);
    } catch (err) {
      alert('从模板创建 scenario 失败: ' + err);
    } finally {
      setLoading(false);
    }
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
    if (cards.length === 0) {
      setNodes([]);
      setEdges([]);
      return;
    }

    const referenceTime = new Date(
      Math.min(...cards.map(c => c.scheduled_at ? new Date(c.scheduled_at).getTime() : Date.now()))
    );

    // --- 混合布局：X 轴 = 时间偏移, Y 轴 = 树形层级 ---
    const NODE_H = 100;
    const GAP_Y = 30;
    const X_PAD = 50;

    const cardMap = new Map(cards.map(c => [c.card_id, c]));
    const childrenMap = new Map<string, string[]>();
    const roots: string[] = [];

    for (const c of cards) {
      const pid = c.parent_card_id;
      if (!pid || !cardMap.has(pid)) {
        roots.push(c.card_id);
      } else {
        const siblings = childrenMap.get(pid) || [];
        siblings.push(c.card_id);
        childrenMap.set(pid, siblings);
      }
    }

    // 按 scheduled_at 排序同层兄弟
    const sortByTime = (ids: string[]) =>
      ids.sort((a, b) => {
        const ta = cardMap.get(a)?.scheduled_at || '';
        const tb = cardMap.get(b)?.scheduled_at || '';
        return ta < tb ? -1 : ta > tb ? 1 : 0;
      });

    sortByTime(roots);
    for (const [, children] of childrenMap) sortByTime(children);

    // 计算每张卡的时间偏移（秒）
    const offsetSecondsMap = new Map<string, number>();
    for (const c of cards) {
      const offsetMs = c.scheduled_at ? new Date(c.scheduled_at).getTime() - referenceTime.getTime() : 0;
      offsetSecondsMap.set(c.card_id, Math.max(0, Math.floor(offsetMs / 1000)));
    }

    // DFS 遍历分配 Y 坐标（树形层级），X 由时间决定
    const positions = new Map<string, { x: number; y: number }>();
    let nextY = 80;

    const layoutSubtree = (nodeId: string): number => {
      const children = childrenMap.get(nodeId) || [];
      const offsetSec = offsetSecondsMap.get(nodeId) || 0;
      const x = offsetSec * timeScale + X_PAD;

      if (children.length === 0) {
        const y = nextY;
        positions.set(nodeId, { x, y });
        nextY += NODE_H + GAP_Y;
        return y;
      }

      let minChildY = Infinity;
      let maxChildY = -Infinity;
      for (const childId of children) {
        const childY = layoutSubtree(childId);
        minChildY = Math.min(minChildY, childY);
        maxChildY = Math.max(maxChildY, childY);
      }
      const y = (minChildY + maxChildY) / 2;
      positions.set(nodeId, { x, y });
      return y;
    };

    for (const rootId of roots) {
      layoutSubtree(rootId);
    }

    const newNodes = cards.map((card) => {
      const offsetSeconds = offsetSecondsMap.get(card.card_id) || 0;
      const pos = positions.get(card.card_id) || { x: X_PAD, y: nextY };

      return {
        id: card.card_id,
        type: 'cybernews',
        position: pos,
        data: { card, offsetSeconds }
      };
    });
    setNodes(newNodes as Node[]);

    const newEdges = cards
      .filter(c => c.parent_card_id && cardMap.has(c.parent_card_id))
      .map(c => ({
        id: `edge-${c.parent_card_id}-${c.card_id}`,
        source: c.parent_card_id!,
        target: c.card_id,
        animated: true,
        style: { stroke: '#22d3ee', strokeWidth: 2 },
        markerEnd: { type: MarkerType.ArrowClosed, color: '#22d3ee' }
      }));
    setEdges(newEdges as Edge[]);
  }, [cards, timeScale, setNodes, setEdges]);

  const onNodeDragStop = useCallback(async (_event: any, node: any) => {
    const card = cards.find(c => c.card_id === node.id);
    if (!card) return;

    const referenceTime = cards.length > 0 
      ? new Date(Math.min(...cards.map(c => c.scheduled_at ? new Date(c.scheduled_at).getTime() : Date.now())))
      : new Date();

    const currentOffsetSeconds = Math.max(0, Math.floor((node.position.x - 50) / timeScale));
    const newScheduledTime = new Date(referenceTime.getTime() + currentOffsetSeconds * 1000).toISOString();

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
  }, [cards, timeScale, selectedScenarioId, playerId]);

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
              onClick={handleCreateScenarioFromTemplate}
              disabled={loading}
              className="cyber-button"
              style={{ padding: '6px' }}
              title="从默认模板创建新 scenario"
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
              padding: '10px 12px 10px 14px',
              borderRadius: '2px',
              cursor: 'pointer',
              fontSize: '13px',
              marginBottom: '8px',
              transition: 'all 0.1s',
              background: selectedScenarioId === null ? '#334155' : 'transparent',
              border: `1px solid ${selectedScenarioId === null ? '#3b82f6' : 'transparent'}`,
              borderLeft: `3px solid ${selectedScenarioId === null ? '#3b82f6' : 'transparent'}`,
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
                padding: '10px 12px 10px 14px',
                borderRadius: '2px',
                cursor: 'pointer',
                fontSize: '13px',
                marginBottom: '4px',
                transition: 'all 0.1s',
                background: selectedScenarioId === s.id ? '#334155' : 'transparent',
                border: `1px solid ${selectedScenarioId === s.id ? '#3b82f6' : 'transparent'}`,
                borderLeft: `3px solid ${selectedScenarioId === s.id ? '#3b82f6' : 'transparent'}`,
                color: selectedScenarioId === s.id ? '#fff' : '#94a3b8',
              }}
              onMouseEnter={(e) => { if (selectedScenarioId !== s.id) e.currentTarget.style.background = '#1e293b'; }}
              onMouseLeave={(e) => { if (selectedScenarioId !== s.id) e.currentTarget.style.background = 'transparent'; }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '6px' }}>
                <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1 }}>{s.name}</span>
                <button
                  onClick={(e) => { e.stopPropagation(); handleDeleteScenario(s.id); }}
                  style={{ background: 'transparent', border: 'none', color: '#64748b', cursor: 'pointer', padding: '2px', flexShrink: 0, display: 'flex', alignItems: 'center' }}
                  title={`删除 ${s.name}`}
                >
                  <Trash2 size={13} />
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Main Workspace */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: '#0f172a', position: 'relative' }}>
        {/* Header */}
        <div style={{ padding: '16px 24px', borderBottom: '1px solid #334155', background: '#111827', zIndex: 10, flexShrink: 0 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <div style={{ fontSize: '10px', color: '#64748b', fontWeight: 'bold', marginBottom: '4px', display: 'flex', alignItems: 'center', gap: '4px' }}>
                <Sparkles size={10} /> SCENARIO STUDIO
              </div>
              <h3 style={{ margin: 0, color: '#f1f5f9', fontSize: '16px' }}>{selectedScenarioId ? selectedScenarioId : 'NO_SCENARIO_SELECTED'}</h3>
            </div>
            <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
              <button
                onClick={handleExportPackage}
                disabled={!selectedScenarioId || loading}
                className="cyber-button"
                style={{ padding: '8px 14px', display: 'flex', alignItems: 'center', gap: '6px' }}
                title="导出世界包"
              >
                <Download size={14} /> EXPORT
              </button>
              <button
                onClick={() => importFileRef.current?.click()}
                disabled={!selectedScenarioId || loading}
                className="cyber-button"
                style={{ padding: '8px 14px', display: 'flex', alignItems: 'center', gap: '6px' }}
                title="导入世界包"
              >
                <Upload size={14} /> IMPORT
              </button>
              <input
                ref={importFileRef}
                type="file"
                accept=".json,application/json"
                style={{ display: 'none' }}
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) handleImportPackage(file);
                  e.target.value = '';
                }}
              />
              <button
                onClick={handleSaveScenarioMeta}
                disabled={!selectedScenarioId || loading}
                className="cyber-button active"
                style={{ padding: '8px 14px', display: 'flex', alignItems: 'center', gap: '6px' }}
              >
                <Save size={14} /> SAVE
              </button>
            </div>
          </div>
        </div>

        {/* Tab Bar */}
        <div style={{ height: '44px', borderBottom: '1px solid #334155', background: '#1e293b', display: 'flex', alignItems: 'center', padding: '0 24px', gap: '8px', zIndex: 10, flexShrink: 0 }}>
          {[ 
            { id: 'worldview', label: 'WORLDVIEW', icon: Book, color: '#3b82f6' },
            { id: 'store', label: 'STORE', icon: Store, color: '#10b981' },
            { id: 'tree', label: 'STORY TREE', icon: GitBranch, color: '#a855f7' }
          ].map((tab) => {
            const Icon = tab.icon;
            const selected = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id as any)}
                className="cyber-button"
                style={{
                  padding: '7px 16px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  fontSize: '11px',
                  fontWeight: 'bold',
                  letterSpacing: '0.5px',
                  background: selected ? `${tab.color}15` : 'transparent',
                  border: `1px solid ${selected ? tab.color : '#334155'}`,
                  color: selected ? '#fff' : '#94a3b8',
                  boxShadow: selected ? `0 0 10px ${tab.color}33` : 'none',
                  transition: 'all 0.15s ease'
                }}
              >
                <Icon size={14} style={{ color: selected ? tab.color : '#64748b' }} /> {tab.label}
              </button>
            );
          })}
        </div>

        {/* Tab Content */}
        <div style={{ flex: 1, overflow: 'hidden', position: 'relative' }}>
          {activeTab === 'worldview' && (
            <div style={{ height: '100%', overflowY: 'auto', padding: '24px 32px', scrollbarWidth: 'thin' }}>
              <div style={{ maxWidth: '960px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '20px' }}>

                {/* Section: Featured Symbols */}
                <div style={{ background: '#111827', border: '1px solid #1e3a8a', borderRadius: '6px', padding: '20px', position: 'relative', overflow: 'hidden' }}>
                  <div style={{ position: 'absolute', top: 0, left: 0, right: 0, height: '2px', background: 'linear-gradient(90deg, #3b82f6, #8b5cf6, #3b82f6)' }} />
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '14px' }}>
                    <Zap size={15} style={{ color: '#3b82f6' }} />
                    <span style={{ fontSize: '11px', fontWeight: 'bold', color: '#94a3b8', letterSpacing: '1.5px' }}>FEATURED SYMBOLS</span>
                  </div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', marginBottom: '12px' }}>
                    {(scenarioWorldview.featured_symbols || []).map((sym, i) => (
                      <span key={i} style={{
                        display: 'inline-flex', alignItems: 'center', gap: '6px',
                        padding: '5px 12px', borderRadius: '3px',
                        background: 'rgba(59, 130, 246, 0.12)', border: '1px solid #3b82f6',
                        color: '#93c5fd', fontSize: '12px', fontWeight: 'bold', fontFamily: 'monospace', letterSpacing: '0.5px'
                      }}>
                        {sym}
                        <button onClick={() => updateScenarioWorldview({ featured_symbols: (scenarioWorldview.featured_symbols || []).filter((_, idx) => idx !== i) })}
                          style={{ background: 'none', border: 'none', color: '#64748b', cursor: 'pointer', padding: 0, fontSize: '14px', lineHeight: 1 }}>x</button>
                      </span>
                    ))}
                  </div>
                  <input
                    className="cyber-input"
                    placeholder="输入标的代号后按回车添加，如 BLUEGOLD"
                    style={{ width: '100%' }}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        const val = (e.target as HTMLInputElement).value.trim().toUpperCase();
                        if (val && !(scenarioWorldview.featured_symbols || []).includes(val)) {
                          updateScenarioWorldview({ featured_symbols: [...(scenarioWorldview.featured_symbols || []), val] });
                        }
                        (e.target as HTMLInputElement).value = '';
                      }
                    }}
                  />
                </div>

                {/* Section: Market Rules - 2 column */}
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                  {[
                    { key: 'market_open_note' as const, label: 'MARKET OPEN', icon: Clock, color: '#10b981', placeholder: '开盘规则说明...' },
                    { key: 'market_close_note' as const, label: 'MARKET CLOSE', icon: Clock, color: '#f59e0b', placeholder: '收盘规则说明...' },
                  ].map(({ key, label, icon: MIcon, color, placeholder }) => (
                    <div key={key} style={{ background: '#111827', border: '1px solid #334155', borderRadius: '6px', padding: '16px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '10px' }}>
                        <MIcon size={13} style={{ color }} />
                        <span style={{ fontSize: '10px', fontWeight: 'bold', color: '#94a3b8', letterSpacing: '1px' }}>{label}</span>
                      </div>
                      <textarea
                        className="cyber-input"
                        value={(scenarioWorldview as any)[key] || ''}
                        onChange={(e) => updateScenarioWorldview({ [key]: e.target.value })}
                        placeholder={placeholder}
                        style={{ width: '100%', minHeight: '80px', resize: 'vertical', lineHeight: '1.6', fontSize: '12px' }}
                      />
                    </div>
                  ))}
                </div>

                {/* Section: Holiday & Overview - 2 column */}
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                  <div style={{ background: '#111827', border: '1px solid #334155', borderRadius: '6px', padding: '16px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '10px' }}>
                      <Sparkles size={13} style={{ color: '#ec4899' }} />
                      <span style={{ fontSize: '10px', fontWeight: 'bold', color: '#94a3b8', letterSpacing: '1px' }}>HOLIDAY RULES</span>
                    </div>
                    <textarea
                      className="cyber-input"
                      value={scenarioWorldview.holiday_note || ''}
                      onChange={(e) => updateScenarioWorldview({ holiday_note: e.target.value })}
                      placeholder="节假日特殊规则..."
                      style={{ width: '100%', minHeight: '80px', resize: 'vertical', lineHeight: '1.6', fontSize: '12px' }}
                    />
                  </div>
                  <div style={{ background: '#111827', border: '1px solid #334155', borderRadius: '6px', padding: '16px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '10px' }}>
                      <Book size={13} style={{ color: '#8b5cf6' }} />
                      <span style={{ fontSize: '10px', fontWeight: 'bold', color: '#94a3b8', letterSpacing: '1px' }}>WORLD OVERVIEW</span>
                    </div>
                    <textarea
                      className="cyber-input"
                      value={scenarioWorldview.overview_note || ''}
                      onChange={(e) => updateScenarioWorldview({ overview_note: e.target.value })}
                      placeholder="世界观概述..."
                      style={{ width: '100%', minHeight: '80px', resize: 'vertical', lineHeight: '1.6', fontSize: '12px' }}
                    />
                  </div>
                </div>

                {/* Section: Background Story - full width prominent */}
                <div style={{ background: '#111827', border: '1px solid #334155', borderRadius: '6px', padding: '20px', position: 'relative', overflow: 'hidden' }}>
                  <div style={{ position: 'absolute', top: 0, left: 0, width: '3px', height: '100%', background: 'linear-gradient(180deg, #8b5cf6, #3b82f6)' }} />
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
                    <Book size={15} style={{ color: '#a78bfa' }} />
                    <span style={{ fontSize: '11px', fontWeight: 'bold', color: '#94a3b8', letterSpacing: '1.5px' }}>BACKGROUND STORY</span>
                    <span style={{ fontSize: '9px', color: '#475569', marginLeft: '8px' }}>剧本背景 · 决定剧情树的叙事基调</span>
                  </div>
                  <textarea
                    className="cyber-input"
                    value={scenarioBackgroundStory}
                    onChange={(e) => setScenarioBackgroundStory(e.target.value)}
                    placeholder="在这里编写场景的背景故事。这段文字将定义整棵剧情树的叙事基调和世界观设定..."
                    style={{ width: '100%', minHeight: '200px', resize: 'vertical', lineHeight: '1.8', fontSize: '13px', background: 'rgba(0,0,0,0.25)' }}
                  />
                </div>

              </div>
            </div>
          )}

          {activeTab === 'store' && (() => {
            const storeKindColors: Record<string, string> = {
              RUMOR: '#64748b', LEAK: '#ef4444', REPORT: '#f59e0b',
              MAJOR_EVENT: '#a855f7', WORLD_EVENT: '#ec4899', EARNINGS: '#10b981', DEFAULT: '#3b82f6'
            };
            const rarityColors: Record<string, string> = {
              COMMON: '#94a3b8', UNCOMMON: '#10b981', RARE: '#3b82f6', EPIC: '#a855f7', LEGENDARY: '#f59e0b'
            };
            return (
            <div style={{ height: '100%', overflowY: 'auto', padding: '24px 32px', scrollbarWidth: 'thin' }}>
              <div style={{ maxWidth: '960px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '16px' }}>

                {/* Header */}
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <Store size={18} style={{ color: '#10b981' }} />
                    <span style={{ fontSize: '13px', fontWeight: 'bold', color: '#f1f5f9', letterSpacing: '1px' }}>NEWS STORE</span>
                    <span style={{ fontSize: '10px', color: '#475569', padding: '2px 8px', background: '#1e293b', borderRadius: '10px' }}>
                      {scenarioStoreItems.length} items
                    </span>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                    <span style={{ fontSize: '10px', color: '#64748b' }}>玩家可购买的新闻商品 · 链式触发逻辑</span>
                    <button
                      onClick={addScenarioStoreItem}
                      type="button"
                      style={{
                        display: 'flex', alignItems: 'center', gap: '5px',
                        padding: '6px 14px', borderRadius: '4px',
                        background: 'rgba(16, 185, 129, 0.12)', border: '1px solid #10b981',
                        color: '#10b981', cursor: 'pointer',
                        fontSize: '11px', fontWeight: 'bold', letterSpacing: '0.5px',
                        transition: 'all 0.15s'
                      }}
                      onMouseEnter={(e) => { e.currentTarget.style.background = 'rgba(16, 185, 129, 0.25)'; }}
                      onMouseLeave={(e) => { e.currentTarget.style.background = 'rgba(16, 185, 129, 0.12)'; }}
                    >
                      <Plus size={14} /> NEW ITEM
                    </button>
                  </div>
                </div>

                {/* Store Items */}
                {scenarioStoreItems.map((item, index) => {
                  const kindColor = storeKindColors[item.kind || 'DEFAULT'] || storeKindColors.DEFAULT;
                  const rarityColor = rarityColors[item.rarity || 'COMMON'] || rarityColors.COMMON;
                  const isDisabled = item.enabled === false;
                  return (
                    <div
                      key={`${item.kind}-${index}`}
                      style={{
                        background: '#111827',
                        border: `1px solid ${isDisabled ? '#1e293b' : '#334155'}`,
                        borderLeft: `3px solid ${isDisabled ? '#475569' : kindColor}`,
                        borderRadius: '6px',
                        padding: '16px 18px',
                        opacity: isDisabled ? 0.6 : 1,
                        transition: 'opacity 0.15s',
                        display: 'flex', flexDirection: 'column', gap: '14px'
                      }}
                    >
                      {/* Item Header */}
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                          <span style={{
                            fontSize: '10px', fontWeight: 'bold', padding: '3px 8px', borderRadius: '2px',
                            background: `${kindColor}20`, border: `1px solid ${kindColor}`, color: kindColor,
                            textTransform: 'uppercase', letterSpacing: '0.5px'
                          }}>
                            {item.kind || 'RUMOR'}
                          </span>
                          <span style={{ fontSize: '13px', color: '#10b981', fontFamily: 'monospace', fontWeight: 'bold' }}>
                            ${Number(item.price_cash || 0).toLocaleString()}
                          </span>
                          <span style={{
                            fontSize: '9px', fontWeight: 'bold', padding: '2px 6px', borderRadius: '2px',
                            background: `${rarityColor}15`, border: `1px solid ${rarityColor}40`, color: rarityColor,
                            letterSpacing: '0.5px'
                          }}>
                            {item.rarity || 'COMMON'}
                          </span>
                          <span style={{
                            fontSize: '9px', padding: '2px 6px', borderRadius: '2px',
                            background: item.trigger_mode === 'AUTO_CHAIN' ? 'rgba(96, 165, 250, 0.1)' : 'rgba(100,116,139,0.1)',
                            border: `1px solid ${item.trigger_mode === 'AUTO_CHAIN' ? '#60a5fa40' : '#47556940'}`,
                            color: item.trigger_mode === 'AUTO_CHAIN' ? '#60a5fa' : '#94a3b8'
                          }}>
                            {item.trigger_mode}
                          </span>
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <label style={{ display: 'flex', alignItems: 'center', gap: '4px', cursor: 'pointer', fontSize: '10px', color: '#64748b' }}>
                            <input type="checkbox" checked={item.enabled !== false} onChange={(e) => updateScenarioStoreItem(index, { enabled: e.target.checked })} style={{ accentColor: '#10b981' }} />
                          </label>
                          <button
                            onClick={() => removeScenarioStoreItem(index)}
                            style={{ background: 'transparent', border: 'none', color: '#475569', cursor: 'pointer', padding: '2px', display: 'flex', alignItems: 'center' }}
                            title="删除商品"
                          >
                            <Trash2 size={13} />
                          </button>
                        </div>
                      </div>

                      {/* Description */}
                      <textarea
                        className="cyber-input"
                        value={item.description || ''}
                        onChange={(e) => updateScenarioStoreItem(index, { description: e.target.value })}
                        placeholder="商品描述 — 玩家在商店中看到的说明文字..."
                        style={{ width: '100%', minHeight: '48px', resize: 'vertical', fontSize: '12px', lineHeight: '1.6' }}
                      />

                      {/* Config Grid */}
                      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: '10px' }}>
                        <label style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
                          <span style={{ fontSize: '9px', color: '#64748b', fontWeight: 'bold', letterSpacing: '0.5px' }}>TRIGGER</span>
                          <select className="cyber-input" value={item.trigger_mode} onChange={(e) => updateScenarioStoreItem(index, { trigger_mode: e.target.value as any })}>
                            <option value="IMMEDIATE">IMMEDIATE</option>
                            <option value="MANUAL">MANUAL</option>
                            <option value="AUTO_CHAIN">AUTO_CHAIN</option>
                          </select>
                        </label>
                        <label style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
                          <span style={{ fontSize: '9px', color: '#64748b', fontWeight: 'bold', letterSpacing: '0.5px' }}>RARITY</span>
                          <select className="cyber-input" value={item.rarity || 'COMMON'} onChange={(e) => updateScenarioStoreItem(index, { rarity: e.target.value })}>
                            <option value="COMMON">COMMON</option>
                            <option value="UNCOMMON">UNCOMMON</option>
                            <option value="RARE">RARE</option>
                            <option value="EPIC">EPIC</option>
                            <option value="LEGENDARY">LEGENDARY</option>
                          </select>
                        </label>
                        <label style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
                          <span style={{ fontSize: '9px', color: '#64748b', fontWeight: 'bold', letterSpacing: '0.5px' }}>CHAIN KIND</span>
                          <input className="cyber-input" value={item.chain_kind || ''} onChange={(e) => updateScenarioStoreItem(index, { chain_kind: e.target.value ? e.target.value.toUpperCase() : null })} placeholder="—" />
                        </label>
                        <label style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
                          <span style={{ fontSize: '9px', color: '#64748b', fontWeight: 'bold', letterSpacing: '0.5px' }}>TAGS</span>
                          <input className="cyber-input" value={(item.tags || []).join(', ')} onChange={(e) => updateScenarioStoreItem(index, { tags: e.target.value.split(',').map(s => s.trim()).filter(Boolean) })} placeholder="—" />
                        </label>
                      </div>

                      {/* Flags & Chain Defaults */}
                      <div style={{ display: 'flex', alignItems: 'center', gap: '16px', flexWrap: 'wrap' }}>
                        <label style={{ display: 'flex', alignItems: 'center', gap: '4px', cursor: 'pointer', fontSize: '11px', color: '#cbd5e1' }}>
                          <input type="checkbox" checked={!!item.requires_symbols} onChange={(e) => updateScenarioStoreItem(index, { requires_symbols: e.target.checked })} style={{ accentColor: '#3b82f6' }} />
                          需要标的
                        </label>
                        <div style={{ width: '1px', height: '14px', background: '#334155' }} />
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                          {[
                            { label: 'T0', field: 't0_seconds' },
                            { label: 'Omen', field: 'omen_interval_seconds' },
                            { label: 'Abort%', field: 'abort_probability' },
                          ].map(({ label, field }) => (
                            <label key={field} style={{ display: 'flex', alignItems: 'center', gap: '3px', fontSize: '10px', color: '#64748b' }}>
                              <span style={{ fontWeight: 'bold' }}>{label}:</span>
                              <input
                                type="number"
                                step={field === 'abort_probability' ? '0.01' : '1'}
                                className="cyber-input"
                                value={Number((item.chain_defaults as any)?.[field] ?? 0)}
                                onChange={(e) => updateScenarioStoreItemChainDefault(index, field, Number(e.target.value))}
                                style={{ width: '52px', padding: '2px 4px', fontSize: '10px' }}
                              />
                            </label>
                          ))}
                        </div>
                      </div>

                      {/* Chain Tree (only for AUTO_CHAIN) */}
                      {item.trigger_mode === 'AUTO_CHAIN' && (
                        <div style={{ border: '1px solid #1e3a8a', borderRadius: '4px', padding: '12px', background: 'rgba(30, 58, 138, 0.08)' }}>
                          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '10px' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '10px', color: '#60a5fa', fontWeight: 'bold', letterSpacing: '1px' }}>
                              <GitBranch size={12} /> CHAIN TREE
                              <span style={{ fontSize: '9px', color: '#475569', fontWeight: 'normal' }}>({(item.chain_tree || []).length} nodes)</span>
                            </div>
                          </div>
                          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                            {(item.chain_tree || []).map((node, nodeIdx) => (
                              <div
                                key={node.node_id}
                                style={{
                                  display: 'grid', gridTemplateColumns: '1fr',
                                  gap: '6px', padding: '10px',
                                  background: 'rgba(0,0,0,0.2)', borderRadius: '4px',
                                  borderLeft: `2px solid ${node.parent_node_id ? '#60a5fa' : '#10b981'}`
                                }}
                              >
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                                    <span style={{ fontSize: '10px', color: '#94a3b8', fontFamily: 'monospace' }}>#{nodeIdx + 1}</span>
                                    <input className="cyber-input" value={node.kind} onChange={(e) => updateChainTreeNode(index, node.node_id, { kind: e.target.value.toUpperCase() })} placeholder="kind" style={{ width: '100px', padding: '2px 6px', fontSize: '10px' }} />
                                    <input type="number" className="cyber-input" value={node.scheduled_delay_seconds} onChange={(e) => updateChainTreeNode(index, node.node_id, { scheduled_delay_seconds: Number(e.target.value) })} style={{ width: '60px', padding: '2px 6px', fontSize: '10px' }} placeholder="delay" />
                                    <span style={{ fontSize: '9px', color: '#475569' }}>s</span>
                                    <input type="number" step="0.01" className="cyber-input" value={node.activation_prob} onChange={(e) => updateChainTreeNode(index, node.node_id, { activation_prob: Number(e.target.value) })} style={{ width: '50px', padding: '2px 6px', fontSize: '10px' }} placeholder="prob" />
                                    <select className="cyber-input" value={node.parent_node_id || ''} onChange={(e) => updateChainTreeNode(index, node.node_id, { parent_node_id: e.target.value || null })} style={{ width: '100px', padding: '2px 6px', fontSize: '10px' }}>
                                      <option value="">root</option>
                                      {(item.chain_tree || []).filter((n) => n.node_id !== node.node_id).map((n) => (
                                        <option key={n.node_id} value={n.node_id}>{n.kind} (..{n.node_id.slice(-4)})</option>
                                      ))}
                                    </select>
                                  </div>
                                  <button
                                    onClick={() => removeChainTreeNode(index, node.node_id)}
                                    style={{ background: 'transparent', border: 'none', color: '#475569', cursor: 'pointer', padding: '2px', display: 'flex', alignItems: 'center' }}
                                  >
                                    <Trash2 size={11} />
                                  </button>
                                </div>
                                <textarea className="cyber-input" value={node.text || ''} onChange={(e) => updateChainTreeNode(index, node.node_id, { text: e.target.value })} placeholder="链式事件文本..." style={{ width: '100%', minHeight: '36px', resize: 'vertical', fontSize: '11px', lineHeight: '1.5' }} />
                              </div>
                            ))}
                          </div>
                          <button
                            onClick={() => addChainTreeNode(index, (item.chain_tree || [])[(item.chain_tree || []).length - 1]?.node_id || null)}
                            type="button"
                            style={{
                              width: '100%', marginTop: '8px',
                              background: 'transparent', border: '1px dashed #3b82f640',
                              color: '#60a5fa', padding: '6px', cursor: 'pointer',
                              fontSize: '10px', borderRadius: '3px', letterSpacing: '0.5px'
                            }}
                          >
                            + ADD CHAIN NODE
                          </button>
                        </div>
                      )}
                    </div>
                  );
                })}

                {/* Add button */}
                <button
                  onClick={addScenarioStoreItem}
                  type="button"
                  style={{
                    width: '100%', padding: '12px',
                    background: 'transparent', border: '1px dashed #334155',
                    color: '#64748b', cursor: 'pointer', borderRadius: '6px',
                    fontSize: '11px', fontWeight: 'bold', letterSpacing: '1px',
                    display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px',
                    transition: 'all 0.15s'
                  }}
                  onMouseEnter={(e) => { e.currentTarget.style.borderColor = '#10b981'; e.currentTarget.style.color = '#10b981'; }}
                  onMouseLeave={(e) => { e.currentTarget.style.borderColor = '#334155'; e.currentTarget.style.color = '#64748b'; }}
                >
                  <Plus size={14} /> ADD STORE ITEM
                </button>
              </div>
            </div>
            );
          })()}

          {activeTab === 'tree' && (
            <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
              {/* Toolbar */}
              <div style={{ height: '60px', borderBottom: '1px solid #334155', background: '#1e293b', display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 24px', zIndex: 10, flexShrink: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '24px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <GitBranch size={18} style={{ color: '#3b82f6' }} />
                    <span style={{ fontSize: '13px', fontWeight: 'bold', color: '#f1f5f9' }}>BACKGROUND NEWS TREE</span>
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '10px', color: '#64748b' }}>
                      <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}><span style={{ width: '8px', height: '8px', background: '#64748b', borderRadius: '1px' }} />RUMOR</span>
                      <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}><span style={{ width: '8px', height: '8px', background: '#ef4444', borderRadius: '1px' }} />LEAK</span>
                      <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}><span style={{ width: '8px', height: '8px', background: '#f59e0b', borderRadius: '1px' }} />REPORT</span>
                      <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}><span style={{ width: '8px', height: '8px', background: '#a855f7', borderRadius: '1px' }} />MAJOR</span>
                      <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}><span style={{ width: '8px', height: '8px', background: '#ec4899', borderRadius: '1px' }} />WORLD</span>
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
                </div>

                <button
                  onClick={handleCreateNewNode}
                  className="cyber-button active"
                  style={{ padding: '6px 16px' }}
                >
                  <Plus size={16} /> New Block
                </button>
              </div>

              {/* Blueprint Canvas */}
              <div style={{ flex: 1, position: 'relative' }}>
                {cards.length === 0 ? (
                  <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', zIndex: 1, background: 'radial-gradient(circle at center, rgba(59,130,246,0.06) 0%, transparent 60%)' }}>
                    <div style={{ 
                      width: '72px', 
                      height: '72px', 
                      borderRadius: '50%', 
                      background: 'linear-gradient(135deg, #1e293b 0%, #0f172a 100%)', 
                      border: '1px solid #334155', 
                      boxShadow: '0 0 20px rgba(59,130,246,0.15)', 
                      display: 'flex', 
                      alignItems: 'center', 
                      justifyContent: 'center', 
                      marginBottom: '20px' 
                    }}>
                      <GitBranch size={36} style={{ color: '#3b82f6' }} />
                    </div>
                    <div style={{ fontSize: '12px', fontWeight: 'bold', color: '#64748b', letterSpacing: '1px', marginBottom: '8px' }}>
                      {selectedScenarioId ? 'EMPTY STORY SEQUENCE' : 'NO SCENARIO SELECTED'}
                    </div>
                    <p style={{ fontSize: '13px', color: '#94a3b8', textAlign: 'center', maxWidth: '360px', lineHeight: '1.6' }}>
                      {selectedScenarioId 
                        ? `Scenario [${selectedScenarioId}] has no background news cards yet. Click “New Block” to seed the sequence.` 
                        : "Select a scenario from the archive on the left to begin editing the background news tree."}
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
                    snapToGrid
                    snapGrid={[20, 20]}
                    attributionPosition="bottom-left"
                  >
                    <Background color="#1e293b" gap={20} size={1} />
                    <Controls style={{ background: '#1e293b', border: '1px solid #334155', borderRadius: '2px' }} />
                    <MiniMap style={{ background: '#0f172a', border: '1px solid #334155' }} nodeColor={() => '#1e293b'} maskColor="rgba(15, 23, 42, 0.7)" />
                  </ReactFlow>
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Node Inspector Sidebar — only relevant in Story Tree tab */}
      {activeTab === 'tree' && (
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
      )}

    </div>
  );
};

export default NewsStudioPage;
