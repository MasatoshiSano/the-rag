export interface SiteMaster {
  code: string;
  name: string;
  aliases: string[];
}

export interface LineMaster {
  code: string;
  name: string;
  siteCode: string;
}

export interface ProcessMaster {
  code: string;
  name: string;
  lineCode: string;
}
