/**
 * Read-only client for the Tembo cockpit API.
 * No provider, broker, or secret credentials belong in the browser.
 */

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export type DecisionResponse = {
  instrument: string;
  timeframe: string;
  provider: string;
  status: string;
  decision: string;
  methodology: string;
  macro_risk: { level: string; reason: string; triggering_event_count: number };
  data_quality: { is_clean: boolean; candle_count: number; last_candle: string };
  market_evidence: {
    last_close: number; regime: string; rsi_14: number | null;
    atr_14: number | null; atr_percent: number | null;
  };
  strategy_gate: { status: string; selected_config_id: string | null; reason: string };
  trade_plan: { decision?: string; direction?: string | null; entry?: number | null;
    stop_loss?: number | null; take_profit?: number | null; reason?: string; [key: string]: unknown };
  risk: { status: string; state: string | null; hierarchy_stage: string | null;
    computed_risk_pct: number | null; position_size: number | null; reason: string };
  paper_eligibility: { eligible: boolean; status: string; reason: string;
    persistent_state_changed: boolean; real_broker_contacted: boolean; execution_enabled: boolean };
  execution: { enabled: boolean; note: string };
};

export type MarketResponse = {
  instrument: string; timeframe: string; provider: string; status: string;
  current_price: number | null; last_update: string | null;
  instrument_metadata?: { symbol: string; display_name: string; pip_size: number; asset_class: string };
  candles: Array<{ timestamp: string; open: number; high: number; low: number; close: number; volume: number }>;
  data_quality: { is_clean: boolean; ohlc_violations: number; duplicate_timestamps: number; unexpected_gaps: number };
  message: string;
};

export async function getHealth() {
  const res = await fetch(`${API_BASE_URL}/health`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Health check failed: ${res.status}`);
  return res.json();
}

export async function getMarket(instrument: string, timeframe: string): Promise<MarketResponse> {
  const params = new URLSearchParams({ instrument, timeframe, limit: "120" });
  const res = await fetch(`${API_BASE_URL}/live/market?${params}`, { cache: "no-store" });
  if (!res.ok) throw new Error(await readApiError(res));
  return res.json();
}

export async function getDecision(instrument: string, timeframe: string): Promise<DecisionResponse> {
  const params = new URLSearchParams({ instrument, timeframe });
  const res = await fetch(`${API_BASE_URL}/live/decision?${params}`, { cache: "no-store" });
  if (!res.ok) throw new Error(await readApiError(res));
  return res.json();
}

async function readApiError(res: Response) {
  try {
    const body = await res.json();
    if (typeof body?.detail === "string") return body.detail;
  } catch {}
  return `API request failed: ${res.status}`;
}
