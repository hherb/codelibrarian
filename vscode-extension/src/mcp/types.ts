export interface Parameter {
  name: string;
  type: string | null;
  default: string | null;
}

export interface SymbolRecord {
  id: number;
  name: string;
  qualified_name: string;
  kind: "function" | "method" | "class" | "module";
  file_path: string;
  relative_path: string;
  line_start: number | null;
  line_end: number | null;
  signature: string | null;
  docstring: string | null;
  parameters: Parameter[];
  return_type: string | null;
  decorators: string[];
}

export interface SearchResult extends SymbolRecord {
  score: number;
  match_type: "semantic" | "fulltext" | "hybrid" | "graph";
}

export interface CallerCount {
  count: number;
  qualified_name: string;
}

export interface ClassHierarchy {
  class: { id: number; qualified_name: string; relative_path: string } | null;
  parents: Array<{ name: string; qualified_name: string; relative_path: string }>;
  children: Array<{ name: string; qualified_name: string; relative_path: string }>;
}

export interface FileImports {
  imports: Array<{
    to_module: string;
    import_name: string | null;
    resolved_path: string | null;
  }>;
  imported_by: Array<{
    path: string;
    relative_path: string;
  }>;
}
