import { ApiClient } from './http'
import type {
  AccountValuationResponse,
  ChatIntroFeeQuoteRequest,
  ChatIntroFeeQuoteResponse,
  ChatListMessagesResponse,
  ChatListThreadsResponse,
  ChatOpenPmRequest,
  ChatOpenPmResponse,
  ChatSendMessageRequest,
  ChatSendMessageResponse,
  ChatSendPmMessageRequest,
  HealthResponse,
  HostingDebugTickResponse,
  HostingDisableResponse,
  HostingEnableResponse,
  HostingStatusResponse,
  MarketCandlesResponse,
  MarketQuoteResponse,
  MarketSeriesResponse,
  MarketSessionResponse,
  NewsBroadcastRequest,
  NewsBroadcastResponse,
  NewsChainStartRequest,
  NewsChainStartResponse,
  NewsCreateCardRequest,
  NewsCreateCardResponse,
  NewsEmitVariantRequest,
  NewsEmitVariantResponse,
  NewsInboxResponse,
  NewsMutateVariantRequest,
  NewsMutateVariantResponse,
  NewsOwnedCardsResponse,
  NewsOwnershipEventResponse,
  NewsOwnershipGrantRequest,
  NewsOwnershipTransferRequest,
  NewsPropagateRequest,
  NewsPropagateResponse,
  NewsStorePurchaseRequest,
  NewsStorePurchaseResponse,
  NewsSuppressRequest,
  NewsSuppressResponse,
  NewsTickRequest,
  NewsTickResponse,
  PlayerAccountResponse,
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
} from './types'

const api = new ApiClient()

export const Api = {
  health: () => api.get<HealthResponse>('/health'),

  marketQuote: (symbol: string) => api.get<MarketQuoteResponse>(`/market/quote/${encodeURIComponent(symbol)}`),
  marketSeries: (symbol: string, limit = 200) =>
    api.get<MarketSeriesResponse>(`/market/series/${encodeURIComponent(symbol)}`, { limit }),
  marketCandles: (symbol: string, interval_seconds = 60, limit = 200) =>
    api.get<MarketCandlesResponse>(`/market/candles/${encodeURIComponent(symbol)}`, {
      interval_seconds,
      limit,
    }),
  marketSession: () => api.get<MarketSessionResponse>('/market/session'),

  submitLimitOrder: (req: PlayerLimitOrderRequest) => api.post<PlayerOrderResponse>('/orders/limit', req),
  submitMarketOrder: async (req: PlayerMarketOrderRequest) => {
    await api.post<unknown>('/orders/market', req)
  },

  playersBootstrap: (req: PlayerBootstrapRequest) => api.post<PlayerBootstrapResponse>('/players/bootstrap', req),

  playerAccount: (player_id: string) => api.get<PlayerAccountResponse>(`/players/${encodeURIComponent(player_id)}/account`),
  accountValuation: (account_id: string, discount_factor = 1.0) =>
    api.get<AccountValuationResponse>(`/accounts/${encodeURIComponent(account_id)}/valuation`, { discount_factor }),

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

  socialFollow: async (req: SocialFollowRequest) => {
    await api.post<unknown>('/social/follow', req)
  },

  newsCreateCard: (req: NewsCreateCardRequest) => api.post<NewsCreateCardResponse>('/news/cards', req),
  newsEmitVariant: (req: NewsEmitVariantRequest) => api.post<NewsEmitVariantResponse>('/news/variants/emit', req),
  newsMutateVariant: (req: NewsMutateVariantRequest) => api.post<NewsMutateVariantResponse>('/news/variants/mutate', req),
  newsPropagate: (req: NewsPropagateRequest) => api.post<NewsPropagateResponse>('/news/propagate', req),
  newsInbox: (player_id: string, limit = 50) => api.get<NewsInboxResponse>(`/news/inbox/${encodeURIComponent(player_id)}`, { limit }),
  newsBroadcast: (req: NewsBroadcastRequest) => api.post<NewsBroadcastResponse>('/news/broadcast', req),
  newsChainStart: (req: NewsChainStartRequest) => api.post<NewsChainStartResponse>('/news/chains/start', req),
  newsTick: (req: NewsTickRequest) => api.post<NewsTickResponse>('/news/tick', req),
  newsSuppress: (req: NewsSuppressRequest) => api.post<NewsSuppressResponse>('/news/suppress', req),
  newsOwnershipGrant: (req: NewsOwnershipGrantRequest) => api.post<NewsOwnershipEventResponse>('/news/ownership/grant', req),
  newsOwnershipTransfer: (req: NewsOwnershipTransferRequest) => api.post<NewsOwnershipEventResponse>('/news/ownership/transfer', req),
  newsOwnershipList: (user_id: string, limit = 200) =>
    api.get<NewsOwnedCardsResponse>(`/news/ownership/${encodeURIComponent(user_id)}`, { limit }),
  newsStorePurchase: (req: NewsStorePurchaseRequest) => api.post<NewsStorePurchaseResponse>('/news/store/purchase', req),

  hostingEnable: (user_id: string) => api.post<HostingEnableResponse>(`/hosting/${encodeURIComponent(user_id)}/enable`),
  hostingDisable: (user_id: string) => api.post<HostingDisableResponse>(`/hosting/${encodeURIComponent(user_id)}/disable`),
  hostingStatus: (user_id: string) => api.get<HostingStatusResponse>(`/hosting/${encodeURIComponent(user_id)}/status`),
  hostingDebugTickOnce: () => api.post<HostingDebugTickResponse>('/hosting/debug/tick_once'),

  debugEmitEvent: (req: DebugEmitEventRequest) => api.post<DebugEmitEventResponse>('/debug/emit_event', req),
}

export { ApiClient }
export * from './http'
export * from './types'
export * from './ws'
