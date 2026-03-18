import { ApiClient } from './http'
import type {
  AccountValuationResponse,
  AccountLedgerResponse,
  AppPreferencesResponse,
  AppPreferencesUpdateRequest,
  ChatIntroFeeQuoteRequest,
  ChatIntroFeeQuoteResponse,
  ChatListMessagesResponse,
  ChatListThreadsResponse,
  ChatOpenPmRequest,
  ChatOpenPmResponse,
  ChatSendMessageRequest,
  ChatSendMessageResponse,
  ChatSendPmMessageRequest,
  ContractActivateRequest,
  ContractAgentContextResponse,
  ContractAgentAuditRequest,
  ContractAgentAuditResponse,
  ContractAgentDraftRequest,
  ContractAgentDraftResponse,
  ContractAgentAppendEditRequest,
  ContractBatchCreateRequest,
  ContractBatchCreateResponse,
  ContractCreateRequest,
  ContractCreateResponse,
  ContractJoinRequest,
  ContractProposalApproveRequest,
  ContractProposalApproveResponse,
  ContractProposalCreateRequest,
  ContractProposalCreateResponse,
  ContractRunRulesRequest,
  ContractSettleRequest,
  ContractSignRequest,
  ContractSignResponse,
  HealthResponse,
  HostingDebugTickResponse,
  HostingDisableResponse,
  HostingEnableResponse,
  HostingStatusResponse,
  LlmConnectionTestRequest,
  LlmConnectionTestResponse,
  LlmNetworkDiagnosticRequest,
  LlmNetworkDiagnosticResponse,
  LlmSettingsResponse,
  LlmSettingsUpdateRequest,
  MarketCandlesResponse,
  MyOpenOrdersListResponse,
  OrderBookResponse,
  PlayerCancelOrderRequest,
  MarketQuoteResponse,
  MarketSeriesResponse,
  MarketSummaryResponse,
  MarketSessionResponse,
  NewsBroadcastRequest,
  NewsBroadcastResponse,
  NewsChainStartRequest,
  NewsChainStartResponse,
  NewsCreateCardRequest,
  NewsCreateCardResponse,
  NewsEmitVariantRequest,
  NewsEmitVariantResponse,
  NewsFeedResponse,
  NewsInboxResponse,
  NewsMutateVariantRequest,
  NewsMutateVariantResponse,
  NewsOwnedCardsResponse,
  NewsOwnershipEventResponse,
  NewsOwnershipGrantRequest,
  NewsOwnershipTransferRequest,
  NewsPropagateRequest,
  NewsPropagateResponse,
  NewsPropagateQuoteRequest,
  NewsPropagateQuoteResponse,
  NewsStoreCatalogResponse,
  NewsStorePurchaseRequest,
  NewsStorePurchaseResponse,
  NewsSuppressRequest,
  NewsSuppressResponse,
  NewsTickRequest,
  NewsTickResponse,
  PlayerAccountResponse,
  ContractResponse,
  PlayerBootstrapRequest,
  PlayerBootstrapResponse,
  PlayerLimitOrderRequest,
  PlayerMarketOrderRequest,
  PlayerOrderResponse,
  SocialFollowRequest,
  WealthPublicRefreshResponse,
  WealthPublicResponse,
  DebugEmitEventRequest,
  DebugEmitEventResponse,
  PlayerListResponse,
  ContractListResponse,
} from './types'

const api = new ApiClient()
const bootstrapCache = new Map<string, { expiresAt: number; value: unknown }>()
const bootstrapInflight = new Map<string, Promise<unknown>>()

function getCached<T>(key: string): T | null {
  const hit = bootstrapCache.get(key)
  if (!hit) return null
  if (hit.expiresAt <= Date.now()) {
    bootstrapCache.delete(key)
    return null
  }
  return hit.value as T
}

function setCached<T>(key: string, value: T, ttlMs: number): T {
  bootstrapCache.set(key, { expiresAt: Date.now() + ttlMs, value })
  return value
}

async function getWithBootstrapCache<T>(key: string, ttlMs: number, loader: () => Promise<T>): Promise<T> {
  const cached = getCached<T>(key)
  if (cached !== null) return cached
  const inflight = bootstrapInflight.get(key)
  if (inflight) return inflight as Promise<T>
  const task = loader()
    .then((value) => setCached(key, value, ttlMs))
    .finally(() => {
      bootstrapInflight.delete(key)
    })
  bootstrapInflight.set(key, task as Promise<unknown>)
  return task
}

export const Api = {
  health: () => api.get<HealthResponse>('/health'),

  marketSymbols: () => getWithBootstrapCache<string[]>('marketSymbols', 8000, () => api.get<string[]>('/market/symbols')),

  marketQuote: (symbol: string) => getWithBootstrapCache<MarketQuoteResponse>(`marketQuote:${String(symbol).toUpperCase()}`, 6000, () => api.get<MarketQuoteResponse>(`/market/quote/${encodeURIComponent(symbol)}`)),
  marketSeries: (symbol: string, limit = 200) =>
    api.get<MarketSeriesResponse>(`/market/series/${encodeURIComponent(symbol)}`, { limit }),
  marketCandles: (symbol: string, interval_seconds = 60, limit = 200) =>
    api.get<MarketCandlesResponse>(`/market/candles/${encodeURIComponent(symbol)}`, {
      interval_seconds,
      limit,
    }),
  marketSession: () => getWithBootstrapCache<MarketSessionResponse>('marketSession', 8000, () => api.get<MarketSessionResponse>('/market/session')),
  marketSummary: () => getWithBootstrapCache<MarketSummaryResponse>('marketSummary', 8000, () => api.get<MarketSummaryResponse>('/market/summary')),

  listPlayers: (limit = 100) => api.get<PlayerListResponse>('/players', { limit }),
  listContracts: (actor_id?: string, limit = 50, status?: string) =>
    api.get<ContractListResponse>('/contracts/list', { actor_id, limit, status }),

  submitLimitOrder: (req: PlayerLimitOrderRequest) => api.post<PlayerOrderResponse>('/orders/limit', req),
  submitMarketOrder: async (req: PlayerMarketOrderRequest) => {
    await api.post<unknown>('/orders/market', req)
  },
  orderBook: (symbol: string, limit = 20) =>
    api.get<OrderBookResponse>(`/orders/book/${encodeURIComponent(symbol)}`, { limit }),
  myOpenOrders: (player_id: string, symbol?: string, limit = 50) =>
    api.get<MyOpenOrdersListResponse>(`/orders/open/${encodeURIComponent(player_id)}`, { symbol, limit }),
  cancelOrder: (order_id: string, req: PlayerCancelOrderRequest) =>
    api.post<void>(`/orders/${encodeURIComponent(order_id)}/cancel`, req),

  playersBootstrap: (req: PlayerBootstrapRequest) => api.post<PlayerBootstrapResponse>('/players/bootstrap', req),

  playerAccount: (player_id: string) => getWithBootstrapCache<PlayerAccountResponse>(`playerAccount:${String(player_id).toLowerCase()}`, 8000, () => api.get<PlayerAccountResponse>(`/players/${encodeURIComponent(player_id)}/account`)),
  accountValuation: (account_id: string, discount_factor = 1.0) =>
    getWithBootstrapCache<AccountValuationResponse>(`accountValuation:${String(account_id).toLowerCase()}:${discount_factor}`, 6000, () => api.get<AccountValuationResponse>(`/accounts/${encodeURIComponent(account_id)}/valuation`, { discount_factor })),

  accountLedger: (account_id: string, limit = 200, before?: string) =>
    api.get<AccountLedgerResponse>(`/accounts/${encodeURIComponent(account_id)}/ledger`, { limit, before }),

  chatIntroFeeQuote: (req: ChatIntroFeeQuoteRequest) =>
    api.post<ChatIntroFeeQuoteResponse>('/chat/intro-fee/quote', req),
  chatOpenPm: (req: ChatOpenPmRequest) => api.post<ChatOpenPmResponse>('/chat/pm/open', req),
  chatPublicSend: (req: ChatSendMessageRequest) => api.post<ChatSendMessageResponse>('/chat/public/send', req),
  chatPmSend: (req: ChatSendPmMessageRequest) => api.post<ChatSendMessageResponse>('/chat/pm/send', req),
  chatPublicMessages: (limit = 50, before?: string) => api.get<ChatListMessagesResponse>('/chat/public/messages', { limit, before }),
  chatPmMessages: (thread_id: string, limit = 50, before?: string) =>
    api.get<ChatListMessagesResponse>(`/chat/pm/${encodeURIComponent(thread_id)}/messages`, { limit, before }),
  chatThreads: (user_id: string, limit = 200) =>
    api.get<ChatListThreadsResponse>(`/chat/threads/${encodeURIComponent(user_id)}`, { limit }),

  wealthPublicRefresh: () => api.post<WealthPublicRefreshResponse>('/wealth/public/refresh'),
  wealthPublicGet: (user_id: string) => api.get<WealthPublicResponse>(`/wealth/public/${encodeURIComponent(user_id)}`),

  contractCreate: (req: ContractCreateRequest) => api.post<ContractCreateResponse>('/contracts/create', req),
  contractBatchCreate: (req: ContractBatchCreateRequest) => api.post<ContractBatchCreateResponse>('/contracts/batch_create', req),
  contractJoin: (contract_id: string, req: ContractJoinRequest) => api.post<void>(`/contracts/${encodeURIComponent(contract_id)}/join`, req),
  contractSign: (contract_id: string, req: ContractSignRequest) => api.post<ContractSignResponse>(`/contracts/${encodeURIComponent(contract_id)}/sign`, req),
  contractActivate: (contract_id: string, req: ContractActivateRequest) => api.post<void>(`/contracts/${encodeURIComponent(contract_id)}/activate`, req),
  contractSettle: (contract_id: string, req: ContractSettleRequest) => api.post<void>(`/contracts/${encodeURIComponent(contract_id)}/settle`, req),
  contractRunRules: (contract_id: string, req: ContractRunRulesRequest) => api.post<void>(`/contracts/${encodeURIComponent(contract_id)}/run_rules`, req),
  contractGet: (contract_id: string) => api.get<ContractResponse>(`/contracts/${encodeURIComponent(contract_id)}`),
  contractProposalCreate: (contract_id: string, req: ContractProposalCreateRequest) => api.post<ContractProposalCreateResponse>(`/contracts/${encodeURIComponent(contract_id)}/proposals/create`, req),
  contractProposalApprove: (contract_id: string, proposal_id: string, req: ContractProposalApproveRequest) => api.post<ContractProposalApproveResponse>(`/contracts/${encodeURIComponent(contract_id)}/proposals/${encodeURIComponent(proposal_id)}/approve`, req),

  contractAgentDraft: (req: ContractAgentDraftRequest) => api.post<ContractAgentDraftResponse>('/contract-agent/draft', req),
  contractAgentAppendEdit: (req: ContractAgentAppendEditRequest) => api.post<ContractAgentDraftResponse>('/contract-agent/append_edit', req),
  contractAgentAudit: (req: ContractAgentAuditRequest) => api.post<ContractAgentAuditResponse>('/contract-agent/audit', req),
  contractAgentGetContext: (actor_id: string) => api.get<ContractAgentContextResponse>(`/contract-agent/context/${encodeURIComponent(actor_id)}`),
  contractAgentClearContext: (actor_id: string) => api.post<void>(`/contract-agent/context/${encodeURIComponent(actor_id)}/clear`),

  socialFollow: async (req: SocialFollowRequest) => {
    await api.post<unknown>('/social/follow', req)
  },

  newsCreateCard: (req: NewsCreateCardRequest) => api.post<NewsCreateCardResponse>('/news/cards', req),
  newsEmitVariant: (req: NewsEmitVariantRequest) => api.post<NewsEmitVariantResponse>('/news/variants/emit', req),
  newsMutateVariant: (req: NewsMutateVariantRequest) => api.post<NewsMutateVariantResponse>('/news/variants/mutate', req),
  newsPropagate: (req: NewsPropagateRequest) => api.post<NewsPropagateResponse>('/news/propagate', req),
  newsPropagateQuote: (req: NewsPropagateQuoteRequest) =>
    api.post<NewsPropagateQuoteResponse>('/news/propagate/quote', req),
  newsInbox: (player_id: string, limit = 50) => api.get<NewsInboxResponse>(`/news/inbox/${encodeURIComponent(player_id)}`, { limit }),
  newsPublicFeed: (limit = 20) => api.get<NewsFeedResponse>('/news/public/feed', { limit }),
  newsBroadcast: (req: NewsBroadcastRequest) => api.post<NewsBroadcastResponse>('/news/broadcast', req),
  newsChainStart: (req: NewsChainStartRequest) => api.post<NewsChainStartResponse>('/news/chains/start', req),
  newsTick: (req: NewsTickRequest) => api.post<NewsTickResponse>('/news/tick', req),
  newsSuppress: (req: NewsSuppressRequest) => api.post<NewsSuppressResponse>('/news/suppress', req),
  newsOwnershipGrant: (req: NewsOwnershipGrantRequest) => api.post<NewsOwnershipEventResponse>('/news/ownership/grant', req),
  newsOwnershipTransfer: (req: NewsOwnershipTransferRequest) => api.post<NewsOwnershipEventResponse>('/news/ownership/transfer', req),
  newsOwnershipList: (user_id: string, limit = 200) =>
    api.get<NewsOwnedCardsResponse>(`/news/ownership/${encodeURIComponent(user_id)}`, { limit }),
  newsStoreCatalog: () => api.get<NewsStoreCatalogResponse>('/news/store/catalog'),
  newsStorePurchase: (req: NewsStorePurchaseRequest) => api.post<NewsStorePurchaseResponse>('/news/store/purchase', req),

  hostingEnable: (user_id: string) => api.post<HostingEnableResponse>(`/hosting/${encodeURIComponent(user_id)}/enable`),
  hostingDisable: (user_id: string) => api.post<HostingDisableResponse>(`/hosting/${encodeURIComponent(user_id)}/disable`),
  hostingStatus: (user_id: string) => api.get<HostingStatusResponse>(`/hosting/${encodeURIComponent(user_id)}/status`),
  hostingDebugTickOnce: () => api.post<HostingDebugTickResponse>('/hosting/debug/tick_once'),

  settingsGetPreferences: (actor_id: string) => api.get<AppPreferencesResponse>(`/settings/preferences/${encodeURIComponent(actor_id)}`),
  settingsSavePreferences: (req: AppPreferencesUpdateRequest) => api.post<AppPreferencesResponse>('/settings/preferences', req),
  settingsGetLlm: (actor_id: string) => api.get<LlmSettingsResponse>(`/settings/llm/${encodeURIComponent(actor_id)}`),
  settingsSaveLlm: (req: LlmSettingsUpdateRequest) => api.post<LlmSettingsResponse>('/settings/llm', req),
  settingsTestLlm: (req: LlmConnectionTestRequest) => api.post<LlmConnectionTestResponse>('/settings/llm/test', req),
  settingsLlmDiagnostics: (req: LlmNetworkDiagnosticRequest) => api.post<LlmNetworkDiagnosticResponse>('/settings/llm/diagnostics', req),

  debugEmitEvent: (req: DebugEmitEventRequest) => api.post<DebugEmitEventResponse>('/debug/emit_event', req),

  bootstrapPrefetch: async (playerId: string, symbol?: string) => {
    const pid = String(playerId || '').trim()
    if (!pid) return
    const accountId = `user:${pid}`
    const symbols = await Api.marketSymbols().catch(() => [] as string[])
    const preferredSymbol = String(symbol || '').trim().toUpperCase()
    const targets = [preferredSymbol, ...symbols].filter((v, idx, arr) => !!v && arr.indexOf(v) === idx).slice(0, 6)
    await Promise.allSettled([
      Api.playerAccount(pid),
      Api.accountValuation(accountId, 1.0),
      Api.marketSession(),
      Api.marketSummary(),
      ...targets.map((s) => Api.marketQuote(s)),
    ])
  },
}

export { ApiClient }
export * from './http'
export * from './types'
export * from './ws'
