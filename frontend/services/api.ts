/**
 * Read-only client for the Tembo cockpit API.
 * No provider, broker, or secret credentials belong in the browser.
 */

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export type LiveDecision = {
  instrument: string; timeframe: string; provider: string; status: string; decision: string;
  methodology: string;
  macro_risk: { level: string; reason: string; triggering_event_count: number };
  data_quality: { is_clean: boolean; candle_count: number; last_candle: string };
  trade_plan: { decision: string; direction: string; entry: number | null; stop_loss: number | null; take_profit: number | null; risk_reward: number | null; rejection_reasons?: string[] };
};
export type ResearchDecision = {
  instrument: string; timeframe: string; selector_status: string; has_validated_edge: boolean;
  selected_config: { config_id: string; strategy_family: string; gate_status: string; verdict: string; statistical_level: string } | null;
  research_gate_status: string | null; reason: string; research_recommendation: string | null;
};
export type MarketResponse = {
  instrument: string; timeframe: string; provider: string; status: string; current_price: number | null;
  last_update: string | null; candles: Array<{timestamp:string;open:number;high:number;low:number;close:number;volume:number}>;
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
  const res = await fetch(`${API_BASE_URL}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(await readApiError(res));
  return res.json();
}
export function getMarket(instrument:string,timeframe:string):Promise<MarketResponse> {
  return getJson(`/live/market?${new URLSearchParams({instrument,timeframe,limit:"120"})}`);
}
export function getLiveDecision(instrument:string,timeframe:string):Promise<LiveDecision> {
  return getJson(`/live/decision?${new URLSearchParams({instrument,timeframe})}`);
}
export function getResearchDecision(instrument:string,timeframe:string):Promise<ResearchDecision> {
  return getJson(`/decisions?${new URLSearchParams({instrument,timeframe})}`);
}
export function getRuntimeStatus():Promise<RuntimeStatus> { return getJson("/paper/runtime/status"); }
export function getRuntimePositions():Promise<RuntimePosition[]> { return getJson("/paper/runtime/positions"); }
async function readApiError(res:Response) {
  try { const body=await res.json(); if(typeof body?.detail==="string") return body.detail; } catch {}
  return `API request failed: ${res.status}`;
}
