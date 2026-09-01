"use client";

type Lang = "zh" | "en";

type ReportPlayer = {
  seat: number;
  name: string;
  backend?: string;
  model?: string;
  rank: number;
  metrics: Record<string, string | number | boolean>;
};

type TrendPoint = {
  turn: number;
  breaks_completed: number;
  final?: boolean;
  players: {seat: number; score: number; appeal: number; conservation: number}[];
};

type TableRow = {
  key: string;
  label_zh: string;
  label_en: string;
  group: string;
  values: (string | number | boolean)[];
};

type ModelQuality = {
  seat: number;
  model_calls: number;
  successful_calls: number;
  fallback_calls: number;
  fallback_rate: number;
  recorded_thinking_seconds: number;
  latency_missing_calls: number;
  trace_recovered_calls?: number;
  fallback_error_kinds: Record<string, number>;
};

export type ArkNovaMatchReportData = {
  schema_version: string;
  match_id: string;
  duration: {wall_seconds: number; started_at: string; finished_at: string};
  turns: number;
  decisions: number;
  breaks: {total: number};
  players: ReportPlayer[];
  model_quality: ModelQuality[];
  score_trend: TrendPoint[];
  table: TableRow[];
};

const GROUP_LABELS: Record<string, Record<Lang, string>> = {
  overview: {zh: "对局概览", en: "Overview"},
  score: {zh: "轨道与得分", en: "Tracks & score"},
  actions: {zh: "行动", en: "Actions"},
  resources: {zh: "资源", en: "Resources"},
  cards: {zh: "卡牌", en: "Cards"},
  association: {zh: "协会", en: "Association"},
  map: {zh: "地图", en: "Map"},
  upgrades: {zh: "行动牌升级", en: "Action-card upgrades"},
  icons: {zh: "图标", en: "Icons"},
};

function durationText(seconds: number, lang: Lang) {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = Math.round(seconds % 60);
  if (lang === "zh") return `${hours ? `${hours}小时` : ""}${minutes}分${secs}秒`;
  return `${hours ? `${hours}h ` : ""}${minutes}m ${secs}s`;
}

function valueText(row: TableRow, value: string | number | boolean, quality: ModelQuality | undefined, lang: Lang) {
  if (row.key === "thinking_seconds" && typeof value === "number") {
    const missing = quality?.latency_missing_calls || 0;
    const suffix = missing
      ? (lang === "zh" ? `（另有 ${missing} 次调用未记录耗时）` : ` (+ ${missing} calls without latency)`)
      : "";
    return `${(value / 60).toFixed(1)} ${lang === "zh" ? "分钟" : "min"}${suffix}`;
  }
  if (typeof value === "boolean") return value ? (lang === "zh" ? "是" : "Yes") : (lang === "zh" ? "否" : "No");
  if (row.key === "map_id") return String(value).replace(/^map-/, "Map ");
  return String(value);
}

function ScoreTrend({report, lang}: {report: ArkNovaMatchReportData; lang: Lang}) {
  const width = 960;
  const height = 320;
  const margin = {left: 54, right: 70, top: 28, bottom: 44};
  const points = report.score_trend;
  const scores = points.flatMap(point => point.players.map(player => player.score));
  const maxTurn = Math.max(1, ...points.map(point => point.turn));
  const rawMin = Math.min(0, ...scores);
  const rawMax = Math.max(1, ...scores);
  const padding = Math.max(3, Math.ceil((rawMax - rawMin) * 0.08));
  const minScore = rawMin - padding;
  const maxScore = rawMax + padding;
  const chartWidth = width - margin.left - margin.right;
  const chartHeight = height - margin.top - margin.bottom;
  const x = (turn: number) => margin.left + (turn / maxTurn) * chartWidth;
  const y = (score: number) => margin.top + ((maxScore - score) / (maxScore - minScore)) * chartHeight;
  const yTicks = Array.from({length: 5}, (_, index) => Math.round(minScore + ((maxScore - minScore) * index) / 4));
  const xTicks = Array.from({length: 6}, (_, index) => Math.round((maxTurn * index) / 5));
  const breakTurns = points.filter((point, index) => index > 0 && point.breaks_completed > points[index - 1].breaks_completed);

  return <section className="ark-report-chart" aria-labelledby="ark-score-trend-title">
    <header><div><span>SCORE TREND</span><h3 id="ark-score-trend-title">{lang === "zh" ? "实时轨道分数趋势" : "Live track-score trend"}</h3></div><small>{lang === "zh" ? "魅力＋保护轨道印刷分；虚线为休息触发点。终局结算分见下表。" : "Appeal plus printed Conservation score; dashed lines mark breaks. Final VP is listed below."}</small></header>
    <div className="ark-report-legend">{report.players.map((player, index) => <span key={player.seat}><i className={`ark-report-series-${index + 1}`}/>{player.name}</span>)}</div>
    <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-labelledby="ark-score-trend-svg-title ark-score-trend-svg-desc">
      <title id="ark-score-trend-svg-title">{lang === "zh" ? "每回合分数趋势图" : "Score by turn"}</title>
      <desc id="ark-score-trend-svg-desc">{report.players.map(player => `${player.name}: ${player.metrics.final_track_score}`).join("; ")}</desc>
      <rect className="ark-report-chart-frame" x={margin.left} y={margin.top} width={chartWidth} height={chartHeight}/>
      {yTicks.map(tick => <g key={`y-${tick}`}><line className="ark-report-grid" x1={margin.left} x2={width - margin.right} y1={y(tick)} y2={y(tick)}/><text className="ark-report-axis" x={margin.left - 10} y={y(tick) + 4} textAnchor="end">{tick}</text></g>)}
      {xTicks.map(tick => <g key={`x-${tick}`}><line className="ark-report-tick" x1={x(tick)} x2={x(tick)} y1={height - margin.bottom} y2={height - margin.bottom + 5}/><text className="ark-report-axis" x={x(tick)} y={height - margin.bottom + 21} textAnchor="middle">{tick}</text></g>)}
      {breakTurns.map(point => <line key={`break-${point.turn}-${point.breaks_completed}`} className="ark-report-break-line" x1={x(point.turn)} x2={x(point.turn)} y1={margin.top} y2={height - margin.bottom}/>) }
      {report.players.map((player, index) => {
        const series = points.map(point => ({turn: point.turn, score: point.players.find(item => item.seat === player.seat)?.score})).filter(item => typeof item.score === "number") as {turn: number; score: number}[];
        const path = series.map((point, pointIndex) => `${pointIndex ? "L" : "M"}${x(point.turn).toFixed(2)},${y(point.score).toFixed(2)}`).join(" ");
        const last = series.at(-1);
        return <g key={player.seat} className={`ark-report-line ark-report-series-${index + 1}`}><path d={path}/>{last && <><circle cx={x(last.turn)} cy={y(last.score)} r="4"/><text x={x(last.turn) + 9} y={y(last.score) + 4}>{last.score}</text></>}</g>;
      })}
      <text className="ark-report-axis-title" x={margin.left + chartWidth / 2} y={height - 7} textAnchor="middle">{lang === "zh" ? "回合" : "Turn"}</text>
      <text className="ark-report-axis-title" transform={`translate(15 ${margin.top + chartHeight / 2}) rotate(-90)`} textAnchor="middle">{lang === "zh" ? "分数" : "Score"}</text>
    </svg>
  </section>;
}

export function ArkNovaMatchReport({report, lang}: {report: ArkNovaMatchReportData; lang: Lang}) {
  const orderedGroups = [...new Set(report.table.map(row => row.group))];
  const qualityBySeat = new Map(report.model_quality.map(item => [item.seat, item]));
  return <section className="ark-match-report">
    <header className="ark-report-heading"><div><span>POSTGAME REPORT</span><h2>{lang === "zh" ? "对局统计与模型质量" : "Match statistics & model quality"}</h2></div><p>{lang === "zh" ? "所有数字由最终状态、事件流与模型调用记录确定性生成。" : "All values are deterministically derived from final state, events, and model-call records."}</p></header>
    <div className="ark-report-summary">
      <div><span>{lang === "zh" ? "游戏耗时" : "Wall time"}</span><strong>{durationText(report.duration.wall_seconds, lang)}</strong></div>
      <div><span>{lang === "zh" ? "休息次数" : "Breaks"}</span><strong>{report.breaks.total}</strong></div>
      <div><span>{lang === "zh" ? "回合 / 决策" : "Turns / decisions"}</span><strong>{report.turns} / {report.decisions}</strong></div>
    </div>
    <ScoreTrend report={report} lang={lang}/>
    <section className="ark-report-quality"><header><span>HARNESS QUALITY</span><h3>{lang === "zh" ? "模型调用完整性" : "Model-call integrity"}</h3></header><div>{report.players.map(player => {
      const quality = qualityBySeat.get(player.seat);
      if (!quality) return null;
      return <article key={player.seat}><strong>{player.name}</strong><span>{quality.successful_calls}/{quality.model_calls} {lang === "zh" ? "次成功" : "successful"}</span><b>{(quality.fallback_rate * 100).toFixed(1)}% {lang === "zh" ? "回退" : "fallback"}</b>{Boolean(quality.trace_recovered_calls) && <small>{lang === "zh" ? `${quality.trace_recovered_calls} 次旧失败调用的耗时已由 turn trace 补回` : `${quality.trace_recovered_calls} historical failure latencies recovered from turn traces`}</small>}{quality.latency_missing_calls > 0 && <small>{lang === "zh" ? `${quality.latency_missing_calls} 次失败调用没有耗时记录` : `${quality.latency_missing_calls} failed calls lack latency`}</small>}</article>;
    })}</div></section>
    <div className="ark-report-table-wrap"><table className="ark-report-table"><thead><tr><th>{lang === "zh" ? "统计项目" : "Metric"}</th>{report.players.map(player => <th key={player.seat}><span>{player.rank === 1 ? (lang === "zh" ? "冠军" : "Winner") : (lang === "zh" ? `第 ${player.rank} 名` : `Rank ${player.rank}`)}</span><strong>{player.name}</strong></th>)}</tr></thead><tbody>
      <tr className="ark-report-result-row"><th>{lang === "zh" ? "游戏结果" : "Result"}</th>{report.players.map(player => <td key={player.seat}>{player.rank === 1 ? (lang === "zh" ? "冠军" : "Winner") : (lang === "zh" ? "亚军" : "Runner-up")}</td>)}</tr>
      {orderedGroups.flatMap(group => [
        <tr className="ark-report-group" key={`group-${group}`}><th colSpan={report.players.length + 1}>{GROUP_LABELS[group]?.[lang] || group}</th></tr>,
        ...report.table.filter(row => row.group === group).map(row => <tr key={row.key}><th>{lang === "zh" ? row.label_zh : row.label_en}</th>{row.values.map((value, index) => <td key={`${row.key}-${report.players[index]?.seat}`}>{valueText(row, value, qualityBySeat.get(report.players[index]?.seat), lang)}</td>)}</tr>),
      ])}
    </tbody></table></div>
  </section>;
}
