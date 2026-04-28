// Master data API: sites, lines, processes
// TODO: Implement master data endpoints

import { apiClient } from "./client";
import type { SiteMaster, LineMaster, ProcessMaster } from "../types/master";

/**
 * TODO: Get all site master records.
 */
export async function getSites(): Promise<SiteMaster[]> {
  // TODO: implement
  return apiClient.get<SiteMaster[]>("/master/sites");
}

/**
 * TODO: Get lines for a given site.
 */
export async function getLines(_siteCode: string): Promise<LineMaster[]> {
  // TODO: implement
  return apiClient.get<LineMaster[]>(`/master/lines?siteCode=${_siteCode}`);
}

/**
 * TODO: Get processes for a given line.
 */
export async function getProcesses(_lineCode: string): Promise<ProcessMaster[]> {
  // TODO: implement
  return apiClient.get<ProcessMaster[]>(`/master/processes?lineCode=${_lineCode}`);
}
