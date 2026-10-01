import { useEffect, useMemo, useState } from "react";
import Head from "next/head";
import { approveAndExecuteDemo, buyDemoContract, getDemoContract, getDemoProposal, sellDemoContract, updateDemoProtection, getDemoProtectionHistory, getDerivMarkets, getDerivStatus, getLiveAnalysis, getLiveDecision, getMarket, getReliabilityRuntime, getReliabilityStatus, getResearchDecision, getRuntimePositions, getRuntimeStatus, getStrategyHealth, getSyntheticSymbols, type DemoBuyResult, type DemoContractResult, type DemoProposal, type DerivMarket, type DerivStatus, type LiveAnalysis, type LiveDecision, type MarketResponse, type ReliabilityRuntime, type ReliabilityStatus, type ResearchDecision, type RuntimePosition, type RuntimeStatus, type StrategyHealth, type SyntheticSymbol } from "../services/api";

const instruments = ["EUR/USD", "GBP/USD", "USD/JPY", "XAU/USD"];
const timeframes = ["m5", "m15", "h1", "h4", "d1"];

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


function CandleChart({ candles, instrument, timeframe, provider, isClean }: { candles: MarketResponse["candles"]; instrument: string; timeframe: string; provider?: string; isClean?: boolean }) {
  const visible = candles.slice(-60);
  if (!visible.length) return <div className="chart-empty">Waiting for verified candle data…</div>;

  const width = 920, height = 360;
  const pad = { top: 18, right: 70, bottom: 34, left: 8 };
  const max = Math.max(...visible.map(c => c.high));
  const min = Math.min(...visible.map(c => c.low));
  const range = Math.max(max - min, Math.abs(max) * 0.00001, 0.0000001);
  const y = (price: number) => pad.top + ((max - price) / range) * (height - pad.top - pad.bottom);
  const step = (width - pad.left - pad.right) / visible.length;
  const bodyWidth = Math.max(3, Math.min(10, step * 0.58));
  const labelEvery = Math.max(1, Math.floor(visible.length / 5));

  return <div className="chart-wrap">
    <div className="chart-head">
      <div><div className="eyebrow">LIVE CANDLESTICK CHART</div><div className="chart-title">{instrument} · {timeframe.toUpperCase()}</div></div>
      <div className="chart-legend"><span><i className="legend-up"/> Bullish</span><span><i className="legend-down"/> Bearish</span><span>{visible.length} completed candles</span></div>
    </div>
    <div className="chart-scroll">
      <svg className="candle-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${instrument} ${timeframe.toUpperCase()} candlestick chart`}>
        {[0, .25, .5, .75, 1].map(ratio => {
          const price = max - range * ratio, yy = y(price);
          return <g key={ratio}><line x1={pad.left} x2={width-pad.right} y1={yy} y2={yy} className="grid-line"/>
            <text x={width-pad.right+10} y={yy+4} className="axis-label">{fmt(price, instrument.includes("XAU/USD") ? 2 : instrument.startsWith("SYNTH:") ? 2 : 5)}</text></g>;
        })}
        {visible.map((c, i) => {
          const x = pad.left + step * i + step / 2;
          const openY = y(c.open), closeY = y(c.close), highY = y(c.high), lowY = y(c.low);
          const bullish = c.close >= c.open, bodyY = Math.min(openY, closeY), bodyH = Math.max(2, Math.abs(closeY-openY));
          return <g key={c.timestamp}>
            <line x1={x} x2={x} y1={highY} y2={lowY} className={bullish ? "wick-up" : "wick-down"}/>
            <rect x={x-bodyWidth/2} y={bodyY} width={bodyWidth} height={bodyH} rx="1" className={bullish ? "body-up" : "body-down"}/>
            {i % labelEvery === 0 && <text x={x} y={height-10} textAnchor="middle" className="time-label">{new Date(c.timestamp).toLocaleTimeString([], {hour:"2-digit", minute:"2-digit"})}</text>}
          </g>;
        })}
      </svg>
    </div>
    <div className="chart-foot">
      <span>Provider: {provider || "—"}</span><span>Data: {isClean ? "VERIFIED" : "CHECKING"}</span>
      <span>Latest completed: {visible.length ? new Date(visible[visible.length-1].timestamp).toLocaleString() : "—"}</span>
    </div>
  </div>;
}


export default function Home() {
  const [instrument,setInstrument]=useState("EUR/USD");
  const [timeframe,setTimeframe]=useState("h1");
  const [synthetics,setSynthetics]=useState<SyntheticSymbol[]>([]);
  const [derivMarkets,setDerivMarkets]=useState<DerivMarket[]>([]);
  const [marketFilter,setMarketFilter]=useState("forex");
  const [derivStatus,setDerivStatus]=useState<DerivStatus|null>(null);
  const [market,setMarket]=useState<MarketResponse|null>(null);
  const [decision,setDecision]=useState<LiveDecision|null>(null);
  const [analysis,setAnalysis]=useState<LiveAnalysis|null>(null);
  const [research,setResearch]=useState<ResearchDecision|null>(null);
  const [runtime,setRuntime]=useState<RuntimeStatus|null>(null);
  const [positions,setPositions]=useState<RuntimePosition[]>([]);
  const [strategyHealth,setStrategyHealth]=useState<StrategyHealth|null>(null);
  const [reliability,setReliability]=useState<ReliabilityStatus|null>(null);
  const [reliabilityRuntime,setReliabilityRuntime]=useState<ReliabilityRuntime|null>(null);
  const [demoStake,setDemoStake]=useState(1);
  const [demoMultiplier,setDemoMultiplier]=useState(10);
  const [demoProposal,setDemoProposal]=useState<DemoProposal|null>(null);
  const [demoBuy,setDemoBuy]=useState<DemoBuyResult|null>(null);
  const [demoContract,setDemoContract]=useState<DemoContractResult|null>(null);
  const [demoAccountBalance,setDemoAccountBalance]=useState<number|null>(null);
  const [demoProtectionHistory,setDemoProtectionHistory]=useState<Record<string, unknown>[]>([]);
  const [demoBusy,setDemoBusy]=useState(false);
  const [demoMessage,setDemoMessage]=useState("");
  const [demoApprovalBusy,setDemoApprovalBusy]=useState(false);
  const [dismissedApproval,setDismissedApproval]=useState<string>("");
  const [error,setError]=useState("");
  const [loading,setLoading]=useState(true);
  const [lastRefresh,setLastRefresh]=useState("");
  const [activityLog,setActivityLog]=useState<Array<{id:string;time:string;instrument:string;timeframe:string;trend:string;momentum:string;volatility:string;signal:string;price:number|null;note:string}>>([]);

  const demoExecutionEligible = Boolean(derivStatus?.connected && decision?.decision && decision.decision !== "NO_TRADE" && decision?.paper_eligibility?.eligible && decision?.paper_eligibility?.execution_enabled === false);
  const approvalKey = decision?.decision && decision?.trade_plan?.entry != null ? `${instrument}|${timeframe}|${decision.decision}|${decision.trade_plan.entry}` : "";
  const approvalDismissed = approvalKey !== "" && dismissedApproval === approvalKey;

  function rejectDemoOpportunity() {
    if (approvalKey) setDismissedApproval(approvalKey);
    setDemoProposal(null);
    setDemoMessage("Opportunity dismissed for this signal. Tembo will continue watching for a new setup.");
  }

  async function requestDemoProposal() {
    if (!demoExecutionEligible) { setDemoMessage("Demo execution is locked until Tembo authorizes the setup."); return; }
    setDemoBusy(true); setDemoMessage(""); setDemoProposal(null);
    try {
      const proposal = await getDemoProposal(instrument, decision!.decision, timeframe, demoStake, demoMultiplier);
      setDemoProposal(proposal); setDemoMessage("Demo proposal received. Nothing has been purchased.");
    } catch (e) { setDemoMessage(e instanceof Error ? e.message : "Unable to obtain a demo proposal."); }
    finally { setDemoBusy(false); }
  }

  async function executeDemoTrade() {
    if (!demoProposal || !demoExecutionEligible) { setDemoMessage("Execution is locked. Pass every Tembo gate first."); return; }
    setDemoBusy(true); setDemoMessage("");
    try {
      const latestDecision = await getLiveDecision(instrument,timeframe);
      if (latestDecision.decision !== decision?.decision || !latestDecision.paper_eligibility.eligible) {
        setDemoProposal(null); setDemoMessage("The decision changed or the trade is no longer eligible. No demo order was sent."); return;
      }
      const result = await buyDemoContract(demoProposal.proposal_id, demoProposal.ask_price, demoProposal.execution_token, timeframe);
      setDemoBuy(result); setDemoContract(null); setDemoAccountBalance(result.balance_after ?? null);
      if (demoProposal.protection?.attached) {
        try {
          await updateDemoProtection(result.contract_id, demoProposal.protection.limit_order.stop_loss ?? null, demoProposal.protection.limit_order.take_profit ?? null);
          setDemoMessage("Demo contract " + result.contract_id + " opened. Broker-side protection synchronized. Real-money execution remains disabled.");
        } catch {
          setDemoMessage("Demo contract " + result.contract_id + " opened with proposal protection. Post-entry synchronization needs attention.");
        }
      } else {
        setDemoMessage("Demo contract " + result.contract_id + " opened. No broker-side protection was attached.");
      }
    } catch (e) { setDemoMessage(e instanceof Error ? e.message : "Demo execution failed safely."); }
    finally { setDemoBusy(false); }
  }

  async function approveAndExecuteTrade() {
    if (!demoExecutionEligible) {
      setDemoMessage("Approval is unavailable: Tembo has not authorized this setup.");
      return;
    }
    setDemoApprovalBusy(true); setDemoMessage(""); setDemoProposal(null);
    try {
      const result = await approveAndExecuteDemo(instrument, decision!.decision, timeframe, demoStake, demoMultiplier);
      setDemoBuy(result); setDemoContract(null); setDemoAccountBalance(result.balance_after ?? null);
      try {
        const status = await getDerivStatus();
        setDerivStatus(status);
        setDemoAccountBalance(status.balance ?? result.balance_after ?? null);
      } catch {}
      setDemoMessage("APPROVED -> BROKER CONFIRMED. Demo contract #" + result.contract_id + " opened. Tembo re-checked the signal immediately before execution.");
      try {
        const current = await getDemoContract(result.contract_id);
        setDemoContract(current);
      } catch {}
    } catch (e) {
      setDemoMessage(e instanceof Error ? e.message : "Approved demo execution failed safely. No order confirmation was received.");
    } finally { setDemoApprovalBusy(false); }
  }

  async function syncDemoProtection() {
    if (!demoBuy?.contract_id || !demoProposal?.protection?.attached) {
      setDemoMessage("No broker-side protection plan is available to sync.");
      return;
    }
    setDemoBusy(true);
    try {
      const result = await updateDemoProtection(
        demoBuy.contract_id,
        demoProposal.protection.limit_order.stop_loss ?? null,
        demoProposal.protection.limit_order.take_profit ?? null,
      );
      setDemoMessage("Broker-side protection synchronized for demo contract " + result.contract_id + ".");
      const refreshed = await getDemoContract(demoBuy.contract_id);
      setDemoContract(refreshed);
      try {
        const history = await getDemoProtectionHistory(demoBuy.contract_id);
        setDemoProtectionHistory(history.history);
      } catch {}
    } catch (e) {
      setDemoMessage(e instanceof Error ? e.message : "Unable to synchronize demo protection.");
    } finally { setDemoBusy(false); }
  }

  async function closeDemoTrade() {
    if (!demoBuy?.contract_id) return;
    setDemoBusy(true);
    try {
      const result = await sellDemoContract(demoBuy.contract_id);
      const soldFor = result.sold_for;
      const buyPrice = demoBuy.buy_price;
      const realized = soldFor != null ? soldFor - buyPrice : null;
      try {
        const finalContract = await getDemoContract(demoBuy.contract_id);
        setDemoContract(finalContract);
        setDemoAccountBalance(finalContract.account_balance ?? null);
      } catch {}
      try {
        const status = await getDerivStatus();
        setDerivStatus(status);
        setDemoAccountBalance(status.balance ?? null);
      } catch {}
      setDemoBuy(null);
      setDemoMessage("Demo contract " + result.contract_id + " closed. Sold for " + String(soldFor ?? "—") + " USD" + (realized != null ? " · realized P/L " + (realized >= 0 ? "+" : "") + realized.toFixed(2) + " USD" : "") + ".");
    } catch (e) { setDemoMessage(e instanceof Error ? e.message : "Unable to close demo contract."); }
    finally { setDemoBusy(false); }
  }
  async function refreshDemoContract() {
    if (!demoBuy?.contract_id) return;
    setDemoBusy(true);
    try {
      const result = await getDemoContract(demoBuy.contract_id);
      const contract = result.contract || {};
      setDemoContract(result);
      setDemoAccountBalance(result.account_balance ?? null);
      try {
        const history = await getDemoProtectionHistory(demoBuy.contract_id);
        setDemoProtectionHistory(history.history);
      } catch {}
      setDemoMessage("Demo contract " + demoBuy.contract_id + ": " + String(contract.status || "UNKNOWN") + ", P&L " + String(contract.profit ?? "—") + " USD.");
    } catch (e) { setDemoMessage(e instanceof Error ? e.message : "Unable to read demo contract."); }
    finally { setDemoBusy(false); }
  }
  useEffect(() => {
    const contractId = demoBuy?.contract_id;
    if (!contractId) return;
    let active = true;
    const poll = async () => {
      try {
        const result = await getDemoContract(contractId);
        if (!active) return;
        setDemoContract(result);
        setDemoAccountBalance(result.account_balance ?? null);
        try {
          const history = await getDemoProtectionHistory(contractId);
          if (active) setDemoProtectionHistory(history.history);
        } catch {}
        // The broker balance is authoritative. Refresh it alongside contract
        // telemetry so realized/unrealized movement is not hidden behind the
        // 15-second cockpit refresh.
        try {
          const status = await getDerivStatus();
          if (active) {
            setDerivStatus(status);
            setDemoAccountBalance(status.balance ?? result.account_balance ?? null);
          }
        } catch {}
        const status = String(result.contract?.status || "").toLowerCase();
        if (["sold","closed","expired"].includes(status) && active) {
          setDemoMessage("Demo contract " + contractId + " is " + status + ". Broker balance has been refreshed.");
        }
      } catch {
        if (active) setDemoMessage("Live demo contract monitor temporarily unavailable.");
      }
    };
    void poll();
    const timer = window.setInterval(() => void poll(), 3000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [demoBuy?.contract_id]);

  async function refreshMarkets() {
    try {
      const result = await getDerivMarkets();
      setDerivMarkets(result.symbols || []);
    } catch {}
  }

  async function refresh() {
    setLoading(true); setError("");
    try {
      const [m,a,d,r,rs,p,ds] = await Promise.all([
        getMarket(instrument,timeframe), getLiveAnalysis(instrument,timeframe), getLiveDecision(instrument,timeframe),
        getResearchDecision(instrument,timeframe), getRuntimeStatus(), getRuntimePositions(), getDerivStatus()
      ]);
      const [shResult, relResult, relRuntimeResult] = await Promise.allSettled([
        getStrategyHealth(instrument,timeframe,a.analysis?.trend?.regime || null),
        getReliabilityStatus(),
        getReliabilityRuntime()
      ]);
      setMarket(m); setAnalysis(a); setDecision(d); setResearch(r); setRuntime(rs); setPositions(p); setDerivStatus(ds); setDemoAccountBalance(ds.balance ?? null);
      const trendState = a.analysis?.trend?.state || "WAITING";
      const momentumState = a.analysis?.analysis?.momentum?.state || "—";
      const volatilityState = a.analysis?.analysis?.volatility?.state || "—";
      const currentSignal = d.decision || "NO_TRADE";
      const currentPrice = m.current_price ?? m.candles?.[m.candles.length - 1]?.close ?? null;
      const candle = m.candles?.[m.candles.length - 1];
      const candleDirection = candle ? (candle.close >= candle.open ? "BULLISH" : "BEARISH") : "WAITING";
      const botNote = currentSignal === "NO_TRADE"
        ? `Watching ${candleDirection.toLowerCase()} price action; waiting for all decision gates to align.`
        : `Opportunity detected: ${currentSignal}. Awaiting your demo approval before any broker order.`;
      const activityId = `${instrument}|${timeframe}|${currentSignal}|${currentPrice ?? "—"}|${trendState}|${momentumState}|${volatilityState}`;
      const activityItem = { id: activityId, time: new Date().toLocaleTimeString(), instrument, timeframe, trend: trendState, momentum: momentumState, volatility: volatilityState, signal: currentSignal, price: currentPrice, note: botNote };
      setActivityLog(prev => prev[0]?.id === activityId ? prev : [activityItem, ...prev].slice(0, 30));
      if (shResult.status === "fulfilled") setStrategyHealth(shResult.value);
      if (relResult.status === "fulfilled") setReliability(relResult.value);
      if (relRuntimeResult.status === "fulfilled") setReliabilityRuntime(relRuntimeResult.value);
      setLastRefresh(new Date().toLocaleTimeString());
    } catch(e) { setError(e instanceof Error ? e.message : "Unable to load Tembo data."); }
    finally { setLoading(false); }
  }
  useEffect(()=>{ void refresh(); },[instrument,timeframe]);
  useEffect(()=>{ void getSyntheticSymbols().then(r=>setSynthetics(r.symbols)).catch(()=>setSynthetics([])); void getDerivStatus().then(setDerivStatus).catch(()=>setDerivStatus(null)); void refreshMarkets(); },[]);
  useEffect(()=>{ const timer = window.setInterval(()=>{ void refresh(); void refreshMarkets(); }, 15000); return ()=>window.clearInterval(timer); },[instrument,timeframe]);

  const latest = useMemo(()=>market?.candles?.[market.candles.length-1], [market]);
  const signal = decision?.decision || "NO_TRADE";
  const selected = research?.selected_config;
  const activePosition = positions.find(p=>p.instrument===instrument && p.timeframe===timeframe);
  const filteredMarkets = useMemo(() => derivMarkets.filter(m => {
    const type = String(m.underlying_symbol_type || "").toLowerCase();
    const market = String(m.market || "").toLowerCase();
    if (marketFilter === "forex") return type === "forex" || market === "forex";
    if (marketFilter === "metals") return type.includes("metal") || type.includes("commod") || market.includes("metal") || market.includes("commod");
    return type.includes("synthetic") || type.includes("index") || market.includes("synthetic") || market.includes("derived");
  }).slice(0,32), [derivMarkets, marketFilter]);

  return <>
    <Head><title>Tembo Forex Bot — Multi-Market Cockpit</title><meta name="description" content="Tembo live-data paper trading cockpit"/></Head>
    <main>
      <header className="topbar">
        <div><div className="brand">TEMBO</div><div className="subbrand">LIVE-DATA · CONTROLLED DEMO EXECUTION COCKPIT</div></div>
        <div className="live-state"><span className="dot"/> PAPER ONLY • BROKER OFF<div className="broker-chip"><span className={derivStatus?.connected ? "broker-dot on" : "broker-dot"}/>DERIV {derivStatus?.connected ? "DEMO CONNECTED" : derivStatus?.configured ? "CHECKING" : "NOT CONFIGURED"}</div></div>
      </header>

      <section className="controls">
        <div><label>Instrument</label><select value={instrument} onChange={e=>setInstrument(e.target.value)}>
          <optgroup label="Forex / Gold">{instruments.map(x=><option key={x}>{x}</option>)}</optgroup>
          {synthetics.length > 0 && <optgroup label="Deriv Synthetic Indices">{synthetics.map(x=><option key={x.symbol} value={x.symbol}>{x.display_name}</option>)}</optgroup>}
        </select></div>
        <div><label>Timeframe</label><select value={timeframe} onChange={e=>setTimeframe(e.target.value)}>{timeframes.map(x=><option key={x}>{x.toUpperCase()}</option>)}</select></div>
        <button onClick={()=>void refresh()} disabled={loading}>{loading?"Refreshing…":"Refresh"}</button>
        <div className="refresh-note">{lastRefresh?`Updated ${lastRefresh}`:"Waiting for data"}</div>
      </section>

      {error && <div className="error"><strong>Data unavailable.</strong> {error}</div>}

      <section className="hero-grid">
        <div className="card"><div className="eyebrow">LIVE MARKET</div><div className="price">{fmt(market?.current_price ?? latest?.close, market?.instrument_metadata?.pip_size && market.instrument_metadata.pip_size < 0.01 ? 5 : instrument.includes("XAU/USD") ? 2 : 5)}</div><div className="meta">{market?.instrument_metadata?.display_name || instrument} · {timeframe.toUpperCase()} · {market?.provider||"—"} · {market?.data_quality.is_clean?"candles verified":"verification pending"}</div></div>
        <div className="card"><div className="eyebrow">SIGNAL</div><div className="signal">{signal}</div><p>{decision?.methodology||"Waiting for verified market evidence."}</p></div>
        <div className="card"><div className="eyebrow">PAPER RUNTIME</div><div className="signal">{runtime?.status||"—"}</div><p>Last cycle: {runtime?.last_cycle_at ? new Date(runtime.last_cycle_at).toLocaleString() : "—"}</p></div>
      </section>

      <section className="section market-chart-section">
        <div className="section-title"><span>01</span> Market candles</div>
        <CandleChart candles={market?.candles || []} instrument={market?.instrument_metadata?.display_name || instrument} timeframe={timeframe} provider={market?.provider} isClean={market?.data_quality.is_clean}/>
      </section>

      <section className="section guidance-section"><div className="section-title"><span>02</span> Tembo Forex Bot Guidance</div>
        <div className="guidance-header">
          <div>
            <div className="guidance-kicker">AI-ASSISTED MARKET GUIDANCE</div>
            <h2>{signal === "NO_TRADE" ? "WAIT — Tembo is not authorizing a trade" : `Tembo sees a ${signal} setup`}</h2>
            <p>{decision?.methodology || "Tembo is waiting for verified market evidence before giving guidance."}</p>
          </div>
          <div className={`decision-badge ${signal === "NO_TRADE" ? "wait" : signal === "BUY" ? "buy" : "sell"}`}>{signal}</div>
        </div>

        <div className="guidance-metrics">
          <div className="guidance-metric"><span>Market</span><strong>{market?.instrument_metadata?.display_name || instrument}</strong><small>{timeframe.toUpperCase()} · {market?.provider || "—"}</small></div>
          <div className="guidance-metric"><span>Data quality</span><strong>{market?.data_quality?.is_clean ? "VERIFIED" : "CHECKING"}</strong><small>{decision?.data_quality?.candle_count ?? 0} completed candles</small></div>
          <div className="guidance-metric"><span>Entry</span><strong>{fmt(decision?.trade_plan?.entry, instrument.includes("XAU/USD") || instrument.startsWith("SYNTH:") ? 2 : 5)}</strong><small>Proposed only</small></div>
          <div className="guidance-metric"><span>Stop loss</span><strong>{fmt(decision?.trade_plan?.stop_loss, instrument.includes("XAU/USD") || instrument.startsWith("SYNTH:") ? 2 : 5)}</strong><small>Risk boundary</small></div>
          <div className="guidance-metric"><span>Take profit</span><strong>{fmt(decision?.trade_plan?.take_profit, instrument.includes("XAU/USD") || instrument.startsWith("SYNTH:") ? 2 : 5)}</strong><small>Target</small></div>
          <div className="guidance-metric"><span>Risk / reward</span><strong>{fmt(decision?.trade_plan?.risk_reward,2)}</strong><small>From current trade plan</small></div>
        </div>

        <div className="guidance-grid">
          <div className="guidance-card"><div className="guidance-card-title">Market reading</div>
            <div className="guidance-big">{analysis?.analysis?.trend?.state || "WAITING"}</div>
            <p>{analysis?.analysis?.trend?.regime || "Tembo is waiting for verified trend evidence."}</p>
            <div className="guidance-row"><span>Momentum</span><b>{analysis?.analysis?.momentum?.state || "—"}</b></div>
            <div className="guidance-row"><span>Volatility</span><b>{analysis?.analysis?.volatility?.state || "—"}</b></div>
            <div className="guidance-row"><span>Structure</span><b>{(analysis?.analysis?.market_structure?.label || "—").replaceAll("_"," ")}</b></div>
          </div>
          <div className="guidance-card"><div className="guidance-card-title">Key levels</div>
            <div className="level-row"><span>Resistance</span><strong>{fmt(analysis?.analysis?.support_resistance?.resistance, instrument.includes("XAU/USD") || instrument.startsWith("SYNTH:") ? 2 : 5)}</strong></div>
            <div className="level-row"><span>Current price</span><strong>{fmt(market?.current_price ?? latest?.close, instrument.includes("XAU/USD") || instrument.startsWith("SYNTH:") ? 2 : 5)}</strong></div>
            <div className="level-row"><span>Support</span><strong>{fmt(analysis?.analysis?.support_resistance?.support, instrument.includes("XAU/USD") || instrument.startsWith("SYNTH:") ? 2 : 5)}</strong></div>
            <p className="guidance-muted">Levels come from the verified market-analysis response.</p>
          </div>
          <div className="guidance-card"><div className="guidance-card-title">Risk & gates</div>
            <div className="gate-line"><span>Research</span><Pill value={research?.research_gate_status || "WAITING"} tone={toneFor(research?.research_gate_status || undefined)}/></div>
            <div className="gate-line"><span>Strategy selector</span><Pill value={decision?.strategy_gate?.status || "WAITING"} tone={toneFor(decision?.strategy_gate?.status || undefined)}/></div>
            <div className="gate-line"><span>Macro risk</span><Pill value={decision?.macro_risk?.level || "WAITING"} tone={toneFor(decision?.macro_risk?.level || undefined)}/></div>
            <div className="gate-line"><span>Risk engine</span><Pill value={decision?.risk?.state || "NOT RUN"} tone={toneFor(decision?.risk?.state || undefined)}/></div>
            <div className="gate-line"><span>Paper eligibility</span><Pill value={decision?.paper_eligibility?.status || "WAITING"} tone={toneFor(decision?.paper_eligibility?.status || undefined)}/></div>
            <p className="guidance-muted">Tembo fails closed: weak, unavailable, or unverified inputs cannot authorize execution.</p>
          </div>
        </div>

        <div className="guidance-plan">
          <div><div className="guidance-card-title">Tembo's guidance</div>
            <p>{decision?.trade_plan?.rejection_reasons?.length ? decision.trade_plan.rejection_reasons.join(" · ") : signal === "NO_TRADE" ? "Wait for a validated setup. Tembo will not manufacture a trade when the evidence or research gate is insufficient." : "Review the entry, stop, target and risk controls shown above. This remains a paper-stage decision until every execution gate passes."}</p>
            <div className="guidance-row"><span>Risk allocation</span><b>{decision?.risk?.computed_risk_pct != null ? `${decision.risk.computed_risk_pct.toFixed(2)}%` : "NOT RUN"}</b></div>
            <div className="guidance-row"><span>Position size</span><b>{decision?.risk?.position_size != null ? fmt(decision.risk.position_size,4) : "NOT RUN"}</b></div>
            <div className="guidance-row"><span>News feed</span><b>{decision?.news?.status || "WAITING"}</b></div>
            <div className="guidance-row"><span>Macro events in window</span><b>{String(decision?.macro_events?.length ?? 0)}</b></div>
          </div>
          <div className="guidance-warning">PAPER MODE · BROKER OFF</div>
        </div>
        <div className="guidance-news-grid">
          <div className="guidance-card"><div className="guidance-card-title">News impact</div>
            <p>{decision?.news?.status === "UNAVAILABLE" ? "News feed unavailable; Tembo does not treat missing news as confirmation." : decision?.news?.headlines?.length ? decision.news.headlines[0].headline : "No relevant headline returned for this instrument."}</p>
            <div className="guidance-muted">{decision?.news?.provider || "—"} · {decision?.news?.freshness || "—"}</div>
          </div>
          <div className="guidance-card"><div className="guidance-card-title">Macro calendar</div>
            {(decision?.macro_events || []).slice(0,3).map(event => <div className="gate-line" key={event.event_id}><span>{event.currency} · {event.event_name}</span><Pill value={event.importance} tone={toneFor(event.importance)}/></div>)}
            {!decision?.macro_events?.length && <p>No upcoming macro events were returned for the current decision window.</p>}
          </div>
        </div>
      </section>

      <section className="section market-monitor-section">
        <div className="section-title"><span>03</span> Tembo live market monitor</div>
        <div className="market-monitor-head">
          <div>
            <div className="market-monitor-kicker">WHAT TEMBO IS SEEING RIGHT NOW</div>
            <h2>{market?.instrument_metadata?.display_name || instrument} · {timeframe.toUpperCase()}</h2>
            <p>Tembo continuously reads the verified market feed, updates the technical state and records what the bot is currently observing. This panel is informational; approval is still required before a demo order.</p>
          </div>
          <div className={signal === "NO_TRADE" ? "monitor-action wait" : "monitor-action opportunity"}>
            {signal === "NO_TRADE" ? "SCANNING / WAITING" : "OPPORTUNITY DETECTED"}
          </div>
        </div>
        <div className="monitor-grid">
          <div><span>Market direction</span><strong>{analysis?.analysis?.trend?.state || "WAITING"}</strong><small>{analysis?.analysis?.trend?.regime || "No verified trend state yet."}</small></div>
          <div><span>Momentum</span><strong>{analysis?.analysis?.momentum?.state || "—"}</strong><small>Current momentum reading</small></div>
          <div><span>Volatility</span><strong>{analysis?.analysis?.volatility?.state || "—"}</strong><small>Current volatility state</small></div>
          <div><span>Structure</span><strong>{(analysis?.analysis?.market_structure?.label || "—").replaceAll("_"," ")}</strong><small>Market structure</small></div>
          <div><span>Current price</span><strong>{fmt(market?.current_price ?? latest?.close, instrument.includes("XAU/USD") || instrument.startsWith("SYNTH:") ? 2 : 5)}</strong><small>{market?.provider || "—"} · {market?.data_quality?.is_clean ? "verified" : "checking"}</small></div>
          <div><span>Bot decision</span><strong>{signal}</strong><small>{decision?.paper_eligibility?.status || "Waiting for gates"}</small></div>
        </div>
        <div className="monitor-log">
          <div className="monitor-log-head"><div><div className="guidance-card-title">LIVE BOT ACTIVITY</div><p>Newest observations appear at the top.</p></div><span>{activityLog.length} observations</span></div>
          {activityLog.length ? activityLog.slice(0,10).map(item => (
            <div className="monitor-event" key={item.id}>
              <div className="monitor-time">{item.time}</div>
              <div className="monitor-event-main">
                <strong>{item.instrument} · {item.timeframe.toUpperCase()} · {item.signal}</strong>
                <span>Trend {item.trend} · Momentum {item.momentum} · Volatility {item.volatility} · Price {fmt(item.price, item.instrument.includes("XAU/USD") || item.instrument.startsWith("SYNTH:") ? 2 : 5)}</span>
                <small>{item.note}</small>
              </div>
            </div>
          )) : <div className="monitor-empty">Waiting for the first verified market observation…</div>}
        </div>
      </section>

            <section className="section demo-execution-section">
        <div className="section-title"><span>03</span> Demo execution desk</div>
        {demoExecutionEligible && !approvalDismissed && !demoBuy && (
          <div className="demo-approval-banner">
            <div>
              <div className="guidance-card-title">TEMBO OPPORTUNITY · YOUR PERMISSION REQUIRED</div>
              <strong>Tembo has detected a {signal} setup on {instrument} · {timeframe.toUpperCase()}.</strong>
              <p>Review the entry, stop loss, take profit and risk gates above. Nothing is sent to Deriv until you explicitly approve it.</p>
            </div>
            <div className="demo-actions">
              <button className="primary-button" onClick={()=>void approveAndExecuteTrade()} disabled={demoApprovalBusy}>{demoApprovalBusy ? "Executing…" : "APPROVE DEMO TRADE"}</button>
              <button className="secondary-button" onClick={rejectDemoOpportunity} disabled={demoApprovalBusy}>REJECT / WAIT</button>
            </div>
          </div>
        )}
        <div className="demo-execution-grid">
          <div className="demo-execution-card">
            <div className="guidance-card-title">CONTROLLED DERIV DEMO</div>
            <h3>{demoExecutionEligible ? "Tembo has authorized a " + signal + " demo setup" : "Demo execution is locked"}</h3>
            <p className="guidance-muted">The server re-checks the live decision immediately before purchase. This desk cannot use a real-money account.</p>
            <div className="demo-controls">
              <label>Stake (USD)<input type="number" min="0.01" max="10" step="0.01" value={demoStake} onChange={e=>setDemoStake(Math.min(10,Math.max(0.01,Number(e.target.value)||0.01)))} /></label>
              <label>Multiplier<input type="number" min="1" max="50" step="1" value={demoMultiplier} onChange={e=>setDemoMultiplier(Math.min(50,Math.max(1,Number(e.target.value)||1)))} /></label>
            </div>
            <div className="demo-actions">
              <button className="secondary-button" onClick={()=>void requestDemoProposal()} disabled={demoBusy || demoApprovalBusy || !demoExecutionEligible}>{demoBusy?"Preparing…":"Preview broker quote"}</button>
              <button className="primary-button" onClick={()=>void approveAndExecuteTrade()} disabled={demoBusy || demoApprovalBusy || !demoExecutionEligible}>{demoApprovalBusy?"Executing…":"APPROVE & EXECUTE DEMO"}</button>
              {demoBuy && demoProposal?.protection?.attached && <button className="secondary-button" onClick={()=>void syncDemoProtection()} disabled={demoBusy || demoApprovalBusy}>Sync protection</button>}
              {demoBuy && <button className="secondary-button" onClick={()=>void refreshDemoContract()} disabled={demoBusy || demoApprovalBusy}>Refresh contract</button>}
              {demoBuy && <button className="secondary-button" onClick={()=>void closeDemoTrade()} disabled={demoBusy || demoApprovalBusy}>Close demo</button>}
            </div>
            <div className="demo-message">The primary button is the approval event: Tembo re-checks the selected <strong>{instrument} · {timeframe.toUpperCase()}</strong> signal on the server, obtains a fresh Deriv quote, and only then buys the demo contract.</div>
            {demoProposal && <div className="demo-proposal">
              <span>Proposal {demoProposal.proposal_id}</span>
              <span>Ask ${demoProposal.ask_price.toFixed(2)}</span>
              <span>Spot {demoProposal.spot == null ? "—" : demoProposal.spot}</span>
              <span>{demoProposal.contract_type} ×{demoProposal.multiplier}</span>
              <span>Protection {demoProposal.protection?.attached ? "ATTACHED" : "NOT ATTACHED"}</span>
            </div>}
            {demoBuy && <div className="demo-open">DEMO CONTRACT #{demoBuy.contract_id} · BUY ${demoBuy.buy_price.toFixed(2)} · BROKER CONFIRMED</div>}
            {demoBuy && <div className="demo-proposal">
              <span>Broker balance {derivStatus?.balance == null ? "—" : "$" + Number(derivStatus.balance).toFixed(2)}</span>
              <span>Stake ${demoStake.toFixed(2)}</span>
              <span>Open positions {String(derivStatus?.open_positions ?? (demoBuy ? 1 : 0))}</span>
              <span>Monitoring every 3s</span>
            </div>}
            {demoProposal?.protection?.attached && <div className="demo-message">Broker-side demo protection attached from Tembo's price plan: SL loss ${demoProposal.protection.limit_order.stop_loss ?? "—"} · TP profit ${demoProposal.protection.limit_order.take_profit ?? "—"}.</div>}
            {demoProtectionHistory.length > 0 && <div className="demo-message">Deriv confirmation: {demoProtectionHistory.slice(-2).map((x:any)=>String(x.order_type || x.display_name || "protection").replaceAll("_"," ")).join(" · ")}.</div>}
            {demoContract?.contract && <div className="demo-proposal">
              <span>Status {String(demoContract.contract.status || "—")}</span>
              <span>P&amp;L {demoContract.contract.profit != null ? "$" + String(demoContract.contract.profit) : "—"}</span>
              <span>Bid {String(demoContract.contract.bid_price ?? "—")}</span>
              <span>Spot {String(demoContract.contract.current_spot ?? "—")}</span>
              <span>Entry {String(demoContract.contract.entry_spot ?? "—")}</span>
              <span>Broker {demoContract.broker_confirmed ? "CONFIRMED" : "—"}</span>
              <span>Balance {demoContract.account_balance == null ? "—" : "$" + demoContract.account_balance.toFixed(2)}</span>
              <span>SL {String((demoContract.contract as Record<string, unknown>).stop_loss ?? demoProposal?.protection?.limit_order.stop_loss ?? "—")}</span>
              <span>TP {String((demoContract.contract as Record<string, unknown>).take_profit ?? demoProposal?.protection?.limit_order.take_profit ?? "—")}</span>
            </div>}
            {demoMessage && <div className="demo-message">{demoMessage}</div>}
          </div>
          <div className="demo-gate-card">
            <div className="guidance-card-title">EXECUTION GATES</div>
            <div className="gate-line"><span>Deriv demo</span><Pill value={derivStatus?.connected ? "CONNECTED" : "NOT CONNECTED"} tone={derivStatus?.connected ? "good" : "bad"}/></div>
            <div className="gate-line"><span>Tembo signal</span><Pill value={signal} tone={signal === "NO_TRADE" ? "bad" : "good"}/></div>
            <div className="gate-line"><span>Paper eligibility</span><Pill value={decision?.paper_eligibility?.status || "WAITING"} tone={toneFor(decision?.paper_eligibility?.status)}/></div>
            <div className="gate-line"><span>Broker mode</span><Pill value="DEMO ONLY" tone="warn"/></div>
            <div className="gate-line"><span>Demo balance</span><strong>{derivStatus?.balance == null ? "—" : "$" + Number(derivStatus.balance).toFixed(2)}</strong></div>
            <div className="gate-line"><span>Open demo positions</span><strong>{String(derivStatus?.open_positions ?? 0)}</strong></div>
            <div className="gate-line"><span>Real-money execution</span><Pill value="DISABLED" tone="good"/></div>
            <p className="guidance-muted">No browser credentials are used. The server holds the Deriv credentials and enforces demo-only mode.</p>
          </div>
        </div>
      </section>
<section className="section"><div className="section-title"><span>02</span> Live analysis</div>
        <div className="analysis-grid">
          <div className="analysis-card"><div className="analysis-label">Market state</div><div className="analysis-main">{analysis?.analysis?.trend?.state || "WAITING"}</div><div className="analysis-sub">{analysis?.analysis?.trend?.regime || analysis?.status || "No verified analysis yet."}</div></div>
          <div className="analysis-card"><div className="analysis-label">Momentum</div><div className="analysis-main">{analysis?.analysis?.momentum?.state || "—"}</div><div className="analysis-sub">RSI 14: {fmt(analysis?.analysis?.momentum?.rsi_14,2)}</div></div>
          <div className="analysis-card"><div className="analysis-label">Volatility</div><div className="analysis-main">{analysis?.analysis?.volatility?.state || "—"}</div><div className="analysis-sub">ATR: {fmt(analysis?.analysis?.volatility?.atr_14, market?.instrument_metadata?.pip_size && market.instrument_metadata.pip_size < 0.01 ? 5 : 2)} · {fmt(analysis?.analysis?.volatility?.atr_percent,4)}%</div></div>
          <div className="analysis-card"><div className="analysis-label">Structure</div><div className="analysis-main">{(analysis?.analysis?.market_structure?.label || "—").replaceAll("_"," ")}</div><div className="analysis-sub">Confirmed swing structure only</div></div>
        </div>
        <div className="analysis-grid analysis-grid-wide">
          <div className="analysis-card"><div className="analysis-label">Support / resistance</div><div className="levels"><span>Support <b>{fmt(analysis?.analysis?.support_resistance?.support, market?.instrument_metadata?.pip_size && market.instrument_metadata.pip_size < 0.01 ? 5 : 2)}</b></span><span>Resistance <b>{fmt(analysis?.analysis?.support_resistance?.resistance, market?.instrument_metadata?.pip_size && market.instrument_metadata.pip_size < 0.01 ? 5 : 2)}</b></span></div><div className="analysis-sub">Recent range: {fmt(analysis?.analysis?.support_resistance?.rolling_range, market?.instrument_metadata?.pip_size && market.instrument_metadata.pip_size < 0.01 ? 5 : 2)}</div></div>
          <div className="analysis-card"><div className="analysis-label">Candlestick evidence</div><div className="pattern-list">{(analysis?.analysis?.candlestick_patterns || []).slice(-4).map((p,i)=><span key={i} className="pattern">{String(p.name || p.pattern || "Pattern")} {p.direction ? "· "+String(p.direction) : ""}</span>)}{!analysis?.analysis?.candlestick_patterns?.length && <span className="analysis-sub">No confirmed pattern reported.</span>}</div></div>
        </div>
        <div className="analysis-note"><strong>How Tembo uses this:</strong> this panel describes verified completed-candle conditions. It does not turn technical context into a trade by itself; the decision, strategy, macro, and risk gates below remain authoritative. {analysis?.analysis?.as_of ? "Analysis as of "+new Date(analysis.analysis.as_of).toLocaleString()+"." : ""}</div>
      </section>

      <section className="section"><div className="section-title"><span>03</span> Evidence</div>
        <div className="metrics">
          <Metric label="Candle count" value={String(decision?.data_quality.candle_count??"—")}/>
          <Metric label="Macro risk" value={decision?.macro_risk.level||"—"}/>
          <Metric label="Research gate" value={research?.research_gate_status||"—"}/>
          <Metric label="Selector" value={research?.selector_status||"—"}/>
          <Metric label="Decision" value={signal}/>
          <Metric label="Data" value={decision?.data_quality.is_clean?"VERIFIED":"REJECTED"}/>
        </div>
      </section>

      <section className="section"><div className="section-title"><span>04</span> Strategy health</div>
        <div className="strategy-health">
          <div className="strategy-health-summary">
            <div>
              <div className="eyebrow">RESEARCH REGISTRY · READ ONLY</div>
              <h3>{strategyHealth?.status ? strategyHealth.status.replaceAll("_"," ") : "WAITING FOR RESEARCH STATE"}</h3>
              <p>{strategyHealth?.reason || "Tembo is checking the research registry against the current market regime."}</p>
            </div>
            <Pill value={strategyHealth?.status || "WAITING"} tone={toneFor(strategyHealth?.status)}/>
          </div>
          <div className="strategy-health-grid">
            <div><span>Current regime</span><strong>{strategyHealth?.current_regime || analysis?.analysis?.trend?.regime || "—"}</strong></div>
            <div><span>Selected config</span><strong>{strategyHealth?.selected_config_id || "NONE"}</strong></div>
            <div><span>Research action</span><strong>{strategyHealth?.research_recommendation || "No additional action returned."}</strong></div>
          </div>
          <div className="strategy-candidates">
            {(strategyHealth?.considered || []).map(candidate => <div className="strategy-candidate" key={candidate.config_id}>
              <div><b>{candidate.config_id}</b><Pill value={candidate.gate_status} tone={toneFor(candidate.gate_status)}/></div>
              <p>{candidate.reason}</p>
            </div>)}
            {!strategyHealth?.considered?.length && <div className="strategy-candidate"><p>No researched configuration has been returned for this instrument/timeframe.</p></div>}
          </div>
        </div>
      </section>

      <section className="section"><div className="section-title"><span>05</span> Reliability & guardrails</div>
        <div className="reliability-panel">
          <div className="reliability-summary">
            <div>
              <div className="eyebrow">RUNTIME SAFETY · READ ONLY</div>
              <h3>{reliabilityRuntime?.governor ? reliabilityRuntime.governor.replaceAll("_"," ") : "WAITING FOR RUNTIME STATE"}</h3>
              <p>{reliabilityRuntime?.reason || reliability?.policy || "Tembo is checking deployed reliability guardrails."}</p>
            </div>
            <Pill value={reliabilityRuntime?.governor || reliability?.status || "WAITING"} tone={toneFor(reliabilityRuntime?.governor || reliability?.status)}/>
          </div>
          <div className="reliability-grid">
            <div><span>Drawdown</span><strong>{reliabilityRuntime?.drawdown_pct != null ? `${reliabilityRuntime.drawdown_pct.toFixed(2)}%` : "—"}</strong></div>
            <div><span>Size multiplier</span><strong>{reliabilityRuntime?.size_multiplier != null ? `${(reliabilityRuntime.size_multiplier * 100).toFixed(0)}%` : "—"}</strong></div>
            <div><span>Execution</span><strong>{reliability?.execution || "—"}</strong></div>
            <div><span>Policy</span><strong>{reliability?.policy || "—"}</strong></div>
          </div>
          <div className="guardrail-list">
            {(reliability?.guardrails || []).map(item => <span className="guardrail-chip" key={item}>{item.replaceAll("_"," ")}</span>)}
          </div>
          <p className="reliability-note">Diagnostics do not place trades or alter the paper account. Drawdown uses the persisted runtime's initial equity plus realized P&L; unrealized P&L is not represented by this diagnostic.</p>
        </div>
      </section>

      <section className="section"><div className="section-title"><span>06</span> Safety chain</div>
        <div className="gates">
          <div className="gate"><div className="gate-top">Market validation <Pill value={decision?.data_quality.is_clean?"AVAILABLE":"UNAVAILABLE"} tone={toneFor(decision?.data_quality.is_clean?"AVAILABLE":"UNAVAILABLE")}/></div><p>Only validated completed candles can reach the decision engine.</p></div>
          <div className="gate"><div className="gate-top">Research selector <Pill value={research?.selector_status||"WAITING"} tone={toneFor(research?.selector_status)}/></div><p>{research?.reason||"No strategy selection loaded."}</p></div>
          <div className="gate"><div className="gate-top">Macro gate <Pill value={decision?.macro_risk.level||"WAITING"} tone={toneFor(decision?.macro_risk.level)}/></div><p>{decision?.macro_risk.reason||"No macro context loaded."}</p></div>
        </div>
        {selected && <div className="selected"><strong>Selected research config:</strong> {selected.config_id} · {selected.strategy_family} · gate {selected.gate_status} · statistical {selected.statistical_level}</div>}
      </section>

      <section className="section"><div className="section-title"><span>07</span> Trade plan</div>
        <div className="plan">
          <Metric label="Direction" value={decision?.trade_plan?.direction||"NONE"}/>
          <Metric label="Entry" value={fmt(decision?.trade_plan?.entry)}/>
          <Metric label="Stop loss" value={fmt(decision?.trade_plan?.stop_loss)}/>
          <Metric label="Take profit" value={fmt(decision?.trade_plan?.take_profit)}/>
          <Metric label="Risk / reward" value={fmt(decision?.trade_plan?.risk_reward,2)}/>
          <Metric label="Position" value={activePosition?.position_size ? fmt(activePosition.position_size,4) : "NOT OPEN"}/>
        </div>
        <div className="reason">{decision?.trade_plan?.rejection_reasons?.join(" · ") || (signal==="NO_TRADE" ? "No trade is authorized by the multi-factor signal." : "Signal passed the technical decision stage; the paper engine still performs its own research and risk gates.")}</div>
      </section>

      <section className="section"><div className="section-title"><span>08</span> Persistent paper account</div>
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

      <section className="section"><div className="section-title"><span>09</span> Research status</div>
        <div className="boundary"><Pill value={research?.research_gate_status||"WAITING"} tone={toneFor(research?.research_gate_status)}/><p>{research?.research_recommendation||"The research gate determines whether a configuration can progress toward paper trading."}</p></div>
      </section>

      <footer>Tembo · evidence first · fail closed · persistent paper stage · live execution disabled</footer>
    </main>
    <style jsx>{`
      *{box-sizing:border-box} body{margin:0;background:#080a0f;color:#e9edf5;font-family:Inter,ui-sans-serif,system-ui,-apple-system,sans-serif}
      main{min-height:100vh;max-width:1280px;margin:auto;padding:24px}.topbar{display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #202632;padding-bottom:22px}
      .brand{font-size:28px;font-weight:900;letter-spacing:.16em}.subbrand,.eyebrow,.section-title span,label{color:#8993a5;font-size:11px;letter-spacing:.13em;text-transform:uppercase}.subbrand{margin-top:4px}
      .live-state{font-size:11px;letter-spacing:.08em;color:#9ba5b7}.broker-chip{margin-top:8px;color:#7f899b;font-size:10px;letter-spacing:.08em;text-transform:uppercase}.broker-dot{display:inline-block;width:7px;height:7px;border-radius:50%;background:#6a7180;margin-right:6px}.broker-dot.on{background:#5ee08b}.dot{display:inline-block;width:7px;height:7px;border-radius:50%;background:#5ee08b;margin-right:7px}
      .market-watch{background:#0b0f15;border:1px solid #202632;border-radius:12px;padding:16px;margin:18px 0 0}.market-watch-head{display:flex;justify-content:space-between;align-items:center;gap:12px}.market-watch-title{font-size:18px;font-weight:800;margin-top:5px}.market-filter{display:flex;gap:6px}.market-filter button{font-size:10px;text-transform:uppercase;letter-spacing:.06em;padding:7px 9px}.market-filter .active-filter{border-color:#3c7658;background:#102219;color:#78dfa0}.market-list{display:grid;grid-template-columns:repeat(4,1fr);gap:7px;margin-top:12px;max-height:310px;overflow:auto}.market-row{display:flex;justify-content:space-between;align-items:center;text-align:left;gap:8px;background:#0e1219;border:1px solid #1d2530;border-radius:8px;padding:10px;color:#dfe5ef}.market-row:hover,.selected-market{border-color:#3b6e54;background:#101c17}.market-row b{display:block;font-size:12px}.market-row small{display:block;color:#667184;font-size:9px;margin-top:3px}.market-open{color:#67d995;font-size:8px;font-weight:800}.market-closed{color:#777f8c;font-size:8px;font-weight:800}.market-empty{grid-column:1/-1;color:#737f91;font-size:12px;padding:18px}.active-filter{color:#fff}
      .instrument-tabs{display:flex;gap:4px;overflow-x:auto;padding:14px 0;border-bottom:1px solid #202632}.instrument-tabs button{border:0;border-radius:7px;background:transparent;color:#717d90;font-size:11px;padding:9px 12px;white-space:nowrap}.instrument-tabs button:hover,.instrument-tabs .instrument-active{background:#111a16;color:#e8f0eb}.instrument-active{border-bottom:1px solid #4fbd7b!important}.tab-dot{display:inline-block;width:5px;height:5px;border-radius:50%;background:#596272;margin-right:7px}.tab-dot.active{background:#63d894}.controls{display:flex;align-items:end;gap:12px;padding:18px 0;border-bottom:1px solid #202632}label{display:block;margin-bottom:7px}
      select,button{background:#11151d;border:1px solid #2a3240;color:#edf1f8;border-radius:8px;padding:10px 13px;font:inherit}button{cursor:pointer;font-weight:700}button:disabled{opacity:.5;cursor:default}.refresh-note{margin-left:auto;color:#727d90;font-size:12px;padding-bottom:10px}
      .error{margin-top:18px;padding:13px 15px;border:1px solid #60333a;background:#211217;color:#f2b6bd;border-radius:9px}.hero-grid{display:grid;grid-template-columns:1.3fr 1fr 1fr;gap:14px;padding:22px 0}
      .card{background:#0e1219;border:1px solid #202632;border-radius:12px;padding:22px;min-height:150px}.price{font-size:42px;font-weight:800;margin:18px 0 9px;letter-spacing:-.04em}.signal{font-size:26px;font-weight:800;margin:18px 0 8px}
      .meta,.card p,.gate p,.reason,.boundary p,.selected,.position{color:#8e98a9;font-size:13px;line-height:1.55;margin:0}.section{border-top:1px solid #202632;padding:24px 0}.section-title{font-size:14px;font-weight:800;margin-bottom:15px}.section-title span{margin-right:9px}
      .metrics,.plan{display:grid;grid-template-columns:repeat(6,1fr);gap:10px}.metrics>div,.plan>div{background:#0e1219;border:1px solid #1e2530;border-radius:9px;padding:14px}.metric-label{color:#747f92;font-size:11px;text-transform:uppercase;letter-spacing:.08em}.metric-value{font-weight:750;margin-top:8px;word-break:break-word}
      .analysis-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}.analysis-grid-wide{grid-template-columns:1fr 1fr;margin-top:10px}
      .analysis-card{background:#0e1219;border:1px solid #1e2530;border-radius:9px;padding:15px;min-height:105px}.analysis-label{color:#747f92;font-size:10px;text-transform:uppercase;letter-spacing:.1em}.analysis-main{font-size:19px;font-weight:800;margin-top:10px}.analysis-sub{color:#7f899b;font-size:12px;line-height:1.45;margin-top:6px}.levels{display:flex;justify-content:space-between;gap:15px;margin-top:14px}.levels span{color:#7f899b;font-size:12px}.levels b{display:block;color:#e9edf5;font-size:15px;margin-top:4px}.pattern-list{display:flex;gap:7px;flex-wrap:wrap;margin-top:13px}.pattern{border:1px solid #2a3442;border-radius:999px;padding:5px 8px;color:#b7c0cf;font-size:10px;text-transform:uppercase;letter-spacing:.05em}.analysis-note{margin-top:10px;padding:13px 15px;border:1px solid #29313e;border-radius:9px;background:#0b0f15;color:#7f899b;font-size:12px;line-height:1.55}.analysis-note strong{color:#cbd2de}
      .gates{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.gate{background:#0e1219;border:1px solid #1e2530;border-radius:9px;padding:15px}.gate-top{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:11px;font-weight:750}
      .pill{display:inline-flex;border:1px solid #344052;border-radius:999px;padding:4px 8px;font-size:10px;font-weight:800;letter-spacing:.07em;text-transform:uppercase}.pill.good{border-color:#2f7650;color:#77e39d;background:#102219}.pill.warn{border-color:#756332;color:#e1c87b;background:#211d11}.pill.bad{border-color:#713a42;color:#ee9ca7;background:#241419}
      .selected,.position{margin-top:12px;background:#0e1219;border:1px solid #1e2530;border-radius:9px;padding:14px}.strategy-health{background:#0e1219;border:1px solid #1e2530;border-radius:10px;padding:16px}.strategy-health-summary{display:flex;justify-content:space-between;gap:18px;align-items:flex-start}.strategy-health-summary h3{font-size:22px;margin:8px 0}.strategy-health-summary p{color:#8994a6;font-size:12px;line-height:1.55;margin:0;max-width:850px}.strategy-health-grid{display:grid;grid-template-columns:1fr 1fr 2fr;gap:10px;margin-top:12px}.strategy-health-grid>div{background:#0b0f15;border:1px solid #202832;border-radius:8px;padding:12px}.strategy-health-grid span{display:block;color:#707c8e;font-size:9px;text-transform:uppercase;letter-spacing:.08em}.strategy-health-grid strong{display:block;color:#e6ebf3;font-size:12px;margin-top:7px;line-height:1.4}.strategy-candidates{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:10px}.strategy-candidate{background:#0b0f15;border:1px solid #202832;border-radius:8px;padding:11px}.strategy-candidate>div{display:flex;justify-content:space-between;gap:8px;align-items:center}.strategy-candidate b{font-size:10px;overflow:hidden;text-overflow:ellipsis}.strategy-candidate p{color:#778294;font-size:10px;line-height:1.45;margin:8px 0 0}.reliability-panel{background:#0e1219;border:1px solid #1e2530;border-radius:10px;padding:16px}.reliability-summary{display:flex;justify-content:space-between;gap:18px;align-items:flex-start}.reliability-summary h3{font-size:22px;margin:8px 0}.reliability-summary p{color:#8994a6;font-size:12px;line-height:1.55;margin:0;max-width:850px}.reliability-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-top:12px}.reliability-grid>div{background:#0b0f15;border:1px solid #202832;border-radius:8px;padding:12px}.reliability-grid span{display:block;color:#707c8e;font-size:9px;text-transform:uppercase;letter-spacing:.08em}.reliability-grid strong{display:block;color:#e6ebf3;font-size:13px;margin-top:7px}.guardrail-list{display:flex;gap:7px;flex-wrap:wrap;margin-top:10px}.guardrail-chip{border:1px solid #2a3442;border-radius:999px;padding:6px 9px;color:#b7c0cf;font-size:9px;text-transform:uppercase;letter-spacing:.05em}.reliability-note{color:#687487;font-size:10px;line-height:1.55;margin:12px 0 0}.boundary{background:#0e1219;border:1px solid #25302b;border-radius:9px;padding:17px}
      .guidance-section{padding-top:28px}.guidance-header{display:flex;justify-content:space-between;gap:20px;align-items:center;background:linear-gradient(135deg,#0d1716,#0e1219);border:1px solid #244235;border-radius:14px;padding:22px;margin-bottom:12px}.guidance-kicker{color:#69d99a;font-size:10px;letter-spacing:.14em;font-weight:800}.guidance-header h2{font-size:25px;margin:7px 0 6px;letter-spacing:-.02em}.guidance-header p{color:#8994a6;font-size:13px;line-height:1.55;margin:0;max-width:760px}.decision-badge{min-width:110px;text-align:center;border-radius:12px;padding:18px 16px;font-size:22px;font-weight:900;letter-spacing:.04em}.decision-badge.buy{background:#0c3b24;border:1px solid #32a867;color:#72e6a0}.decision-badge.sell{background:#3d171d;border:1px solid #a44c58;color:#f09aa5}.decision-badge.wait{background:#2d2815;border:1px solid #8a7131;color:#e7ce78}.guidance-metrics{display:grid;grid-template-columns:repeat(6,1fr);gap:10px}.guidance-metric{background:#0e1219;border:1px solid #1e2530;border-radius:9px;padding:14px}.guidance-metric span,.guidance-card-title{display:block;color:#727e91;font-size:10px;text-transform:uppercase;letter-spacing:.1em}.guidance-metric strong{display:block;font-size:18px;margin-top:8px}.guidance-metric small{display:block;color:#687487;font-size:10px;margin-top:5px}.guidance-grid{display:grid;grid-template-columns:1.2fr 1fr 1fr;gap:10px;margin-top:10px}.guidance-card{background:#0e1219;border:1px solid #1e2530;border-radius:10px;padding:17px}.guidance-big{font-size:22px;font-weight:850;margin-top:10px}.guidance-card p{color:#8791a3;font-size:12px;line-height:1.55;margin:7px 0 14px}.guidance-row,.level-row,.gate-line{display:flex;justify-content:space-between;align-items:center;gap:10px;border-top:1px solid #1c232e;padding:9px 0;color:#778295;font-size:11px}.guidance-row b,.level-row strong{color:#e8edf5}.guidance-muted{font-size:10px!important;color:#687487!important}.guidance-news-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:10px}.guidance-plan{margin-top:10px;background:#0b1016;border:1px solid #27313d;border-radius:10px;padding:16px;display:flex;justify-content:space-between;gap:20px;align-items:center}.guidance-plan p{margin:7px 0 0;color:#9aa4b5;font-size:12px;line-height:1.55;max-width:900px}.guidance-warning{white-space:nowrap;border:1px solid #715f2e;background:#211d11;color:#dfc875;border-radius:999px;padding:7px 10px;font-size:9px;font-weight:800;letter-spacing:.08em}
      .market-monitor-section{padding-top:18px}.market-monitor-head{display:flex;justify-content:space-between;align-items:center;gap:20px;background:#0e1219;border:1px solid #202632;border-radius:12px;padding:18px}.market-monitor-kicker{color:#69d99a;font-size:10px;letter-spacing:.14em;font-weight:800}.market-monitor-head h2{font-size:22px;margin:7px 0}.market-monitor-head p{color:#8994a6;font-size:12px;line-height:1.55;margin:0;max-width:820px}.monitor-action{white-space:nowrap;border-radius:999px;padding:9px 12px;font-size:9px;font-weight:900;letter-spacing:.08em}.monitor-action.wait{border:1px solid #715f2e;background:#211d11;color:#dfc875}.monitor-action.opportunity{border:1px solid #2f7650;background:#102219;color:#77e39d}.monitor-grid{display:grid;grid-template-columns:repeat(6,1fr);gap:8px;margin-top:10px}.monitor-grid>div{background:#0e1219;border:1px solid #1e2530;border-radius:9px;padding:13px}.monitor-grid span{display:block;color:#707c8e;font-size:9px;text-transform:uppercase;letter-spacing:.08em}.monitor-grid strong{display:block;color:#e8edf5;font-size:14px;margin-top:7px}.monitor-grid small{display:block;color:#687487;font-size:10px;line-height:1.4;margin-top:5px}.monitor-log{margin-top:10px;background:#0b0f15;border:1px solid #202832;border-radius:10px;overflow:hidden}.monitor-log-head{display:flex;justify-content:space-between;align-items:center;padding:13px 15px;border-bottom:1px solid #202832}.monitor-log-head p{color:#687487;font-size:10px;margin:4px 0 0}.monitor-log-head>span{color:#697486;font-size:10px}.monitor-event{display:grid;grid-template-columns:82px 1fr;gap:12px;padding:12px 15px;border-bottom:1px solid #171e27}.monitor-event:last-child{border-bottom:0}.monitor-time{color:#657084;font-size:10px;padding-top:2px}.monitor-event-main strong{display:block;font-size:11px}.monitor-event-main span,.monitor-event-main small{display:block;color:#7f899b;font-size:10px;line-height:1.45;margin-top:4px}.monitor-event-main small{color:#9aa4b5}.monitor-empty{padding:18px;color:#687487;font-size:11px}
      .demo-execution-section{padding-top:18px}.demo-execution-grid{display:grid;grid-template-columns:1.5fr 1fr;gap:10px}.demo-execution-card,.demo-gate-card{background:#0e1219;border:1px solid #202632;border-radius:12px;padding:18px}.demo-execution-card h3{margin:7px 0;font-size:18px}.demo-controls{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:14px 0}.demo-controls label{display:flex;flex-direction:column;gap:6px;color:#778295;font-size:10px;text-transform:uppercase;letter-spacing:.08em}.demo-controls input{background:#0a0e14;color:#eef2f7;border:1px solid #27313d;border-radius:8px;padding:10px}.demo-actions{display:flex;flex-wrap:wrap;gap:8px}.primary-button,.secondary-button{border-radius:8px;padding:10px 13px;font-weight:800;font-size:11px;cursor:pointer}.primary-button{background:#d9f5e4;color:#0a1710;border:1px solid #8ed0a7}.secondary-button{background:#151b24;color:#dce3ec;border:1px solid #2a3441}.primary-button:disabled,.secondary-button:disabled{opacity:.45;cursor:not-allowed}.demo-proposal{display:flex;flex-wrap:wrap;gap:10px;margin-top:12px;padding:10px;border:1px solid #27313d;border-radius:8px;color:#aeb7c6;font-size:10px}.demo-open{margin-top:10px;color:#72d99a;font-weight:800;font-size:11px}.demo-message{margin-top:10px;padding:9px;border-radius:8px;background:#111722;color:#aeb7c6;font-size:11px;line-height:1.45}.market-chart-section{padding-top:18px}.chart-wrap{background:#0e1219;border:1px solid #202632;border-radius:12px;padding:18px}
      .chart-head{display:flex;justify-content:space-between;align-items:flex-end;gap:14px;margin-bottom:12px}.chart-title{font-size:20px;font-weight:800;margin-top:6px}
      .chart-legend{display:flex;gap:14px;flex-wrap:wrap;color:#778295;font-size:11px}.chart-legend span{display:inline-flex;align-items:center;gap:6px}.chart-legend i{display:inline-block;width:8px;height:8px;border-radius:2px}.legend-up{background:#55d991}.legend-down{background:#ed707c}
      .chart-scroll{width:100%;overflow-x:auto;overflow-y:hidden}.candle-chart{display:block;width:100%;min-width:720px;height:auto}
      .grid-line{stroke:#202732;stroke-width:1}.axis-label,.time-label{fill:#667184;font-size:11px;font-family:inherit}.wick-up,.wick-down{stroke-width:1.5}.wick-up{stroke:#55d991}.wick-down{stroke:#ed707c}.body-up{fill:#55d991;stroke:#55d991}.body-down{fill:#ed707c;stroke:#ed707c}
      .chart-foot{display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;margin-top:10px;color:#6f7b8d;font-size:11px}.chart-foot span:nth-child(2){color:#70d99a;font-weight:700}.chart-empty{padding:80px 20px;text-align:center;color:#778295}
      footer{border-top:1px solid #202632;margin-top:10px;padding:20px 0 30px;color:#697486;font-size:11px;letter-spacing:.08em;text-transform:uppercase}
      @media(max-width:850px){.demo-execution-grid{grid-template-columns:1fr}.strategy-health-grid,.strategy-candidates,.reliability-grid{grid-template-columns:1fr}.strategy-health-summary,.reliability-summary{flex-direction:column}.cockpit-shell{display:block}.sidebar{position:relative;height:auto;border-right:0;border-bottom:1px solid #1e2530}.side-nav{display:flex;overflow-x:auto}.side-nav button{white-space:nowrap}.side-bottom{display:none}.cockpit-main{padding:16px}.market-list{grid-template-columns:repeat(2,1fr)}.market-monitor-head{align-items:flex-start;flex-direction:column}.monitor-grid{grid-template-columns:repeat(2,1fr)}.guidance-news-grid{grid-template-columns:1fr}.chart-head{align-items:flex-start;flex-direction:column}.hero-grid,.gates,.analysis-grid,.analysis-grid-wide,.guidance-grid{grid-template-columns:1fr}.metrics,.plan,.guidance-metrics{grid-template-columns:repeat(2,1fr)}.controls{flex-wrap:wrap}.refresh-note{width:100%;margin:0}.guidance-header,.guidance-plan{align-items:flex-start;flex-direction:column}.decision-badge{width:100%}}
      .demo-approval-banner{display:flex;justify-content:space-between;gap:20px;align-items:center;margin:0 0 18px;padding:18px 20px;border:1px solid #245d46;border-radius:16px;background:rgba(8,44,31,.55)}.demo-approval-banner strong{display:block;font-size:18px;margin-top:6px}.demo-approval-banner p{margin:8px 0 0;color:#9aa7b8}.demo-approval-banner .demo-actions{justify-content:flex-end}@media(max-width:760px){.demo-approval-banner{flex-direction:column;align-items:stretch}.demo-approval-banner .demo-actions{justify-content:stretch}}
    `}
</style>
  </>;
}
