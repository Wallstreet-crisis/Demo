import { useEffect, useMemo, useState } from 'react'
import { Api, ApiError, type LlmSettingsResponse } from '../api'

type Props = {
  actorId: string
  open: boolean
  onClose: () => void
}

const panelStyle: React.CSSProperties = {
  width: 'min(720px, calc(100vw - 40px))',
  maxHeight: 'calc(100vh - 80px)',
  overflowY: 'auto',
  background: '#09111f',
  border: '1px solid var(--terminal-border)',
  boxShadow: '0 20px 80px rgba(0, 0, 0, 0.55)',
  padding: '18px',
}

const sectionStyle: React.CSSProperties = {
  border: '1px solid rgba(148,163,184,0.18)',
  padding: '14px',
  marginTop: '12px',
  background: 'rgba(15, 23, 42, 0.55)',
}

const inputStyle: React.CSSProperties = {
  width: '100%',
  maxWidth: '100%',
  boxSizing: 'border-box',
  background: '#020617',
  color: '#e2e8f0',
  border: '1px solid var(--terminal-border)',
  padding: '8px 10px',
  marginTop: '6px',
}

const defaultBaseUrls: Record<string, string> = {
  openrouter: 'https://openrouter.ai/api/v1',
  deepseek: 'https://api.deepseek.com/v1',
  minimax: 'https://api.minimax.chat/v1',
  kimi: 'https://api.moonshot.cn/v1',
  openai: 'https://api.openai.com/v1',
  anthropic: 'https://api.anthropic.com/v1',
  google: 'https://generativelanguage.googleapis.com/v1beta/openai',
  xai: 'https://api.x.ai/v1',
}

const recommendedModels: Record<string, { light: string; standard: string; heavy: string }> = {
  openrouter: {
    light: 'google/gemini-2.0-flash-001',
    standard: 'google/gemini-2.0-flash-001',
    heavy: 'deepseek/deepseek-chat-v3-0324',
  },
  deepseek: {
    light: 'deepseek-chat',
    standard: 'deepseek-chat',
    heavy: 'deepseek-reasoner',
  },
  minimax: {
    light: 'MiniMax-Text-01',
    standard: 'MiniMax-Text-01',
    heavy: 'MiniMax-M1',
  },
  kimi: {
    light: 'moonshot-v1-8k',
    standard: 'moonshot-v1-32k',
    heavy: 'moonshot-v1-128k',
  },
  openai: {
    light: 'gpt-4.1-mini',
    standard: 'gpt-4.1',
    heavy: 'o3-mini',
  },
  anthropic: {
    light: 'claude-3-5-haiku-latest',
    standard: 'claude-3-7-sonnet-latest',
    heavy: 'claude-3-7-sonnet-latest',
  },
  google: {
    light: 'gemini-2.0-flash',
    standard: 'gemini-2.5-flash',
    heavy: 'gemini-2.5-pro',
  },
  xai: {
    light: 'grok-2-latest',
    standard: 'grok-2-latest',
    heavy: 'grok-3-beta',
  },
}

export default function SettingsModal({ actorId, open, onClose }: Props) {
  const [llm, setLlm] = useState<LlmSettingsResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [savingPrefs, setSavingPrefs] = useState(false)
  const [savingLlm, setSavingLlm] = useState(false)
  const [testingLlm, setTestingLlm] = useState(false)
  const [diagnosingLlm, setDiagnosingLlm] = useState(false)
  const [message, setMessage] = useState<string>('')
  const [llmTestMessage, setLlmTestMessage] = useState<string>('')
  const [llmDiagnostics, setLlmDiagnostics] = useState<Array<{ provider: string; base_url: string; ok: boolean; latency_ms: number; message: string; model_count: number; first_model?: string | null }>>([])

  const [language, setLanguage] = useState('zh-CN')
  const [riseColor, setRiseColor] = useState('red_up')
  const [priceColorScheme, setPriceColorScheme] = useState('cn_red_up')
  const [compactQuotes, setCompactQuotes] = useState(false)
  const [showPhaseBadge, setShowPhaseBadge] = useState(true)

  const [providerApiKeys, setProviderApiKeys] = useState<Record<string, string>>({})
  const [lightProvider, setLightProvider] = useState('openrouter')
  const [lightModel, setLightModel] = useState('google/gemini-2.0-flash-001')
  const [lightTimeout, setLightTimeout] = useState('12')
  const [standardProvider, setStandardProvider] = useState('openrouter')
  const [standardModel, setStandardModel] = useState('google/gemini-2.0-flash-001')
  const [standardTimeout, setStandardTimeout] = useState('20')
  const [heavyProvider, setHeavyProvider] = useState('openrouter')
  const [heavyModel, setHeavyModel] = useState('deepseek/deepseek-chat-v3-0324')
  const [heavyTimeout, setHeavyTimeout] = useState('35')
  const [commonbotRoute, setCommonbotRoute] = useState('light')
  const [hostingRoute, setHostingRoute] = useState('standard')
  const [auditRoute, setAuditRoute] = useState('standard')
  const [draftRoute, setDraftRoute] = useState('heavy')
  const [defaultRoute, setDefaultRoute] = useState('standard')

  useEffect(() => {
    if (!open || !actorId) return
    let cancelled = false
    const load = async () => {
      setLoading(true)
      setMessage('')
      setLlmTestMessage('')
      setLlmDiagnostics([])
      try {
        const [prefResult, llmResult] = await Promise.allSettled([
          Api.settingsGetPreferences(actorId),
          Api.settingsGetLlm(actorId),
        ])
        if (cancelled) return
        const errors: string[] = []

        if (prefResult.status === 'fulfilled') {
          const prefRes = prefResult.value
          setLanguage(prefRes.language)
          setRiseColor(prefRes.rise_color)
          setPriceColorScheme(prefRes.display?.price_color_scheme ?? 'cn_red_up')
          setCompactQuotes(Boolean(prefRes.display?.compact_quotes))
          setShowPhaseBadge(Boolean(prefRes.display?.show_market_phase_badge))
        } else {
          const err = prefResult.reason
          const msg = err instanceof ApiError ? err.message : (err instanceof Error ? err.message : String(err))
          errors.push(`通用设置加载失败：${msg}`)
        }

        if (llmResult.status === 'fulfilled') {
          const llmRes = llmResult.value
          setLlm(llmRes)
          setLightProvider(llmRes.profiles?.light?.provider ?? llmRes.provider ?? 'openrouter')
          setLightModel(llmRes.profiles?.light?.model ?? 'google/gemini-2.0-flash-001')
          setLightTimeout(String(llmRes.profiles?.light?.timeout_seconds ?? 12))
          setStandardProvider(llmRes.profiles?.standard?.provider ?? llmRes.provider ?? 'openrouter')
          setStandardModel(llmRes.profiles?.standard?.model ?? 'google/gemini-2.0-flash-001')
          setStandardTimeout(String(llmRes.profiles?.standard?.timeout_seconds ?? 20))
          setHeavyProvider(llmRes.profiles?.heavy?.provider ?? llmRes.provider ?? 'openrouter')
          setHeavyModel(llmRes.profiles?.heavy?.model ?? 'deepseek/deepseek-chat-v3-0324')
          setHeavyTimeout(String(llmRes.profiles?.heavy?.timeout_seconds ?? 35))
          setCommonbotRoute(llmRes.routing?.commonbot_news ?? 'light')
          setHostingRoute(llmRes.routing?.hosting_agent ?? 'standard')
          setAuditRoute(llmRes.routing?.contract_audit ?? 'standard')
          setDraftRoute(llmRes.routing?.contract_draft ?? 'heavy')
          setDefaultRoute(llmRes.routing?.default ?? 'standard')
          setProviderApiKeys({})
        } else {
          const err = llmResult.reason
          const msg = err instanceof ApiError ? err.message : (err instanceof Error ? err.message : String(err))
          errors.push(`LLM 设置加载失败：${msg}`)
          setLlm({
            actor_id: actorId,
            can_manage: false,
            provider: 'openrouter',
            model: 'google/gemini-2.5-flash',
            base_url: 'https://openrouter.ai/api/v1',
            timeout_seconds: 20,
            profiles: {
              light: { provider: 'openrouter', model: 'google/gemini-2.0-flash-001', base_url: 'https://openrouter.ai/api/v1', timeout_seconds: 12 },
              standard: { provider: 'openrouter', model: 'google/gemini-2.0-flash-001', base_url: 'https://openrouter.ai/api/v1', timeout_seconds: 20 },
              heavy: { provider: 'openrouter', model: 'deepseek/deepseek-chat-v3-0324', base_url: 'https://openrouter.ai/api/v1', timeout_seconds: 35 },
            },
            routing: {
              commonbot_news: 'light',
              hosting_agent: 'standard',
              contract_audit: 'standard',
              contract_draft: 'heavy',
              default: 'standard',
            },
            providers_supported: ['openrouter', 'deepseek', 'minimax', 'kimi', 'openai', 'anthropic', 'google', 'xai'],
            provider_api_key_masks: {},
            has_api_key: false,
            api_key_masked: null,
          })
          setDefaultRoute('standard')
          setProviderApiKeys({})
        }

        if (errors.length > 0) {
          setMessage(errors.join('；'))
        }
      } catch (e) {
        const msg = e instanceof ApiError ? e.message : (e instanceof Error ? e.message : String(e))
        if (!cancelled) setMessage(`加载设置失败：${msg}`)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [actorId, open])

  const llmHint = useMemo(() => {
    if (!llm) return ''
    if (!llm.can_manage) return '当前身份不可配置房间级 LLM。普通玩家默认不显示此能力。'
    const configured = Object.entries(llm.provider_api_key_masks ?? {}).filter(([, v]) => Boolean(v))
    if (configured.length > 0) return `已配置 ${configured.length} 个提供商密钥，可供不同方案复用。`
    return '尚未配置密钥。请先在“供应商密钥管理”中录入各厂商 Key，再将任务路由到对应方案。'
  }, [llm])

  const supportedProviders = llm?.providers_supported?.length ? llm.providers_supported : ['openrouter', 'deepseek', 'minimax', 'kimi', 'openai', 'anthropic', 'google', 'xai']

  const effectiveProviderApiPlaceholder = (name: string) => llm?.provider_api_key_masks?.[name] ?? ''

  const getRecommendedModel = (provider: string, slot: string) => {
    const providerTemplates = recommendedModels[provider] ?? recommendedModels.openrouter
    if (slot === 'light') return providerTemplates.light
    if (slot === 'heavy') return providerTemplates.heavy
    return providerTemplates.standard
  }

  const updateProfileProvider = (slot: string, nextProvider: string) => {
    const recommended = getRecommendedModel(nextProvider, slot)
    if (slot === 'light') {
      setLightProvider(nextProvider)
      setLightModel(recommended)
      return
    }
    if (slot === 'heavy') {
      setHeavyProvider(nextProvider)
      setHeavyModel(recommended)
      return
    }
    setStandardProvider(nextProvider)
    setStandardModel(recommended)
  }

  const applyRecommendedModel = (slot: string) => {
    if (slot === 'light') {
      setLightModel(getRecommendedModel(lightProvider, slot))
      return
    }
    if (slot === 'heavy') {
      setHeavyModel(getRecommendedModel(heavyProvider, slot))
      return
    }
    setStandardModel(getRecommendedModel(standardProvider, slot))
  }

  const profileOptions = [
    { key: 'light', label: '轻量方案', provider: lightProvider, model: lightModel, timeout: lightTimeout, setModel: setLightModel, setTimeout: setLightTimeout },
    { key: 'standard', label: '标准方案', provider: standardProvider, model: standardModel, timeout: standardTimeout, setModel: setStandardModel, setTimeout: setStandardTimeout },
    { key: 'heavy', label: '重度方案', provider: heavyProvider, model: heavyModel, timeout: heavyTimeout, setModel: setHeavyModel, setTimeout: setHeavyTimeout },
  ]

  const getProfileConfig = (slot: string) => {
    if (slot === 'light') return { provider: lightProvider, model: lightModel, base_url: defaultBaseUrls[lightProvider] ?? 'https://openrouter.ai/api/v1', timeout_seconds: Number(lightTimeout || '12') }
    if (slot === 'heavy') return { provider: heavyProvider, model: heavyModel, base_url: defaultBaseUrls[heavyProvider] ?? 'https://openrouter.ai/api/v1', timeout_seconds: Number(heavyTimeout || '35') }
    return { provider: standardProvider, model: standardModel, base_url: defaultBaseUrls[standardProvider] ?? 'https://openrouter.ai/api/v1', timeout_seconds: Number(standardTimeout || '20') }
  }

  const collectProviderApiKeys = () => {
    const merged: Record<string, string> = {}
    for (const item of supportedProviders) {
      const value = String(providerApiKeys[item] ?? '').trim()
      if (value) merged[item] = value
    }
    return merged
  }

  if (!open) return null

  const savePreferences = async () => {
    setSavingPrefs(true)
    setMessage('')
    try {
      await Api.settingsSavePreferences({
        actor_id: actorId,
        language,
        rise_color: riseColor,
        display: {
          price_color_scheme: priceColorScheme,
          compact_quotes: compactQuotes,
          show_market_phase_badge: showPhaseBadge,
        },
      })
      setMessage('通用设置已保存')
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : (e instanceof Error ? e.message : String(e))
      setMessage(`保存通用设置失败：${msg}`)
    } finally {
      setSavingPrefs(false)
    }
  }

  const diagnoseLlm = async () => {
    if (!llm?.can_manage) return
    setDiagnosingLlm(true)
    setLlmTestMessage('')
    try {
      const res = await Api.settingsLlmDiagnostics({
        actor_id: actorId,
        providers: supportedProviders,
        api_keys: Object.keys(collectProviderApiKeys()).length > 0 ? collectProviderApiKeys() : undefined,
        timeout_seconds: 12,
      })
      setLlmDiagnostics(res.items)
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : (e instanceof Error ? e.message : String(e))
      setLlmTestMessage(`网络诊断失败：${msg}`)
    } finally {
      setDiagnosingLlm(false)
    }
  }

  const saveLlm = async () => {
    if (!llm?.can_manage) return
    setSavingLlm(true)
    setMessage('')
    try {
      const defaultCfg = getProfileConfig(defaultRoute)
      const saved = await Api.settingsSaveLlm({
        actor_id: actorId,
        provider: defaultCfg.provider,
        model: defaultCfg.model,
        base_url: defaultCfg.base_url,
        timeout_seconds: defaultCfg.timeout_seconds,
        profiles: {
          light: { provider: lightProvider, model: lightModel, base_url: defaultBaseUrls[lightProvider] ?? 'https://openrouter.ai/api/v1', timeout_seconds: Number(lightTimeout || '12') },
          standard: { provider: standardProvider, model: standardModel, base_url: defaultBaseUrls[standardProvider] ?? 'https://openrouter.ai/api/v1', timeout_seconds: Number(standardTimeout || '20') },
          heavy: { provider: heavyProvider, model: heavyModel, base_url: defaultBaseUrls[heavyProvider] ?? 'https://openrouter.ai/api/v1', timeout_seconds: Number(heavyTimeout || '35') },
        },
        routing: {
          commonbot_news: commonbotRoute,
          hosting_agent: hostingRoute,
          contract_audit: auditRoute,
          contract_draft: draftRoute,
          default: defaultRoute,
        },
        api_keys: Object.keys(collectProviderApiKeys()).length > 0 ? collectProviderApiKeys() : undefined,
      })
      setLlm(saved)
      setProviderApiKeys({})
      setMessage('LLM 设置已安全保存')
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : (e instanceof Error ? e.message : String(e))
      setMessage(`保存 LLM 设置失败：${msg}`)
    } finally {
      setSavingLlm(false)
    }
  }

  const testLlm = async () => {
    if (!llm?.can_manage) return
    setTestingLlm(true)
    setLlmTestMessage('')
    try {
      const defaultCfg = getProfileConfig(defaultRoute)
      const reqKeys = collectProviderApiKeys()
      const res = await Api.settingsTestLlm({
        actor_id: actorId,
        provider: defaultCfg.provider,
        model: defaultCfg.model,
        base_url: defaultCfg.base_url,
        timeout_seconds: defaultCfg.timeout_seconds,
        api_key: reqKeys[defaultCfg.provider] || undefined,
      })
      if (res.ok) {
        const suffix = res.first_model ? `，示例模型：${res.first_model}` : ''
        setLlmTestMessage(`默认方案连接成功，可访问 ${res.model_count} 个模型${suffix}`)
      } else {
        setLlmTestMessage(`连接失败：${res.message}`)
      }
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : (e instanceof Error ? e.message : String(e))
      setLlmTestMessage(`连接失败：${msg}`)
    } finally {
      setTestingLlm(false)
    }
  }

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(2, 6, 23, 0.75)', zIndex: 2000, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '20px' }}>
      <div style={panelStyle}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
          <div>
            <div style={{ fontSize: '18px', color: '#fff', fontWeight: 700 }}>设置中心</div>
            <div style={{ fontSize: '12px', color: '#94a3b8', marginTop: '4px' }}>预留语言、显示风格与房间级大模型配置能力</div>
          </div>
          <button className="cyber-button" onClick={onClose}>关闭</button>
        </div>

        {message && <div style={{ marginTop: '8px', color: '#38bdf8', fontSize: '12px' }}>{message}</div>}
        {loading && <div style={{ marginTop: '12px', color: '#94a3b8' }}>加载中...</div>}

        {!loading && (
          <>
            <div style={sectionStyle}>
              <div style={{ color: '#fff', fontWeight: 600 }}>通用设置</div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginTop: '12px' }}>
                <label>
                  <div style={{ fontSize: '12px', color: '#94a3b8' }}>语言</div>
                  <select value={language} onChange={(e) => setLanguage(e.target.value)} style={inputStyle}>
                    <option value="zh-CN">简体中文</option>
                    <option value="en-US">English</option>
                  </select>
                </label>
                <label>
                  <div style={{ fontSize: '12px', color: '#94a3b8' }}>涨跌文化预设</div>
                  <select value={riseColor} onChange={(e) => setRiseColor(e.target.value)} style={inputStyle}>
                    <option value="red_up">红涨绿跌</option>
                    <option value="green_up">绿涨红跌</option>
                  </select>
                </label>
                <label>
                  <div style={{ fontSize: '12px', color: '#94a3b8' }}>价格颜色方案</div>
                  <select value={priceColorScheme} onChange={(e) => setPriceColorScheme(e.target.value)} style={inputStyle}>
                    <option value="cn_red_up">CN / 红涨绿跌</option>
                    <option value="intl_green_up">INTL / 绿涨红跌</option>
                    <option value="mono">单色模式</option>
                  </select>
                </label>
                <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'flex-end', gap: '8px' }}>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '12px', color: '#cbd5e1' }}>
                    <input type="checkbox" checked={compactQuotes} onChange={(e) => setCompactQuotes(e.target.checked)} />
                    紧凑报价显示
                  </label>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '12px', color: '#cbd5e1' }}>
                    <input type="checkbox" checked={showPhaseBadge} onChange={(e) => setShowPhaseBadge(e.target.checked)} />
                    显示市场状态徽标
                  </label>
                </div>
              </div>
              <div style={{ marginTop: '14px' }}>
                <button className="cyber-button" disabled={savingPrefs} onClick={savePreferences}>{savingPrefs ? '保存中...' : '保存通用设置'}</button>
              </div>
            </div>

            <div style={sectionStyle}>
              <div style={{ color: '#fff', fontWeight: 600 }}>房间级大模型配置</div>
              <div style={{ fontSize: '12px', color: '#94a3b8', marginTop: '6px' }}>{llmHint}</div>

              {llm?.can_manage ? (
                <>
                  <div style={{ marginTop: '16px', color: '#e2e8f0', fontWeight: 600, fontSize: '13px' }}>供应商密钥管理</div>
                  <div style={{ fontSize: '12px', color: '#94a3b8', marginTop: '6px' }}>如果模型分层混用了多个 provider，请在这里分别填写对应 Key。留空表示保持后端已保存值不变。</div>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginTop: '12px' }}>
                    {supportedProviders.map((item) => (
                      <label key={`api-key-${item}`}>
                        <div style={{ fontSize: '12px', color: '#94a3b8' }}>{item} API Key</div>
                        <input
                          type="password"
                          value={providerApiKeys[item] ?? ''}
                          onChange={(e) => setProviderApiKeys((prev) => ({ ...prev, [item]: e.target.value }))}
                          placeholder={effectiveProviderApiPlaceholder(item) || '输入新密钥以更新'}
                          style={inputStyle}
                        />
                      </label>
                    ))}
                  </div>
                  <div style={{ marginTop: '16px', color: '#e2e8f0', fontWeight: 600, fontSize: '13px' }}>配置方案</div>
                  <div style={{ fontSize: '12px', color: '#94a3b8', marginTop: '6px' }}>每个方案是一套完整的大模型配置，任务只关心“用哪个方案”，不直接绑定某个 API Key。</div>
                  <div style={{ display: 'grid', gap: '12px', marginTop: '12px' }}>
                    {profileOptions.map((item) => (
                      <div key={item.key} style={{ border: '1px solid rgba(148,163,184,0.18)', padding: '12px', background: 'rgba(2, 6, 23, 0.35)', minWidth: 0, overflow: 'hidden' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '12px' }}>
                          <div style={{ color: '#e2e8f0', fontWeight: 600 }}>{item.label}</div>
                          <div style={{ fontSize: '12px', color: defaultRoute === item.key ? '#22c55e' : '#94a3b8' }}>{defaultRoute === item.key ? '当前默认方案' : '可用于任务路由'}</div>
                        </div>
                        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 220px) minmax(0, 140px) minmax(0, 1fr)', gap: '12px', marginTop: '12px', alignItems: 'end', minWidth: 0 }}>
                          <label style={{ minWidth: 0 }}>
                            <div style={{ fontSize: '12px', color: '#94a3b8' }}>提供商</div>
                            <select value={item.provider} onChange={(e) => updateProfileProvider(item.key, e.target.value)} style={inputStyle}>
                              {supportedProviders.map((providerItem) => (
                                <option key={`${item.key}-${providerItem}`} value={providerItem}>{providerItem}</option>
                              ))}
                            </select>
                          </label>
                          <label style={{ minWidth: 0 }}>
                            <div style={{ fontSize: '12px', color: '#94a3b8' }}>超时</div>
                            <input value={item.timeout} onChange={(e) => item.setTimeout(e.target.value)} style={inputStyle} />
                          </label>
                          <div style={{ display: 'flex', justifyContent: 'flex-end', alignItems: 'center', gap: '10px', flexWrap: 'wrap', minWidth: 0 }}>
                            <div style={{ fontSize: '12px', color: '#94a3b8', minWidth: 0, overflowWrap: 'anywhere' }}>推荐：`{getRecommendedModel(item.provider, item.key)}`</div>
                            <button className="cyber-button" onClick={() => applyRecommendedModel(item.key)} style={{ marginTop: '6px', flexShrink: 0 }}>套用推荐模型</button>
                          </div>
                        </div>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: '12px', marginTop: '12px', minWidth: 0 }}>
                          <label style={{ minWidth: 0 }}>
                            <div style={{ fontSize: '12px', color: '#94a3b8' }}>模型</div>
                            <input value={item.model} onChange={(e) => item.setModel(e.target.value)} style={inputStyle} />
                          </label>
                          <div style={{ minWidth: 0 }}>
                            <div style={{ fontSize: '12px', color: '#94a3b8' }}>Base URL</div>
                            <div style={{ ...inputStyle, display: 'flex', alignItems: 'center', color: '#cbd5e1', wordBreak: 'break-all' }}>{defaultBaseUrls[item.provider] ?? 'https://openrouter.ai/api/v1'}</div>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                  <div style={{ marginTop: '16px', color: '#e2e8f0', fontWeight: 600, fontSize: '13px' }}>任务路由</div>
                  <div style={{ fontSize: '12px', color: '#94a3b8', marginTop: '6px' }}>每个任务只选择方案名；默认方案用于通用测试与兜底调用。</div>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginTop: '12px' }}>
                    <label>
                      <div style={{ fontSize: '12px', color: '#94a3b8' }}>默认方案</div>
                      <select value={defaultRoute} onChange={(e) => setDefaultRoute(e.target.value)} style={inputStyle}>
                        <option value="light">light</option>
                        <option value="standard">standard</option>
                        <option value="heavy">heavy</option>
                      </select>
                    </label>
                    <div />
                    <label>
                      <div style={{ fontSize: '12px', color: '#94a3b8' }}>CommonBot 新闻</div>
                      <select value={commonbotRoute} onChange={(e) => setCommonbotRoute(e.target.value)} style={inputStyle}>
                        <option value="light">light</option>
                        <option value="standard">standard</option>
                        <option value="heavy">heavy</option>
                      </select>
                    </label>
                    <label>
                      <div style={{ fontSize: '12px', color: '#94a3b8' }}>托管代理</div>
                      <select value={hostingRoute} onChange={(e) => setHostingRoute(e.target.value)} style={inputStyle}>
                        <option value="light">light</option>
                        <option value="standard">standard</option>
                        <option value="heavy">heavy</option>
                      </select>
                    </label>
                    <label>
                      <div style={{ fontSize: '12px', color: '#94a3b8' }}>合同审计</div>
                      <select value={auditRoute} onChange={(e) => setAuditRoute(e.target.value)} style={inputStyle}>
                        <option value="light">light</option>
                        <option value="standard">standard</option>
                        <option value="heavy">heavy</option>
                      </select>
                    </label>
                    <label>
                      <div style={{ fontSize: '12px', color: '#94a3b8' }}>合同草拟</div>
                      <select value={draftRoute} onChange={(e) => setDraftRoute(e.target.value)} style={inputStyle}>
                        <option value="light">light</option>
                        <option value="standard">standard</option>
                        <option value="heavy">heavy</option>
                      </select>
                    </label>
                  </div>
                  {llmTestMessage && (
                    <div style={{ marginTop: '12px', fontSize: '12px', color: llmTestMessage.startsWith('连接成功') ? '#22c55e' : '#f59e0b' }}>
                      {llmTestMessage}
                    </div>
                  )}
                  {llmDiagnostics.length > 0 && (
                    <div style={{ marginTop: '12px', display: 'grid', gap: '8px' }}>
                      {llmDiagnostics.map((item) => (
                        <div key={`${item.provider}-${item.base_url}`} style={{ border: '1px solid rgba(148,163,184,0.18)', padding: '10px', background: 'rgba(2, 6, 23, 0.45)' }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', fontSize: '12px' }}>
                            <span style={{ color: '#e2e8f0', fontWeight: 600 }}>{item.provider}</span>
                            <span style={{ color: item.ok ? '#22c55e' : '#f59e0b' }}>{item.ok ? 'reachable' : 'failed'}</span>
                          </div>
                          <div style={{ marginTop: '4px', fontSize: '12px', color: '#94a3b8' }}>{item.base_url}</div>
                          <div style={{ marginTop: '4px', fontSize: '12px', color: '#cbd5e1' }}>耗时：{item.latency_ms.toFixed(0)} ms</div>
                          <div style={{ marginTop: '4px', fontSize: '12px', color: '#cbd5e1' }}>结果：{item.message}</div>
                          {item.ok && (
                            <div style={{ marginTop: '4px', fontSize: '12px', color: '#cbd5e1' }}>模型数：{item.model_count}{item.first_model ? `，示例：${item.first_model}` : ''}</div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                  <div style={{ marginTop: '14px' }}>
                    <button className="cyber-button" disabled={savingLlm} onClick={saveLlm}>{savingLlm ? '保存中...' : '安全保存 LLM 设置'}</button>
                    <button className="cyber-button" disabled={testingLlm} onClick={testLlm} style={{ marginLeft: '10px' }}>{testingLlm ? '测试中...' : '测试连接'}</button>
                    <button className="cyber-button" disabled={diagnosingLlm} onClick={diagnoseLlm} style={{ marginLeft: '10px' }}>{diagnosingLlm ? '诊断中...' : '官方 API 网络诊断'}</button>
                  </div>
                </>
              ) : (
                <div style={{ marginTop: '10px', color: '#64748b', fontSize: '12px' }}>当前用户不是房主/管理员时，不显示敏感配置入口。</div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  )
}
