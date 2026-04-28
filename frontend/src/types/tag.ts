export interface TagSuggestion {
  tagKey: string;
  tagValue: string;
  confidence: number;
  source: "alias_match" | "like_search" | "semantic_search";
}

export interface Tag {
  key: string;
  value: string;
  confirmed: boolean;
}
