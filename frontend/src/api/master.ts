// Master データ API: サイト・ライン・工程の参照

import { apiClient } from "./client";
import type { SiteMaster, LineMaster, ProcessMaster } from "../types/master";

interface SitesResponse {
  sites: SiteMaster[];
}

interface LinesResponse {
  lines: LineMaster[];
}

interface ProcessesResponse {
  processes: ProcessMaster[];
}

/** サイトマスタの一覧をマスターキャッシュから取得する */
export async function getSites(): Promise<SiteMaster[]> {
  const response = await apiClient.get<SitesResponse>("/master/sites");
  return response.sites;
}

/** 指定サイトに属するライン一覧を取得する */
export async function getLines(siteCode: string): Promise<LineMaster[]> {
  const query = new URLSearchParams({ site_code: siteCode });
  const response = await apiClient.get<LinesResponse>(
    `/master/lines?${query.toString()}`
  );
  return response.lines;
}

/** 指定ラインに属する工程一覧を取得する */
export async function getProcesses(lineCode: string): Promise<ProcessMaster[]> {
  const query = new URLSearchParams({ line_code: lineCode });
  const response = await apiClient.get<ProcessesResponse>(
    `/master/processes?${query.toString()}`
  );
  return response.processes;
}
