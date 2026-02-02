CREATE CONSTRAINT user_id_unique IF NOT EXISTS
FOR (u:User)
REQUIRE u.user_id IS UNIQUE;

CREATE CONSTRAINT news_id_unique IF NOT EXISTS
FOR (n:News)
REQUIRE n.news_id IS UNIQUE;

CREATE CONSTRAINT variant_id_unique IF NOT EXISTS
FOR (v:NewsVariant)
REQUIRE v.variant_id IS UNIQUE;

CREATE CONSTRAINT contract_id_unique IF NOT EXISTS
FOR (c:Contract)
REQUIRE c.contract_id IS UNIQUE;

CREATE CONSTRAINT disclosure_id_unique IF NOT EXISTS
FOR (d:Disclosure)
REQUIRE d.disclosure_id IS UNIQUE;

CREATE CONSTRAINT asset_symbol_unique IF NOT EXISTS
FOR (a:Asset)
REQUIRE a.symbol IS UNIQUE;

CREATE CONSTRAINT ai_agent_id_unique IF NOT EXISTS
FOR (aa:AiAgent)
REQUIRE aa.agent_id IS UNIQUE;

CREATE CONSTRAINT ai_model_id_unique IF NOT EXISTS
FOR (am:AiModel)
REQUIRE am.model_id IS UNIQUE;

CREATE CONSTRAINT event_id_unique IF NOT EXISTS
FOR (e:Event)
REQUIRE e.event_id IS UNIQUE;

CREATE INDEX event_type_idx IF NOT EXISTS
FOR ()-[e:EMITTED_EVENT]-()
ON (e.event_type);

CREATE INDEX event_correlation_id_idx IF NOT EXISTS
FOR (e:Event)
ON (e.correlation_id);

CREATE INDEX event_occurred_at_idx IF NOT EXISTS
FOR (e:Event)
ON (e.occurred_at);

CREATE INDEX propagated_at_idx IF NOT EXISTS
FOR ()-[r:PROPAGATED]->()
ON (r.propagated_at);
