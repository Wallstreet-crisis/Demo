export type HealthResponse = { status: string }

export type MarketQuoteResponse = {
  symbol: string
  last_price: number | null
  prev_price: number | null
  change_pct: number | null
  ma_5: number | null
  ma_20: number | null
  vol_20: number | null
}

export type MarketSeriesResponse = {
  symbol: string
  prices: number[]
}

export type MarketCandleItem = {
  bucket_start: string
  open: number
  high: number
  low: number
  close: number
  volume: number
  vwap: number
  trades: number
}

export type MarketCandlesResponse = {
  symbol: string
  interval_seconds: number
  candles: MarketCandleItem[]
}

export type MarketSessionResponse = {
  enabled: boolean
  phase: string
  game_day_index: number
  seconds_into_day: number
  seconds_per_game_day: number
  trading_seconds: number
  closing_buffer_seconds: number
}

export type PlayerAccountResponse = {
  account_id: string
  cash: number
  positions: Record<string, number>
}

export type PlayerBootstrapRequest = {
  player_id: string
  initial_cash?: number | null
  caste_id?: string | null
}

export type PlayerBootstrapResponse = PlayerAccountResponse

export type AccountValuationResponse = {
  account_id: string
  cash: number
  positions: Record<string, number>
  equity_value: number
  total_value: number
  discount_factor: number
  prices: Record<string, number | null>
}

export type PlayerLimitOrderRequest = {
  player_id: string
  symbol: string
  side: string
  price: number
  quantity: number
}

export type PlayerOrderResponse = {
  order_id: string
}

export type PlayerMarketOrderRequest = {
  player_id: string
  symbol: string
  side: string
  quantity: number
}

export type ChatIntroFeeQuoteRequest = {
  rich_user_id: string
  fee_cash?: number
  actor_id: string
}

export type ChatIntroFeeQuoteResponse = {
  event_id: string
  correlation_id: string | null
}

export type ChatOpenPmRequest = {
  requester_id: string
  target_id: string
}

export type ChatOpenPmResponse = {
  thread_id: string
  paid_intro_fee: boolean
  intro_fee_cash: number
}

export type ChatSendMessageRequest = {
  sender_id: string
  message_type?: string
  content?: string
  payload?: Record<string, unknown>
  anonymous?: boolean
  alias?: string | null
}

export type ChatSendPmMessageRequest = ChatSendMessageRequest & {
  thread_id: string
}

export type ChatSendMessageResponse = {
  event_id: string
  correlation_id: string | null
}

export type ChatMessageResponse = {
  message_id: string
  thread_id: string
  sender_id: string | null
  sender_display: string
  message_type: string
  content: string
  payload: Record<string, unknown>
  created_at: string
}

export type ChatListMessagesResponse = {
  items: ChatMessageResponse[]
}

export type ChatThreadResponse = {
  thread_id: string
  kind: string
  participant_a: string
  participant_b: string
  status: string
  created_at: string
}

export type ChatListThreadsResponse = {
  items: ChatThreadResponse[]
}

export type NewsCreateCardRequest = {
  actor_id: string
  kind: string
  image_anchor_id?: string | null
  image_uri?: string | null
  truth_payload?: Record<string, unknown> | null
  symbols?: string[]
  tags?: string[]
  correlation_id?: string | null
}

export type NewsCreateCardResponse = {
  card_id: string
  event_id: string
  correlation_id: string | null
}

export type NewsEmitVariantRequest = {
  card_id: string
  author_id: string
  text: string
  parent_variant_id?: string | null
  influence_cost?: number
  risk_roll?: Record<string, unknown> | null
  correlation_id?: string | null
}

export type NewsEmitVariantResponse = {
  variant_id: string
  event_id: string
  correlation_id: string | null
}

export type NewsMutateVariantRequest = {
  parent_variant_id: string
  editor_id: string
  new_text: string
  influence_cost?: number
  spend_cash?: number | null
  risk_roll?: Record<string, unknown> | null
  correlation_id?: string | null
}

export type NewsMutateVariantResponse = {
  new_variant_id: string
  event_id: string
  correlation_id: string | null
}

export type NewsPropagateRequest = {
  variant_id: string
  from_actor_id: string
  visibility_level?: string
  spend_influence?: number
  spend_cash?: number | null
  limit?: number
  correlation_id?: string | null
}

export type NewsPropagateResponse = {
  delivered: number
  correlation_id: string | null
}

export type NewsInboxResponseItem = {
  delivery_id: string
  card_id: string
  variant_id: string
  from_actor_id: string
  visibility_level: string
  delivery_reason: string
  delivered_at: string
  text: string
  symbols?: string[]
  tags?: string[]
  truth_payload?: unknown
}

export type NewsInboxResponse = {
  items: NewsInboxResponseItem[]
}

export type NewsBroadcastRequest = {
  variant_id: string
  actor_id: string
  channel?: string
  visibility_level?: string
  limit_users?: number
  correlation_id?: string | null
}

export type NewsBroadcastResponse = {
  delivered: number
  event_id: string
  correlation_id: string | null
}

export type NewsChainStartRequest = {
  kind: string
  actor_id: string
  t0_seconds?: number
  t0_at?: string | null
  omen_interval_seconds?: number
  abort_probability?: number
  grant_count?: number
  seed?: number
  correlation_id?: string | null
}

export type NewsChainStartResponse = {
  chain_id: string
  major_card_id: string
  t0_at: string
}

export type NewsTickRequest = {
  now_iso?: string | null
  limit?: number
}

export type NewsTickResponse = {
  now: string
  chains: Record<string, unknown>[]
}

export type NewsSuppressRequest = {
  actor_id: string
  chain_id: string
  spend_influence: number
  signal_class?: string | null
  scope?: string
  correlation_id?: string | null
}

export type NewsSuppressResponse = {
  event_id: string
  correlation_id: string | null
}

export type NewsOwnershipGrantRequest = {
  card_id: string
  to_user_id: string
  granter_id: string
  correlation_id?: string | null
}

export type NewsOwnershipTransferRequest = {
  card_id: string
  from_user_id: string
  to_user_id: string
  transferred_by: string
  correlation_id?: string | null
}

export type NewsOwnershipEventResponse = {
  event_id: string
  correlation_id: string | null
}

export type NewsOwnedCardsResponse = {
  cards: string[]
}

export type NewsStoreCatalogItem = {
  kind: string
  price_cash: number
  requires_symbols?: boolean
  preview_text: string
  presets?: NewsStoreCatalogPreset[]
  symbol_options?: string[]
}

export type NewsStoreCatalogResponse = {
  items: NewsStoreCatalogItem[]
}

export type NewsStoreCatalogPreset = {
  preset_id: string
  text: string
}

export type NewsStorePurchaseRequest = {
  buyer_user_id: string
  kind: string
  price_cash: number
  preset_id?: string | null
  image_anchor_id?: string | null
  image_uri?: string | null
  truth_payload?: Record<string, unknown> | null
  symbols?: string[]
  tags?: string[]
  initial_text?: string
  t0_seconds?: number
  t0_at?: string | null
  omen_interval_seconds?: number
  abort_probability?: number
  grant_count?: number
  seed?: number
  correlation_id?: string | null
}

export type NewsStorePurchaseResponse = {
  kind: string
  buyer_user_id: string
  card_id: string | null
  variant_id: string | null
  chain_id: string | null
}

export type HostingStatusResponse = {
  user_id: string
  enabled: boolean
  status: string
  updated_at: string
}

export type HostingEnableResponse = {
  state: HostingStatusResponse
  event_id: string
  correlation_id: string | null
}

export type HostingDisableResponse = {
  state: HostingStatusResponse
  event_id: string
  correlation_id: string | null
}

export type HostingDebugTickResponse = {
  ok: boolean
}

export type WealthPublicRefreshResponse = {
  public_count: number
  event_id: string
  correlation_id: string | null
}

export type WealthPublicResponse = {
  user_id: string
  public_total_value: number | null
}

export type SocialFollowRequest = {
  follower_id: string
  followee_id: string
}

export type DebugEmitEventRequest = {
  event_type: string
  payload: Record<string, unknown>
  actor_user_id?: string | null
  actor_agent_id?: string | null
  correlation_id?: string | null
  causation_id?: string | null
}

export type DebugEmitEventResponse = {
  event_id: string
  correlation_id: string | null
}

export type ContractAgentDraftRequest = {
  actor_id: string
  natural_language: string
}

export type ContractAgentDraftResponse = {
  draft_id: string
  template_id: string
  contract_create: Record<string, unknown>
  explanation: string
  questions: string[]
  risk_rating: string
}

export type ContractAgentContextResponse = {
  actor_id: string
  context: Record<string, unknown>
}

export type ContractCreateRequest = {
  actor_id: string
  kind: string
  title: string
  terms: Record<string, unknown>
  parties: string[]
  required_signers: string[]
  participation_mode?: string | null
  invited_parties?: string[] | null
}

export type ContractCreateResponse = {
  contract_id: string
}

export type ContractBatchItem = {
  kind: string
  title: string
  terms: Record<string, unknown>
  parties: string[]
  required_signers: string[]
  participation_mode?: string | null
  invited_parties?: string[] | null
}

export type ContractBatchCreateRequest = {
  actor_id: string
  contracts: ContractBatchItem[]
}

export type ContractBatchCreateResponseItem = {
  index: number
  contract_id: string
}

export type ContractBatchCreateResponse = {
  contracts: ContractBatchCreateResponseItem[]
}

export type ContractJoinRequest = {
  joiner: string
}

export type ContractSignRequest = {
  signer: string
}

export type ContractSignResponse = {
  status: string
}

export type ContractActivateRequest = {
  actor_id: string
}

export type ContractSettleRequest = {
  actor_id: string
}

export type ContractRunRulesRequest = {
  actor_id: string
}

export type ContractProposalCreateRequest = {
  proposer: string
  proposal_type: string
  details: Record<string, unknown>
}

export type ContractProposalCreateResponse = {
  proposal_id: string
}

export type ContractProposalApproveRequest = {
  approver: string
}

export type ContractProposalApproveResponse = {
  applied: boolean
  contract_status: string
  proposal_type: string
}

export type ContractResponse = {
  contract_id: string
  kind: string
  title: string
  status: string
  terms: Record<string, unknown>
  parties: string[]
  required_signers: string[]
  signatures: Record<string, string>
  participation_mode: string
  invited_parties: string[]
  created_at: string
  updated_at: string
  proposals: unknown[]
}
