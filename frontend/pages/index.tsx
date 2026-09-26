import { useEffect, useMemo, useState } from "react";
import Head from "next/head";
import { getLiveDecision, getMarket, getResearchDecision, getRuntimePositions, getRuntimeStatus, type LiveDecision, type MarketResponse, type ResearchDecision, type RuntimePosition, type RuntimeStatus } from "../services/api";

const instruments = ["EUR/USD", "GBP/USD", "XAU/USD"];
const timeframes = ["h1"];

function fmt(value: number | null | undefined, digits = 5) {
  return value == null || !Number.isFinite(value) ? "—" : value.toFixed(digits);
}
function Pill({ value, tone = "neutral" }: { value: string; tone?: "good" | "warn" | "bad" | "neutral" }) {
  return <span className={`pill ${tone}`}>{value.replaceAll("_", " ")}</span>;
}
function toneFor(status?: string) {
  if (!status) return "neutral";
  if (["AVAILABLE","RUNNING","PAPER_CANDIDATE","TRADEABLE","LOW","NONE","DISABLED"].includes(status)) return "good";
  if (["PROMISING","PROMISING_NOT_TRADEABLE","MEDIUM","CONFIGURED"].includes(status)) return "warn";
  return ["NO_VALIDATED_EDGE","RESEARCH_REQUIRED","HIGH","UNAVAILABLE"].includes(status) ? "bad" : "neutral";
}
function Metric({ label, value }: { label: string; value: string }) {
  return <div><div className="metric-label">{label}</div><div className="metric-value">{value}</div></div>;
}

export default function Home() {
  const [instrument,setInstrument]=useState("EUR/USD");
  const [timeframe]=useState("h1");
  const [market,setMarket]=useState<MarketResponse|null>(null);
  const [decision,setDecision]=useState<LiveDecision|null>(null);
  const [research,setResearch]=useState<ResearchDecision|null>(null);
  const [runtime,setRuntime]=useState<RuntimeStatus|null>(null);
  const [positions,setPositions]=useState<RuntimePosition[]>([]);
  const [error,setError]=useState("");
  const [loading,setLoading]=useState(true);
  const [lastRefresh,setLastRefresh]=useState("");

  async function refresh() {
    setLoading(true); setError("");
    try {
      const [m,d,r,rs,p] = await Promise.all([
        getMarket(instrument,timeframe), getLiveDecision(instrument,timeframe),
        getResearchDecision(instrument,timeframe), getRuntimeStatus(), getRuntimePositions()
      ]);
      setMarket(m); setDecision(d); setResearch(r); setRuntime(rs); setPositions(p);
      setLastRefresh(new Date().toLocaleTimeString());
    } catch(e) { setError(e instanceof Error ? e.message : "Unable to load Tembo data."); }
    finally { setLoading(false); }
  }
  useEffect(()=>{ void refresh(); },[instrument]);

  const latest = useMemo(()=>market?.candles?.[market.candles.length-1], [market]);
  const signal = decision?.decision || "NO_TRADE";
  const selected = research?.selected_config;
  const activePosition = positions.find(p=>p.instrument===instrument && p.timeframe===timeframe);

  return <>
    <Head><title>Tembo Forex Bot — Cockpit</title><meta name="description" content="Tembo live-data paper trading cockpit"/></Head>
    <main>
      <header className="topbar">
        <div><div className="brand">TEMBO</div><div className="subbrand">LIVE-DATA PAPER TRADING COCKPIT</div></div>
        <div className="live-state"><span className="dot"/> PAPER ONLY • BROKER OFF</div>
      </header>

      <section className="controls">
        <div><label>Instrument</label><select value={instrument} onChange={e=>setInstrument(e.target.value)}>{instruments.map(x=><option key={x}>{x}</option>)}</select></div>
        <div><label>Timeframe</label><select value={timeframe} disabled><option>h1</option></select></div>
        <button onClick={()=>void refresh()} disabled={loading}>{loading?"Refreshing…":"Refresh"}</button>
        <div className="refresh-note">{lastRefresh?`Updated ${lastRefresh}`:"Waiting for data"}</div>
      </section>

      {error && <div className="error"><strong>Data unavailable.</strong> {error}</div>}

      <section className="hero-grid">
        <div className="card"><div className="eyebrow">LIVE MARKET</div><div className="price">{fmt(market?.current_price ?? latest?.close)}</div><div className="meta">{market?.provider||"—"} · {market?.data_quality.is_clean?"candles verified":"verification pending"}</div></div>
        <div className="card"><div className="eyebrow">SIGNAL</div><div className="signal">{signal}</div><p>{decision?.methodology||"Waiting for verified market evidence."}</p></div>
        <div className="card"><div className="eyebrow">PAPER RUNTIME</div><div className="signal">{runtime?.status||"—"}</div><p>Last cycle: {runtime?.last_cycle_at ? new Date(runtime.last_cycle_at).toLocaleString() : "—"}</p></div>
      </section>

      <section className="section"><div className="section-title"><span>01</span> Evidence</div>
        <div className="metrics">
          <Metric label="Candle count" value={String(decision?.data_quality.candle_count??"—")}/>
          <Metric label="Macro risk" value={decision?.macro_risk.level||"—"}/>
          <Metric label="Research gate" value={research?.research_gate_status||"—"}/>
          <Metric label="Selector" value={research?.selector_status||"—"}/>
          <Metric label="Decision" value={signal}/>
          <Metric label="Data" value={decision?.data_quality.is_clean?"VERIFIED":"REJECTED"}/>
        </div>
      </section>

      <section className="section"><div className="section-title"><span>02</span> Safety chain</div>
        <div className="gates">
          <div className="gate"><div className="gate-top">Market validation <Pill value={decision?.data_quality.is_clean?"AVAILABLE":"UNAVAILABLE"} tone={toneFor(decision?.data_quality.is_clean?"AVAILABLE":"UNAVAILABLE")}/></div><p>Only validated completed candles can reach the decision engine.</p></div>
          <div className="gate"><div className="gate-top">Research selector <Pill value={research?.selector_status||"WAITING"} tone={toneFor(research?.selector_status)}/></div><p>{research?.reason||"No strategy selection loaded."}</p></div>
          <div className="gate"><div className="gate-top">Macro gate <Pill value={decision?.macro_risk.level||"WAITING"} tone={toneFor(decision?.macro_risk.level)}/></div><p>{decision?.macro_risk.reason||"No macro context loaded."}</p></div>
        </div>
        {selected && <div className="selected"><strong>Selected research config:</strong> {selected.config_id} · {selected.strategy_family} · gate {selected.gate_status} · statistical {selected.statistical_level}</div>}
      </section>

      <section className="section"><div className="section-title"><span>03</span> Trade plan</div>
        <div className="plan">
          <Metric label="Direction" value={decision?.trade_plan.direction||"NONE"}/>
          <Metric label="Entry" value={fmt(decision?.trade_plan.entry)}/>
          <Metric label="Stop loss" value={fmt(decision?.trade_plan.stop_loss)}/>
          <Metric label="Take profit" value={fmt(decision?.trade_plan.take_profit)}/>
          <Metric label="Risk / reward" value={fmt(decision?.trade_plan.risk_reward,2)}/>
          <Metric label="Position" value={activePosition?.position_size ? fmt(activePosition.position_size,4) : "NOT OPEN"}/>
        </div>
        <div className="reason">{decision?.trade_plan.rejection_reasons?.join(" · ") || (signal==="NO_TRADE" ? "No trade is authorized by the multi-factor signal." : "Signal passed the technical decision stage; the paper engine still performs its own research and risk gates.")}</div>
      </section>

      <section className="section"><div className="section-title"><span>04</span> Persistent paper account</div>
        <div className="metrics">
          <Metric label="Initial equity" value={`$${fmt(runtime?.initial_equity,2)}`}/>
          <Metric label="Realized P&L" value={`$${fmt(runtime?.realized_pnl,2)}`}/>
          <Metric label="Peak equity" value={`$${fmt(runtime?.peak_equity,2)}`}/>
          <Metric label="Open positions" value={String(runtime?.open_positions??"—")}/>
          <Metric label="Broker contacted" value={runtime?.broker_contacted?"YES":"NO"}/>
          <Metric label="Execution" value={runtime?.execution_enabled?"ON":"OFF"}/>
        </div>
        {activePosition && <div className="position"><strong>{activePosition.direction} {activePosition.instrument}</strong> · entry {fmt(activePosition.entry_price)} · stop {fmt(activePosition.stop_price)} · TP {fmt(activePosition.take_profit_price)} · held {activePosition.periods_held} cycles</div>}
      </section>

      <section className="section"><div className="section-title"><span>05</span> Research status</div>
        <div className="boundary"><Pill value={research?.research_gate_status||"WAITING"} tone={toneFor(research?.research_gate_status)}/><p>{research?.research_recommendation||"The research gate determines whether a configuration can progress toward paper trading."}</p></div>
      </section>

      <footer>Tembo · evidence first · fail closed · persistent paper stage · live execution disabled</footer>
    </main>
    <style jsx>{`
      *{box-sizing:border-box} body{margin:0;background:#080a0f;color:#e9edf5;font-family:Inter,ui-sans-serif,system-ui,-apple-system,sans-serif}
      main{min-height:100vh;max-width:1280px;margin:auto;padding:24px}.topbar{display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #202632;padding-bottom:22px}
      .brand{font-size:28px;font-weight:900;letter-spacing:.16em}.subbrand,.eyebrow,.section-title span,label{color:#8993a5;font-size:11px;letter-spacing:.13em;text-transform:uppercase}.subbrand{margin-top:4px}
      .live-state{font-size:11px;letter-spacing:.08em;color:#9ba5b7}.dot{display:inline-block;width:7px;height:7px;border-radius:50%;background:#5ee08b;margin-right:7px}
      .controls{display:flex;align-items:end;gap:12px;padding:22px 0;border-bottom:1px solid #202632}label{display:block;margin-bottom:7px}
      select,button{background:#11151d;border:1px solid #2a3240;color:#edf1f8;border-radius:8px;padding:10px 13px;font:inherit}button{cursor:pointer;font-weight:700}button:disabled{opacity:.5;cursor:default}.refresh-note{margin-left:auto;color:#727d90;font-size:12px;padding-bottom:10px}
      .error{margin-top:18px;padding:13px 15px;border:1px solid #60333a;background:#211217;color:#f2b6bd;border-radius:9px}.hero-grid{display:grid;grid-template-columns:1.3fr 1fr 1fr;gap:14px;padding:22px 0}
      .card{background:#0e1219;border:1px solid #202632;border-radius:12px;padding:22px;min-height:150px}.price{font-size:42px;font-weight:800;margin:18px 0 9px;letter-spacing:-.04em}.signal{font-size:26px;font-weight:800;margin:18px 0 8px}
      .meta,.card p,.gate p,.reason,.boundary p,.selected,.position{color:#8e98a9;font-size:13px;line-height:1.55;margin:0}.section{border-top:1px solid #202632;padding:24px 0}.section-title{font-size:14px;font-weight:800;margin-bottom:15px}.section-title span{margin-right:9px}
      .metrics,.plan{display:grid;grid-template-columns:repeat(6,1fr);gap:10px}.metrics>div,.plan>div{background:#0e1219;border:1px solid #1e2530;border-radius:9px;padding:14px}.metric-label{color:#747f92;font-size:11px;text-transform:uppercase;letter-spacing:.08em}.metric-value{font-weight:750;margin-top:8px;word-break:break-word}
      .gates{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.gate{background:#0e1219;border:1px solid #1e2530;border-radius:9px;padding:15px}.gate-top{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:11px;font-weight:750}
      .pill{display:inline-flex;border:1px solid #344052;border-radius:999px;padding:4px 8px;font-size:10px;font-weight:800;letter-spacing:.07em;text-transform:uppercase}.pill.good{border-color:#2f7650;color:#77e39d;background:#102219}.pill.warn{border-color:#756332;color:#e1c87b;background:#211d11}.pill.bad{border-color:#713a42;color:#ee9ca7;background:#241419}
      .selected,.position{margin-top:12px;background:#0e1219;border:1px solid #1e2530;border-radius:9px;padding:14px}.boundary{background:#0e1219;border:1px solid #25302b;border-radius:9px;padding:17px}
      footer{border-top:1px solid #202632;margin-top:10px;padding:20px 0 30px;color:#697486;font-size:11px;letter-spacing:.08em;text-transform:uppercase}
      @media(max-width:850px){main{padding:16px}.hero-grid,.gates{grid-template-columns:1fr}.metrics,.plan{grid-template-columns:repeat(2,1fr)}.controls{flex-wrap:wrap}.refresh-note{width:100%;margin:0}}
    `}</style>
  </>;
}
