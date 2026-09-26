import { useEffect, useMemo, useState } from "react";
import Head from "next/head";
import { getDecision, getMarket, type DecisionResponse, type MarketResponse } from "../services/api";

const instruments = ["EUR/USD", "GBP/USD", "XAU/USD"];
const timeframes = ["m5", "m15", "h1", "h4", "d1"];

function fmt(value: number | null | undefined, digits = 5) {
  return value == null || !Number.isFinite(value) ? "—" : value.toFixed(digits);
}

function Pill({ value, tone = "neutral" }: { value: string; tone?: "good" | "warn" | "bad" | "neutral" }) {
  return <span className={`pill ${tone}`}>{value.replaceAll("_", " ")}</span>;
}

function Gate({ label, status, detail }: { label: string; status: string; detail: string }) {
  const good = ["TRADEABLE", "APPROVED", "PAPER_ELIGIBLE"].includes(status);
  const blocked = ["REJECTED", "NO_VALIDATED_EDGE", "NOT_ELIGIBLE", "RESEARCH_REQUIRED"].includes(status);
  return (
    <div className="gate">
      <div className="gate-top"><span>{label}</span><Pill value={status} tone={good ? "good" : blocked ? "bad" : "warn"} /></div>
      <p>{detail}</p>
    </div>
  );
}

export default function Home() {
  const [instrument, setInstrument] = useState("EUR/USD");
  const [timeframe, setTimeframe] = useState("h1");
  const [market, setMarket] = useState<MarketResponse | null>(null);
  const [decision, setDecision] = useState<DecisionResponse | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [lastRefresh, setLastRefresh] = useState("");

  async function refresh() {
    setLoading(true);
    setError("");
    try {
      const [m, d] = await Promise.all([
        getMarket(instrument, timeframe),
        getDecision(instrument, timeframe),
      ]);
      setMarket(m);
      setDecision(d);
      setLastRefresh(new Date().toLocaleTimeString());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to load Tembo data.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void refresh(); }, [instrument, timeframe]);

  const latest = useMemo(() => market?.candles?.[market.candles.length - 1], [market]);

  return (
    <>
      <Head>
        <title>Tembo Forex Bot — Cockpit</title>
        <meta name="description" content="Tembo read-only trading cockpit" />
      </Head>
      <main>
        <header className="topbar">
          <div><div className="brand">TEMBO</div><div className="subbrand">FOREX RESEARCH & PAPER COCKPIT</div></div>
          <div className="live-state"><span className="dot" /> READ-ONLY • EXECUTION OFF</div>
        </header>

        <section className="controls">
          <div>
            <label>Instrument</label>
            <select value={instrument} onChange={e => setInstrument(e.target.value)}>
              {instruments.map(x => <option key={x}>{x}</option>)}
            </select>
          </div>
          <div>
            <label>Timeframe</label>
            <select value={timeframe} onChange={e => setTimeframe(e.target.value)}>
              {timeframes.map(x => <option key={x}>{x}</option>)}
            </select>
          </div>
          <button onClick={() => void refresh()} disabled={loading}>{loading ? "Refreshing…" : "Refresh"}</button>
          <div className="refresh-note">{lastRefresh ? `Updated ${lastRefresh}` : "Waiting for data"}</div>
        </section>

        {error && <div className="error"><strong>Data unavailable.</strong> {error}</div>}

        <section className="hero-grid">
          <div className="price-card">
            <div className="eyebrow">LIVE MARKET EVIDENCE</div>
            <div className="price">{fmt(market?.current_price ?? latest?.close)}</div>
            <div className="price-meta">
              <span>{market?.provider || "—"}</span>
              <span>{market?.data_quality.is_clean ? "✓ candles verified" : "⚠ awaiting verification"}</span>
            </div>
          </div>
          <div className="signal-card">
            <div className="eyebrow">MULTI-FACTOR SIGNAL</div>
            <div className="signal">{decision?.decision || "—"}</div>
            <p>{decision?.methodology || "Waiting for verified market evidence."}</p>
          </div>
          <div className="risk-card">
            <div className="eyebrow">PAPER ELIGIBILITY</div>
            <div className="signal">{decision?.paper_eligibility.status || "—"}</div>
            <p>{decision?.paper_eligibility.reason || "No decision loaded."}</p>
          </div>
        </section>

        <section className="section">
          <div className="section-title"><span>01</span> Evidence</div>
          <div className="metrics">
            <Metric label="Regime" value={decision?.market_evidence.regime || "—"} />
            <Metric label="RSI 14" value={fmt(decision?.market_evidence.rsi_14, 2)} />
            <Metric label="ATR 14" value={fmt(decision?.market_evidence.atr_14, 5)} />
            <Metric label="ATR %" value={decision?.market_evidence.atr_percent == null ? "—" : `${decision.market_evidence.atr_percent.toFixed(3)}%`} />
            <Metric label="Candles" value={String(decision?.data_quality.candle_count ?? "—")} />
            <Metric label="Macro risk" value={decision?.macro_risk.level || "—"} />
          </div>
        </section>

        <section className="section">
          <div className="section-title"><span>02</span> Safety chain</div>
          <div className="gates">
            <Gate label="Strategy selector" status={decision?.strategy_gate.status || "WAITING"} detail={decision?.strategy_gate.reason || "No strategy evaluation yet."} />
            <Gate label="Risk engine" status={decision?.risk.state || decision?.risk.status || "WAITING"} detail={decision?.risk.reason || "Risk layer not reached."} />
            <Gate label="Paper account" status={decision?.paper_eligibility.status || "WAITING"} detail={decision?.paper_eligibility.reason || "Paper eligibility not evaluated."} />
          </div>
        </section>

        <section className="section">
          <div className="section-title"><span>03</span> Trade plan</div>
          <div className="plan">
            <Metric label="Decision" value={decision?.trade_plan.decision || decision?.decision || "NO_TRADE"} />
            <Metric label="Entry" value={fmt(decision?.trade_plan.entry)} />
            <Metric label="Stop loss" value={fmt(decision?.trade_plan.stop_loss)} />
            <Metric label="Take profit" value={fmt(decision?.trade_plan.take_profit)} />
            <Metric label="Risk %" value={decision?.risk.computed_risk_pct == null ? "—" : `${decision.risk.computed_risk_pct.toFixed(3)}%`} />
            <Metric label="Position size" value={fmt(decision?.risk.position_size, 4)} />
          </div>
          <div className="reason">{decision?.trade_plan.reason || "Tembo will not invent a trade when the evidence or research gate is insufficient."}</div>
        </section>

        <section className="section">
          <div className="section-title"><span>04</span> Execution boundary</div>
          <div className="boundary">
            <div><Pill value="DISABLED" tone="good" /><strong> Broker execution is OFF</strong></div>
            <p>{decision?.execution.note || "This cockpit is analysis and paper-eligibility only. No order is placed from this page."}</p>
            <div className="checks">
              <span>Persistent state: {decision?.paper_eligibility.persistent_state_changed ? "CHANGED" : "UNCHANGED"}</span>
              <span>Broker contacted: {decision?.paper_eligibility.real_broker_contacted ? "YES" : "NO"}</span>
              <span>Execution enabled: {decision?.paper_eligibility.execution_enabled ? "YES" : "NO"}</span>
            </div>
          </div>
        </section>

        <footer>Tembo • evidence first • fail closed • paper stage only</footer>
      </main>
      <style jsx>{`
        * { box-sizing: border-box; }
        body { margin: 0; background: #080a0f; color: #e9edf5; font-family: Inter, ui-sans-serif, system-ui, -apple-system, sans-serif; }
        main { min-height: 100vh; max-width: 1280px; margin: auto; padding: 24px; }
        .topbar { display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid #202632; padding-bottom:22px; }
        .brand { font-size:28px; font-weight:900; letter-spacing:.16em; }
        .subbrand,.eyebrow,.section-title span,label { color:#8993a5; font-size:11px; letter-spacing:.13em; text-transform:uppercase; }
        .subbrand { margin-top:4px; }
        .live-state { font-size:11px; letter-spacing:.08em; color:#9ba5b7; }
        .dot { display:inline-block; width:7px; height:7px; border-radius:50%; background:#5ee08b; margin-right:7px; }
        .controls { display:flex; align-items:end; gap:12px; padding:22px 0; border-bottom:1px solid #202632; }
        label { display:block; margin-bottom:7px; }
        select,button { background:#11151d; border:1px solid #2a3240; color:#edf1f8; border-radius:8px; padding:10px 13px; font:inherit; }
        button { cursor:pointer; font-weight:700; } button:disabled { opacity:.5; cursor:default; }
        .refresh-note { margin-left:auto; color:#727d90; font-size:12px; padding-bottom:10px; }
        .error { margin-top:18px; padding:13px 15px; border:1px solid #60333a; background:#211217; color:#f2b6bd; border-radius:9px; }
        .hero-grid { display:grid; grid-template-columns:1.3fr 1fr 1fr; gap:14px; padding:22px 0; }
        .price-card,.signal-card,.risk-card { background:#0e1219; border:1px solid #202632; border-radius:12px; padding:22px; min-height:150px; }
        .price { font-size:42px; font-weight:800; margin:18px 0 9px; letter-spacing:-.04em; }
        .signal { font-size:26px; font-weight:800; margin:18px 0 8px; }
        .price-meta,.signal-card p,.risk-card p,.gate p,.reason,.boundary p { color:#8e98a9; font-size:13px; line-height:1.55; margin:0; }
        .price-meta { display:flex; gap:15px; }
        .section { border-top:1px solid #202632; padding:24px 0; }
        .section-title { font-size:14px; font-weight:800; margin-bottom:15px; }
        .section-title span { margin-right:9px; }
        .metrics,.plan { display:grid; grid-template-columns:repeat(6,1fr); gap:10px; }
        .metrics > div,.plan > div { background:#0e1219; border:1px solid #1e2530; border-radius:9px; padding:14px; }
        .metric-label { color:#747f92; font-size:11px; text-transform:uppercase; letter-spacing:.08em; }
        .metric-value { font-weight:750; margin-top:8px; word-break:break-word; }
        .gates { display:grid; grid-template-columns:repeat(3,1fr); gap:10px; }
        .gate { background:#0e1219; border:1px solid #1e2530; border-radius:9px; padding:15px; }
        .gate-top { display:flex; align-items:center; justify-content:space-between; gap:10px; margin-bottom:11px; font-weight:750; }
        .pill { display:inline-flex; border:1px solid #344052; border-radius:999px; padding:4px 8px; font-size:10px; font-weight:800; letter-spacing:.07em; text-transform:uppercase; }
        .pill.good { border-color:#2f7650; color:#77e39d; background:#102219; }
        .pill.warn { border-color:#756332; color:#e1c87b; background:#211d11; }
        .pill.bad { border-color:#713a42; color:#ee9ca7; background:#241419; }
        .boundary { background:#0e1219; border:1px solid #25302b; border-radius:9px; padding:17px; }
        .checks { display:flex; gap:18px; flex-wrap:wrap; margin-top:14px; color:#a3adbd; font-size:12px; }
        footer { border-top:1px solid #202632; margin-top:10px; padding:20px 0 30px; color:#697486; font-size:11px; letter-spacing:.08em; text-transform:uppercase; }
        @media (max-width: 850px) {
          main { padding:16px; } .hero-grid,.gates { grid-template-columns:1fr; }
          .metrics,.plan { grid-template-columns:repeat(2,1fr); }
          .controls { flex-wrap:wrap; } .refresh-note { width:100%; margin:0; }
        }
      `}</style>
    </>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return <div><div className="metric-label">{label}</div><div className="metric-value">{value}</div></div>;
}
