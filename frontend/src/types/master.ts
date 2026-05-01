export interface SiteMaster {
  code: string;
  name: string;
  aliases: string[];
}

export interface LineMaster {
  code: string;
  name: string;
  site_code: string;
  aliases: string[];
}

export interface ProcessMaster {
  code: string;
  name: string;
  line_code: string;
}
