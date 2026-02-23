import * as vscode from "vscode";
import type { McpSupervisor } from "../mcp/McpSupervisor.js";
import type { SymbolRecord } from "../mcp/types.js";

interface CachedCount {
  count: number;
  timestamp: number;
}

const CACHE_TTL_MS = 60_000;

export class CodeLibrarianCodeLensProvider implements vscode.CodeLensProvider {
  private readonly _onDidChangeCodeLenses = new vscode.EventEmitter<void>();
  readonly onDidChangeCodeLenses = this._onDidChangeCodeLenses.event;

  private cache = new Map<string, CachedCount>();

  constructor(private readonly supervisor: McpSupervisor) {}

  invalidateCache(): void {
    this.cache.clear();
    this._onDidChangeCodeLenses.fire();
  }

  invalidateFile(uri: vscode.Uri): void {
    for (const key of this.cache.keys()) {
      if (key.startsWith(uri.fsPath + ":")) {
        this.cache.delete(key);
      }
    }
    this._onDidChangeCodeLenses.fire();
  }

  async provideCodeLenses(
    document: vscode.TextDocument,
    _token: vscode.CancellationToken,
  ): Promise<vscode.CodeLens[]> {
    const client = this.supervisor.mcpClient;
    if (!client?.ready) return [];

    const symbols = await client.listSymbolsInFile(document.uri.fsPath);
    if (!symbols.length) return [];

    const lenses: vscode.CodeLens[] = [];
    for (const sym of symbols) {
      if (sym.line_start == null) continue;
      const line = sym.line_start - 1;
      const range = new vscode.Range(line, 0, line, 0);

      lenses.push(
        new SymbolCodeLens(range, sym, "callers"),
      );

      if (sym.kind === "class") {
        lenses.push(
          new SymbolCodeLens(range, sym, "hierarchy"),
        );
      }
    }

    return lenses;
  }

  async resolveCodeLens(
    codeLens: vscode.CodeLens,
    _token: vscode.CancellationToken,
  ): Promise<vscode.CodeLens> {
    if (!(codeLens instanceof SymbolCodeLens)) return codeLens;

    const client = this.supervisor.mcpClient;
    if (!client?.ready) {
      codeLens.command = { title: "...", command: "" };
      return codeLens;
    }

    const sym = codeLens.symbol;
    const lensType = codeLens.lensType;

    if (lensType === "callers") {
      const cacheKey = `${sym.file_path}:${sym.qualified_name}:callers`;
      let cached = this.cache.get(cacheKey);
      if (!cached || Date.now() - cached.timestamp > CACHE_TTL_MS) {
        const count = await client.countCallers(sym.qualified_name);
        cached = { count, timestamp: Date.now() };
        this.cache.set(cacheKey, cached);
      }
      const n = cached.count;
      codeLens.command = {
        title: `${n} caller${n !== 1 ? "s" : ""}`,
        command: "codelibrarian.showCallers",
        arguments: [sym.qualified_name],
      };
    } else if (lensType === "hierarchy") {
      codeLens.command = {
        title: "class hierarchy",
        command: "codelibrarian.showHierarchy",
        arguments: [sym.qualified_name],
      };
    }

    return codeLens;
  }

  dispose(): void {
    this._onDidChangeCodeLenses.dispose();
  }
}

class SymbolCodeLens extends vscode.CodeLens {
  constructor(
    range: vscode.Range,
    public readonly symbol: SymbolRecord,
    public readonly lensType: "callers" | "hierarchy",
  ) {
    super(range);
  }
}
