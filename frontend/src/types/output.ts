export type ChartType = "line" | "bar" | "pie" | "histogram" | "area";

export interface ColumnDef {
  key: string;
  label: string;
  type: "string" | "number" | "date";
}

export interface SeriesConfig {
  key: string;
  label: string;
  color: string;
}

export interface TableData {
  columns: ColumnDef[];
  rows: Record<string, string | number>[];
}

export interface ChartConfig {
  type: ChartType;
  title: string;
  xAxis: string;
  yAxis: string;
  series: SeriesConfig[];
}

export interface OutputData {
  messageId: string;
  tableData: TableData | null;
  chartConfig: ChartConfig | null;
  sqlExecuted: string | null;
  rowCount: number;
}
