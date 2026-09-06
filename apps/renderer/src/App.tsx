import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
  type ReactNode,
} from "react";
import {
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
  createChart,
  createSeriesMarkers,
  type CandlestickData,
  type HistogramData,
  type LineData,
  type SeriesMarker,
  type Time,
} from "lightweight-charts";
import {
  Bell,
  BookOpen,
  Bot,
  Brain,
  Check,
  ChevronDown,
  ClipboardPenLine,
  Download,
  Eye,
  EyeOff,
  FileDown,
  FileText,
  HardDrive,
  History,
  LayoutDashboard,
  Mic,
  MoreHorizontal,
  PanelRightClose,
  PanelRightOpen,
  Pencil,
  Play,
  Plus,
  Search,
  Save,
  Send,
  Settings2,
  ShieldCheck,
  Sparkles,
  Star,
  Trash2,
  WifiOff,
  X,
} from "lucide-react";
import "./App.css";
import InvestmentNewsFrame from "./InvestmentNewsFrame";

const shellBackendPort = new URLSearchParams(window.location.search).get(
  "backendPort",
);
const API_BASE = shellBackendPort
  ? `http://127.0.0.1:${shellBackendPort}`
  : "http://127.0.0.1:8000";

type Taxonomy = {
  primarySectors: {
    id: string;
    name: string;
    industries: string[];
    topics?: string[];
  }[];
  industries: string[];
  themes: string[];
};

type NewsItem = {
  id: number;
  title: string;
  summary: string;
  url: string;
  source_name: string;
  published_at: string | null;
  fetched_at: string;
  primary_sector: string;
  industry: string;
  topics: string[];
  is_read?: boolean;
  matched_subscriptions?: string[];
};

type NewsResponse = {
  items: NewsItem[];
  count: number;
  total: number;
  offset: number;
  limit: number;
  updatedAt: string | null;
};

type SourceHealth = {
  source_id: string;
  source_name: string;
  status: string;
  item_count: number;
  detail: string;
  last_checked_at: string | null;
  last_success_at?: string | null;
  delay_minutes?: number | null;
  is_stale?: boolean;
};

type NewsSubscription = { id: string; keyword: string; created_at: string };

function formatDate(value: string | null) {
  if (!value) return "时间待确认";
  return value.length > 24 ? value.slice(0, 16).replace("T", " ") : value;
}

type Conversation = {
  id: string;
  title: string;
  preview: string;
  created_at: string;
  updated_at: string;
};

type MemoryItem = {
  id: string;
  label: string;
  value: string;
  updated_at: string;
  memory_created?: boolean;
  memory_name?: string;
  memory_type?: string;
};

type UsedMemory = {
  name: string;
  description: string;
  type: "user" | "feedback" | "project" | "reference";
  relevance: "high" | "medium" | "low";
};

type ConversationMessage = {
  id: string;
  conversation_id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
  used_memories?: UsedMemory[];
};

type StreamEvent =
  | { type: "delta"; content: string }
  | {
      type: "done";
      userMessage: ConversationMessage;
      assistantMessage: ConversationMessage;
      usedMemories?: UsedMemory[];
    }
  | { type: "error"; message: string };

type SpeechRecognitionInstance = {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  onresult:
    | ((event: {
        results: ArrayLike<ArrayLike<{ transcript: string }>>;
      }) => void)
    | null;
  onerror: (() => void) | null;
  onend: (() => void) | null;
  start: () => void;
};

type SpeechRecognitionConstructor = new () => SpeechRecognitionInstance;

type WatchlistItem = {
  id: string;
  code: string;
  name: string;
  created_at: string;
};

type WorkbenchQueryResult = {
  tool: string;
  status: string;
  source?: string;
  updatedAt?: string;
  error?: string;
  data?: unknown;
  cacheHit?: boolean;
  fallbackUsed?: boolean;
  requestedTool?: string;
  attempts?: number;
};

type ProviderStatus = {
  provider: "deepseek" | "openai" | "claude";
  label: string;
  configured: boolean;
  keyName: string;
};

type ModelProviderSettings = ProviderStatus & {
  keySource: "settings" | "environment" | null;
  keyPreview: string;
  baseUrl: string;
  defaultBaseUrl: string;
};

type DataManagement = {
  storagePath: string;
  totalBytes: number;
  fileCount: number;
  automaticBackup: "off" | "daily" | "weekly";
  lastBackupAt: string | null;
  backupCount: number;
};

type ChartMode = "day" | "intraday";
type IndicatorKey =
  | "ma5"
  | "ma10"
  | "ma20"
  | "bollinger"
  | "macd"
  | "kdj"
  | "rsi";
type WorkbenchSection =
  | "overview"
  | "detail"
  | "limit"
  | "strategy"
  | "research";
type DetailPanel =
  | "summary"
  | "kline"
  | "fundamentals"
  | "reports"
  | "concepts"
  | "flow";
type CanvasRequest = { section: WorkbenchSection; code?: string };

type ResearchNote = {
  code: string;
  title: string;
  thesis: string;
  risks: string;
  key_metrics: string;
  reminders: string;
  created_at: string;
  updated_at: string;
};

type InvestmentDecision = {
  id: string;
  code: string;
  action: "buy" | "sell" | "hold" | "review";
  shares: number | null;
  price: number | null;
  rationale: string;
  target_or_stop: string;
  review: string;
  created_at: string;
};

type StrategyVersion = {
  id: string;
  strategy_id: string | null;
  strategy_name: string;
  version: string;
  change_summary: string;
  rationale: string;
  backtest_summary: string;
  created_at: string;
};

type ResearchReport = {
  id: string;
  code: string;
  report_type: "fundamental" | "technical" | "event";
  title: string;
  content: string;
  source_summary: string;
  created_at: string;
};

type BacktestResult = {
  status: string;
  code: string;
  source?: string;
  updatedAt?: string;
  error?: string;
  strategyName?: string;
  summary?: {
    bars: number;
    trades: number;
    winRate: number;
    totalReturnPct: number;
    annualizedReturnPct?: number;
    maxDrawdownPct?: number;
    sharpeRatio?: number;
    profitLossRatio?: number | string | null;
    averageHoldingBars?: number;
    benchmarkReturnPct?: number | null;
    excessReturnPct?: number | null;
    finalEquity?: number;
  };
  assumptions?: {
    initialCapital: number;
    positionPct: number;
    commissionRate: number;
    stampDutyRate: number;
    slippageRate: number;
    takeProfitPct?: number | null;
    stopLossPct?: number | null;
    maxHoldingBars?: number;
  };
  trades?: {
    entryTime: string;
    entryPrice: number;
    exitTime: string;
    exitPrice: number;
    returnPct: number;
    profit?: number;
    shares?: number;
    exitReason?: string;
    holdingBars?: number;
  }[];
  equityCurve?: { time: string; equity: number; drawdownPct: number }[];
};

type BacktestField =
  | "close"
  | "ma5"
  | "ma10"
  | "ma20"
  | "volume"
  | "volume_ma5";
type BacktestOperator = "gt" | "gte" | "lt" | "lte" | "cross_up" | "cross_down";
type BacktestRuleDraft = {
  field: BacktestField;
  operator: BacktestOperator;
  value: string;
  compareField: BacktestField | "";
};

type AlertItem = {
  id: string;
  code: string;
  name: string;
  field: string;
  operator: string;
  value: number;
  enabled: boolean;
  triggered_at?: string | null;
  last_checked_at?: string | null;
  last_value?: number | null;
};

type StrategyCondition = {
  field: string;
  operator: string;
  value?: number;
  compare_field?: string;
};
type StrategyDraft = {
  name: string;
  type: string;
  code: string;
  conditions: StrategyCondition[];
  mode: string;
  weight: number;
  schedule_mode: "manual" | "interval" | "time-point" | "condition";
  interval_seconds: number;
  schedule_at: string;
  analysis_prompt: string;
  actions: string[];
  source: string;
};
type SavedStrategy = {
  id: string;
  name: string;
  type: string;
  code: string;
  field: string;
  operator: string;
  value: number;
  mode: string;
  weight: number;
  status: "active" | "paused";
  conditions?: StrategyCondition[];
  schedule?: { mode: string; intervalSeconds: number; at: string };
  actions?: string[];
  last_run_at?: string | null;
  last_triggered_at?: string | null;
};
type StrategyDecision = {
  id: string;
  mode: string;
  rating: number;
  conclusion: string;
  tree: { step: string; result: string }[];
  risks?: string[];
  catalysts?: string[];
  triggerSource?: string;
  createdAt: string;
};

function formatBytes(value: number) {
  if (!Number.isFinite(value) || value <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const index = Math.min(
    Math.floor(Math.log(value) / Math.log(1024)),
    units.length - 1,
  );
  return `${(value / 1024 ** index).toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}

function LocalPrivacyBanner() {
  const [offline, setOffline] = useState(() => !navigator.onLine);

  useEffect(() => {
    const updateState = () => setOffline(!navigator.onLine);
    window.addEventListener("online", updateState);
    window.addEventListener("offline", updateState);
    return () => {
      window.removeEventListener("online", updateState);
      window.removeEventListener("offline", updateState);
    };
  }, []);

  if (offline)
    return (
      <div className="offline-banner" role="status">
        <WifiOff size={16} />
        <strong>离线模式</strong>
        <span>历史数据可用，无法获取最新行情和资讯。</span>
      </div>
    );
  return (
    <div className="privacy-banner">
      <ShieldCheck size={16} />
      <strong>100% 本地运行</strong>
      <span>持仓、策略、研究笔记和对话不会上传云端</span>
      <code>D:\桌面agent\state\</code>
    </div>
  );
}

function workbenchRows(data: unknown): Record<string, unknown>[] {
  if (Array.isArray(data))
    return data.filter(
      (item): item is Record<string, unknown> =>
        Boolean(item) && typeof item === "object",
    );
  if (data && typeof data === "object") {
    const record = data as Record<string, unknown>;
    const nested = Object.values(record).find((value) => Array.isArray(value));
    if (Array.isArray(nested))
      return nested.filter(
        (item): item is Record<string, unknown> =>
          Boolean(item) && typeof item === "object",
      );
    const mapped = Object.entries(record).filter(
      ([, value]) =>
        Boolean(value) && typeof value === "object" && !Array.isArray(value),
    );
    if (mapped.length)
      return mapped.map(([key, value]) => ({
        ...(value as Record<string, unknown>),
        code: (value as Record<string, unknown>).code ?? key,
      }));
    return [record];
  }
  return [];
}

function workbenchValue(row: Record<string, unknown>, keys: string[]) {
  const entry = Object.entries(row).find(([key]) =>
    keys.some((candidate) =>
      key.toLowerCase().includes(candidate.toLowerCase()),
    ),
  );
  const value = entry?.[1];
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "number")
    return Number.isFinite(value)
      ? value.toLocaleString("zh-CN", { maximumFractionDigits: 4 })
      : "—";
  return String(value);
}

function rowNumber(row: Record<string, unknown>, keys: string[]) {
  const raw = workbenchValue(row, keys);
  if (raw === "—") return null;
  const value = Number(String(raw).replace(/[% ,]/g, ""));
  return Number.isFinite(value) ? value : null;
}

function rowText(row: Record<string, unknown>, keys: string[]) {
  const value = workbenchValue(row, keys);
  return value === "—" ? "" : value;
}

function chartTime(value: string): Time | null {
  const clean = value.trim().replace(/\//g, "-");
  if (!clean) return null;
  if (/^\d{4}-\d{2}-\d{2}$/.test(clean)) return clean as Time;
  const date = new Date(clean.includes("T") ? clean : clean.replace(" ", "T"));
  if (Number.isNaN(date.getTime())) return null;
  return Math.floor(date.getTime() / 1000) as Time;
}

function normalizeChartRows(
  result?: WorkbenchQueryResult,
): (CandlestickData<Time> & { volume?: number })[] {
  return workbenchRows(result?.data).reduce<
    (CandlestickData<Time> & { volume?: number })[]
  >((items, row) => {
    const time = chartTime(rowText(row, ["日期", "date", "datetime", "time"]));
    const open = rowNumber(row, ["开盘", "open"]);
    const high = rowNumber(row, ["最高", "high"]);
    const low = rowNumber(row, ["最低", "low"]);
    const close = rowNumber(row, ["收盘", "close", "最新"]);
    const volume = rowNumber(row, ["成交量", "volume"]);
    if (
      !time ||
      open === null ||
      high === null ||
      low === null ||
      close === null
    )
      return items;
    items.push({ time, open, high, low, close, volume: volume ?? undefined });
    return items;
  }, []);
}

type TechnicalSnapshot = {
  ma5: number | null;
  ma10: number | null;
  ma20: number | null;
  upper: number | null;
  lower: number | null;
  macd: number | null;
  k: number | null;
  d: number | null;
  rsi: number | null;
};

function calculateTechnicalSnapshot(
  rows: (CandlestickData<Time> & { volume?: number })[],
): TechnicalSnapshot {
  const closes = rows.map((row) => row.close);
  const average = (size: number) =>
    closes.length >= size
      ? closes.slice(-size).reduce((total, value) => total + value, 0) / size
      : null;
  const ma5 = average(5);
  const ma10 = average(10);
  const ma20 = average(20);
  const recent20 = closes.slice(-20);
  const deviation =
    ma20 && recent20.length === 20
      ? Math.sqrt(
          recent20.reduce((total, value) => total + (value - ma20) ** 2, 0) /
            20,
        )
      : null;
  const ema = (period: number) =>
    closes.reduce<number | null>(
      (previous, value) =>
        previous === null
          ? value
          : value * (2 / (period + 1)) + previous * (1 - 2 / (period + 1)),
      null,
    );
  const ema12 = ema(12);
  const ema26 = ema(26);
  const macd = ema12 !== null && ema26 !== null ? (ema12 - ema26) * 2 : null;
  const recent14 = closes.slice(-15);
  const gains = recent14
    .slice(1)
    .map((value, index) => Math.max(0, value - recent14[index]));
  const losses = recent14
    .slice(1)
    .map((value, index) => Math.max(0, recent14[index] - value));
  const averageGain = gains.length
    ? gains.reduce((total, value) => total + value, 0) / gains.length
    : 0;
  const averageLoss = losses.length
    ? losses.reduce((total, value) => total + value, 0) / losses.length
    : 0;
  const rsi =
    recent14.length === 15
      ? averageLoss === 0
        ? 100
        : 100 - 100 / (1 + averageGain / averageLoss)
      : null;
  const recent9 = rows.slice(-9);
  const highest =
    recent9.length === 9 ? Math.max(...recent9.map((row) => row.high)) : null;
  const lowest =
    recent9.length === 9 ? Math.min(...recent9.map((row) => row.low)) : null;
  const rsv =
    highest !== null && lowest !== null && highest !== lowest
      ? ((closes.at(-1)! - lowest) / (highest - lowest)) * 100
      : null;
  const k = rsv === null ? null : (2 * 50 + rsv) / 3;
  const d = k === null ? null : (2 * 50 + k) / 3;
  return {
    ma5,
    ma10,
    ma20,
    upper: ma20 !== null && deviation !== null ? ma20 + deviation * 2 : null,
    lower: ma20 !== null && deviation !== null ? ma20 - deviation * 2 : null,
    macd,
    k,
    d,
    rsi,
  };
}

function chartMarkers(
  rows: (CandlestickData<Time> & { volume?: number })[],
  trades?: BacktestResult["trades"],
): SeriesMarker<Time>[] {
  if (!rows.length) return [];
  const high = rows.reduce(
    (best, row) => (row.high > best.high ? row : best),
    rows[0],
  );
  const low = rows.reduce(
    (best, row) => (row.low < best.low ? row : best),
    rows[0],
  );
  const tradeMarkers = (trades ?? [])
    .flatMap((trade): SeriesMarker<Time>[] => {
      const entryTime = chartTime(trade.entryTime);
      const exitTime = chartTime(trade.exitTime);
      const markers: SeriesMarker<Time>[] = [];
      if (entryTime)
        markers.push({
          time: entryTime,
          position: "belowBar",
          color: "#047857",
          shape: "arrowUp",
          text: `入 ${trade.entryPrice}`,
        });
      if (exitTime)
        markers.push({
          time: exitTime,
          position: "aboveBar",
          color: trade.returnPct >= 0 ? "#0f766e" : "#dc2626",
          shape: "arrowDown",
          text: `${trade.returnPct}%`,
        });
      return markers;
    })
    .slice(0, 40);
  return [
    {
      time: high.time,
      position: "aboveBar",
      color: "#b45309",
      shape: "circle",
      text: `高 ${high.high}`,
    },
    {
      time: low.time,
      position: "belowBar",
      color: "#2563eb",
      shape: "circle",
      text: `低 ${low.low}`,
    },
    ...tradeMarkers,
  ];
}

function StockPriceChart({
  daily,
  intraday,
  mode,
  trades,
}: {
  daily?: WorkbenchQueryResult;
  intraday?: WorkbenchQueryResult;
  mode: ChartMode;
  trades?: BacktestResult["trades"];
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const rows = normalizeChartRows(mode === "intraday" ? intraday : daily);
  const technical = calculateTechnicalSnapshot(rows);
  const [visibleIndicators, setVisibleIndicators] = useState<
    Record<IndicatorKey, boolean>
  >({
    ma5: true,
    ma10: true,
    ma20: true,
    bollinger: true,
    macd: true,
    kdj: true,
    rsi: true,
  });
  const toggleIndicator = (key: IndicatorKey) => {
    setVisibleIndicators((current) => ({
      ...current,
      [key]: !current[key],
    }));
  };

  useEffect(() => {
    const container = containerRef.current;
    if (!container || !rows.length) return;
    const chart = createChart(container, {
      autoSize: true,
      layout: { background: { color: "#ffffff" }, textColor: "#334155" },
      grid: {
        vertLines: { color: "#eef2f7" },
        horzLines: { color: "#eef2f7" },
      },
      rightPriceScale: { borderVisible: false },
      timeScale: { borderVisible: false, rightOffset: 8, barSpacing: 8 },
      crosshair: { mode: 1 },
    });
    const volumeData: HistogramData<Time>[] = rows.map((row) => ({
      time: row.time,
      value: row.volume ?? 0,
      color:
        row.close >= row.open ? "rgba(4,120,87,.25)" : "rgba(220,38,38,.22)",
    }));
    if (mode === "intraday") {
      const line = chart.addSeries(LineSeries, {
        color: "#0f766e",
        lineWidth: 2,
        priceLineVisible: true,
      });
      const lineData: LineData<Time>[] = rows.map((row) => ({
        time: row.time,
        value: row.close,
      }));
      line.setData(lineData);
      createSeriesMarkers(line, chartMarkers(rows, trades));
    } else {
      const candle = chart.addSeries(CandlestickSeries, {
        upColor: "#047857",
        downColor: "#dc2626",
        borderVisible: false,
        wickUpColor: "#047857",
        wickDownColor: "#dc2626",
      });
      candle.setData(rows);
      createSeriesMarkers(candle, chartMarkers(rows, trades));
      const lineData = (period: number) =>
        rows
          .map((row, index) =>
            index + 1 >= period
              ? {
                  time: row.time,
                  value:
                    rows
                      .slice(index + 1 - period, index + 1)
                      .reduce((total, item) => total + item.close, 0) / period,
                }
              : null,
          )
          .filter((item): item is LineData<Time> => item !== null);
      if (visibleIndicators.ma5) {
        chart
          .addSeries(LineSeries, {
            color: "#2563eb",
            lineWidth: 1,
            priceLineVisible: false,
            lastValueVisible: false,
          })
          .setData(lineData(5));
      }
      if (visibleIndicators.ma10) {
        chart
          .addSeries(LineSeries, {
            color: "#b45309",
            lineWidth: 1,
            priceLineVisible: false,
            lastValueVisible: false,
          })
          .setData(lineData(10));
      }
      if (visibleIndicators.ma20) {
        chart
          .addSeries(LineSeries, {
            color: "#7c3aed",
            lineWidth: 1,
            priceLineVisible: false,
            lastValueVisible: false,
          })
          .setData(lineData(20));
      }
      if (
        visibleIndicators.bollinger &&
        technical.upper !== null &&
        technical.lower !== null
      ) {
        const bollinger = (multiplier: number) =>
          rows
            .map((row, index) => {
              const window = rows.slice(Math.max(0, index - 19), index + 1);
              if (window.length < 20) return null;
              const mean =
                window.reduce((total, item) => total + item.close, 0) / 20;
              const stddev = Math.sqrt(
                window.reduce(
                  (total, item) => total + (item.close - mean) ** 2,
                  0,
                ) / 20,
              );
              return { time: row.time, value: mean + stddev * multiplier };
            })
            .filter((item): item is LineData<Time> => item !== null);
        chart
          .addSeries(LineSeries, {
            color: "#94a3b8",
            lineWidth: 1,
            lineStyle: 2,
            priceLineVisible: false,
            lastValueVisible: false,
          })
          .setData(bollinger(2));
        chart
          .addSeries(LineSeries, {
            color: "#94a3b8",
            lineWidth: 1,
            lineStyle: 2,
            priceLineVisible: false,
            lastValueVisible: false,
          })
          .setData(bollinger(-2));
      }
    }
    const volume = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "volume",
    });
    volume.setData(volumeData);
    chart
      .priceScale("volume")
      .applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });
    chart.timeScale().fitContent();
    return () => chart.remove();
  }, [
    mode,
    rows,
    trades,
    technical.lower,
    technical.upper,
    visibleIndicators,
  ]);

  if (!rows.length)
    return (
      <div className="workbench-empty">
        <strong>暂无可绘制数据</strong>
        <span>数据源没有返回完整的开高低收字段。</span>
      </div>
    );
  const value = (number: number | null) =>
    number === null ? "—" : number.toFixed(2);
  return (
    <>
      <div className="stock-chart" ref={containerRef} />
      <div className="technical-summary" aria-label="技术指标当前读数">
        <button
          type="button"
          className={!visibleIndicators.ma5 ? "is-hidden" : undefined}
          aria-pressed={visibleIndicators.ma5}
          onClick={() => toggleIndicator("ma5")}
          title={`MA5（5日均线）: ${value(technical.ma5)}\n含义：近5个交易日平均价格\n多头信号：MA5 > MA10 > MA20\n${visibleIndicators.ma5 ? "点击隐藏" : "点击显示"}`}
        >
          MA5 {value(technical.ma5)}
        </button>
        <button
          type="button"
          className={!visibleIndicators.ma10 ? "is-hidden" : undefined}
          aria-pressed={visibleIndicators.ma10}
          onClick={() => toggleIndicator("ma10")}
          title={`MA10（10日均线）: ${value(technical.ma10)}\n含义：近10个交易日平均价格\n趋势判断：观察与MA5、MA20的位置关系\n${visibleIndicators.ma10 ? "点击隐藏" : "点击显示"}`}
        >
          MA10 {value(technical.ma10)}
        </button>
        <button
          type="button"
          className={!visibleIndicators.ma20 ? "is-hidden" : undefined}
          aria-pressed={visibleIndicators.ma20}
          onClick={() => toggleIndicator("ma20")}
          title={`MA20（20日均线）: ${value(technical.ma20)}\n含义：近20个交易日平均价格\n支撑/阻力：常用作支撑位或阻力位参考\n${visibleIndicators.ma20 ? "点击隐藏" : "点击显示"}`}
        >
          MA20 {value(technical.ma20)}
        </button>
        <button
          type="button"
          className={!visibleIndicators.bollinger ? "is-hidden" : undefined}
          aria-pressed={visibleIndicators.bollinger}
          onClick={() => toggleIndicator("bollinger")}
          title={`布林线: ${value(technical.lower)} - ${value(technical.upper)}\n含义：波动区间指标，上下轨为±2倍标准差\n用法：价格触及上轨可能回调，触及下轨可能反弹\n${visibleIndicators.bollinger ? "点击隐藏" : "点击显示"}`}
        >
          布林 {value(technical.lower)} - {value(technical.upper)}
        </button>
        <button
          type="button"
          className={!visibleIndicators.macd ? "is-hidden" : undefined}
          aria-pressed={visibleIndicators.macd}
          onClick={() => toggleIndicator("macd")}
          title={`MACD: ${value(technical.macd)}\n含义：趋势强弱指标\n${technical.macd !== null && technical.macd > 0 ? "当前：多头强势（正值）" : "当前：空头强势（负值）"}\n金叉：DIF上穿DEA为买入信号\n${visibleIndicators.macd ? "点击隐藏" : "点击显示"}`}
        >
          MACD {value(technical.macd)}
        </button>
        <button
          type="button"
          className={!visibleIndicators.kdj ? "is-hidden" : undefined}
          aria-pressed={visibleIndicators.kdj}
          onClick={() => toggleIndicator("kdj")}
          title={`KDJ: K=${value(technical.k)} D=${value(technical.d)}\n含义：超买超卖指标\n${technical.k !== null && technical.k > 80 ? "当前：超买区（K>80，谨慎追高）" : technical.k !== null && technical.k < 20 ? "当前：超卖区（K<20，可能反弹）" : "当前：正常区间"}\n金叉：K线上穿D线为买入信号\n${visibleIndicators.kdj ? "点击隐藏" : "点击显示"}`}
        >
          KDJ {value(technical.k)} / {value(technical.d)}
        </button>
        <button
          type="button"
          className={!visibleIndicators.rsi ? "is-hidden" : undefined}
          aria-pressed={visibleIndicators.rsi}
          onClick={() => toggleIndicator("rsi")}
          title={`RSI: ${value(technical.rsi)}\n含义：相对强弱指标（0-100）\n${technical.rsi !== null && technical.rsi > 70 ? "当前：超买（RSI>70，可能回调）" : technical.rsi !== null && technical.rsi < 30 ? "当前：超卖（RSI<30，可能反弹）" : "当前：正常区间"}\n用法：50为多空分界线\n${visibleIndicators.rsi ? "点击隐藏" : "点击显示"}`}
        >
          RSI {value(technical.rsi)}
        </button>
      </div>
    </>
  );
}

function EquityCurveChart({
  points,
}: {
  points?: BacktestResult["equityCurve"];
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartPoints = (points ?? []).flatMap((point) => {
    const time = chartTime(point.time);
    return time ? [{ time, value: point.equity }] : [];
  });

  useEffect(() => {
    const container = containerRef.current;
    if (!container || chartPoints.length < 2) return;
    const chart = createChart(container, {
      autoSize: true,
      layout: { background: { color: "#ffffff" }, textColor: "#475569" },
      grid: {
        vertLines: { color: "#eef2f7" },
        horzLines: { color: "#eef2f7" },
      },
      rightPriceScale: { borderVisible: false },
      timeScale: { borderVisible: false },
    });
    const line = chart.addSeries(LineSeries, {
      color: "#0f766e",
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: true,
    });
    line.setData(chartPoints);
    chart.timeScale().fitContent();
    return () => chart.remove();
  }, [chartPoints]);

  if (chartPoints.length < 2)
    return <div className="equity-empty">回测完成后显示权益曲线。</div>;
  return (
    <div
      className="equity-chart"
      ref={containerRef}
      aria-label="策略权益曲线"
    />
  );
}

function WorkbenchResultMeta({ result }: { result?: WorkbenchQueryResult }) {
  if (!result) return null;
  const stateLabel =
    result.status === "success"
      ? result.cacheHit
        ? "已使用缓存"
        : result.fallbackUsed
          ? "备用源已返回"
          : "数据已返回"
      : result.error || "数据源暂时不可用";
  return (
    <div
      className={`workbench-result-meta ${result.status === "success" ? "result-ok" : "result-error"}`}
    >
      <span>{stateLabel}</span>
      <span>{result.source || "受控工具"}</span>
      {result.attempts && result.attempts > 1 ? (
        <span>尝试 {result.attempts} 次</span>
      ) : null}
      <time>
        {result.updatedAt ? formatDate(result.updatedAt) : "时间待确认"}
      </time>
    </div>
  );
}

function WorkbenchDataTable({
  result,
  columns,
}: {
  result?: WorkbenchQueryResult;
  columns: { label: string; keys: string[] }[];
}) {
  if (!result)
    return <div className="workbench-loading">选择模块后读取数据…</div>;
  if (result.status !== "success")
    return (
      <div className="workbench-empty">
        <strong>数据源暂时不可用</strong>
        <span>{result.error || "请稍后重试"}</span>
      </div>
    );
  const rows = workbenchRows(result.data).slice(0, 30);
  if (!rows.length)
    return (
      <div className="workbench-empty">
        <strong>暂无返回数据</strong>
        <span>来源没有提供可展示的记录。</span>
      </div>
    );
  return (
    <div className="workbench-table-wrap">
      <table className="workbench-table">
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column.label}>{column.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={index}>
              {columns.map((column) => (
                <td key={column.label}>{workbenchValue(row, column.keys)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function inlineAssistantContent(text: string): ReactNode[] {
  const tokenPattern =
    /(\*\*[^*]+\*\*|__[^_]+__|`[^`]+`|\[[^\]]+\]\(https?:\/\/[^)]+\))/g;
  return text
    .split(tokenPattern)
    .filter(Boolean)
    .map((part, index) => {
      if (
        (part.startsWith("**") && part.endsWith("**")) ||
        (part.startsWith("__") && part.endsWith("__"))
      )
        return <strong key={index}>{part.slice(2, -2)}</strong>;
      if (part.startsWith("`") && part.endsWith("`"))
        return <code key={index}>{part.slice(1, -1)}</code>;
      const link = part.match(/^\[([^\]]+)\]\((https?:\/\/[^)]+)\)$/);
      if (link)
        return (
          <a key={index} href={link[2]} target="_blank" rel="noreferrer">
            {link[1]}
          </a>
        );
      return part;
    });
}

function tableCells(line: string) {
  return line
    .trim()
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((cell) => cell.trim());
}

function isTableDivider(line: string) {
  return /^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(line);
}

function renderAssistantContent(content: string): ReactNode {
  const lines = content.replace(/\r/g, "").split("\n");
  const blocks: ReactNode[] = [];
  let index = 0;
  while (index < lines.length) {
    const line = lines[index].trim();
    if (!line) {
      index += 1;
      continue;
    }
    if (
      index + 1 < lines.length &&
      line.includes("|") &&
      isTableDivider(lines[index + 1])
    ) {
      const headers = tableCells(line);
      const rows: string[][] = [];
      index += 2;
      while (
        index < lines.length &&
        lines[index].includes("|") &&
        lines[index].trim()
      ) {
        rows.push(tableCells(lines[index]));
        index += 1;
      }
      blocks.push(
        <div className="assistant-table-wrap" key={`table-${index}`}>
          <table className="assistant-table">
            <thead>
              <tr>
                {headers.map((header, cellIndex) => (
                  <th key={cellIndex}>{inlineAssistantContent(header)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, rowIndex) => (
                <tr key={rowIndex}>
                  {headers.map((_, cellIndex) => (
                    <td key={cellIndex}>
                      {inlineAssistantContent(row[cellIndex] ?? "")}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      );
      continue;
    }
    const heading = line.match(/^#{1,3}\s+(.+)$/);
    if (heading) {
      const Heading = `h${Math.min(line.indexOf(" "), 3)}` as
        | "h1"
        | "h2"
        | "h3";
      blocks.push(
        <Heading key={`heading-${index}`}>
          {inlineAssistantContent(heading[1])}
        </Heading>,
      );
      index += 1;
      continue;
    }
    if (/^(?:[-*•])\s+/.test(line)) {
      const items: string[] = [];
      while (
        index < lines.length &&
        /^(?:[-*•])\s+/.test(lines[index].trim())
      ) {
        items.push(lines[index].trim().replace(/^(?:[-*•])\s+/, ""));
        index += 1;
      }
      blocks.push(
        <ul key={`list-${index}`}>
          {items.map((item, itemIndex) => (
            <li key={itemIndex}>{inlineAssistantContent(item)}</li>
          ))}
        </ul>,
      );
      continue;
    }
    if (/^\d+[.)]\s+/.test(line)) {
      const items: string[] = [];
      while (index < lines.length && /^\d+[.)]\s+/.test(lines[index].trim())) {
        items.push(lines[index].trim().replace(/^\d+[.)]\s+/, ""));
        index += 1;
      }
      blocks.push(
        <ol key={`ordered-list-${index}`}>
          {items.map((item, itemIndex) => (
            <li key={itemIndex}>{inlineAssistantContent(item)}</li>
          ))}
        </ol>,
      );
      continue;
    }
    const paragraph: string[] = [];
    while (index < lines.length) {
      const next = lines[index].trim();
      if (
        !next ||
        (paragraph.length > 0 &&
          (/^#{1,3}\s+/.test(next) ||
            /^(?:[-*•])\s+/.test(next) ||
            /^\d+[.)]\s+/.test(next)))
      )
        break;
      paragraph.push(
        next.includes("|") ? next.replace(/\s*\|\s*/g, " · ") : next,
      );
      index += 1;
    }
    blocks.push(
      <p key={`paragraph-${index}`}>
        {paragraph.map((part, partIndex) => (
          <span key={partIndex}>
            {partIndex > 0 && <br />}
            {inlineAssistantContent(part)}
          </span>
        ))}
      </p>,
    );
  }
  return <div className="assistant-content">{blocks}</div>;
}

function conversationTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "刚刚";
  const today = new Date();
  if (date.toDateString() === today.toDateString()) return "今天";
  return `${date.getMonth() + 1} 月 ${date.getDate()} 日`;
}

function StockWorkbench({
  onOpenAgent,
  onOpenNews,
  embedded = false,
  request,
}: {
  onOpenAgent: () => void;
  onOpenNews: () => void;
  embedded?: boolean;
  request?: CanvasRequest;
}) {
  const [items, setItems] = useState<WatchlistItem[]>([]);
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [selectedCode, setSelectedCode] = useState("600519");
  const [section, setSection] = useState<WorkbenchSection>("overview");
  const [panel, setPanel] = useState<DetailPanel>("summary");
  const [overview, setOverview] = useState<
    Record<string, WorkbenchQueryResult>
  >({});
  const [detail, setDetail] = useState<Record<string, WorkbenchQueryResult>>(
    {},
  );
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [querying, setQuerying] = useState(false);
  const [chartMode, setChartMode] = useState<ChartMode>("day");
  const [strategyField, setStrategyField] = useState("close");
  const [strategyOperator, setStrategyOperator] = useState<
    "gt" | "gte" | "lt" | "lte" | "cross_up" | "cross_down"
  >("gte");
  const [strategyValue, setStrategyValue] = useState("0");
  const [backtest, setBacktest] = useState<BacktestResult | null>(null);
  const [backtesting, setBacktesting] = useState(false);
  const [backtestName, setBacktestName] = useState("均线突破策略");
  const [backtestRules, setBacktestRules] = useState<BacktestRuleDraft[]>([
    { field: "ma5", operator: "cross_up", value: "", compareField: "ma10" },
  ]);
  const [exitBars, setExitBars] = useState("10");
  const [takeProfit, setTakeProfit] = useState("10");
  const [stopLoss, setStopLoss] = useState("5");
  const [initialCapital, setInitialCapital] = useState("100000");
  const [positionPct, setPositionPct] = useState("95");
  const [commissionRate, setCommissionRate] = useState("0.025");
  const [stampDutyRate, setStampDutyRate] = useState("0.1");
  const [slippageRate, setSlippageRate] = useState("0.5");
  const [reportDownloading, setReportDownloading] = useState(false);
  const [researchNote, setResearchNote] = useState<ResearchNote | null>(null);
  const [noteDraft, setNoteDraft] = useState({
    title: "",
    thesis: "",
    risks: "",
    key_metrics: "",
    reminders: "",
  });
  const [investmentDecisions, setInvestmentDecisions] = useState<InvestmentDecision[]>([]);
  const [decisionDraft, setDecisionDraft] = useState({
    action: "review" as InvestmentDecision["action"],
    shares: "",
    price: "",
    rationale: "",
    target_or_stop: "",
    review: "",
  });
  const [strategyVersions, setStrategyVersions] = useState<StrategyVersion[]>([]);
  const [versionDraft, setVersionDraft] = useState({
    strategy_name: "",
    version: "v1.0",
    change_summary: "",
    rationale: "",
    backtest_summary: "",
  });
  const [researchReports, setResearchReports] = useState<ResearchReport[]>([]);
  const [reportType, setReportType] = useState<ResearchReport["report_type"]>("fundamental");
  const [reportGenerating, setReportGenerating] = useState(false);
  const [researchSaving, setResearchSaving] = useState(false);
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [alertOperator, setAlertOperator] = useState<
    "gt" | "gte" | "lt" | "lte"
  >("gte");
  const [alertValue, setAlertValue] = useState("");
  const [checkingAlerts, setCheckingAlerts] = useState(false);
  const [strategies, setStrategies] = useState<SavedStrategy[]>([]);
  const [strategyName, setStrategyName] = useState("");
  const [strategyType, setStrategyType] = useState("selection");
  const [strategyMode, setStrategyMode] = useState("weighted");
  const [strategyWeight, setStrategyWeight] = useState("1");
  const [decision, setDecision] = useState<StrategyDecision | null>(null);
  const [strategyPrompt, setStrategyPrompt] = useState("");
  const [strategyDraft, setStrategyDraft] = useState<StrategyDraft | null>(
    null,
  );
  const [draftingStrategy, setDraftingStrategy] = useState(false);
  const [savingDraft, setSavingDraft] = useState(false);

  const query = async (
    tool: string,
    argumentsValue: Record<string, unknown>,
  ) => {
    const response = await fetch(`${API_BASE}/agent/workbench/query`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tool, arguments: argumentsValue }),
    });
    const body = (await response.json().catch(() => null)) as
      | WorkbenchQueryResult
      | { detail?: string }
      | null;
    if (!response.ok)
      throw new Error(
        (body && "detail" in body && body.detail) || "工作台查询失败",
      );
    return body as WorkbenchQueryResult;
  };

  const loadOverview = async () => {
    const tradeDate = new Date().toISOString().slice(0, 10);
    setOverview({});
    const entries = await Promise.all([
      query("get_market_quote", { codes: ["000001", "399001", "399006"] })
        .then((result) => ["market", result] as const)
        .catch(
          (requestError) =>
            [
              "market",
              {
                tool: "get_market_quote",
                status: "error",
                error:
                  requestError instanceof Error
                    ? requestError.message
                    : "查询失败",
              },
            ] as const,
        ),
      query("get_industry_comparison", { top_n: 12 })
        .then((result) => ["industry", result] as const)
        .catch(
          (requestError) =>
            [
              "industry",
              {
                tool: "get_industry_comparison",
                status: "error",
                error:
                  requestError instanceof Error
                    ? requestError.message
                    : "查询失败",
              },
            ] as const,
        ),
      query("get_limit_pool", { pool: "limit_up", trade_date: tradeDate })
        .then((result) => ["limitUp", result] as const)
        .catch(
          (requestError) =>
            [
              "limitUp",
              {
                tool: "get_limit_pool",
                status: "error",
                error:
                  requestError instanceof Error
                    ? requestError.message
                    : "查询失败",
              },
            ] as const,
        ),
      query("get_limit_up_sentiment", { trade_date: tradeDate })
        .then((result) => ["sentiment", result] as const)
        .catch(
          (requestError) =>
            [
              "sentiment",
              {
                tool: "get_limit_up_sentiment",
                status: "error",
                error:
                  requestError instanceof Error
                    ? requestError.message
                    : "查询失败",
              },
            ] as const,
        ),
    ]);
    setOverview(Object.fromEntries(entries));
  };

  const loadWatchlist = async () => {
    const response = await fetch(`${API_BASE}/agent/watchlist`);
    if (!response.ok) throw new Error("无法读取自选股");
    const storedItems = (await response.json()) as WatchlistItem[];
    setItems(storedItems);
    if (storedItems[0]) setSelectedCode(storedItems[0].code);
  };

  const loadAlerts = async () => {
    const response = await fetch(`${API_BASE}/agent/alerts`);
    if (!response.ok) throw new Error("无法读取提醒");
    setAlerts((await response.json()) as AlertItem[]);
  };

  const loadStrategies = async () => {
    const response = await fetch(`${API_BASE}/agent/strategies`);
    if (!response.ok) throw new Error("无法读取策略");
    setStrategies((await response.json()) as SavedStrategy[]);
  };

  const loadResearch = async (code = selectedCode) => {
    const normalized = code.trim().replace(/^(sh|sz|bj)/i, "");
    if (!/^\d{6}$/.test(normalized)) return;
    const [noteResponse, decisionResponse, versionResponse, reportResponse] =
      await Promise.all([
        fetch(`${API_BASE}/agent/research/notes/${normalized}`),
        fetch(`${API_BASE}/agent/research/decisions?code=${normalized}`),
        fetch(`${API_BASE}/agent/research/strategy-versions`),
        fetch(`${API_BASE}/agent/research/reports?code=${normalized}`),
      ]);
    if (!noteResponse.ok || !decisionResponse.ok || !versionResponse.ok || !reportResponse.ok)
      throw new Error("无法读取本地研究档案");
    const note = (await noteResponse.json()) as ResearchNote | null;
    setResearchNote(note);
    setNoteDraft({
      title: note?.title || "",
      thesis: note?.thesis || "",
      risks: note?.risks || "",
      key_metrics: note?.key_metrics || "",
      reminders: note?.reminders || "",
    });
    setInvestmentDecisions((await decisionResponse.json()) as InvestmentDecision[]);
    setStrategyVersions((await versionResponse.json()) as StrategyVersion[]);
    setResearchReports((await reportResponse.json()) as ResearchReport[]);
  };

  const saveResearchNote = async (event: FormEvent) => {
    event.preventDefault();
    setResearchSaving(true);
    setError("");
    try {
      const response = await fetch(`${API_BASE}/agent/research/notes`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code: selectedCode, ...noteDraft }),
      });
      const body = (await response.json().catch(() => null)) as ResearchNote | { detail?: string } | null;
      if (!response.ok) throw new Error(body && "detail" in body ? body.detail : "保存研究笔记失败");
      setResearchNote(body as ResearchNote);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "保存研究笔记失败");
    } finally {
      setResearchSaving(false);
    }
  };

  const createInvestmentDecision = async (event: FormEvent) => {
    event.preventDefault();
    if (!decisionDraft.rationale.trim()) {
      setError("请填写决策依据");
      return;
    }
    setResearchSaving(true);
    setError("");
    try {
      const response = await fetch(`${API_BASE}/agent/research/decisions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          code: selectedCode,
          ...decisionDraft,
          shares: decisionDraft.shares ? Number(decisionDraft.shares) : null,
          price: decisionDraft.price ? Number(decisionDraft.price) : null,
        }),
      });
      const body = (await response.json().catch(() => null)) as InvestmentDecision | { detail?: string } | null;
      if (!response.ok) throw new Error(body && "detail" in body ? body.detail : "保存决策日志失败");
      setInvestmentDecisions((current) => [body as InvestmentDecision, ...current]);
      setDecisionDraft({ action: "review", shares: "", price: "", rationale: "", target_or_stop: "", review: "" });
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "保存决策日志失败");
    } finally {
      setResearchSaving(false);
    }
  };

  const createStrategyVersion = async (event: FormEvent) => {
    event.preventDefault();
    if (!versionDraft.strategy_name.trim() || !versionDraft.change_summary.trim()) {
      setError("请填写策略名称和版本变更");
      return;
    }
    setResearchSaving(true);
    setError("");
    try {
      const selectedStrategy = strategies.find((item) => item.name === versionDraft.strategy_name);
      const response = await fetch(`${API_BASE}/agent/research/strategy-versions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...versionDraft, strategy_id: selectedStrategy?.id || null }),
      });
      const body = (await response.json().catch(() => null)) as StrategyVersion | { detail?: string } | null;
      if (!response.ok) throw new Error(body && "detail" in body ? body.detail : "保存策略版本失败");
      setStrategyVersions((current) => [body as StrategyVersion, ...current]);
      setVersionDraft((current) => ({ ...current, change_summary: "", rationale: "", backtest_summary: "" }));
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "保存策略版本失败");
    } finally {
      setResearchSaving(false);
    }
  };

  const generateResearchReport = async (event: FormEvent) => {
    event.preventDefault();
    setReportGenerating(true);
    setError("");
    try {
      const response = await fetch(`${API_BASE}/agent/research/reports/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code: selectedCode, report_type: reportType, model: "deepseek" }),
      });
      const body = (await response.json().catch(() => null)) as ResearchReport | { detail?: string } | null;
      if (!response.ok) throw new Error(body && "detail" in body ? body.detail : "生成研究报告失败");
      setResearchReports((current) => [body as ResearchReport, ...current]);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "生成研究报告失败");
    } finally {
      setReportGenerating(false);
    }
  };

  const downloadResearchReport = async (report: ResearchReport) => {
    try {
      const response = await fetch(`${API_BASE}/agent/research/reports/${report.id}/pdf`);
      if (!response.ok) throw new Error("下载研究报告失败");
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `research-report-${report.code}.pdf`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "下载研究报告失败");
    }
  };

  useEffect(() => {
    // The initial workspace load is intentionally performed once when this view mounts.
    void Promise.all([
      loadWatchlist(),
      loadOverview(),
      loadAlerts(),
      loadStrategies(),
      loadResearch(),
    ])
      .catch((requestError) =>
        setError(
          requestError instanceof Error
            ? requestError.message
            : "工作台初始化失败",
        ),
      )
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const addWatchlistItem = async (event: FormEvent) => {
    event.preventDefault();
    if (!code.trim()) return;
    try {
      setError("");
      const response = await fetch(`${API_BASE}/agent/watchlist`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code, name }),
      });
      const body = (await response.json().catch(() => null)) as
        | { detail?: string }
        | WatchlistItem
        | null;
      if (!response.ok)
        throw new Error(
          body && "detail" in body ? body.detail : "无法添加自选股",
        );
      setItems((current) => [body as WatchlistItem, ...current]);
      setCode("");
      setName("");
    } catch (requestError) {
      setError(
        requestError instanceof Error ? requestError.message : "无法添加自选股",
      );
    }
  };

  const removeWatchlistItem = async (item: WatchlistItem) => {
    try {
      const response = await fetch(`${API_BASE}/agent/watchlist/${item.id}`, {
        method: "DELETE",
      });
      if (!response.ok) throw new Error("无法删除自选股");
      setItems((current) =>
        current.filter((currentItem) => currentItem.id !== item.id),
      );
    } catch (requestError) {
      setError(
        requestError instanceof Error ? requestError.message : "无法删除自选股",
      );
    }
  };

  const loadDetail = async (nextCode: string) => {
    const normalized = nextCode.trim().replace(/^(sh|sz|bj)/i, "");
    if (!/^\d{6}$/.test(normalized)) {
      setError("请输入六位 A 股代码");
      return;
    }
    setSelectedCode(normalized);
    setSection("detail");
    setPanel("kline");
    setChartMode("day");
    setBacktest(null);
    void loadResearch(normalized).catch((requestError) =>
      setError(requestError instanceof Error ? requestError.message : "无法读取本地研究档案"),
    );
    setQuerying(true);
    setError("");
    setDetail({});
    void query("get_kline_with_ma", { code: normalized })
      .then((result) => setDetail((current) => ({ ...current, kline: result })))
      .catch((requestError) =>
        setDetail((current) => ({
          ...current,
          kline: {
            tool: "get_kline_with_ma",
            status: "error",
            error:
              requestError instanceof Error ? requestError.message : "查询失败",
          },
        })),
      );
    const entries = await Promise.all(
      [
        query("get_market_quote", { codes: [normalized] }).then(
          (result) => ["quote", result] as const,
        ),
        query("get_finance_snapshot", { code: normalized }).then(
          (result) => ["finance", result] as const,
        ),
        query("get_concept_blocks", { code: normalized }).then(
          (result) => ["concepts", result] as const,
        ),
      ].map((promise) =>
        promise.catch(
          (requestError) =>
            [
              "error",
              {
                tool: "workbench",
                status: "error",
                error:
                  requestError instanceof Error
                    ? requestError.message
                    : "查询失败",
              },
            ] as const,
        ),
      ),
    );
    setDetail((current) => ({ ...current, ...Object.fromEntries(entries) }));
    setQuerying(false);
  };

  useEffect(() => {
    if (!request) return;
    if (request.section === "detail" && request.code) {
      void loadDetail(request.code);
      return;
    }
    setSection(request.section);
    // The request is an explicit user action from the conversation pane.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [request]);

  const loadPanel = async (nextPanel: DetailPanel) => {
    setPanel(nextPanel);
    if (nextPanel === "summary" || detail[nextPanel]) return;
    setQuerying(true);
    const tools: Record<
      Exclude<DetailPanel, "summary">,
      [string, Record<string, unknown>]
    > = {
      kline: ["get_kline", { code: selectedCode, period: "day", limit: 120 }],
      fundamentals: [
        "get_financial_statements",
        { code: selectedCode, report_type: "lrb", periods: 8 },
      ],
      reports: ["get_announcements", { code: selectedCode, limit: 20 }],
      concepts: ["get_hot_concepts", { code: selectedCode }],
      flow: ["get_fund_flow_history", { code: selectedCode }],
    };
    const [tool, args] = tools[nextPanel];
    try {
      if (nextPanel === "kline") {
        const daily = await query("get_kline_with_ma", { code: selectedCode });
        setDetail((current) => ({ ...current, kline: daily }));
        setQuerying(false);
        return;
      }
      if (nextPanel === "reports") {
        const [announcements, reports] = await Promise.all([
          query("get_announcements", { code: selectedCode, limit: 20 }),
          query("get_stock_reports", { code: selectedCode, max_pages: 2 }),
        ]);
        const combinedRows = [
          ...workbenchRows(announcements.data),
          ...workbenchRows(reports.data).map((row) => ({
            ...row,
            type: "研报",
          })),
        ];
        setDetail((current) => ({
          ...current,
          reports: { ...announcements, data: combinedRows },
        }));
        setQuerying(false);
        return;
      }
      if (nextPanel === "fundamentals") {
        const [income, balance, cashflow] = await Promise.all([
          query("get_financial_statements", {
            code: selectedCode,
            report_type: "lrb",
            periods: 8,
          }),
          query("get_financial_statements", {
            code: selectedCode,
            report_type: "fzb",
            periods: 8,
          }),
          query("get_financial_statements", {
            code: selectedCode,
            report_type: "llb",
            periods: 8,
          }),
        ]);
        const combinedRows = [
          ...workbenchRows(income.data).map((row) => ({
            ...row,
            statement: "利润表",
          })),
          ...workbenchRows(balance.data).map((row) => ({
            ...row,
            statement: "资产负债表",
          })),
          ...workbenchRows(cashflow.data).map((row) => ({
            ...row,
            statement: "现金流量表",
          })),
        ];
        const firstFailure = [income, balance, cashflow].find(
          (result) => result.status !== "success",
        );
        setDetail((current) => ({
          ...current,
          fundamentals: {
            ...income,
            status: combinedRows.length
              ? "success"
              : firstFailure?.status || income.status,
            source: [income.source, balance.source, cashflow.source]
              .filter(Boolean)
              .join(" / "),
            data: combinedRows,
            error: firstFailure?.error,
          },
        }));
        setQuerying(false);
        return;
      }
      const result = await query(tool, args);
      setDetail((current) => ({ ...current, [nextPanel]: result }));
    } catch (requestError) {
      setDetail((current) => ({
        ...current,
        [nextPanel]: {
          tool,
          status: "error",
          error:
            requestError instanceof Error ? requestError.message : "查询失败",
        },
      }));
    } finally {
      setQuerying(false);
    }
  };

  const backtestPayload = (): {
    payload: Record<string, unknown>;
    error?: string;
  } => {
    const rules = backtestRules.map((rule) => {
      const value = rule.value.trim() ? Number(rule.value) : undefined;
      return {
        field: rule.field,
        operator: rule.operator,
        value,
        compare_field: rule.compareField || undefined,
      };
    });
    const invalidRule = rules.some(
      (rule) =>
        (rule.value === undefined && !rule.compare_field) ||
        (rule.value !== undefined && !Number.isFinite(rule.value)),
    );
    const numeric = [
      initialCapital,
      positionPct,
      commissionRate,
      stampDutyRate,
      slippageRate,
      exitBars,
      takeProfit,
      stopLoss,
    ].map(Number);
    if (
      invalidRule ||
      numeric.some((value) => !Number.isFinite(value)) ||
      numeric[0] < 10000 ||
      numeric[1] <= 0 ||
      numeric[1] > 100 ||
      numeric[5] < 1 ||
      numeric[6] < 0 ||
      numeric[7] < 0
    )
      return { payload: {}, error: "请完整填写入场条件、资金、仓位和退出参数" };
    return {
      payload: {
        code: selectedCode,
        strategy_name: backtestName.trim() || "自定义策略",
        period: "day",
        limit: 360,
        rules,
        exit_after_bars: Math.round(numeric[5]),
        initial_capital: numeric[0],
        position_pct: numeric[1] / 100,
        commission_rate: numeric[2] / 100,
        stamp_duty_rate: numeric[3] / 100,
        slippage_rate: numeric[4] / 100,
        take_profit_pct: numeric[6],
        stop_loss_pct: numeric[7],
      },
    };
  };

  const updateBacktestRule = (
    index: number,
    patch: Partial<BacktestRuleDraft>,
  ) =>
    setBacktestRules((current) =>
      current.map((rule, ruleIndex) =>
        ruleIndex === index ? { ...rule, ...patch } : rule,
      ),
    );
  const addBacktestRule = () =>
    setBacktestRules((current) => [
      ...current,
      {
        field: "volume",
        operator: "gt",
        value: "1.5",
        compareField: "volume_ma5",
      },
    ]);
  const removeBacktestRule = (index: number) =>
    setBacktestRules((current) =>
      current.length > 1
        ? current.filter((_, ruleIndex) => ruleIndex !== index)
        : current,
    );

  const runBacktest = async (event: FormEvent) => {
    event.preventDefault();
    const built = backtestPayload();
    if (built.error) {
      setError(built.error);
      return;
    }
    setBacktesting(true);
    setError("");
    try {
      const response = await fetch(`${API_BASE}/agent/strategy/backtest`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(built.payload),
      });
      const result = (await response.json().catch(() => null)) as
        | BacktestResult
        | { detail?: string }
        | null;
      if (!response.ok)
        throw new Error(
          result && "detail" in result ? result.detail : "回测失败",
        );
      setBacktest(result as BacktestResult);
    } catch (requestError) {
      setError(
        requestError instanceof Error ? requestError.message : "回测失败",
      );
    } finally {
      setBacktesting(false);
    }
  };

  const exportBacktestCsv = () => {
    if (!backtest?.trades?.length) return;
    const headers = [
      "买入日期",
      "买入价",
      "卖出日期",
      "卖出价",
      "股数",
      "收益率",
      "收益金额",
      "退出原因",
    ];
    const rows = backtest.trades.map((trade) => [
      trade.entryTime,
      trade.entryPrice,
      trade.exitTime,
      trade.exitPrice,
      trade.shares ?? "",
      trade.returnPct,
      trade.profit ?? "",
      trade.exitReason ?? "",
    ]);
    const csv = [headers, ...rows]
      .map((row) =>
        row.map((cell) => `"${String(cell).replaceAll('"', '""')}"`).join(","),
      )
      .join("\r\n");
    const blob = new Blob([`\ufeff${csv}`], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `backtest-trades-${selectedCode}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  };

  const downloadBacktestReport = async () => {
    const built = backtestPayload();
    if (built.error) {
      setError(built.error);
      return;
    }
    setReportDownloading(true);
    try {
      const response = await fetch(
        `${API_BASE}/agent/strategy/backtest/report`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ backtest: built.payload }),
        },
      );
      if (!response.ok) throw new Error("PDF 报告生成失败");
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `backtest-report-${selectedCode}.pdf`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "PDF 报告生成失败",
      );
    } finally {
      setReportDownloading(false);
    }
  };

  const createAlert = async (event: FormEvent) => {
    event.preventDefault();
    const value = Number(alertValue);
    if (!Number.isFinite(value)) {
      setError("提醒价格必须是数字");
      return;
    }
    try {
      const response = await fetch(`${API_BASE}/agent/alerts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          code: selectedCode,
          field: "price",
          operator: alertOperator,
          value,
        }),
      });
      const body = (await response.json().catch(() => null)) as
        | AlertItem
        | { detail?: string }
        | null;
      if (!response.ok)
        throw new Error(
          body && "detail" in body ? body.detail : "无法创建提醒",
        );
      setAlerts((current) => [body as AlertItem, ...current]);
      setAlertValue("");
    } catch (requestError) {
      setError(
        requestError instanceof Error ? requestError.message : "无法创建提醒",
      );
    }
  };

  const removeAlert = async (alert: AlertItem) => {
    try {
      const response = await fetch(`${API_BASE}/agent/alerts/${alert.id}`, {
        method: "DELETE",
      });
      if (!response.ok) throw new Error("无法删除提醒");
      setAlerts((current) => current.filter((item) => item.id !== alert.id));
    } catch (requestError) {
      setError(
        requestError instanceof Error ? requestError.message : "无法删除提醒",
      );
    }
  };

  const checkAlerts = async () => {
    setCheckingAlerts(true);
    try {
      const response = await fetch(`${API_BASE}/agent/alerts/check`, {
        method: "POST",
      });
      if (!response.ok) throw new Error("无法检查提醒");
      await response.json();
      await loadAlerts();
    } catch (requestError) {
      setError(
        requestError instanceof Error ? requestError.message : "无法检查提醒",
      );
    } finally {
      setCheckingAlerts(false);
    }
  };

  const saveStrategy = async (event: FormEvent) => {
    event.preventDefault();
    const value = Number(strategyValue);
    const weight = Number(strategyWeight);
    if (
      !strategyName.trim() ||
      !Number.isFinite(value) ||
      !Number.isFinite(weight)
    ) {
      setError("请填写策略名称、阈值和权重");
      return;
    }
    try {
      const response = await fetch(`${API_BASE}/agent/strategies`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: strategyName,
          type: strategyType,
          code: selectedCode,
          field: strategyField === "pct" ? "pct" : "price",
          operator: strategyOperator,
          value,
          mode: strategyMode,
          weight,
        }),
      });
      if (!response.ok) throw new Error("无法保存策略");
      setStrategyName("");
      await loadStrategies();
    } catch (requestError) {
      setError(
        requestError instanceof Error ? requestError.message : "无法保存策略",
      );
    }
  };

  const draftNaturalStrategy = async (event: FormEvent) => {
    event.preventDefault();
    if (!strategyPrompt.trim()) return;
    setDraftingStrategy(true);
    setError("");
    try {
      const response = await fetch(`${API_BASE}/agent/strategies/draft`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: strategyPrompt, model: "deepseek" }),
      });
      const body = (await response.json().catch(() => null)) as {
        draft?: StrategyDraft;
        detail?: string;
      } | null;
      if (!response.ok || !body?.draft)
        throw new Error(body?.detail || "无法解析策略描述");
      setStrategyDraft(body.draft);
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "无法解析策略描述",
      );
    } finally {
      setDraftingStrategy(false);
    }
  };

  const saveStrategyDraft = async () => {
    if (!strategyDraft) return;
    setSavingDraft(true);
    setError("");
    try {
      const response = await fetch(`${API_BASE}/agent/strategies`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(strategyDraft),
      });
      const body = (await response.json().catch(() => null)) as {
        detail?: string;
      } | null;
      if (!response.ok) throw new Error(body?.detail || "无法启用策略");
      setStrategyDraft(null);
      setStrategyPrompt("");
      await loadStrategies();
    } catch (requestError) {
      setError(
        requestError instanceof Error ? requestError.message : "无法启用策略",
      );
    } finally {
      setSavingDraft(false);
    }
  };

  const updateStrategy = async (id: string, status: "active" | "paused") => {
    await fetch(`${API_BASE}/agent/strategies/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    });
    await loadStrategies();
  };
  const removeStrategy = async (id: string) => {
    await fetch(`${API_BASE}/agent/strategies/${id}`, { method: "DELETE" });
    await loadStrategies();
  };
  const runDecision = async () => {
    try {
      const response = await fetch(`${API_BASE}/agent/strategies/decision`, {
        method: "POST",
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail || "运行失败");
      setDecision(body as StrategyDecision);
      await loadStrategies();
    } catch (requestError) {
      setError(
        requestError instanceof Error ? requestError.message : "综合决策失败",
      );
    }
  };

  const strategyScheduleText = (strategy: Pick<SavedStrategy, "schedule">) => {
    if (strategy.schedule?.mode === "interval")
      return `每 ${Math.round(strategy.schedule.intervalSeconds / 60)} 分钟检查`;
    if (strategy.schedule?.mode === "time-point")
      return `每日 ${strategy.schedule.at} 检查`;
    if (strategy.schedule?.mode === "condition")
      return `条件轮询，每 ${Math.round(strategy.schedule.intervalSeconds / 60)} 分钟检查`;
    return "仅手动运行";
  };
  const conditionText = (condition: StrategyCondition) =>
    `${condition.field} ${condition.operator} ${condition.compare_field || (condition.value ?? "—")}`;

  const renderStrategyConsole = () => (
    <section className="strategy-console">
      <section className="workbench-panel">
        <div className="panel-heading">
          <div>
            <span className="workbench-section-label">AI STRATEGY</span>
            <h2>一句话建立策略</h2>
          </div>
          <button
            type="button"
            onClick={() => void runDecision()}
            disabled={!strategies.some((item) => item.status === "active")}
          >
            <Brain size={16} />
            运行综合决策
          </button>
        </div>
        <form className="strategy-prompt" onSubmit={draftNaturalStrategy}>
          <label className="sr-only" htmlFor="strategy-prompt">
            用自然语言描述策略
          </label>
          <textarea
            id="strategy-prompt"
            value={strategyPrompt}
            onChange={(event) => setStrategyPrompt(event.target.value)}
            placeholder="例如：600519 价格高于 1500 且涨跌幅大于 2%，每 5 分钟检查，命中后记录决策"
            rows={2}
          />
          <button
            type="submit"
            disabled={!strategyPrompt.trim() || draftingStrategy}
          >
            <Sparkles size={16} />
            {draftingStrategy ? "解析中" : "AI 解析"}
          </button>
        </form>
        {strategyDraft && (
          <section className="strategy-draft">
            <div>
              <strong>{strategyDraft.name}</strong>
              <span>
                {strategyDraft.type} · {strategyDraft.code} ·{" "}
                {strategyDraft.conditions.map(conditionText).join(" 且 ")}
              </span>
            </div>
            <p>
              {strategyDraft.schedule_mode === "interval"
                ? `每 ${Math.round(strategyDraft.interval_seconds / 60)} 分钟检查`
                : strategyDraft.schedule_mode === "time-point"
                  ? `每日 ${strategyDraft.schedule_at} 检查`
                  : strategyDraft.schedule_mode === "condition"
                    ? `条件轮询，每 ${Math.round(strategyDraft.interval_seconds / 60)} 分钟检查`
                    : "仅手动运行"}{" "}
              · 动作：{strategyDraft.actions.join("、") || "记录决策"}
            </p>
            <div>
              <button
                type="button"
                onClick={() => void saveStrategyDraft()}
                disabled={savingDraft}
              >
                <Check size={16} />
                {savingDraft ? "启用中" : "确认启用"}
              </button>
              <button type="button" onClick={() => setStrategyDraft(null)}>
                <X size={16} />
                取消
              </button>
            </div>
          </section>
        )}
      </section>
      <section className="workbench-panel">
        <div className="panel-heading">
          <div>
            <span className="workbench-section-label">MANUAL RULE</span>
            <h2>手动规则</h2>
          </div>
        </div>
        <form className="strategy-form strategy-create" onSubmit={saveStrategy}>
          <input
            value={strategyName}
            onChange={(event) => setStrategyName(event.target.value)}
            placeholder="策略名称"
          />
          <select
            value={strategyType}
            onChange={(event) => setStrategyType(event.target.value)}
          >
            <option value="selection">选股</option>
            <option value="timing">择时</option>
            <option value="risk">风控</option>
            <option value="review">复盘</option>
            <option value="custom">自定义</option>
          </select>
          <select
            value={strategyField}
            onChange={(event) => setStrategyField(event.target.value)}
          >
            <option value="price">价格</option>
            <option value="pct">涨跌幅</option>
          </select>
          <select
            value={strategyOperator}
            onChange={(event) =>
              setStrategyOperator(event.target.value as typeof strategyOperator)
            }
          >
            <option value="gte">≥</option>
            <option value="gt">&gt;</option>
            <option value="lte">≤</option>
            <option value="lt">&lt;</option>
          </select>
          <input
            value={strategyValue}
            onChange={(event) => setStrategyValue(event.target.value)}
            placeholder="阈值"
          />
          <select
            value={strategyMode}
            onChange={(event) => setStrategyMode(event.target.value)}
          >
            <option value="weighted">加权</option>
            <option value="veto">否决</option>
            <option value="consensus">共识</option>
          </select>
          <input
            value={strategyWeight}
            onChange={(event) => setStrategyWeight(event.target.value)}
            placeholder="权重"
          />
          <button type="submit">
            <Plus size={16} />
            保存策略
          </button>
        </form>
        <div className="strategy-list">
          {strategies.map((item) => (
            <article className="strategy-item" key={item.id}>
              <div>
                <strong>{item.name}</strong>
                <span>
                  {item.type} · {item.code} ·{" "}
                  {item.conditions?.length
                    ? item.conditions.map(conditionText).join(" 且 ")
                    : `${item.field} ${item.operator} ${item.value}`}{" "}
                  · {item.mode} × {item.weight}
                </span>
                <small>
                  {strategyScheduleText(item)}
                  {item.actions?.length
                    ? ` · 动作：${item.actions.join("、")}`
                    : ""}
                </small>
              </div>
              <div>
                <button
                  type="button"
                  onClick={() =>
                    void updateStrategy(
                      item.id,
                      item.status === "active" ? "paused" : "active",
                    )
                  }
                >
                  {item.status === "active" ? "暂停" : "启用"}
                </button>
                <button
                  type="button"
                  onClick={() => void removeStrategy(item.id)}
                  aria-label={`删除${item.name}`}
                >
                  <Trash2 size={15} />
                </button>
              </div>
            </article>
          ))}
          {!strategies.length && (
            <p className="conversation-empty">
              用一句话描述策略，或建立一条手动规则。
            </p>
          )}
        </div>
      </section>
      {decision && (
        <section className="workbench-panel decision-panel">
          <div>
            <span className="workbench-section-label">DECISION LAYER</span>
            <h2>{decision.conclusion}</h2>
            <p>
              合成方式：{decision.mode} · 一致度 {decision.rating}% ·{" "}
              {decision.triggerSource === "scheduler" ? "自动触发" : "手动运行"}
            </p>
          </div>
          {decision.catalysts?.length ? (
            <p>条件催化：{decision.catalysts.join("、")}</p>
          ) : null}
          {decision.risks?.length ? (
            <p>风险提示：{decision.risks.join("、")}</p>
          ) : null}
          {decision.tree.map((node) => (
            <div className="decision-step" key={node.step}>
              <strong>{node.step}</strong>
              <span>{node.result}</span>
            </div>
          ))}
        </section>
      )}
    </section>
  );

  const renderResearchArchive = () => (
    <section className="research-archive">
      <header className="research-archive-header">
        <div>
          <span className="workbench-section-label">PRIVATE RESEARCH ARCHIVE</span>
          <h2>投研档案 · {selectedCode}</h2>
          <p>笔记、决策、策略版本和 AI 报告均保存到本机。</p>
        </div>
        <button
          type="button"
          className="icon-action"
          onClick={() => void loadResearch().catch((requestError) => setError(requestError instanceof Error ? requestError.message : "刷新失败"))}
          title="刷新投研档案"
          aria-label="刷新投研档案"
        >
          <History size={16} />
        </button>
      </header>
      <div className="research-grid">
        <section className="workbench-panel research-panel">
          <div className="panel-heading">
            <div>
              <span className="workbench-section-label">RESEARCH NOTE</span>
              <h3>研究笔记</h3>
            </div>
            <BookOpen size={18} aria-hidden="true" />
          </div>
          <form className="research-form" onSubmit={saveResearchNote}>
            <label>
              标题
              <input value={noteDraft.title} onChange={(event) => setNoteDraft((current) => ({ ...current, title: event.target.value }))} placeholder={`${selectedCode} · 我的研究笔记`} />
            </label>
            <label>
              投资逻辑
              <textarea value={noteDraft.thesis} onChange={(event) => setNoteDraft((current) => ({ ...current, thesis: event.target.value }))} rows={4} placeholder="记录你为什么关注这家公司，以及需要验证的事实。" />
            </label>
            <label>
              风险关注
              <textarea value={noteDraft.risks} onChange={(event) => setNoteDraft((current) => ({ ...current, risks: event.target.value }))} rows={3} placeholder="估值、竞争、业绩或数据时效风险。" />
            </label>
            <div className="research-form-split">
              <label>
                关键指标
                <textarea value={noteDraft.key_metrics} onChange={(event) => setNoteDraft((current) => ({ ...current, key_metrics: event.target.value }))} rows={3} placeholder="例如：ROE、PE、库存、毛利率" />
              </label>
              <label>
                提醒事项
                <textarea value={noteDraft.reminders} onChange={(event) => setNoteDraft((current) => ({ ...current, reminders: event.target.value }))} rows={3} placeholder="下次财报、公告或数据验证节点" />
              </label>
            </div>
            <div className="research-form-actions">
              <small>{researchNote ? `最后更新 ${formatDate(researchNote.updated_at)}` : "尚未保存"}</small>
              <button type="submit" disabled={researchSaving}><Save size={15} />{researchSaving ? "保存中" : "保存笔记"}</button>
            </div>
          </form>
        </section>

        <section className="workbench-panel research-panel">
          <div className="panel-heading">
            <div>
              <span className="workbench-section-label">DECISION LOG</span>
              <h3>决策日志</h3>
            </div>
            <ClipboardPenLine size={18} aria-hidden="true" />
          </div>
          <form className="research-form" onSubmit={createInvestmentDecision}>
            <div className="research-form-split">
              <label>
                类型
                <select value={decisionDraft.action} onChange={(event) => setDecisionDraft((current) => ({ ...current, action: event.target.value as InvestmentDecision["action"] }))}>
                  <option value="review">观察</option>
                  <option value="buy">买入记录</option>
                  <option value="sell">卖出记录</option>
                  <option value="hold">继续持有</option>
                </select>
              </label>
              <label>股数<input value={decisionDraft.shares} onChange={(event) => setDecisionDraft((current) => ({ ...current, shares: event.target.value }))} inputMode="numeric" placeholder="可选" /></label>
              <label>价格<input value={decisionDraft.price} onChange={(event) => setDecisionDraft((current) => ({ ...current, price: event.target.value }))} inputMode="decimal" placeholder="可选" /></label>
            </div>
            <label>
              决策依据
              <textarea value={decisionDraft.rationale} onChange={(event) => setDecisionDraft((current) => ({ ...current, rationale: event.target.value }))} rows={4} placeholder="记录数据依据、触发条件和当时的判断。" required />
            </label>
            <label>
              目标 / 止损
              <input value={decisionDraft.target_or_stop} onChange={(event) => setDecisionDraft((current) => ({ ...current, target_or_stop: event.target.value }))} placeholder="例如：PE 回到 35 倍或跌破前低" />
            </label>
            <label>
              复盘（事后填写）
              <textarea value={decisionDraft.review} onChange={(event) => setDecisionDraft((current) => ({ ...current, review: event.target.value }))} rows={2} placeholder="执行是否符合计划，结论哪里需要修正。" />
            </label>
            <div className="research-form-actions"><span /><button type="submit" disabled={researchSaving}><ClipboardPenLine size={15} />记录决策</button></div>
          </form>
          <div className="research-log-list">
            {investmentDecisions.slice(0, 5).map((item) => (
              <article className="research-log-item" key={item.id}>
                <div><strong>{({ buy: "买入", sell: "卖出", hold: "持有", review: "观察" } as Record<string, string>)[item.action]}</strong><time>{formatDate(item.created_at)}</time></div>
                <p>{item.rationale}</p>
                {(item.shares || item.price) && <small>{item.shares ? `${item.shares} 股` : ""}{item.price ? ` @ ${item.price}` : ""}</small>}
              </article>
            ))}
            {!investmentDecisions.length && <p className="research-empty">还没有决策记录。</p>}
          </div>
        </section>
      </div>

      <section className="workbench-panel research-panel strategy-history-panel">
        <div className="panel-heading">
          <div><span className="workbench-section-label">STRATEGY EVOLUTION</span><h3>策略演进</h3></div>
          <History size={18} aria-hidden="true" />
        </div>
        <form className="strategy-version-form" onSubmit={createStrategyVersion}>
          <label>策略名称<select value={versionDraft.strategy_name} onChange={(event) => setVersionDraft((current) => ({ ...current, strategy_name: event.target.value }))}><option value="">选择已有策略</option>{strategies.map((item) => <option value={item.name} key={item.id}>{item.name}</option>)}<option value="自定义策略">自定义策略</option></select></label>
          <label>版本<input value={versionDraft.version} onChange={(event) => setVersionDraft((current) => ({ ...current, version: event.target.value }))} /></label>
          <label>变更内容<input value={versionDraft.change_summary} onChange={(event) => setVersionDraft((current) => ({ ...current, change_summary: event.target.value }))} placeholder="增加成交量过滤" /></label>
          <label>原因<input value={versionDraft.rationale} onChange={(event) => setVersionDraft((current) => ({ ...current, rationale: event.target.value }))} placeholder="减少假突破" /></label>
          <label>回测摘要<input value={versionDraft.backtest_summary} onChange={(event) => setVersionDraft((current) => ({ ...current, backtest_summary: event.target.value }))} placeholder="胜率 62%，收益 +12%" /></label>
          <button type="submit" disabled={researchSaving}><Save size={15} />记录版本</button>
        </form>
        <div className="strategy-version-list">
          {strategyVersions.map((item) => <article className="strategy-version-item" key={item.id}><div><strong>{item.strategy_name} {item.version}</strong><time>{formatDate(item.created_at)}</time></div><p>{item.change_summary}</p><small>{item.rationale || "未填写修改原因"}{item.backtest_summary ? ` · ${item.backtest_summary}` : ""}</small></article>)}
          {!strategyVersions.length && <p className="research-empty">还没有策略版本记录。回测后把有效改动记在这里。</p>}
        </div>
      </section>

      <section className="workbench-panel research-panel report-panel">
        <div className="panel-heading">
          <div><span className="workbench-section-label">AI RESEARCH REPORT</span><h3>投研报告</h3><p>调用行情、财务、K 线和公告数据，生成结构化研究底稿。</p></div>
          <FileText size={18} aria-hidden="true" />
        </div>
        <form className="report-generate-form" onSubmit={generateResearchReport}>
          <label>报告类型<select value={reportType} onChange={(event) => setReportType(event.target.value as ResearchReport["report_type"])}><option value="fundamental">基本面深度分析</option><option value="technical">技术面趋势判断</option><option value="event">事件影响评估</option></select></label>
          <button type="submit" disabled={reportGenerating}><Sparkles size={15} />{reportGenerating ? "生成中" : "生成研究报告"}</button>
        </form>
        <div className="research-report-list">
          {researchReports.map((report) => <article className="research-report-item" key={report.id}><header><div><strong>{report.title}</strong><time>{formatDate(report.created_at)}</time></div><button type="button" onClick={() => void downloadResearchReport(report)} title="下载 PDF"><Download size={15} /> PDF</button></header><div className="research-report-content">{renderAssistantContent(report.content)}</div></article>)}
          {!researchReports.length && <p className="research-empty">还没有研究报告。选择类型后生成第一份本地底稿。</p>}
        </div>
      </section>
    </section>
  );

  const renderWatchlist = () => (
    <section className="watchlist-section" aria-labelledby="watchlist-title">
      <div className="watchlist-heading">
        <div>
          <span className="workbench-section-label">WATCHLIST</span>
          <h2 id="watchlist-title">自选股</h2>
        </div>
        <span>{items.length} 只</span>
      </div>
      <form className="watchlist-form" onSubmit={addWatchlistItem}>
        <label htmlFor="watchlist-code">股票代码</label>
        <input
          id="watchlist-code"
          value={code}
          onChange={(event) => setCode(event.target.value)}
          placeholder="例如 600519"
          inputMode="numeric"
        />
        <label htmlFor="watchlist-name">名称（可选）</label>
        <input
          id="watchlist-name"
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="例如 贵州茅台"
        />
        <button type="submit" disabled={!code.trim()}>
          <Plus size={16} />
          加入自选
        </button>
      </form>
      {items.length === 0 ? (
        <div className="workbench-empty">
          <Star size={20} />
          <strong>还没有自选股</strong>
          <span>添加一个六位股票代码开始建立关注列表。</span>
        </div>
      ) : (
        <div className="watchlist-grid">
          {items.map((item) => (
            <article className="watchlist-item" key={item.id}>
              <div className="watchlist-symbol">
                <Star size={17} />
                <strong>{item.code}</strong>
              </div>
              <div className="watchlist-name">{item.name || "名称待补充"}</div>
              <div className="watchlist-item-actions">
                <button
                  type="button"
                  onClick={() => void loadDetail(item.code)}
                >
                  查看详情
                </button>
                <button
                  type="button"
                  onClick={() => void removeWatchlistItem(item)}
                  aria-label={`删除${item.code}`}
                  title="删除"
                >
                  <Trash2 size={16} />
                </button>
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );

  const renderOverview = () => (
    <>
      <div className="workbench-section-grid">
        <section className="workbench-panel workbench-market-panel">
          <div className="panel-heading">
            <div>
              <span className="workbench-section-label">MARKET OVERVIEW</span>
              <h2>市场概览</h2>
            </div>
            <button
              type="button"
              className="icon-action"
              onClick={() => void loadOverview()}
              title="刷新市场概览"
            >
              <span aria-hidden="true">↻</span>
            </button>
          </div>
          <WorkbenchResultMeta result={overview.market} />
          {loading && !overview.market ? (
            <div className="workbench-loading">正在读取市场行情…</div>
          ) : (
            <div className="quote-grid">
              {workbenchRows(overview.market?.data)
                .slice(0, 6)
                .map((row, index) => (
                  <article className="quote-card" key={index}>
                    <strong>
                      {workbenchValue(row, ["name", "名称", "symbol", "代码"])}
                    </strong>
                    <b>{workbenchValue(row, ["price", "最新", "现价"])}</b>
                    <span>
                      {workbenchValue(row, [
                        "涨跌幅",
                        "changepercent",
                        "percent",
                        "涨幅",
                      ])}
                    </span>
                  </article>
                ))}
            </div>
          )}
        </section>
        <section className="workbench-panel">
          <div className="panel-heading">
            <div>
              <span className="workbench-section-label">INDUSTRY RANKING</span>
              <h2>行业表现</h2>
            </div>
          </div>
          <WorkbenchResultMeta result={overview.industry} />
          <WorkbenchDataTable
            result={overview.industry}
            columns={[
              { label: "行业", keys: ["行业", "name", "板块"] },
              { label: "涨跌幅", keys: ["涨跌幅", "changepercent", "涨幅"] },
              { label: "成交额", keys: ["成交额", "amount", "资金"] },
            ]}
          />
        </section>
      </div>
      {renderWatchlist()}
      <section className="workbench-panel">
        <div className="panel-heading">
          <div>
            <span className="workbench-section-label">LIMIT-UP POOL</span>
            <h2>涨停池与情绪</h2>
          </div>
        </div>
        <WorkbenchResultMeta result={overview.limitUp} />
        <WorkbenchDataTable
          result={overview.limitUp}
          columns={[
            { label: "代码", keys: ["代码", "code", "symbol"] },
            { label: "名称", keys: ["名称", "name"] },
            { label: "最新价", keys: ["最新价", "price"] },
            { label: "涨停原因", keys: ["原因", "reason", "概念"] },
          ]}
        />
        <div className="sentiment-line">
          {overview.sentiment?.status === "success"
            ? `情绪数据已更新：${workbenchRows(overview.sentiment.data)
                .slice(0, 1)
                .map((row) =>
                  workbenchValue(row, ["炸板率", "连板高度", "涨停家数"]),
                )
                .join(" ")}`
            : "涨停情绪数据待接入"}
        </div>
      </section>
    </>
  );

  const renderDetail = () => (
    <>
      <section className="workbench-panel detail-selector">
        <div>
          <span className="workbench-section-label">STOCK DETAIL</span>
          <h2>单股详情</h2>
        </div>
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void loadDetail(selectedCode);
          }}
        >
          <input
            aria-label="查询股票代码"
            value={selectedCode}
            onChange={(event) => setSelectedCode(event.target.value)}
          />
          <button type="submit">查询</button>
        </form>
        {items.length > 0 && (
          <div className="quick-symbols">
            {items.map((item) => (
              <button
                type="button"
                key={item.id}
                className={
                  selectedCode === item.code ? "quick-symbol-active" : ""
                }
                onClick={() => void loadDetail(item.code)}
              >
                {item.code}
                {item.name ? ` ${item.name}` : ""}
              </button>
            ))}
          </div>
        )}
      </section>
      <nav className="detail-tabs" aria-label="单股详情模块">
        {(
          [
            ["summary", "行情"],
            ["kline", "K 线 / 分时"],
            ["fundamentals", "基本面"],
            ["reports", "公告研报"],
            ["concepts", "行业概念"],
            ["flow", "资金流"],
          ] as [DetailPanel, string][]
        ).map(([value, label]) => (
          <button
            type="button"
            key={value}
            className={panel === value ? "detail-tab-active" : ""}
            onClick={() => void loadPanel(value)}
          >
            {label}
          </button>
        ))}
      </nav>
      {querying && (
        <p className="workbench-loading">正在读取 {selectedCode} 数据…</p>
      )}
      {panel === "summary" && (
        <div className="detail-grid">
          <section className="workbench-panel">
            <div className="panel-heading">
              <h2>实时行情</h2>
            </div>
            <WorkbenchResultMeta result={detail.quote} />
            <WorkbenchDataTable
              result={detail.quote}
              columns={[
                { label: "标的", keys: ["名称", "name", "symbol"] },
                { label: "现价", keys: ["现价", "price", "最新"] },
                {
                  label: "涨跌幅",
                  keys: ["涨跌幅", "percent", "changepercent"],
                },
                { label: "成交额", keys: ["成交额", "amount"] },
              ]}
            />
          </section>
          <section className="workbench-panel">
            <div className="panel-heading">
              <h2>财务快照</h2>
            </div>
            <WorkbenchResultMeta result={detail.finance} />
            <WorkbenchDataTable
              result={detail.finance}
              columns={[
                { label: "指标", keys: ["指标", "name", "项目"] },
                { label: "数值", keys: ["数值", "value", "值"] },
                { label: "报告期", keys: ["报告期", "date", "时间"] },
              ]}
            />
          </section>
        </div>
      )}
      {panel === "kline" && (
        <section className="workbench-panel chart-panel">
          <div className="panel-heading">
            <div>
              <h2>{selectedCode} 专业图表</h2>
              <p>
                鼠标滚轮缩放，拖动查看历史；高低点和回测买卖点会显示为图表标记。
              </p>
            </div>
            <div className="chart-mode-switch">
              <button
                type="button"
                className={chartMode === "day" ? "chart-mode-active" : ""}
                onClick={() => setChartMode("day")}
              >
                日 K
              </button>
              <button
                type="button"
                className={chartMode === "intraday" ? "chart-mode-active" : ""}
                onClick={() => setChartMode("intraday")}
              >
                分时
              </button>
            </div>
          </div>
          <WorkbenchResultMeta
            result={chartMode === "intraday" ? detail.intraday : detail.kline}
          />
          <StockPriceChart
            daily={detail.kline}
            intraday={detail.intraday}
            mode={chartMode}
            trades={backtest?.trades}
          />
          <div className="strategy-alert-grid">
            <section className="strategy-box">
              <div className="panel-heading">
                <div>
                  <span className="workbench-section-label">STRATEGY</span>
                  <h3>策略条件与回测</h3>
                </div>
              </div>
              <form className="backtest-config" onSubmit={runBacktest}>
                <div className="backtest-config-top">
                  <label>
                    策略名称
                    <input
                      value={backtestName}
                      onChange={(event) => setBacktestName(event.target.value)}
                    />
                  </label>
                  <label>
                    初始资金
                    <input
                      value={initialCapital}
                      onChange={(event) => setInitialCapital(event.target.value)}
                      inputMode="decimal"
                    />
                    <span>元</span>
                  </label>
                  <label>
                    仓位控制
                    <input
                      value={positionPct}
                      onChange={(event) => setPositionPct(event.target.value)}
                      inputMode="decimal"
                    />
                    <span>%</span>
                  </label>
                </div>
                <section className="backtest-rule-section">
                  <div className="backtest-rule-heading">
                    <div>
                      <span>入场条件</span>
                      <small>全部满足后开仓</small>
                    </div>
                    <button type="button" onClick={addBacktestRule}>
                      <Plus size={14} />
                      添加条件
                    </button>
                  </div>
                  {backtestRules.map((rule, index) => (
                    <div className="backtest-rule-row" key={index}>
                      <span>条件 {index + 1}</span>
                      <select
                        value={rule.field}
                        onChange={(event) =>
                          updateBacktestRule(index, {
                            field: event.target.value as BacktestField,
                          })
                        }
                      >
                        <option value="close">收盘价</option>
                        <option value="ma5">MA5</option>
                        <option value="ma10">MA10</option>
                        <option value="ma20">MA20</option>
                        <option value="volume">成交量</option>
                        <option value="volume_ma5">成交量 MA5</option>
                      </select>
                      <select
                        value={rule.operator}
                        onChange={(event) =>
                          updateBacktestRule(index, {
                            operator: event.target.value as BacktestOperator,
                          })
                        }
                      >
                        <option value="cross_up">上穿</option>
                        <option value="cross_down">下穿</option>
                        <option value="gte">≥</option>
                        <option value="gt">&gt;</option>
                        <option value="lte">≤</option>
                        <option value="lt">&lt;</option>
                      </select>
                      {rule.compareField || rule.operator.startsWith("cross_") ? (
                        <select
                          value={rule.compareField}
                          onChange={(event) =>
                            updateBacktestRule(index, {
                              compareField: event.target.value as BacktestField,
                            })
                          }
                        >
                          <option value="ma5">MA5</option>
                          <option value="ma10">MA10</option>
                          <option value="ma20">MA20</option>
                          <option value="volume_ma5">成交量 MA5</option>
                          <option value="close">收盘价</option>
                        </select>
                      ) : (
                        <input
                          value={rule.value}
                          onChange={(event) =>
                            updateBacktestRule(index, { value: event.target.value })
                          }
                          inputMode="decimal"
                          aria-label={`条件 ${index + 1} 阈值`}
                        />
                      )}
                      {backtestRules.length > 1 && (
                        <button
                          type="button"
                          className="backtest-remove-rule"
                          onClick={() => removeBacktestRule(index)}
                          title="删除条件"
                          aria-label={`删除条件 ${index + 1}`}
                        >
                          <Trash2 size={14} />
                        </button>
                      )}
                    </div>
                  ))}
                </section>
                <section className="backtest-exit-section">
                  <div>
                    <strong>退出条件</strong>
                    <label>
                      <span>止损</span>
                      <input
                        value={stopLoss}
                        onChange={(event) => setStopLoss(event.target.value)}
                        inputMode="decimal"
                      />
                      %
                    </label>
                    <label>
                      <span>止盈</span>
                      <input
                        value={takeProfit}
                        onChange={(event) => setTakeProfit(event.target.value)}
                        inputMode="decimal"
                      />
                      %
                    </label>
                    <label>
                      <span>最大持仓</span>
                      <input
                        value={exitBars}
                        onChange={(event) => setExitBars(event.target.value)}
                        inputMode="numeric"
                      />
                      天
                    </label>
                  </div>
                  <div>
                    <strong>交易成本</strong>
                    <label>
                      <span>佣金</span>
                      <input
                        value={commissionRate}
                        onChange={(event) => setCommissionRate(event.target.value)}
                        inputMode="decimal"
                      />
                      %
                    </label>
                    <label>
                      <span>印花税</span>
                      <input
                        value={stampDutyRate}
                        onChange={(event) => setStampDutyRate(event.target.value)}
                        inputMode="decimal"
                      />
                      %
                    </label>
                    <label>
                      <span>滑点</span>
                      <input
                        value={slippageRate}
                        onChange={(event) => setSlippageRate(event.target.value)}
                        inputMode="decimal"
                      />
                      %
                    </label>
                  </div>
                </section>
                <div className="backtest-actions">
                  <button type="submit" disabled={backtesting}>
                    <Play size={15} />
                    {backtesting ? "正在回测" : "立即回测"}
                  </button>
                  {backtest?.status === "success" && (
                    <>
                      <button
                        type="button"
                        className="backtest-secondary"
                        onClick={exportBacktestCsv}
                      >
                        <Download size={15} />
                        导出 CSV
                      </button>
                      <button
                        type="button"
                        className="backtest-secondary"
                        onClick={() => void downloadBacktestReport()}
                        disabled={reportDownloading}
                      >
                        <FileDown size={15} />
                        {reportDownloading ? "生成 PDF" : "下载 PDF"}
                      </button>
                    </>
                  )}
                </div>
              </form>
              {backtest?.status === "success" && backtest.summary && (
                <section className="backtest-report">
                  <div className="backtest-summary">
                    <span>交易 {backtest.summary.trades}</span>
                    <span>胜率 {backtest.summary.winRate}%</span>
                    <span>累计 {backtest.summary.totalReturnPct}%</span>
                  </div>
                  <div className="backtest-metric-grid">
                    <div><span>年化收益率</span><strong>{backtest.summary.annualizedReturnPct ?? 0}%</strong></div>
                    <div><span>最大回撤</span><strong>{backtest.summary.maxDrawdownPct ?? 0}%</strong></div>
                    <div><span>夏普比率</span><strong>{backtest.summary.sharpeRatio ?? 0}</strong></div>
                    <div><span>盈亏比</span><strong>{backtest.summary.profitLossRatio ?? '—'}</strong></div>
                    <div><span>沪深 300</span><strong>{backtest.summary.benchmarkReturnPct ?? '—'}%</strong></div>
                    <div><span>超额收益</span><strong>{backtest.summary.excessReturnPct ?? '—'}%</strong></div>
                  </div>
                  <div className="equity-report-heading"><span>权益曲线</span><small>期末权益 {backtest.summary.finalEquity?.toLocaleString('zh-CN', { maximumFractionDigits: 0 }) ?? '—'} 元</small></div>
                  <EquityCurveChart points={backtest.equityCurve} />
                </section>
              )}
              {backtest?.status === "error" && (
                <p className="workbench-error">{backtest.error}</p>
              )}
              <WorkbenchDataTable
                result={
                  backtest?.status === "success"
                    ? {
                        tool: "backtest",
                        status: "success",
                        data: backtest.trades ?? [],
                        source: backtest.source,
                        updatedAt: backtest.updatedAt,
                      }
                    : undefined
                }
                columns={[
                  { label: "买入时间", keys: ["entryTime"] },
                  { label: "买入价", keys: ["entryPrice"] },
                  { label: "卖出时间", keys: ["exitTime"] },
                  { label: "收益", keys: ["returnPct"] },
                  { label: "原因", keys: ["exitReason"] },
                ]}
              />
            </section>
            <section className="strategy-box">
              <div className="panel-heading">
                <div>
                  <span className="workbench-section-label">ALERTS</span>
                  <h3>自动提醒</h3>
                </div>
                <button
                  type="button"
                  className="icon-action"
                  onClick={() => void checkAlerts()}
                  disabled={checkingAlerts}
                  title="检查提醒"
                >
                  <Bell size={15} />
                </button>
              </div>
              <form className="strategy-form" onSubmit={createAlert}>
                <select
                  value={alertOperator}
                  onChange={(event) =>
                    setAlertOperator(event.target.value as typeof alertOperator)
                  }
                >
                  <option value="gte">价格 ≥</option>
                  <option value="gt">价格 &gt;</option>
                  <option value="lte">价格 ≤</option>
                  <option value="lt">价格 &lt;</option>
                </select>
                <input
                  value={alertValue}
                  onChange={(event) => setAlertValue(event.target.value)}
                  placeholder="提醒价"
                  inputMode="decimal"
                />
                <button type="submit">
                  <Plus size={15} />
                  添加
                </button>
              </form>
              <div className="alert-list">
                {alerts
                  .filter((alert) => alert.code === selectedCode)
                  .map((alert) => (
                    <article
                      className={`alert-item ${alert.triggered_at ? "alert-triggered" : ""}`}
                      key={alert.id}
                    >
                      <div>
                        <strong>{alert.code}</strong>
                        <span>
                          {alert.operator} {alert.value} · 最新{" "}
                          {alert.last_value ?? "未检查"}
                        </span>
                      </div>
                      <button
                        type="button"
                        onClick={() => void removeAlert(alert)}
                        title="删除提醒"
                      >
                        <Trash2 size={15} />
                      </button>
                    </article>
                  ))}
                {alerts.filter((alert) => alert.code === selectedCode)
                  .length === 0 && (
                  <p className="conversation-empty">当前股票还没有提醒。</p>
                )}
              </div>
            </section>
          </div>
          <WorkbenchDataTable
            result={detail.kline}
            columns={[
              { label: "日期", keys: ["日期", "date", "datetime", "time"] },
              { label: "开盘", keys: ["开盘", "open"] },
              { label: "最高", keys: ["最高", "high"] },
              { label: "最低", keys: ["最低", "low"] },
              { label: "收盘", keys: ["收盘", "close"] },
              { label: "成交量", keys: ["成交量", "volume"] },
            ]}
          />
        </section>
      )}
      {panel === "fundamentals" && (
        <section className="workbench-panel">
          <div className="panel-heading">
            <h2>利润表与基本面</h2>
          </div>
          <WorkbenchResultMeta result={detail.fundamentals} />
          <WorkbenchDataTable
            result={detail.fundamentals}
            columns={[
              { label: "报告期", keys: ["报告期", "date", "time"] },
              { label: "营业收入", keys: ["营业收入", "revenue"] },
              { label: "净利润", keys: ["净利润", "netprofit", "净利"] },
              { label: "同比", keys: ["同比", "增长"] },
            ]}
          />
        </section>
      )}
      {panel === "reports" && (
        <section className="workbench-panel">
          <div className="panel-heading">
            <h2>公告与研报</h2>
          </div>
          <WorkbenchResultMeta result={detail.reports} />
          <WorkbenchDataTable
            result={detail.reports}
            columns={[
              { label: "日期", keys: ["日期", "date", "publish"] },
              { label: "标题", keys: ["标题", "title", "名称"] },
              { label: "类型", keys: ["类型", "type", "category"] },
              { label: "来源", keys: ["来源", "source", "机构"] },
            ]}
          />
        </section>
      )}
      {panel === "concepts" && (
        <section className="workbench-panel">
          <div className="panel-heading">
            <h2>行业概念</h2>
          </div>
          <WorkbenchResultMeta result={detail.concepts} />
          <div className="concept-list">
            {workbenchRows(detail.concepts?.data)
              .flatMap((row) =>
                Object.values(row).filter((value) => typeof value === "string"),
              )
              .slice(0, 30)
              .map((value, index) => (
                <span className="concept-tag" key={`${value}-${index}`}>
                  {String(value)}
                </span>
              ))}
          </div>
        </section>
      )}
      {panel === "flow" && (
        <section className="workbench-panel">
          <div className="panel-heading">
            <h2>资金流</h2>
          </div>
          <WorkbenchResultMeta result={detail.flow} />
          <WorkbenchDataTable
            result={detail.flow}
            columns={[
              { label: "日期", keys: ["日期", "date", "time"] },
              { label: "主力净流入", keys: ["主力净流入", "main", "主力"] },
              { label: "超大单", keys: ["超大单", "super"] },
              { label: "散户", keys: ["散户", "retail"] },
            ]}
          />
        </section>
      )}
    </>
  );

  return (
    <main
      className={`stock-workbench ${embedded ? "stock-canvas-workbench" : ""}`}
    >
      {!embedded && (
        <header className="workbench-header">
          <div>
            <p className="workbench-kicker">STOCK WORKBENCH</p>
            <h1>股票工作台</h1>
            <p>
              行情、研究与交易观察集中在一个页面，所有数据标注来源和更新时间。
            </p>
          </div>
          <div className="workbench-nav">
            <button type="button" onClick={onOpenNews}>
              <LayoutDashboard size={16} />
              资讯雷达
            </button>
            <button type="button" onClick={onOpenAgent}>
              <Bot size={16} />
              股票助手
            </button>
          </div>
        </header>
      )}
      <nav className="workbench-tabs" aria-label="工作台模块">
        <button
          type="button"
          className={section === "overview" ? "workbench-tab-active" : ""}
          onClick={() => setSection("overview")}
        >
          市场概览
        </button>
        <button
          type="button"
          className={section === "detail" ? "workbench-tab-active" : ""}
          onClick={() => {
            setSection("detail");
            void loadDetail(selectedCode);
          }}
        >
          单股详情
        </button>
        <button
          type="button"
          className={section === "limit" ? "workbench-tab-active" : ""}
          onClick={() => setSection("limit")}
        >
          涨停池
        </button>
        <button
          type="button"
          className={section === "strategy" ? "workbench-tab-active" : ""}
          onClick={() => setSection("strategy")}
        >
          策略决策
        </button>
        <button
          type="button"
          className={section === "research" ? "workbench-tab-active" : ""}
          onClick={() => {
            setSection("research");
            void loadResearch().catch((requestError) => setError(requestError instanceof Error ? requestError.message : "无法读取本地研究档案"));
          }}
        >
          投研档案
        </button>
      </nav>
      <div className="workbench-content">
        {error && (
          <p className="workbench-error" role="alert">
            {error}
          </p>
        )}
        {section === "overview" && renderOverview()}
        {section === "limit" && (
          <section className="workbench-panel">
            <div className="panel-heading">
              <div>
                <span className="workbench-section-label">LIMIT-UP POOL</span>
                <h2>涨停池</h2>
              </div>
            </div>
            <WorkbenchResultMeta result={overview.limitUp} />
            <WorkbenchDataTable
              result={overview.limitUp}
              columns={[
                { label: "代码", keys: ["代码", "code", "symbol"] },
                { label: "名称", keys: ["名称", "name"] },
                { label: "价格", keys: ["价格", "price", "最新"] },
                { label: "涨停原因", keys: ["原因", "reason", "概念"] },
              ]}
            />
          </section>
        )}
        {section === "detail" && renderDetail()}
        {section === "strategy" && renderStrategyConsole()}
        {section === "research" && renderResearchArchive()}
      </div>
    </main>
  );
}

function canvasRequestFromPrompt(prompt: string): CanvasRequest {
  const code = prompt
    .match(/(?:sh|sz|bj)?\d{6}/i)?.[0]
    ?.replace(/^(sh|sz|bj)/i, "");
  if (/(涨停|炸板|跌停|连板|情绪|异常波动)/.test(prompt))
    return { section: "limit" };
  if (/(笔记|决策日志|投研档案|研究报告|策略演进|复盘)/.test(prompt))
    return { section: "research", code };
  if (
    code ||
    /(个股|K线|分时|盘口|资金流|财务|公告|研报|概念|估值)/.test(prompt)
  )
    return { section: "detail", code };
  return { section: "overview" };
}

function DataManagementPanel({
  data,
  loading,
  message,
  modelSettings,
  modelSettingsLoading,
  onClose,
  onExport,
  onClear,
  onBackupChange,
  onSaveModelSettings,
}: {
  data: DataManagement | null;
  loading: boolean;
  message: string;
  modelSettings: ModelProviderSettings[];
  modelSettingsLoading: boolean;
  onClose: () => void;
  onExport: () => void;
  onClear: () => void;
  onBackupChange: (value: DataManagement["automaticBackup"]) => void;
  onSaveModelSettings: (
    provider: ModelProviderSettings["provider"],
    apiKey: string,
    baseUrl: string,
  ) => void;
}) {
  const [selectedProvider, setSelectedProvider] = useState<
    ModelProviderSettings["provider"]
  >("deepseek");
  const [apiKey, setApiKey] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const selectedModel = modelSettings.find(
    (provider) => provider.provider === selectedProvider,
  );

  useEffect(() => {
    if (!selectedModel) return;
    setApiKey("");
    setBaseUrl(selectedModel.baseUrl);
  }, [selectedModel]);

  return (
    <div className="settings-backdrop" role="presentation">
      <section
        className="settings-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="settings-title"
      >
        <header>
          <div>
            <p>SETTINGS</p>
            <h2 id="settings-title">设置</h2>
            <span>模型配置和本机数据管理</span>
          </div>
          <button type="button" onClick={onClose} aria-label="关闭设置">
            <X size={18} />
          </button>
        </header>
        <div className="data-management-content">
          <section className="model-settings-section" aria-labelledby="model-settings-title">
            <div>
              <p className="settings-section-label">MODEL PROVIDER</p>
              <h3 id="model-settings-title">大模型配置</h3>
              <span>Key 仅保存在本机，页面不会再次显示完整内容。</span>
            </div>
            {modelSettingsLoading && modelSettings.length === 0 ? (
              <p className="settings-loading">正在读取模型配置…</p>
            ) : (
              <>
                <label>
                  模型供应商
                  <select
                    value={selectedProvider}
                    onChange={(event) =>
                      setSelectedProvider(
                        event.target.value as ModelProviderSettings["provider"],
                      )
                    }
                  >
                    {modelSettings.map((provider) => (
                      <option key={provider.provider} value={provider.provider}>
                        {provider.label} · {provider.configured ? "已配置" : "未配置"}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  API Key
                  <input
                    type="password"
                    value={apiKey}
                    onChange={(event) => setApiKey(event.target.value)}
                    placeholder={
                      selectedModel?.keyPreview
                        ? `当前已保存：${selectedModel.keyPreview}`
                        : selectedModel?.keyName ?? "请输入 API Key"
                    }
                    autoComplete="off"
                  />
                </label>
                <label>
                  接口地址
                  <input
                    type="url"
                    value={baseUrl}
                    onChange={(event) => setBaseUrl(event.target.value)}
                    placeholder={selectedModel?.defaultBaseUrl}
                  />
                </label>
                <button
                  className="save-model-settings"
                  type="button"
                  onClick={() =>
                    onSaveModelSettings(selectedProvider, apiKey, baseUrl)
                  }
                  disabled={modelSettingsLoading || !baseUrl.trim()}
                >
                  <Save size={16} />
                  保存模型配置
                </button>
              </>
            )}
          </section>
          <div className="settings-divider" />
          <section className="settings-data-section" aria-labelledby="data-management-title">
            <div>
              <p className="settings-section-label">LOCAL DATA</p>
              <h3 id="data-management-title">数据管理</h3>
            </div>
          {loading && !data ? (
            <p className="settings-loading">正在读取本地数据状态…</p>
          ) : (
            <>
              <section className="storage-summary">
                <HardDrive size={22} />
                <div>
                  <strong>{formatBytes(data?.totalBytes ?? 0)}</strong>
                  <span>
                    {data?.fileCount ?? 0} 个本地文件 · {data?.backupCount ?? 0}{" "}
                    个备份
                  </span>
                </div>
              </section>
              <dl className="storage-location">
                <div>
                  <dt>数据存储位置</dt>
                  <dd>{data?.storagePath ?? "暂不可用"}</dd>
                </div>
                <div>
                  <dt>最近自动备份</dt>
                  <dd>
                    {data?.lastBackupAt
                      ? formatDate(data.lastBackupAt)
                      : "尚未创建"}
                  </dd>
                </div>
              </dl>
              <section className="data-actions">
                <button type="button" onClick={onExport} disabled={loading}>
                  <Download size={16} />
                  导出所有数据（ZIP）
                </button>
                <button
                  type="button"
                  className="danger-action"
                  onClick={onClear}
                  disabled={loading}
                >
                  <Trash2 size={16} />
                  清空本地历史数据
                </button>
              </section>
              <label className="backup-setting">
                自动备份
                <select
                  value={data?.automaticBackup ?? "off"}
                  onChange={(event) =>
                    onBackupChange(
                      event.target.value as DataManagement["automaticBackup"],
                    )
                  }
                  disabled={loading}
                >
                  <option value="off">关闭</option>
                  <option value="daily">每日</option>
                  <option value="weekly">每周</option>
                </select>
              </label>
              <p className="settings-note">
                导出文件包含本地会话、偏好、自选、策略、回测和资讯缓存。清空操作不会删除应用程序或模型密钥。
              </p>
            </>
          )}
          </section>
          {message && (
            <p className="settings-message" role="status">
              {message}
            </p>
          )}
        </div>
      </section>
    </div>
  );
}

function PrivacyNotice({ onClose }: { onClose: () => void }) {
  return (
    <div className="settings-backdrop" role="presentation">
      <section
        className="privacy-notice"
        role="dialog"
        aria-modal="true"
        aria-labelledby="privacy-notice-title"
      >
        <ShieldCheck size={27} />
        <h2 id="privacy-notice-title">你的投研数据保存在本地</h2>
        <p>
          对话历史、自选股和策略配置存储在这台电脑。模型 API
          密钥仅用于调用模型，不会上传你的投资数据。
        </p>
        <button type="button" onClick={onClose}>
          我知道了
        </button>
      </section>
    </div>
  );
}

function AgentWorkspace({ onOpenNews }: { onOpenNews: () => void }) {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<
    string | null
  >(null);
  const [conversationQuery, setConversationQuery] = useState("");
  const [recentConversationsOpen, setRecentConversationsOpen] = useState(true);
  const [composer, setComposer] = useState("");
  const [model, setModel] = useState("deepseek");
  const [providers, setProviders] = useState<ProviderStatus[]>([]);
  const [memoryOpen, setMemoryOpen] = useState(false);
  const [memories, setMemories] = useState<MemoryItem[]>([]);
  const [editingMemoryId, setEditingMemoryId] = useState<string | null>(null);
  const [editingValue, setEditingValue] = useState("");
  const [newMemoryLabel, setNewMemoryLabel] = useState("");
  const [newMemoryValue, setNewMemoryValue] = useState("");
  const [agentError, setAgentError] = useState("");
  const [messages, setMessages] = useState<ConversationMessage[]>([]);
  const [pendingMessage, setPendingMessage] = useState<string | null>(null);
  const [streamingContent, setStreamingContent] = useState("");
  const [sending, setSending] = useState(false);
  const [canvasRequest, setCanvasRequest] = useState<CanvasRequest>({
    section: "overview",
  });
  const [canvasOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [listening, setListening] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [dataManagement, setDataManagement] = useState<DataManagement | null>(
    null,
  );
  const [dataManagementLoading, setDataManagementLoading] = useState(false);
  const [dataManagementMessage, setDataManagementMessage] = useState("");
  const [modelSettings, setModelSettings] = useState<ModelProviderSettings[]>([]);
  const [modelSettingsLoading, setModelSettingsLoading] = useState(false);
  const [privacyNoticeOpen, setPrivacyNoticeOpen] = useState(
    () =>
      window.localStorage.getItem("ai-research-privacy-notice-seen") !== "1",
  );

  const activeConversation = conversations.find(
    (conversation) => conversation.id === activeConversationId,
  );
  const visibleConversations = conversations.filter(
    (conversation) =>
      conversation.title.includes(conversationQuery.trim()) ||
      conversation.preview.includes(conversationQuery.trim()),
  );
  const activeProvider = providers.find(
    (provider) => provider.provider === model,
  );
  const providerReady = activeProvider?.configured === true;

  const loadDataManagement = async () => {
    setDataManagementLoading(true);
    try {
      const response = await fetch(`${API_BASE}/agent/data-management`);
      if (!response.ok) throw new Error("无法读取本地数据状态");
      setDataManagement((await response.json()) as DataManagement);
    } catch (requestError) {
      setDataManagementMessage(
        requestError instanceof Error
          ? requestError.message
          : "无法读取本地数据状态",
      );
    } finally {
      setDataManagementLoading(false);
    }
  };

  const loadModelSettings = async () => {
    setModelSettingsLoading(true);
    try {
      const response = await fetch(`${API_BASE}/agent/settings/models`);
      if (!response.ok) throw new Error("无法读取模型配置");
      setModelSettings((await response.json()) as ModelProviderSettings[]);
    } catch (requestError) {
      setDataManagementMessage(
        requestError instanceof Error ? requestError.message : "无法读取模型配置",
      );
    } finally {
      setModelSettingsLoading(false);
    }
  };

  useEffect(() => {
    let cancelled = false;
    const loadWorkspace = async () => {
      try {
        const [
          providerResponse,
          conversationResponse,
          preferenceResponse,
          dataManagementResponse,
        ] = await Promise.all([
          fetch(`${API_BASE}/providers`),
          fetch(`${API_BASE}/agent/conversations`),
          fetch(`${API_BASE}/agent/preferences`),
          fetch(`${API_BASE}/agent/data-management`),
        ]);
        if (
          !providerResponse.ok ||
          !conversationResponse.ok ||
          !preferenceResponse.ok ||
          !dataManagementResponse.ok
        )
          throw new Error("本机数据服务不可用");
        const [
          provider,
          storedConversations,
          storedPreferences,
          storedDataManagement,
        ] = await Promise.all([
          providerResponse.json() as Promise<ProviderStatus[]>,
          conversationResponse.json() as Promise<Conversation[]>,
          preferenceResponse.json() as Promise<MemoryItem[]>,
          dataManagementResponse.json() as Promise<DataManagement>,
        ]);
        if (cancelled) return;
        setProviders(provider);
        setConversations(storedConversations);
        setMemories(storedPreferences);
        setDataManagement(storedDataManagement);
        setActiveConversationId(storedConversations[0]?.id ?? null);
      } catch (requestError) {
        if (!cancelled) {
          setProviders([]);
          setAgentError(
            requestError instanceof Error
              ? requestError.message
              : "无法连接本机数据服务",
          );
        }
      }
    };
    void loadWorkspace();
    return () => {
      cancelled = true;
    };
  }, []);

  const openSettings = () => {
    setDataManagementMessage("");
    setSettingsOpen(true);
    void Promise.all([loadDataManagement(), loadModelSettings()]);
  };

  const saveModelSettings = async (
    provider: ModelProviderSettings["provider"],
    apiKey: string,
    baseUrl: string,
  ) => {
    setDataManagementMessage("");
    setModelSettingsLoading(true);
    try {
      const response = await fetch(`${API_BASE}/agent/settings/models/${provider}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...(apiKey.trim() ? { api_key: apiKey.trim() } : {}),
          base_url: baseUrl.trim(),
        }),
      });
      if (!response.ok) {
        const detail = (await response.json().catch(() => ({}))) as { detail?: string };
        throw new Error(detail.detail || "无法保存模型配置");
      }
      const saved = (await response.json()) as ModelProviderSettings;
      setModelSettings((current) =>
        current.map((item) => (item.provider === saved.provider ? saved : item)),
      );
      setProviders((current) =>
        current.map((item) =>
          item.provider === saved.provider
            ? { ...item, configured: saved.configured, keyName: saved.keyName }
            : item,
        ),
      );
      setDataManagementMessage("模型配置已保存在本机。");
    } catch (requestError) {
      setDataManagementMessage(
        requestError instanceof Error ? requestError.message : "无法保存模型配置",
      );
    } finally {
      setModelSettingsLoading(false);
    }
  };

  const exportLocalData = async () => {
    setDataManagementMessage("");
    setDataManagementLoading(true);
    try {
      const response = await fetch(`${API_BASE}/agent/data-management/export`);
      if (!response.ok) throw new Error("导出本地数据失败");
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "ai-research-local-data.zip";
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      setDataManagementMessage("本地数据已导出为 ZIP 文件。");
    } catch (requestError) {
      setDataManagementMessage(
        requestError instanceof Error
          ? requestError.message
          : "导出本地数据失败",
      );
    } finally {
      setDataManagementLoading(false);
    }
  };

  const clearLocalData = async () => {
    if (
      !window.confirm(
        "这会清空本地会话、偏好、自选、策略、回测和资讯缓存。该操作无法撤销，是否继续？",
      )
    )
      return;
    setDataManagementMessage("");
    setDataManagementLoading(true);
    try {
      const response = await fetch(`${API_BASE}/agent/data-management/clear`, {
        method: "POST",
      });
      if (!response.ok) throw new Error("清空本地历史数据失败");
      const result = (await response.json()) as DataManagement;
      setDataManagement(result);
      setConversations([]);
      setMessages([]);
      setMemories([]);
      setActiveConversationId(null);
      setDataManagementMessage("本地历史数据已清空。");
    } catch (requestError) {
      setDataManagementMessage(
        requestError instanceof Error
          ? requestError.message
          : "清空本地历史数据失败",
      );
    } finally {
      setDataManagementLoading(false);
    }
  };

  const updateAutomaticBackup = async (
    automaticBackup: DataManagement["automaticBackup"],
  ) => {
    setDataManagementMessage("");
    setDataManagementLoading(true);
    try {
      const response = await fetch(`${API_BASE}/agent/data-management`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ automatic_backup: automaticBackup }),
      });
      if (!response.ok) throw new Error("无法保存自动备份设置");
      setDataManagement((await response.json()) as DataManagement);
      setDataManagementMessage(
        automaticBackup === "off"
          ? "已关闭自动备份。"
          : `已设置${automaticBackup === "daily" ? "每日" : "每周"}自动备份。`,
      );
    } catch (requestError) {
      setDataManagementMessage(
        requestError instanceof Error
          ? requestError.message
          : "无法保存自动备份设置",
      );
    } finally {
      setDataManagementLoading(false);
    }
  };

  const closePrivacyNotice = () => {
    window.localStorage.setItem("ai-research-privacy-notice-seen", "1");
    setPrivacyNoticeOpen(false);
  };

  useEffect(() => {
    if (!activeConversationId) {
      // Clear the previous conversation immediately when no conversation is selected.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setMessages([]);
      return;
    }
    let cancelled = false;
    const loadConversation = async () => {
      try {
        const messageResponse = await fetch(
          `${API_BASE}/agent/conversations/${activeConversationId}/messages`,
        );
        if (!messageResponse.ok) throw new Error("无法读取会话记录");
        const storedMessages =
          (await messageResponse.json()) as ConversationMessage[];
        if (!cancelled) {
          setMessages(storedMessages);
        }
      } catch (requestError) {
        if (!cancelled)
          setAgentError(
            requestError instanceof Error
              ? requestError.message
              : "无法读取会话记录",
          );
      }
    };
    void loadConversation();
    return () => {
      cancelled = true;
    };
  }, [activeConversationId]);

  const createConversation = async (): Promise<Conversation | null> => {
    try {
      setAgentError("");
      const response = await fetch(`${API_BASE}/agent/conversations`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: "未命名研究对话" }),
      });
      if (!response.ok) throw new Error("无法新建会话");
      const conversation = (await response.json()) as Conversation;
      setConversations((current) => [conversation, ...current]);
      setActiveConversationId(conversation.id);
      setMessages([]);
      return conversation;
    } catch (requestError) {
      setAgentError(
        requestError instanceof Error ? requestError.message : "无法新建会话",
      );
      return null;
    }
  };

  const deleteConversation = async (conversation: Conversation) => {
    if (!window.confirm(`确定删除会话“${conversation.title}”吗？`)) return;
    try {
      setAgentError("");
      const response = await fetch(
        `${API_BASE}/agent/conversations/${conversation.id}`,
        { method: "DELETE" },
      );
      if (!response.ok) throw new Error("无法删除会话");
      const remaining = conversations.filter(
        (item) => item.id !== conversation.id,
      );
      setConversations(remaining);
      if (activeConversationId === conversation.id) {
        setActiveConversationId(remaining[0]?.id ?? null);
        setMessages([]);
      }
    } catch (requestError) {
      setAgentError(
        requestError instanceof Error ? requestError.message : "无法删除会话",
      );
    }
  };

  const handleComposerKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (
      event.key !== "Enter" ||
      event.shiftKey ||
      event.nativeEvent.isComposing
    )
      return;
    event.preventDefault();
    if (!sending && composer.trim() && providerReady) {
      event.currentTarget.form?.requestSubmit();
    }
  };

  const startVoiceInput = () => {
    const browser = window as typeof window & {
      SpeechRecognition?: SpeechRecognitionConstructor;
      webkitSpeechRecognition?: SpeechRecognitionConstructor;
    };
    const Recognition =
      browser.SpeechRecognition || browser.webkitSpeechRecognition;
    if (!Recognition) {
      setAgentError(
        "当前桌面环境不支持语音识别，请使用 Chromium 浏览器或直接输入文字",
      );
      return;
    }
    const recognition = new Recognition();
    recognition.lang = "zh-CN";
    recognition.interimResults = false;
    recognition.continuous = false;
    recognition.onresult = (event) =>
      setComposer(
        (current) =>
          `${current}${current ? " " : ""}${event.results[0][0].transcript}`,
      );
    recognition.onerror = () =>
      setAgentError("语音识别未完成，请检查麦克风权限后重试");
    recognition.onend = () => setListening(false);
    setListening(true);
    recognition.start();
  };

  const sendMessage = async (event: FormEvent) => {
    event.preventDefault();
    const content = composer.trim();
    if (!content || sending || !providerReady) return;
    setCanvasRequest(canvasRequestFromPrompt(content));
    let conversationId = activeConversationId;
    if (!conversationId) {
      const conversation = await createConversation();
      if (!conversation) return;
      conversationId = conversation.id;
    }
    try {
      setAgentError("");
      setComposer("");
      setPendingMessage(content);
      setStreamingContent("");
      setSending(true);
      const response = await fetch(
        `${API_BASE}/agent/conversations/${conversationId}/chat/stream`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ content, model }),
        },
      );
      if (!response.ok) {
        const errorBody = (await response.json().catch(() => null)) as {
          detail?: string;
        } | null;
        throw new Error(errorBody?.detail || "无法获取助手回答");
      }
      if (!response.body) throw new Error("浏览器不支持流式回答");
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      const completion: {
        value: Extract<StreamEvent, { type: "done" }> | null;
      } = { value: null };
      const consumeEvent = (packet: string) => {
        const dataLine = packet
          .split("\n")
          .find((line) => line.startsWith("data: "));
        if (!dataLine) return;
        const streamEvent = JSON.parse(dataLine.slice(6)) as StreamEvent;
        if (streamEvent.type === "delta") {
          setStreamingContent((current) => `${current}${streamEvent.content}`);
          return;
        }
        if (streamEvent.type === "error") throw new Error(streamEvent.message);
        completion.value = streamEvent;
      };
      while (true) {
        const { done, value } = await reader.read();
        buffer += decoder.decode(value, { stream: !done });
        let boundary = buffer.indexOf("\n\n");
        while (boundary >= 0) {
          consumeEvent(buffer.slice(0, boundary));
          buffer = buffer.slice(boundary + 2);
          boundary = buffer.indexOf("\n\n");
        }
        if (done) break;
      }
      if (buffer.trim()) consumeEvent(buffer);
      const completedResult = completion.value;
      if (!completedResult) throw new Error("流式回答意外中断，请稍后重试");
      setPendingMessage(null);

      // 将 usedMemories 附加到 assistantMessage
      const assistantMessageWithMemories = {
        ...completedResult.assistantMessage,
        used_memories: completedResult.usedMemories || []
      };

      setMessages((current) => [
        ...current,
        completedResult.userMessage,
        assistantMessageWithMemories,
      ]);
      setConversations((current) => {
        const updatedConversation = current.find(
          (conversation) => conversation.id === conversationId,
        );
        if (!updatedConversation) return current;
        const nextConversation = {
          ...updatedConversation,
          preview: completedResult.assistantMessage.content.slice(0, 120),
          updated_at: completedResult.assistantMessage.created_at,
        };
        return [
          nextConversation,
          ...current.filter(
            (conversation) => conversation.id !== conversationId,
          ),
        ];
      });
    } catch (requestError) {
      setComposer(content);
      setAgentError(
        requestError instanceof Error
          ? requestError.message
          : "无法获取助手回答",
      );
    } finally {
      setPendingMessage(null);
      setStreamingContent("");
      setSending(false);
    }
  };

  const beginMemoryEdit = (memory: MemoryItem) => {
    setEditingMemoryId(memory.id);
    setEditingValue(memory.value);
  };

  const saveMemoryEdit = async () => {
    if (!editingMemoryId || !editingValue.trim()) return;
    const memory = memories.find((item) => item.id === editingMemoryId);
    if (!memory) return;
    try {
      setAgentError("");
      const response = await fetch(
        `${API_BASE}/agent/preferences/${editingMemoryId}`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            label: memory.label,
            value: editingValue.trim(),
          }),
        },
      );
      if (!response.ok) throw new Error("无法保存偏好");
      const updatedMemory = (await response.json()) as MemoryItem;
      setMemories((current) =>
        current.map((item) =>
          item.id === updatedMemory.id ? updatedMemory : item,
        ),
      );
      setEditingMemoryId(null);
    } catch (requestError) {
      setAgentError(
        requestError instanceof Error ? requestError.message : "无法保存偏好",
      );
    }
  };

  const createMemory = async (event: FormEvent) => {
    event.preventDefault();
    if (!newMemoryLabel.trim() || !newMemoryValue.trim()) return;
    try {
      setAgentError("");
      const response = await fetch(`${API_BASE}/agent/preferences`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          label: newMemoryLabel.trim(),
          value: newMemoryValue.trim(),
        }),
      });
      if (!response.ok) throw new Error("无法新增偏好");
      const memory = (await response.json()) as MemoryItem;
      setMemories((current) => [memory, ...current]);
      setNewMemoryLabel("");
      setNewMemoryValue("");
    } catch (requestError) {
      setAgentError(
        requestError instanceof Error ? requestError.message : "无法新增偏好",
      );
    }
  };

  const deleteMemory = async (memoryId: string) => {
    try {
      setAgentError("");
      const response = await fetch(
        `${API_BASE}/agent/preferences/${memoryId}`,
        { method: "DELETE" },
      );
      if (!response.ok) throw new Error("无法删除偏好");
      setMemories((current) =>
        current.filter((memory) => memory.id !== memoryId),
      );
    } catch (requestError) {
      setAgentError(
        requestError instanceof Error ? requestError.message : "无法删除偏好",
      );
    }
  };

  return (
    <main
      className={`agent-app app-shell-9 ${sidebarCollapsed ? "sidebar-collapsed" : ""} ${canvasOpen ? "" : "agent-app-canvas-hidden"}`}
    >
      <aside className="agent-sidebar" aria-label="股票助手会话导航">
        <div className="agent-brand">
          <div className="agent-brand-icon">
            <Bot size={19} />
          </div>
          <div>
            <strong>研析</strong>
            <span>Research copilot</span>
          </div>
          <button
            className="brand-collapse-button"
            type="button"
            onClick={() => setSidebarCollapsed((current) => !current)}
            title={sidebarCollapsed ? "展开侧边栏" : "收起侧边栏"}
            aria-label={sidebarCollapsed ? "展开侧边栏" : "收起侧边栏"}
          >
            {sidebarCollapsed ? <PanelRightOpen size={16} /> : <PanelRightClose size={16} />}
          </button>
        </div>
        <nav className="agent-nav" aria-label="应用视图">
          <button className="agent-nav-item agent-home-link" type="button" onClick={onOpenNews}>
            <LayoutDashboard size={17} />
            返回首页
          </button>
        </nav>
        <div className="agent-primary-actions">
          <button
            className="new-conversation-button"
            type="button"
            onClick={createConversation}
          >
            <Plus size={17} />
            新建对话
          </button>
          <button
            className="sidebar-icon-button"
            type="button"
            title="会话管理"
            aria-label="会话管理"
          >
            <MoreHorizontal size={18} />
          </button>
        </div>
        <label className="conversation-search">
          <Search size={16} />
          <span className="sr-only">搜索会话</span>
          <input
            value={conversationQuery}
            onChange={(event) => setConversationQuery(event.target.value)}
            placeholder="搜索会话"
          />
        </label>
        <button
          className="conversation-section-heading"
          type="button"
          onClick={() => setRecentConversationsOpen((open) => !open)}
          aria-expanded={recentConversationsOpen}
          aria-controls="recent-conversation-list"
        >
          <span>最近</span>
          <span>{conversations.length}</span>
          <ChevronDown
            className={recentConversationsOpen ? "section-chevron-open" : ""}
            size={14}
            aria-hidden="true"
          />
        </button>
        {recentConversationsOpen && (
          <div className="conversation-list" id="recent-conversation-list">
            {visibleConversations.map((conversation) => (
              <div className="conversation-item-row" key={conversation.id}>
                <button
                  className={`conversation-item ${activeConversationId === conversation.id ? "conversation-item-active" : ""}`}
                  type="button"
                  onClick={() => setActiveConversationId(conversation.id)}
                >
                  <strong>{conversation.title}</strong>
                  <span>{conversation.preview}</span>
                  <time>{conversationTime(conversation.updated_at)}</time>
                </button>
                <button
                  className="conversation-delete-button"
                  type="button"
                  title="删除会话"
                  aria-label={`删除会话 ${conversation.title}`}
                  onClick={() => void deleteConversation(conversation)}
                >
                  <Trash2 size={14} />
                </button>
              </div>
            ))}
            {conversations.length > 0 && visibleConversations.length === 0 && (
              <p className="conversation-empty">没有匹配的会话</p>
            )}
          </div>
        )}
        <div className="agent-sidebar-footer">
          <button
            className="preference-entry"
            type="button"
            onClick={() => setMemoryOpen(true)}
          >
            <Brain size={17} />
            <span>
              <strong>偏好</strong>
              <small>长期记忆</small>
            </span>
            <ChevronDown size={15} />
          </button>
          <button
            className="settings-button"
            type="button"
            onClick={openSettings}
            title="设置"
            aria-label="设置"
          >
            <Settings2 size={18} />
          </button>
        </div>
      </aside>

      <section className="agent-main" aria-label="股票助手对话">
        <header className="agent-header">
          <div>
            <div className="agent-title-row">
              <span className="header-bot-mark"><Bot size={16} /></span>
              <h1>{activeConversation?.title ?? "新建对话"}</h1>
              <span className="saved-indicator">
                <Check size={13} />
                本机已保存
              </span>
            </div>
            <p>投研助手 · 结论请结合数据来源与风险说明判断</p>
          </div>
          <div className="agent-header-actions">
            <button
              className="preference-header-button"
              type="button"
              onClick={() => setMemoryOpen(true)}
            >
              <Brain size={17} />
              偏好
            </button>
          </div>
        </header>
        <LocalPrivacyBanner />
        <div
          className="conversation-canvas"
          role="log"
          aria-label="聊天记录"
          aria-live="off"
          tabIndex={0}
        >
          <div className="date-divider">
            <span>今天</span>
          </div>
          {messages.map((message) => {
            return (
              <article
                className={`chat-message chat-message-${message.role}`}
                key={message.id}
              >
                <div
                  className={`message-avatar ${message.role === "user" ? "user-avatar" : "assistant-avatar"}`}
                >
                  {message.role === "user" ? "你" : <Bot size={17} />}
                </div>
                <div className="message-body">
                  {message.role === "assistant" && (
                    <div className="message-author">
                      <strong>股票助手</strong>
                      <span>{activeProvider?.label ?? "模型"}</span>
                    </div>
                  )}
                  {message.role === "assistant" ? (
                    renderAssistantContent(message.content)
                  ) : (
                    <p>{message.content}</p>
                  )}

                  {/* 显示使用的记忆 */}
                  {message.role === "assistant" && message.used_memories && message.used_memories.length > 0 && (
                    <section className="used-memories-section">
                      <div className="used-memories-header">
                        <Brain size={14} />
                        <span>使用了 {message.used_memories.length} 条记忆</span>
                      </div>
                      <div className="used-memories-list">
                        {message.used_memories.map((memory, idx) => {
                          const memoryTypeLabels = {
                            user: "用户画像",
                            feedback: "反馈",
                            project: "项目",
                            reference: "资源"
                          };
                          const memoryTypeColors = {
                            user: "#3b82f6",
                            feedback: "#f59e0b",
                            project: "#10b981",
                            reference: "#8b5cf6"
                          };
                          return (
                            <div key={idx} className="used-memory-item">
                              <span
                                className="memory-type-badge"
                                style={{ backgroundColor: memoryTypeColors[memory.type] }}
                              >
                                {memoryTypeLabels[memory.type]}
                              </span>
                              <span className="memory-description">{memory.description}</span>
                            </div>
                          );
                        })}
                      </div>
                    </section>
                  )}

                </div>
              </article>
            );
          })}
          {pendingMessage &&
            !messages.some(
              (message) =>
                message.role === "user" && message.content === pendingMessage,
            ) && (
              <article className="chat-message chat-message-user">
                <div className="message-avatar user-avatar">你</div>
                <div className="message-body">
                  <p>{pendingMessage}</p>
                </div>
              </article>
            )}
          {sending && (
            <article
              className="chat-message chat-message-assistant"
              aria-live="polite"
            >
              <div className="message-avatar assistant-avatar">
                <Bot size={17} />
              </div>
              <div className="message-body">
                <div className="message-author">
                  <strong>股票助手</strong>
                  <span>{activeProvider?.label ?? "模型"} · 输出中</span>
                </div>
                {streamingContent ? (
                  renderAssistantContent(streamingContent)
                ) : (
                  <p className="assistant-thinking">
                    正在连接 {activeProvider?.label ?? "模型"}…
                  </p>
                )}
                <span className="streaming-caret" aria-hidden="true" />
              </div>
            </article>
          )}
          {!activeConversationId && !pendingMessage && (
            <div className="agent-empty-chat app-shell-welcome">
              <div className="welcome-avatar"><Bot size={26} /></div>
              <p className="welcome-author">研析助手 <span>在线，随时为你整理研究线索</span></p>
              <h2>今天想研究什么？</h2>
              <p>从一个问题开始，我会把公开信息、数据线索和风险点整理成可继续追问的结论。</p>
            </div>
          )}
          {activeConversationId &&
            messages.length === 0 &&
            !pendingMessage &&
            !sending && (
              <div className="agent-empty-chat">
                <Bot size={20} />
                <strong>这个会话还没有消息</strong>
                <p>输入问题即可开始。</p>
              </div>
            )}
        </div>
        <footer className="composer-wrap">
          <form className="composer" onSubmit={sendMessage}>
            <label className="sr-only" htmlFor="agent-message">
              向股票助手提问
            </label>
            <textarea
              id="agent-message"
              value={composer}
              onChange={(event) => setComposer(event.target.value)}
              onKeyDown={handleComposerKeyDown}
              placeholder="向股票助手提问，例如：整理某行业最近的公告与风险点"
              rows={3}
              disabled={sending}
            />
            <div className="composer-toolbar">
              <div className="composer-options">
                <label className="model-select">
                  <span className="sr-only">模型选择</span>
                  <select
                    value={model}
                    onChange={(event) => setModel(event.target.value)}
                    disabled={sending}
                  >
                    {providers.map((provider) => (
                      <option value={provider.provider} key={provider.provider}>
                        {provider.label} ·{" "}
                        {provider.configured ? "已配置" : "未配置"}
                      </option>
                    ))}
                  </select>
                </label>
                <button
                  className="voice-input-button"
                  type="button"
                  onClick={startVoiceInput}
                  disabled={sending || listening}
                  title="语音输入"
                >
                  <Mic size={15} />
                  {listening ? "聆听中" : "语音输入"}
                </button>
                <span className="composer-note">
                  <Sparkles size={14} />
                  {providerReady
                    ? `${activeProvider?.label} 已接入，密钥仅由后端读取`
                    : activeProvider
                      ? `请配置 ${activeProvider.keyName}`
                      : "正在检查本机模型配置"}
                </span>
              </div>
              <button
                className="send-button"
                type="submit"
                disabled={!composer.trim() || sending || !providerReady}
                title={
                  providerReady
                    ? "发送问题"
                    : `${activeProvider?.label ?? "模型"} 尚未配置`
                }
              >
                <Send size={17} />
                {sending ? "思考中" : "发送"}
              </button>
            </div>
          </form>
          {agentError && (
            <p className="chat-error" role="alert">
              {agentError}
            </p>
          )}
          <p className="composer-disclaimer">
            助手用于信息整理与研究辅助，不提供涨跌预测、买卖指令或仓位建议。
          </p>
        </footer>
      </section>

      {canvasOpen && (
        <aside className="agent-canvas" aria-label="股票画布">
          <header className="agent-canvas-header">
            <div>
              <p>AI CANVAS</p>
              <h2>股票画布</h2>
            </div>
            <span>跟随当前提问</span>
          </header>
          <div className="agent-canvas-body">
            <StockWorkbench
              embedded
              request={canvasRequest}
              onOpenAgent={() => undefined}
              onOpenNews={onOpenNews}
            />
          </div>
        </aside>
      )}

      {memoryOpen && (
        <aside className="memory-panel" aria-label="偏好与长期记忆">
          <header>
            <div>
              <p>LONG-TERM MEMORY</p>
              <h2>偏好</h2>
              <span>已保存到本机</span>
            </div>
            <button
              type="button"
              onClick={() => setMemoryOpen(false)}
              aria-label="关闭偏好面板"
            >
              <X size={18} />
            </button>
          </header>
          <div className="memory-intro">
            <Brain size={18} />
            <p>
              长期记忆会和会话历史分开保存，用于保留稳定的关注方向和回答习惯。
            </p>
          </div>
          <form className="memory-create" onSubmit={createMemory}>
            <label htmlFor="memory-label">新增偏好</label>
            <input
              id="memory-label"
              value={newMemoryLabel}
              onChange={(event) => setNewMemoryLabel(event.target.value)}
              placeholder="例如：关注标的"
            />
            <label className="sr-only" htmlFor="memory-value">
              偏好内容
            </label>
            <input
              id="memory-value"
              value={newMemoryValue}
              onChange={(event) => setNewMemoryValue(event.target.value)}
              placeholder="例如：中际旭创、寒武纪"
            />
            <button
              type="submit"
              disabled={!newMemoryLabel.trim() || !newMemoryValue.trim()}
            >
              <Plus size={15} />
              新增
            </button>
          </form>
          {agentError && (
            <p className="memory-error" role="alert">
              {agentError}
            </p>
          )}
          <div className="memory-list">
            {memories.map((memory) => (
              <section className="memory-item" key={memory.id}>
                <strong>{memory.label}</strong>
                {editingMemoryId === memory.id ? (
                  <div className="memory-editor">
                    <label className="sr-only" htmlFor={`memory-${memory.id}`}>
                      {memory.label}
                    </label>
                    <input
                      id={`memory-${memory.id}`}
                      value={editingValue}
                      onChange={(event) => setEditingValue(event.target.value)}
                    />
                    <button
                      type="button"
                      onClick={saveMemoryEdit}
                      aria-label={`保存${memory.label}`}
                      title="保存"
                    >
                      <Check size={16} />
                    </button>
                    <button
                      type="button"
                      onClick={() => setEditingMemoryId(null)}
                      aria-label={`取消编辑${memory.label}`}
                      title="取消"
                    >
                      <X size={16} />
                    </button>
                  </div>
                ) : (
                  <>
                    <p>{memory.value}</p>
                    <div className="memory-actions">
                      <button
                        type="button"
                        onClick={() => beginMemoryEdit(memory)}
                      >
                        <Pencil size={14} />
                        修改
                      </button>
                      <button
                        className="memory-delete"
                        type="button"
                        onClick={() => void deleteMemory(memory.id)}
                      >
                        <Trash2 size={14} />
                        删除
                      </button>
                    </div>
                  </>
                )}
              </section>
            ))}
            {memories.length === 0 && (
              <p className="conversation-empty">暂无长期偏好</p>
            )}
          </div>
          <footer>
            <span>偏好保存到本机；提问时会作为回答偏好提供给当前模型。</span>
          </footer>
        </aside>
      )}
      {settingsOpen && (
        <DataManagementPanel
          data={dataManagement}
          loading={dataManagementLoading}
          message={dataManagementMessage}
          modelSettings={modelSettings}
          modelSettingsLoading={modelSettingsLoading}
          onClose={() => setSettingsOpen(false)}
          onExport={() => void exportLocalData()}
          onClear={() => void clearLocalData()}
          onBackupChange={(value) => void updateAutomaticBackup(value)}
          onSaveModelSettings={(provider, apiKey, baseUrl) =>
            void saveModelSettings(provider, apiKey, baseUrl)
          }
        />
      )}
      {privacyNoticeOpen && <PrivacyNotice onClose={closePrivacyNotice} />}
    </main>
  );
}

function LegacyNewsWorkspace() {
  const [taxonomy, setTaxonomy] = useState<Taxonomy | null>(null);
  const [news, setNews] = useState<NewsItem[]>([]);
  const [sources, setSources] = useState<SourceHealth[]>([]);
  const [activeSector, setActiveSector] = useState("全部行业");
  const [activeIndustry, setActiveIndustry] = useState("");
  const [activeTopic, setActiveTopic] = useState("");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [offset, setOffset] = useState(0);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState("");
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);
  const [showAgent, setShowAgent] = useState(false);
  const [subscriptions, setSubscriptions] = useState<NewsSubscription[]>([]);
  const [subscriptionInput, setSubscriptionInput] = useState("");

  const industries = useMemo(() => {
    if (!taxonomy) return [];
    if (activeSector === "全部行业") return taxonomy.industries;
    return (
      taxonomy.primarySectors.find((sector) => sector.name === activeSector)
        ?.industries ?? []
    );
  }, [activeSector, taxonomy]);

  const loadNews = async (
    shouldRefresh = false,
    requestOffset = 0,
    append = false,
  ) => {
    setError("");
    if (shouldRefresh) setRefreshing(true);
    if (append) setLoadingMore(true);
    try {
      if (shouldRefresh) await fetch(`${API_BASE}/refresh`, { method: "POST" });
      const query = new URLSearchParams();
      if (activeSector !== "全部行业")
        query.set("primary_sector", activeSector);
      if (activeIndustry) query.set("industry", activeIndustry);
      if (activeTopic) query.set("topic", activeTopic);
      query.set("limit", "50");
      query.set("offset", String(requestOffset));
      const [newsResponse, sourceResponse] = await Promise.all([
        fetch(`${API_BASE}/news?${query.toString()}`),
        fetch(`${API_BASE}/sources`),
      ]);
      if (!newsResponse.ok || !sourceResponse.ok)
        throw new Error("新闻服务返回异常");
      const newsData = (await newsResponse.json()) as NewsResponse;
      setNews((current) =>
        requestOffset === 0 ? newsData.items : [...current, ...newsData.items],
      );
      setOffset(requestOffset + newsData.items.length);
      setTotal(newsData.total);
      setUpdatedAt(newsData.updatedAt);
      setSources(await sourceResponse.json());
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "无法连接新闻服务",
      );
    } finally {
      setLoading(false);
      setRefreshing(false);
      setLoadingMore(false);
    }
  };

  useEffect(() => {
    const initialize = async () => {
      try {
        const taxonomyResponse = await fetch(`${API_BASE}/taxonomy`);
        if (!taxonomyResponse.ok) throw new Error("分类服务不可用");
        setTaxonomy(await taxonomyResponse.json());
      } catch (requestError) {
        setError(
          requestError instanceof Error ? requestError.message : "无法连接后端",
        );
      }
    };
    void initialize();
  }, []);

  const loadSubscriptions = async () => {
    const response = await fetch(`${API_BASE}/news/subscriptions`);
    if (!response.ok) throw new Error("无法读取关键词订阅");
    setSubscriptions((await response.json()) as NewsSubscription[]);
  };

  useEffect(() => {
    void loadSubscriptions().catch(() => undefined);
  }, []);

  const addSubscription = async (event: FormEvent) => {
    event.preventDefault();
    if (!subscriptionInput.trim()) return;
    try {
      const response = await fetch(`${API_BASE}/news/subscriptions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ keyword: subscriptionInput.trim() }),
      });
      if (!response.ok)
        throw new Error(
          (
            (await response.json().catch(() => ({ detail: "订阅失败" }))) as {
              detail?: string;
            }
          ).detail || "订阅失败",
        );
      const subscription = (await response.json()) as NewsSubscription;
      setSubscriptions((current) => [subscription, ...current]);
      setSubscriptionInput("");
    } catch (requestError) {
      setError(
        requestError instanceof Error ? requestError.message : "订阅失败",
      );
    }
  };

  const deleteSubscription = async (subscription: NewsSubscription) => {
    const response = await fetch(
      `${API_BASE}/news/subscriptions/${subscription.id}`,
      { method: "DELETE" },
    );
    if (response.ok)
      setSubscriptions((current) =>
        current.filter((item) => item.id !== subscription.id),
      );
  };

  const setNewsRead = async (item: NewsItem, isRead: boolean) => {
    const response = await fetch(`${API_BASE}/news/${item.id}/read`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ is_read: isRead }),
    });
    if (response.ok)
      setNews((current) =>
        current.map((currentItem) =>
          currentItem.id === item.id
            ? { ...currentItem, is_read: isRead }
            : currentItem,
        ),
      );
  };

  useEffect(() => {
    // Filter changes intentionally restart the news query with the latest selected values.
    if (taxonomy) void loadNews();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [taxonomy, activeSector, activeIndustry, activeTopic]);

  const backendOnline = Boolean(taxonomy);
  const failedSources = sources.filter((source) => source.status === "error");
  const pendingSources = sources.filter(
    (source) => source.status === "pending",
  );

  if (showAgent)
    return <AgentWorkspace onOpenNews={() => setShowAgent(false)} />;

  return (
    <main className="news-app">
      <aside className="news-sidebar" aria-label="资讯导航">
        <div className="brand-block">
          <div className="brand-mark">▲</div>
          <div>
            <strong>股票资讯</strong>
            <span>Stock News</span>
          </div>
        </div>
        <div className="nav-heading">视图</div>
        <button className="view-item view-item-active" type="button">
          ● 资讯看板
        </button>
        <button
          className="view-item"
          type="button"
          onClick={() => setShowAgent(true)}
        >
          ● 股票助手
        </button>
        <div className="nav-heading">一级板块</div>
        <div className="sector-list">
          <button
            className={`sector-item ${activeSector === "全部行业" ? "sector-item-active" : ""}`}
            type="button"
            onClick={() => {
              setActiveSector("全部行业");
              setActiveIndustry("");
            }}
          >
            <span>全部行业</span>
            <small>{news.length}</small>
          </button>
          {taxonomy?.primarySectors.map((sector) => (
            <button
              className={`sector-item ${activeSector === sector.name ? "sector-item-active" : ""}`}
              key={sector.id}
              type="button"
              onClick={() => {
                setActiveSector(sector.name);
                setActiveIndustry("");
              }}
            >
              <span>{sector.name}</span>
              <small>{sector.industries.length}</small>
            </button>
          ))}
        </div>
      </aside>

      <section className="news-main">
        <header className="news-header">
          <div>
            <p className="section-kicker">INVESTMENT NEWS</p>
            <h1>{activeSector}</h1>
            <p className="header-meta">
              {news.length} 条已存资讯 ·{" "}
              <span>
                {updatedAt ? `更新于 ${formatDate(updatedAt)}` : "等待首次抓取"}
              </span>
            </p>
          </div>
          <div className="header-actions">
            <span
              className={`backend-connection ${backendOnline ? "backend-connection-online" : "backend-connection-offline"}`}
              role="status"
              title={
                error || (backendOnline ? "后端服务已连接" : "后端服务未连接")
              }
            >
              <span className="backend-connection-dot" aria-hidden="true" />
              {backendOnline ? "已连接" : "未连接"}
            </span>
            <button
              type="button"
              aria-label="刷新资讯"
              onClick={() => void loadNews(true)}
              disabled={refreshing}
            >
              {refreshing ? "…" : "↻"}
            </button>
            <button
              className="ai-button"
              type="button"
              onClick={() => setShowAgent(true)}
            >
              AI
            </button>
          </div>
        </header>

        <LocalPrivacyBanner />

        <div className="filter-bar" aria-label="资讯筛选">
          <label>
            行业
            <select
              value={activeIndustry}
              onChange={(event) => setActiveIndustry(event.target.value)}
            >
              <option value="">全部行业</option>
              {industries.map((industry) => (
                <option key={industry} value={industry}>
                  {industry}
                </option>
              ))}
            </select>
          </label>
          <div className="topic-filters">
            <span>主题</span>
            {taxonomy?.themes.slice(0, 8).map((topic) => (
              <button
                className={activeTopic === topic ? "topic-active" : ""}
                key={topic}
                type="button"
                onClick={() => {
                  const nextTopic = activeTopic === topic ? "" : topic;
                  setActiveTopic(nextTopic);
                  if (nextTopic) setSubscriptionInput(nextTopic);
                }}
              >
                {topic}
              </button>
            ))}
          </div>
          <form className="subscription-form" onSubmit={addSubscription}>
            <input
              value={subscriptionInput}
              onChange={(event) => setSubscriptionInput(event.target.value)}
              placeholder="订阅关键词"
              aria-label="订阅关键词"
            />
            <button type="submit" title="添加订阅">
              <Plus size={15} />
            </button>
          </form>
        </div>

        <div className="news-content">
          {failedSources.length > 0 && (
            <div className="source-warning" role="alert">
              {failedSources.length} 个来源暂时不可用：
              {failedSources.map((source) => source.source_name).join("、")}
              。其他来源仍可继续刷新。
            </div>
          )}
          {pendingSources.length > 0 && (
            <div className="source-pending" role="status">
              {pendingSources.length} 个来源显示“数据源待接入”：
              {pendingSources.map((source) => source.source_name).join("、")}
              。当前不会展示未经验证的内容。
            </div>
          )}
          {loading && <div className="empty-state">正在读取本地资讯库…</div>}
          {!loading && news.length === 0 && (
            <div className="empty-state">
              <strong>暂无匹配资讯</strong>
              <span>点击右上角刷新按钮抓取已配置来源，或调整筛选条件。</span>
            </div>
          )}
          {subscriptions.length > 0 && (
            <div className="subscription-tags">
              {subscriptions.map((subscription) => (
                <button
                  key={subscription.id}
                  type="button"
                  onClick={() => void deleteSubscription(subscription)}
                  title="取消订阅"
                >
                  {subscription.keyword} <X size={12} />
                </button>
              ))}
            </div>
          )}
          <div className="news-list">
            {news.map((item) => (
              <article
                className={`news-card ${item.is_read ? "news-card-read" : "news-card-unread"}`}
                key={item.id}
              >
                <div className="news-bullet" />
                <div className="news-card-body">
                  <h2>
                    <a
                      href={item.url}
                      target="_blank"
                      rel="noreferrer"
                      onClick={() => void setNewsRead(item, true)}
                    >
                      {item.title}
                    </a>
                  </h2>
                  {item.summary && <p>{item.summary}</p>}
                  <div className="news-tags">
                    <span className="tag">{item.primary_sector}</span>
                    {item.industry && (
                      <span className="tag">{item.industry}</span>
                    )}
                    {item.topics.map((topic) => (
                      <span className="tag" key={topic}>
                        {topic}
                      </span>
                    ))}
                    {item.matched_subscriptions?.map((keyword) => (
                      <span className="tag subscription-match" key={keyword}>
                        {keyword}
                      </span>
                    ))}
                  </div>
                </div>
                <div className="news-card-meta">
                  <strong>{item.source_name}</strong>
                  <time>{formatDate(item.published_at)}</time>
                  <small>
                    {item.fetched_at
                      ? `抓取于 ${formatDate(item.fetched_at)}`
                      : ""}
                  </small>
                  <button
                    type="button"
                    onClick={() => void setNewsRead(item, !item.is_read)}
                    title={item.is_read ? "标为未读" : "标为已读"}
                  >
                    {item.is_read ? <EyeOff size={15} /> : <Eye size={15} />}
                  </button>
                </div>
              </article>
            ))}
          </div>
          {!loading && news.length < total && (
            <button
              className="load-more-button"
              type="button"
              onClick={() => void loadNews(false, offset, true)}
              disabled={loadingMore}
            >
              {loadingMore
                ? "正在加载..."
                : `加载更多（已显示 ${news.length} / ${total}）`}
            </button>
          )}
          {sources.length > 0 && (
            <section className="source-panel">
              <h2>来源健康</h2>
              {sources.map((source) => (
                <div className="source-row" key={source.source_id}>
                  <span
                    className={`source-dot source-${source.is_stale ? "error" : source.status}`}
                  />{" "}
                  <strong>{source.source_name}</strong>
                  <span>
                    {source.status === "ok"
                      ? `${source.item_count} 条 · ${source.delay_minutes ?? "—"} 分钟前成功`
                      : source.status === "pending"
                        ? "数据源待接入"
                        : source.detail || "不可用"}
                    {source.is_stale ? " · 超过 2 小时未更新" : ""}
                  </span>
                </div>
              ))}
            </section>
          )}
        </div>
      </section>
    </main>
  );
}

type RootView = "news" | "agent";

function readRootView(): RootView {
  return new URLSearchParams(window.location.search).get("view") === "agent"
    ? "agent"
    : "news";
}

function App() {
  const [view, setView] = useState<RootView>(readRootView);

  useEffect(() => {
    const onPopState = () => setView(readRootView());
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  const navigateToNews = () => {
    const url = new URL(window.location.href);
    url.searchParams.delete("view");
    window.history.pushState({}, "", url);
    setView("news");
  };

  if (view === "agent") {
    return <AgentWorkspace onOpenNews={navigateToNews} />;
  }

  return <InvestmentNewsFrame />;
}

void LegacyNewsWorkspace;

export default App;
