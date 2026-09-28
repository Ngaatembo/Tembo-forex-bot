/**
 * Read-only client for the Tembo cockpit API.
 * No provider, broker, or secret credentials belong in the browser.
 */

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "https://tembo-forex-bot.onrender.com";

export type LiveDecision = {
  instrument: string; timeframe: string; provider: string; status: string; decision: string;
  methodology: string;
  macro_risk: { level: string; reason: string; triggering_event_count: number };
  news: { status: string; freshness: string; provider: string; last_successful_fetch: string | null; error: string | null; headlines: Array<{ news_id: string; timestamp: string; headline: string; source: string; url: string | null }> };
  macro_events: Array<{ event_id: string; timestamp: string; currency: string; country: string | null; event_name: string; importance: string; previous: number | null; forecast: number | null; actual: number | null; source: string; time_confirmed: boolean }>;
  risk: { status: string; state: string | null; hierarchy_stage: string | null; computed_risk_pct: number | null; position_size: number | null; reason: string };
  strategy_gate: { status: string; selected_config_id: string | null; reason: string; live_evaluation?: { status?: string; decision?: string; strategy_family?: string; config_id?: string | null; reason?: string; entry?: number | null; stop_loss?: number | null; take_profit?: number | null; risk_reward?: number | null } };
  paper_eligibility: { eligible: boolean; status: string; reason: string; persistent_state_changed: boolean; real_broker_contacted: boolean; execution_enabled: boolean };
  data_quality: { is_clean: boolean; candle_count: number; last_candle: string };
  trade_plan: { decision: string; direction: string; entry: number | null; stop_loss: number | null; take_profit: number | null; risk_reward: number | null; rejection_reasons?: string[] } | null;
};
export type LiveAnalysis = {
  instrument: string; timeframe: string; provider: string; status: string; message: string;
  data_quality?: { is_clean: boolean; ohlc_violations: number; duplicate_timestamps: number; unexpected_gaps: number };
  analysis: {
    status: string; reason?: string; as_of?: string; close?: number;
    trend?: { state: string; regime: string; sma_10: number | null; sma_50: number | null; sma_50_slope: number | null; sma_distance_pct: number | null };
    momentum?: { state: string; rsi_14: number | null };
    volatility?: { state: string; atr_14: number | null; atr_percent: number | null };
    support_resistance?: { support: number | null; resistance: number | null; recent_high: number | null; recent_low: number | null; rolling_range: number | null };
    market_structure?: { label: string; confirmed_swing_high: number | null; previous_swing_high: number | null; confirmed_swing_low: number | null; previous_swing_low: number | null };
    candlestick_patterns?: Array<{ pattern?: string; name?: string; direction?: string; confidence?: string; timestamp?: string; [key: string]: unknown }>;
  } | null;
};

export type ResearchDecision = {
  instrument: string; timeframe: string; selector_status: string; has_validated_edge: boolean;
  selected_config: { config_id: string; strategy_family: string; gate_status: string; verdict: string; statistical_level: string } | null;
  research_gate_status: string | null; reason: string; research_recommendation: string | null;
};
export type StrategyHealth = {
  instrument: string; timeframe: string; current_regime: string | null; status: string;
  selected_config_id: string | null; reason: string; research_recommendation: string | null;
  considered: Array<{ config_id: string; gate_status: string; reason: string }>;
};
export type ReliabilityStatus = {
  status: string; mode: string; execution: string; guardrails: string[]; policy: string;
};
export type ReliabilityRuntime = {
  status: string; drawdown_pct: number | null; governor: string; size_multiplier: number;
  reason: string; equity_basis?: string;
};
export type MarketResponse = {
  instrument: string; timeframe: string; provider: string; status: string; current_price: number | null;
  instrument_metadata?: { symbol: string; display_name: string; pip_size: number; asset_class: string };
  last_update: string | null; candles: Array<{timestamp:string;open:number;high:number;low:number;close:number;volume:number | null}>;
  data_quality: {is_clean:boolean;ohlc_violations:number;duplicate_timestamps:number;unexpected_gaps:number};
};
export type RuntimeStatus = {
  status: string; account_id: string; initial_equity: number; realized_pnl: number;
  peak_equity: number; open_positions: number; last_cycle_at: string | null;
  execution_enabled: boolean; broker_contacted: boolean;
};
export type RuntimePosition = {
  position_id:string; instrument:string; timeframe:string; direction:string; entry_price:number;
  stop_price:number|null; take_profit_price:number|null; position_size:number;
  candidate_config_id:string; entry_time:string; periods_held:number; status:string;
};

async function getJson(path: string) {
  const res = await fetch(API_BASE_URL + path, { cache: "no-store" });
  if (!res.ok) throw new Error(await readApiError(res));
  return res.json();
}
export type SyntheticSymbol = {
  symbol: string; underlying_symbol: string; display_name: string; market: string;
  submarket?: string | null; subgroup?: string | null; pip_size: number; exchange_is_open: boolean;
};
export type SyntheticSymbolsResponse = { provider: string; status: string; symbols: SyntheticSymbol[]; message: string };
export type DerivStatus = {
  connected: boolean; configured: boolean; mode: string; account_id?: string | null;
  account_type?: string | null; status?: string | null; currency?: string | null;
  balance?: number | null; open_positions?: number; message: string;
};

export function getDerivStatus():Promise<DerivStatus> { return getJson("/deriv/status"); }
export type DerivMarket = {
  underlying_symbol: string; display_name: string; symbol: string;
  underlying_symbol_type?: string | null; market?: string | null;
  pip_size: number; exchange_is_open: boolean;
};
export type DerivMarketsResponse = { status: string; symbols: DerivMarket[] };
export type DemoProposal = {
  status: string; instrument: string; underlying_symbol: string; direction: string;
  contract_type: string; stake: number; multiplier: number; proposal_id: string;
  ask_price: number; spot: number | null; payout: number | null; currency: string;
};
export type DemoBuyResult = {
  status: string; contract_id: number; transaction_id?: number | string | null;
  buy_price: number; balance_after: number | null;
};
export function getDerivMarkets():Promise<DerivMarketsResponse> { return getJson("/deriv/markets"); }
async function postJson(path:string, body:unknown) {
  const res = await fetch(API_BASE_URL + path, {
    method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await readApiError(res));
  return res.json();
}
export function getDemoProposal(instrument:string,direction:string,stake:number,multiplier:number):Promise<DemoProposal> {
  return postJson("/deriv/demo/proposal",{instrument,direction,stake,multiplier});
}
export function buyDemoContract(proposal_id:string,price:number):Promise<DemoBuyResult> {
  return postJson("/deriv/demo/buy",{proposal_id,price});
}
export function getDemoContract(contract_id:number):Promise<{status:string;contract:Record<string,unknown>}> {
  return getJson("/deriv/demo/contract?contract_id="+encodeURIComponent(String(contract_id)));
}
export function sellDemoContract(contract_id:number):Promise<{status:string;contract_id:number;sold_for:number|null}> {
  return postJson("/deriv/demo/sell",{contract_id});
}

export function getSyntheticSymbols():Promise<SyntheticSymbolsResponse> { return getJson("/live/synthetic-symbols"); }
export function getMarket(instrument:string,timeframe:string):Promise<MarketResponse> {
  return getJson("/live/market?" + new URLSearchParams({instrument,timeframe,limit:"120"}));
}
export function getLiveDecision(instrument:string,timeframe:string):Promise<LiveDecision> {
  return getJson("/live/decision?" + new URLSearchParams({instrument,timeframe}));
}
export function getLiveAnalysis(instrument:string,timeframe:string):Promise<LiveAnalysis> {
  return getJson("/live/analysis?" + new URLSearchParams({instrument,timeframe}));
}
export function getResearchDecision(instrument:string,timeframe:string):Promise<ResearchDecision> {
  return getJson("/decisions?" + new URLSearchParams({instrument,timeframe}));
}
export function getStrategyHealth(instrument:string,timeframe:string,currentRegime?:string|null):Promise<StrategyHealth> {
  const params = new URLSearchParams({instrument,timeframe});
  if (currentRegime) params.set("current_regime", currentRegime);
  return getJson("/strategy-health/instrument?" + params);
}
export function getReliabilityStatus():Promise<ReliabilityStatus> { return getJson("/reliability/status"); }
export function getReliabilityRuntime():Promise<ReliabilityRuntime> { return getJson("/reliability/runtime"); }
export function getRuntimeStatus():Promise<RuntimeStatus> { return getJson("/paper/runtime/status"); }
export function getRuntimePositions():Promise<RuntimePosition[]> { return getJson("/paper/runtime/positions"); }
async function readApiError(res:Response) {
  try { const body=await res.json(); if(typeof body?.detail==="string") return body.detail; } catch {}
  return "API request failed: " + res.status;
}
