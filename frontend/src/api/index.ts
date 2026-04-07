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
  RoomJoinRequest,
  RoomJoinResponse,
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

export type CreateRoomRequest = {
  room_id?: string
  player_id: string
  name?: string
}

export type CreateRoomResponse = {
  ok: boolean
  room_id: string
}

export type RoomMeta = {
  room_id: string
  name: string
  player_id: string
  created_at: string
  updated_at: string
}

export type LocalRoomsResponse = {
  rooms: RoomMeta[]
}

const api = new ApiClient()
const bootstrapCache = new Map<string, { expiresAt: number; value: unknown }>()
const bootstrapInflight = new Map<string, Promise<unknown>>()
const roomRequest = { includeRoomId: true } as const

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

function getRuntimeScopeKey(): string {
  const roomId = localStorage.getItem('if_room_id') || 'default'
  const networkTarget = localStorage.getItem('if_network_target') || 'local'
  return `${networkTarget}::${roomId}`
}

function scopedKey(key: string): string {
  return `${getRuntimeScopeKey()}::${key}`
}

async function getWithBootstrapCache<T>(key: string, ttlMs: number, loader: () => Promise<T>): Promise<T> {
  const resolvedKey = scopedKey(key)
  const cached = getCached<T>(resolvedKey)
  if (cached !== null) return cached
  const inflight = bootstrapInflight.get(resolvedKey)
  if (inflight) return inflight as Promise<T>
  const task = loader()
    .then((value) => setCached(resolvedKey, value, ttlMs))
    .finally(() => {
      bootstrapInflight.delete(resolvedKey)
    })
  bootstrapInflight.set(resolvedKey, task as Promise<unknown>)
  return task
}

export const Api = {
  health: () => api.get<HealthResponse>('/health'),

  roomJoin: (req: RoomJoinRequest) => api.post<RoomJoinResponse>('/rooms/join', req, roomRequest),
  createRoom: (req: CreateRoomRequest) => api.post<CreateRoomResponse>('/rooms', req, roomRequest),
  activateRoom: (roomId: string) => api.post<{ok: boolean, room_id: string}>(`/rooms/${encodeURIComponent(roomId)}/activate`, undefined, roomRequest),
  closeRoom: (roomId: string) => api.post<void>(`/rooms/${encodeURIComponent(roomId)}/close`, undefined, roomRequest),
  deleteRoom: (roomId: string) => api.delete<{ok: boolean}>(`/rooms/${encodeURIComponent(roomId)}`, roomRequest),
  listLocalRooms: () => api.get<LocalRoomsResponse>('/rooms/local', undefined, roomRequest),
  networkJoinCheck: () => api.get<LocalRoomsResponse>('/rooms/network_join'),
  updateRoomMeta: (roomId: string, name: string) => api.post<{ok: boolean, meta: RoomMeta}>(`/rooms/${encodeURIComponent(roomId)}/meta`, { name }, roomRequest),

  marketSymbols: () => getWithBootstrapCache<string[]>('marketSymbols', 8000, () => api.get<string[]>('/market/symbols', undefined, roomRequest)),

  marketQuote: (symbol: string) => getWithBootstrapCache<MarketQuoteResponse>(`marketQuote:${String(symbol).toUpperCase()}`, 6000, () => api.get<MarketQuoteResponse>(`/market/quote/${encodeURIComponent(symbol)}`, undefined, roomRequest)),
  marketSeries: (symbol: string, limit = 200) =>
    getWithBootstrapCache<MarketSeriesResponse>(`marketSeries:${String(symbol).toUpperCase()}:${limit}`, 6000, () => api.get<MarketSeriesResponse>(`/market/series/${encodeURIComponent(symbol)}`, { limit }, roomRequest)),
  marketCandles: (symbol: string, interval_seconds = 60, limit = 200) =>
    getWithBootstrapCache<MarketCandlesResponse>(`marketCandles:${String(symbol).toUpperCase()}:${interval_seconds}:${limit}`, 6000, () => api.get<MarketCandlesResponse>(`/market/candles/${encodeURIComponent(symbol)}`, {
      interval_seconds,
      limit,
    }, roomRequest)),
  marketSession: () => getWithBootstrapCache<MarketSessionResponse>('marketSession', 8000, () => api.get<MarketSessionResponse>('/market/session', undefined, roomRequest)),
  marketSummary: () => getWithBootstrapCache<MarketSummaryResponse>('marketSummary', 8000, () => api.get<MarketSummaryResponse>('/market/summary', undefined, roomRequest)),

  listPlayers: (limit = 100) => getWithBootstrapCache<PlayerListResponse>(`listPlayers:${limit}`, 8000, () => api.get<PlayerListResponse>('/players', { limit }, roomRequest)),
  listContracts: (actor_id?: string, limit = 50, status?: string) =>
    getWithBootstrapCache<ContractListResponse>(`listContracts:${actor_id || 'all'}:${limit}:${status || 'all'}`, 8000, () => api.get<ContractListResponse>('/contracts/list', { actor_id, limit, status }, roomRequest)),

  submitLimitOrder: (req: PlayerLimitOrderRequest) => api.post<PlayerOrderResponse>('/orders/limit', req, roomRequest),
  submitMarketOrder: async (req: PlayerMarketOrderRequest) => {
    await api.post<unknown>('/orders/market', req, roomRequest)
  },
  orderBook: (symbol: string, limit = 20) =>
    api.get<OrderBookResponse>(`/orders/book/${encodeURIComponent(symbol)}`, { limit }, roomRequest),
  myOpenOrders: (player_id: string, symbol?: string, limit = 50) =>
    api.get<MyOpenOrdersListResponse>(`/orders/open/${encodeURIComponent(player_id)}`, { symbol, limit }, roomRequest),
  cancelOrder: (order_id: string, req: PlayerCancelOrderRequest) =>
    api.post<void>(`/orders/${encodeURIComponent(order_id)}/cancel`, req, roomRequest),

  playersBootstrap: (req: PlayerBootstrapRequest) => api.post<PlayerBootstrapResponse>('/players/bootstrap', req, roomRequest),

  playerAccount: (player_id: string) => getWithBootstrapCache<PlayerAccountResponse>(`playerAccount:${String(player_id).toLowerCase()}`, 8000, () => api.get<PlayerAccountResponse>(`/players/${encodeURIComponent(player_id)}/account`, undefined, roomRequest)),
  accountValuation: (account_id: string, discount_factor = 1.0) =>
    getWithBootstrapCache<AccountValuationResponse>(`accountValuation:${String(account_id).toLowerCase()}:${discount_factor}`, 6000, () => api.get<AccountValuationResponse>(`/accounts/${encodeURIComponent(account_id)}/valuation`, { discount_factor }, roomRequest)),

  accountLedger: (account_id: string, limit = 200, before?: string) =>
    api.get<AccountLedgerResponse>(`/accounts/${encodeURIComponent(account_id)}/ledger`, { limit, before }, roomRequest),

  chatIntroFeeQuote: (req: ChatIntroFeeQuoteRequest) =>
    api.post<ChatIntroFeeQuoteResponse>('/chat/intro-fee/quote', req, roomRequest),
  chatOpenPm: (req: ChatOpenPmRequest) => api.post<ChatOpenPmResponse>('/chat/pm/open', req, roomRequest),
  chatPublicSend: (req: ChatSendMessageRequest) => api.post<ChatSendMessageResponse>('/chat/public/send', req, roomRequest),
  chatPmSend: (req: ChatSendPmMessageRequest) => api.post<ChatSendMessageResponse>('/chat/pm/send', req, roomRequest),
  chatPublicMessages: (limit = 50, before?: string) => api.get<ChatListMessagesResponse>('/chat/public/messages', { limit, before }, roomRequest),
  chatPmMessages: (thread_id: string, limit = 50, before?: string) =>
    api.get<ChatListMessagesResponse>(`/chat/pm/${encodeURIComponent(thread_id)}/messages`, { limit, before }, roomRequest),
  chatThreads: (user_id: string, limit = 200) =>
    api.get<ChatListThreadsResponse>(`/chat/threads/${encodeURIComponent(user_id)}`, { limit }, roomRequest),

  wealthPublicRefresh: () => api.post<WealthPublicRefreshResponse>('/wealth/public/refresh', undefined, roomRequest),
  wealthPublicGet: (user_id: string) => getWithBootstrapCache<WealthPublicResponse>(`wealthPublic:${String(user_id).toLowerCase()}`, 5000, () => api.get<WealthPublicResponse>(`/wealth/public/${encodeURIComponent(user_id)}`, undefined, roomRequest)),

  contractCreate: (req: ContractCreateRequest) => api.post<ContractCreateResponse>('/contracts/create', req, roomRequest),
  contractBatchCreate: (req: ContractBatchCreateRequest) => api.post<ContractBatchCreateResponse>('/contracts/batch_create', req, roomRequest),
  contractJoin: (contract_id: string, req: ContractJoinRequest) => api.post<void>(`/contracts/${encodeURIComponent(contract_id)}/join`, req, roomRequest),
  contractSign: (contract_id: string, req: ContractSignRequest) => api.post<ContractSignResponse>(`/contracts/${encodeURIComponent(contract_id)}/sign`, req, roomRequest),
  contractActivate: (contract_id: string, req: ContractActivateRequest) => api.post<void>(`/contracts/${encodeURIComponent(contract_id)}/activate`, req, roomRequest),
  contractSettle: (contract_id: string, req: ContractSettleRequest) => api.post<void>(`/contracts/${encodeURIComponent(contract_id)}/settle`, req, roomRequest),
  contractRunRules: (contract_id: string, req: ContractRunRulesRequest) => api.post<void>(`/contracts/${encodeURIComponent(contract_id)}/run_rules`, req, roomRequest),
  contractGet: (contract_id: string) => api.get<ContractResponse>(`/contracts/${encodeURIComponent(contract_id)}`, undefined, roomRequest),
  contractProposalCreate: (contract_id: string, req: ContractProposalCreateRequest) => api.post<ContractProposalCreateResponse>(`/contracts/${encodeURIComponent(contract_id)}/proposals/create`, req, roomRequest),
  contractProposalApprove: (contract_id: string, proposal_id: string, req: ContractProposalApproveRequest) => api.post<ContractProposalApproveResponse>(`/contracts/${encodeURIComponent(contract_id)}/proposals/${encodeURIComponent(proposal_id)}/approve`, req, roomRequest),

  contractAgentDraft: (req: ContractAgentDraftRequest) => api.post<ContractAgentDraftResponse>('/contract-agent/draft', req, roomRequest),
  contractAgentAppendEdit: (req: ContractAgentAppendEditRequest) => api.post<ContractAgentDraftResponse>('/contract-agent/append_edit', req, roomRequest),
  contractAgentAudit: (req: ContractAgentAuditRequest) => api.post<ContractAgentAuditResponse>('/contract-agent/audit', req, roomRequest),
  contractAgentGetContext: (actor_id: string) => api.get<ContractAgentContextResponse>(`/contract-agent/context/${encodeURIComponent(actor_id)}`, undefined, roomRequest),
  contractAgentClearContext: (actor_id: string) => api.post<void>(`/contract-agent/context/${encodeURIComponent(actor_id)}/clear`, undefined, roomRequest),

  socialFollow: async (req: SocialFollowRequest) => {
    await api.post<unknown>('/social/follow', req, roomRequest)
  },

  newsCreateCard: (req: NewsCreateCardRequest) => api.post<NewsCreateCardResponse>('/news/cards', req, roomRequest),
  newsEmitVariant: (req: NewsEmitVariantRequest) => api.post<NewsEmitVariantResponse>('/news/variants/emit', req, roomRequest),
  newsMutateVariant: (req: NewsMutateVariantRequest) => api.post<NewsMutateVariantResponse>('/news/variants/mutate', req, roomRequest),
  newsPropagate: (req: NewsPropagateRequest) => api.post<NewsPropagateResponse>('/news/propagate', req, roomRequest),
  newsPropagateQuote: (req: NewsPropagateQuoteRequest) =>
    api.post<NewsPropagateQuoteResponse>('/news/propagate/quote', req, roomRequest),
  newsInbox: (player_id: string, limit = 50) => getWithBootstrapCache<NewsInboxResponse>(`newsInbox:${String(player_id).toLowerCase()}:${limit}`, 5000, () => api.get<NewsInboxResponse>(`/news/inbox/${encodeURIComponent(player_id)}`, { limit }, roomRequest)),
  newsPublicFeed: (limit = 20) => getWithBootstrapCache<NewsFeedResponse>(`newsPublicFeed:${limit}`, 5000, () => api.get<NewsFeedResponse>('/news/public/feed', { limit }, roomRequest)),
  newsBroadcast: (req: NewsBroadcastRequest) => api.post<NewsBroadcastResponse>('/news/broadcast', req, roomRequest),
  newsChainStart: (req: NewsChainStartRequest) => api.post<NewsChainStartResponse>('/news/chains/start', req, roomRequest),
  newsTick: (req: NewsTickRequest) => api.post<NewsTickResponse>('/news/tick', req, roomRequest),
  newsSuppress: (req: NewsSuppressRequest) => api.post<NewsSuppressResponse>('/news/suppress', req, roomRequest),
  newsOwnershipGrant: (req: NewsOwnershipGrantRequest) => api.post<NewsOwnershipEventResponse>('/news/ownership/grant', req, roomRequest),
  newsOwnershipTransfer: (req: NewsOwnershipTransferRequest) => api.post<NewsOwnershipEventResponse>('/news/ownership/transfer', req, roomRequest),
  newsOwnershipList: (user_id: string, limit = 200) =>
    api.get<NewsOwnedCardsResponse>(`/news/ownership/${encodeURIComponent(user_id)}`, { limit }, roomRequest),
  newsStoreCatalog: (user_id: string, force_refresh = false) => 
    api.get<NewsStoreCatalogResponse>('/news/store/catalog', { user_id, force_refresh }, roomRequest),
  newsStorePurchase: (req: NewsStorePurchaseRequest) => api.post<NewsStorePurchaseResponse>('/news/store/purchase', req, roomRequest),

  hostingEnable: (user_id: string) => api.post<HostingEnableResponse>(`/hosting/${encodeURIComponent(user_id)}/enable`, undefined, roomRequest),
  hostingDisable: (user_id: string) => api.post<HostingDisableResponse>(`/hosting/${encodeURIComponent(user_id)}/disable`, undefined, roomRequest),
  hostingStatus: (user_id: string) => getWithBootstrapCache<HostingStatusResponse>(`hostingStatus:${String(user_id).toLowerCase()}`, 5000, () => api.get<HostingStatusResponse>(`/hosting/${encodeURIComponent(user_id)}/status`, undefined, roomRequest)),
  hostingDebugTickOnce: () => api.post<HostingDebugTickResponse>('/hosting/debug/tick_once', undefined, roomRequest),

  settingsGetPreferences: (actor_id: string) => api.get<AppPreferencesResponse>(`/settings/preferences/${encodeURIComponent(actor_id)}`, undefined, roomRequest),
  settingsSavePreferences: (req: AppPreferencesUpdateRequest) => api.post<AppPreferencesResponse>('/settings/preferences', req, roomRequest),
  settingsGetLlm: (actor_id: string) => api.get<LlmSettingsResponse>(`/settings/llm/${encodeURIComponent(actor_id)}`, undefined, roomRequest),
  settingsSaveLlm: (req: LlmSettingsUpdateRequest) => api.post<LlmSettingsResponse>('/settings/llm', req, roomRequest),
  settingsTestLlm: (req: LlmConnectionTestRequest) => api.post<LlmConnectionTestResponse>('/settings/llm/test', req, roomRequest),
  settingsLlmDiagnostics: (req: LlmNetworkDiagnosticRequest) => api.post<LlmNetworkDiagnosticResponse>('/settings/llm/diagnostics', req, roomRequest),

  debugEmitEvent: (req: DebugEmitEventRequest) => api.post<DebugEmitEventResponse>('/debug/emit_event', req, roomRequest),

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
