import React, { useState, useEffect, useMemo } from 'react';
import { 
  Plus, 
  Image as ImageIcon, 
  Save, 
  Zap,
  RefreshCw,
  Clock,
  Settings,
  AlertTriangle,
  GitBranch,
  Book,
  Download,
  Trash2,
  ChevronRight,
  ChevronDown,
  ArrowRight
} from 'lucide-react';
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

const NewsStudioPage: React.FC = () => {
  const { playerId } = useAppSession();
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [selectedScenarioId, setSelectedScenarioId] = useState<string | null>(null);
  const [cards, setCards] = useState<NewsCard[]>([]);
  const [selectedCardId, setSelectedCardId] = useState<string | null>(null);
  const [presets, setPresets] = useState<Record<string, string[]>>({});
  const [loading, setLoading] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [scenarioFilter, setScenarioFilter] = useState('');

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
    loadScenarios();
    loadPresets();
  }, []);

  useEffect(() => {
    if (selectedScenarioId) {
      loadScenarioCards(selectedScenarioId);
    } else {
      loadAllCards();
    }
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
      // 预设依然可以从房间获取，或者未来也移至全局
      const data = await Api.studioNewsPresets(playerId || 'author');
      setPresets(data);
    } catch (err) { console.error('Failed to load presets:', err); }
  };

  const handleSaveCard = async () => {
    try {
      setLoading(true);
      const payload = {
        ...editCard,
        actor_id: playerId || 'author',
        scenario_id: selectedScenarioId || editCard.scenario_id
      };
      const resp = await Api.globalStudioNewsCreateCard(payload as any);
      setIsCreating(false);
      setSelectedCardId(resp.card_id);
      if (selectedScenarioId) loadScenarioCards(selectedScenarioId);
      alert('保存成功');
    } catch (err) { alert('保存失败: ' + err); }
    finally { setLoading(false); }
  };

  // 树形结构辅助函数
  const treeNodes = useMemo(() => {
    const rootNodes = cards.filter(c => !c.parent_card_id || !cards.find(p => p.card_id === c.parent_card_id));
    return rootNodes;
  }, [cards]);

  const getChildren = (parentId: string) => cards.filter(c => c.parent_card_id === parentId);

  // 递归渲染树节点
  const TreeNode: React.FC<{ card: NewsCard; depth: number }> = ({ card, depth }) => {
    const [expanded, setExpanded] = useState(true);
    const children = getChildren(card.card_id);
    const isSelected = selectedCardId === card.card_id;

    return (
      <div className="ml-4 border-l border-slate-800 pl-4 mt-2">
        <div 
          onClick={() => setSelectedCardId(card.card_id)}
          className={`group flex items-center gap-2 p-2 rounded-md cursor-pointer transition-all ${
            isSelected ? 'bg-cyan-500/10 border border-cyan-500/50 shadow-[0_0_10px_rgba(6,182,212,0.2)]' : 'hover:bg-slate-800 border border-transparent'
          }`}
        >
          <div className="shrink-0 text-slate-500">
            {children.length > 0 ? (
              expanded ? <ChevronDown size={14} onClick={(e) => { e.stopPropagation(); setExpanded(false); }} /> : 
                        <ChevronRight size={14} onClick={(e) => { e.stopPropagation(); setExpanded(true); }} />
            ) : <ArrowRight size={14} className="opacity-30" />}
          </div>
          
          <div className={`text-xs px-1.5 py-0.5 rounded border ${
            card.kind === 'EARNINGS' ? 'border-green-500/30 text-green-400 bg-green-500/5' :
            card.kind === 'MILITARY' ? 'border-red-500/30 text-red-400 bg-red-500/5' :
            'border-blue-500/30 text-blue-400 bg-blue-500/5'
          }`}>
            {card.kind}
          </div>
          
          <span className={`text-xs font-mono truncate max-w-[120px] ${isSelected ? 'text-cyan-400' : 'text-slate-300'}`}>
            {card.card_id.split('-')[0]}
          </span>

          <div className="ml-auto flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
             <button 
              title="添加后续事件"
              onClick={(e) => {
                e.stopPropagation();
                setIsCreating(true);
                setEditCard({
                  ...editCard,
                  card_id: undefined as any,
                  parent_card_id: card.card_id,
                  scenario_id: card.scenario_id
                });
                setSelectedCardId(null);
              }}
              className="p-1 hover:text-cyan-400"
            >
               <Plus size={14} />
             </button>
          </div>
        </div>
        
        {expanded && children.length > 0 && (
          <div className="mt-1">
            {children.map(child => (
              <TreeNode key={child.card_id} card={child} depth={depth + 1} />
            ))}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="flex h-screen bg-slate-950 text-slate-200 overflow-hidden font-mono">
      {/* 极窄侧边栏：剧本列表 */}
      <div className="w-64 border-r border-slate-800 flex flex-col bg-slate-900/50">
        <div className="p-4 border-b border-slate-800 flex justify-between items-center bg-slate-900/80">
          <h2 className="text-sm font-bold flex items-center gap-2 text-indigo-400 uppercase tracking-widest">
            <Book size={16} /> 新闻剧本
          </h2>
          <button 
            onClick={() => {
              const name = prompt('请输入新剧本名称:');
              if (name) setSelectedScenarioId(name);
            }}
            className="p-1 hover:bg-slate-700 rounded text-indigo-400"
          >
            <Plus size={16} />
          </button>
        </div>
        <div className="p-2">
          <input 
            type="text" placeholder="过滤剧本..." 
            className="w-full bg-slate-800 border border-slate-700 rounded-md py-1.5 px-3 text-[10px] focus:outline-none focus:border-indigo-500"
            value={scenarioFilter}
            onChange={(e) => setScenarioFilter(e.target.value)}
          />
        </div>
        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          <div 
            onClick={() => setSelectedScenarioId(null)}
            className={`p-2 rounded text-[10px] cursor-pointer border transition-colors ${
              selectedScenarioId === null ? 'border-indigo-500 bg-indigo-500/10' : 'border-transparent hover:bg-slate-800'
            }`}
          >
            ALL_RECORDS (所有孤立事件)
          </div>
          {scenarios.filter(s => s.name.toLowerCase().includes(scenarioFilter.toLowerCase())).map(s => (
            <div 
              key={s.id}
              onClick={() => setSelectedScenarioId(s.id)}
              className={`p-2 rounded text-[10px] cursor-pointer border transition-colors ${
                selectedScenarioId === s.id ? 'border-indigo-500 bg-indigo-500/10 text-indigo-400' : 'border-transparent hover:bg-slate-800'
              }`}
            >
              {s.name}
            </div>
          ))}
        </div>
      </div>

      {/* 中间栏：树状设计器 */}
      <div className="w-80 border-r border-slate-800 flex flex-col bg-slate-900">
        <div className="p-4 border-b border-slate-800 bg-slate-900/50 flex justify-between items-center">
          <h2 className="text-sm font-bold flex items-center gap-2 text-cyan-400 uppercase tracking-widest">
            <GitBranch size={16} /> 节点树
          </h2>
          <div className="flex gap-2">
            <button 
              onClick={() => {
                setIsCreating(true);
                setSelectedCardId(null);
                setEditCard({
                  kind: 'EARNINGS',
                  symbols: [],
                  tags: [],
                  truth_payload: { impact: 0.1, direction: 'UP', intensity: 0.5, ttl_seconds: 3600 },
                  activation_prob: 1.0,
                  scenario_id: selectedScenarioId
                });
              }}
              className="p-1 hover:bg-slate-700 rounded text-cyan-400"
            >
              <Plus size={18} />
            </button>
            <button className="p-1 hover:bg-slate-700 rounded text-slate-500"><Download size={18} /></button>
          </div>
        </div>
        
        <div className="flex-1 overflow-y-auto p-2 custom-scrollbar">
          {loading ? (
            <div className="flex justify-center p-8 text-slate-600 animate-spin"><RefreshCw /></div>
          ) : treeNodes.length === 0 ? (
            <div className="p-8 text-center text-slate-600 text-[10px]">
              此剧本尚无事件，点击上方 + 创建根节点
            </div>
          ) : (
            treeNodes.map(node => (
              <TreeNode key={node.card_id} card={node} depth={0} />
            ))
          )}
        </div>
      </div>

      {/* 主界面：高级编辑器 */}
      <div className="flex-1 flex flex-col bg-slate-950 overflow-hidden">
        {!selectedCardId && !isCreating ? (
          <div className="flex-1 flex flex-col items-center justify-center text-slate-500 gap-4">
            <div className="w-24 h-24 rounded-full bg-slate-900 flex items-center justify-center border border-slate-800 animate-pulse">
              <Zap size={48} className="text-slate-800 shadow-[0_0_20px_rgba(255,255,255,0.05)]" />
            </div>
            <p className="text-sm tracking-widest opacity-50 uppercase">Select or create a news node</p>
          </div>
        ) : (
          <div className="flex-1 flex flex-col">
            <div className="flex-1 overflow-y-auto p-8 space-y-8 custom-scrollbar">
              <div className="flex justify-between items-start">
                <div>
                  <h1 className="text-2xl font-black text-white flex items-center gap-3">
                    {isCreating ? 'NEW_NODE_CONSTRUCTION' : 'NODE_PARAMETER_TUNING'}
                    {editCard.kind && (
                      <span className="text-xs px-2 py-1 bg-cyan-900/30 text-cyan-400 border border-cyan-500/30 rounded">
                        {editCard.kind}
                      </span>
                    )}
                  </h1>
                  <p className="text-slate-500 text-xs mt-2 uppercase tracking-tighter">
                    {editCard.card_id || 'Generating unique cryptographic signature...'}
                  </p>
                </div>
                <div className="flex gap-4">
                  <button 
                    onClick={handleSaveCard}
                    className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 text-white px-6 py-2.5 rounded shadow-[0_0_20px_rgba(79,70,229,0.3)] transition-all uppercase text-xs font-bold"
                  >
                    <Save size={18} /> Commit Changes
                  </button>
                  <button className="p-2.5 border border-slate-800 hover:border-red-500/50 hover:bg-red-500/10 text-slate-600 hover:text-red-400 rounded transition-all">
                    <Trash2 size={18} />
                  </button>
                </div>
              </div>

              <div className="grid grid-cols-12 gap-8">
                {/* 左列：基础 */}
                <div className="col-span-7 space-y-6">
                  <div className="bg-slate-900/50 border border-slate-800 p-6 rounded-lg space-y-6">
                    <h3 className="text-xs font-bold text-slate-400 border-b border-slate-800 pb-4 flex items-center gap-2">
                      <Settings size={14} /> CORE_ATTRIBUTES
                    </h3>
                    
                    <div className="grid grid-cols-2 gap-6">
                      <div className="space-y-2">
                        <label className="text-[10px] text-slate-500 uppercase">Event Kind</label>
                        <select 
                          className="w-full bg-slate-950 border border-slate-800 rounded py-2 px-3 text-sm focus:border-cyan-500 outline-none"
                          value={editCard.kind}
                          onChange={e => setEditCard({...editCard, kind: e.target.value})}
                        >
                          {Object.keys(presets).map(k => <option key={k} value={k}>{k}</option>)}
                        </select>
                      </div>
                      <div className="space-y-2">
                        <label className="text-[10px] text-slate-500 uppercase">Target Symbols</label>
                        <input 
                          type="text" placeholder="BTC, ETH..."
                          className="w-full bg-slate-950 border border-slate-800 rounded py-2 px-3 text-sm focus:border-cyan-500 outline-none placeholder:text-slate-800"
                          value={editCard.symbols?.join(', ')}
                          onChange={e => setEditCard({...editCard, symbols: e.target.value.split(',').map(s => s.trim()).filter(Boolean)})}
                        />
                      </div>
                    </div>

                    <div className="space-y-2">
                      <label className="text-[10px] text-slate-500 uppercase">Visual Identity (Image URI)</label>
                      <div className="relative">
                        <ImageIcon size={14} className="absolute left-3 top-3 text-slate-700" />
                        <input 
                          type="text" placeholder="https://cdn.os.ifrontier.ai/assets/..."
                          className="w-full bg-slate-950 border border-slate-800 rounded py-2 pl-10 pr-3 text-sm focus:border-cyan-500 outline-none"
                          value={editCard.image_uri || ''}
                          onChange={e => setEditCard({...editCard, image_uri: e.target.value})}
                        />
                      </div>
                    </div>
                  </div>

                  <div className="bg-slate-900/50 border border-slate-800 p-6 rounded-lg space-y-6">
                    <h3 className="text-xs font-bold text-slate-400 border-b border-slate-800 pb-4 flex items-center gap-2">
                      <Zap size={14} /> TRUTH_PAYLOAD (MARKET_IMPACT)
                    </h3>
                    <div className="grid grid-cols-3 gap-4">
                      <div className="space-y-2">
                        <label className="text-[10px] text-slate-500 uppercase">Impact Factor</label>
                        <input 
                          type="number" step="0.01" min="-1" max="1"
                          className="w-full bg-slate-950 border border-slate-800 rounded py-2 px-3 text-sm focus:border-cyan-500 outline-none"
                          value={editCard.truth_payload?.impact || 0}
                          onChange={e => setEditCard({...editCard, truth_payload: {...editCard.truth_payload, impact: parseFloat(e.target.value)}})}
                        />
                      </div>
                      <div className="space-y-2">
                        <label className="text-[10px] text-slate-500 uppercase">Intensity</label>
                        <input 
                          type="number" step="0.1" min="0" max="1"
                          className="w-full bg-slate-950 border border-slate-800 rounded py-2 px-3 text-sm focus:border-cyan-500 outline-none"
                          value={editCard.truth_payload?.intensity || 0.5}
                          onChange={e => setEditCard({...editCard, truth_payload: {...editCard.truth_payload, intensity: parseFloat(e.target.value)}})}
                        />
                      </div>
                      <div className="space-y-2">
                        <label className="text-[10px] text-slate-500 uppercase">Bias Direction</label>
                        <select 
                          className="w-full bg-slate-950 border border-slate-800 rounded py-2 px-3 text-sm focus:border-cyan-500 outline-none"
                          value={editCard.truth_payload?.direction || 'STABLE'}
                          onChange={e => setEditCard({...editCard, truth_payload: {...editCard.truth_payload, direction: e.target.value}})}
                        >
                          <option value="UP">BULLISH (UP)</option>
                          <option value="DOWN">BEARISH (DOWN)</option>
                          <option value="STABLE">STABLE</option>
                        </select>
                      </div>
                    </div>
                  </div>
                </div>

                {/* 右列：逻辑 */}
                <div className="col-span-5 space-y-6">
                   <div className="bg-slate-900/50 border border-slate-800 p-6 rounded-lg space-y-6">
                    <h3 className="text-xs font-bold text-slate-400 border-b border-slate-800 pb-4 flex items-center gap-2">
                      <GitBranch size={14} /> SEQUENCING_LOGIC
                    </h3>
                    <div className="space-y-4">
                       <div className="space-y-2">
                        <label className="text-[10px] text-slate-500 uppercase">Success Probability (0.0 - 1.0)</label>
                        <div className="flex items-center gap-4">
                          <input 
                            type="range" min="0" max="1" step="0.1"
                            className="flex-1 accent-indigo-500 h-1 bg-slate-800 rounded-lg appearance-none cursor-pointer"
                            value={editCard.activation_prob || 0}
                            onChange={e => setEditCard({...editCard, activation_prob: parseFloat(e.target.value)})}
                          />
                          <span className="text-indigo-400 text-xs font-bold w-8">{Math.round((editCard.activation_prob || 0) * 100)}%</span>
                        </div>
                      </div>
                      
                      <div className="space-y-2">
                        <label className="text-[10px] text-slate-500 uppercase">Scheduled Release (T+N)</label>
                        <div className="relative">
                          <Clock size={14} className="absolute left-3 top-3 text-slate-700" />
                          <input 
                            type="datetime-local"
                            className="w-full bg-slate-950 border border-slate-800 rounded py-2 pl-10 pr-3 text-xs focus:border-indigo-500 outline-none"
                            value={editCard.scheduled_at?.slice(0, 16) || ''}
                            onChange={e => setEditCard({...editCard, scheduled_at: e.target.value})}
                          />
                        </div>
                      </div>

                      <div className="space-y-2">
                        <label className="text-[10px] text-slate-500 uppercase">Scenario Metadata</label>
                        <div className="text-[10px] bg-slate-950 border border-slate-800 rounded p-2 text-slate-500 italic">
                           Scenario ID: {editCard.scenario_id || 'STANDALONE_EVENT'}
                        </div>
                      </div>
                    </div>
                  </div>

                  <div className="bg-slate-900/50 border border-slate-800 p-6 rounded-lg space-y-4">
                    <div className="flex gap-2 p-3 bg-amber-500/5 border border-amber-500/20 rounded-md">
                       <AlertTriangle className="text-amber-500 shrink-0" size={16} />
                       <div className="text-[10px] text-amber-500/70 leading-relaxed">
                          DESIGNER_WARNING: Modifying logic nodes will affect all downstream triggers in this tree branch. Ensure consistency before committing.
                       </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* 变体与新闻链部分 */}
            {selectedCardId && !isCreating && (
              <section className="space-y-6">
                <div className="flex justify-between items-center">
                  <h3 className="text-xl font-bold text-cyan-400 flex items-center gap-2">
                    <Book size={22} /> 信号内容与变体 (Signal Text Variants)
                  </h3>
                </div>

                <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-xl">
                  <label className="block text-xs text-slate-400 mb-2 uppercase tracking-wider">编写新文本变体 (New Content)</label>
                  <textarea 
                    className="w-full bg-slate-800 border border-slate-700 rounded-md py-3 px-4 focus:outline-none focus:border-cyan-500 text-slate-200 min-h-[100px] text-sm leading-relaxed"
                    placeholder="在这里输入新闻文案，它是最终玩家看到的内容..."
                    id="new-variant-text"
                  />
                  <div className="flex justify-end mt-4">
                    <button 
                      onClick={() => {
                        const area = document.getElementById('new-variant-text') as HTMLTextAreaElement;
                        if (area && area.value) handleEmitVariant(area.value);
                      }}
                      className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 text-white px-6 py-2 rounded-md font-bold transition-all shadow-[0_0_15px_rgba(79,70,229,0.3)]"
                    >
                      <Plus size={18} /> 保存文本变体
                    </button>
                  </div>
                </div>

                <div className="space-y-4">
                  {variants.length === 0 ? (
                    <div className="p-8 border-2 border-dashed border-slate-800 rounded-xl text-center text-slate-600">
                      该节点目前为空壳（无文本）。请在上方为其编写具体的显示内容。
                    </div>
                  ) : (
                    variants.map((v, i) => (
                      <div key={v.variant_id} className="relative group">
                        <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-5 hover:border-cyan-500/50 transition-all flex gap-4 items-start group shadow-lg">
                          <div className="w-10 h-10 rounded-full bg-slate-800 flex items-center justify-center shrink-0">
                            <span className="text-cyan-400 font-bold">{variants.length - i}</span>
                          </div>
                          <div className="flex-1">
                            <div className="flex justify-between items-start mb-2">
                              <span className="text-[10px] font-mono text-slate-500">VAR_ID: {v.variant_id.split('-')[0]}...</span>
                            </div>
                            <p className="text-slate-200 text-sm leading-relaxed mb-4">{v.text}</p>
                          </div>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </section>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default NewsStudioPage;
