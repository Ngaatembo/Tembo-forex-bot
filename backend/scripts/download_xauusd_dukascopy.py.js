const { getHistoricalRates } = require("dukascopy-node");

(async () => {
  const data = await getHistoricalRates({
    instrument: "xauusd",
    dates: { from: new Date("2003-05-05"), to: new Date("2026-09-25") },
    timeframe: "h1",
    format: "json"
  });
  require("fs").mkdirSync("data", { recursive: true });
  require("fs").writeFileSync("data/xauusd_dukascopy_h1.json", JSON.stringify(data));
  console.log("Downloaded", data.length, "H1 bars");
})();
