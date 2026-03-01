import * as vscode from "vscode";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import type {
  SymbolRecord,
  SearchResult,
  CallerCount,
  ClassHierarchy,
  FileImports,
} from "./types.js";

const log = vscode.window.createOutputChannel("Codelibrarian", { log: true });

export class McpClient {
  private client: Client | null = null;
  private transport: StdioClientTransport | null = null;
  private _ready = false;

  constructor(
    private readonly executablePath: string,
    private readonly workspaceRoot: string,
    private readonly onClose: () => void,
  ) {}

  get ready(): boolean {
    return this._ready;
  }

  async connect(): Promise<void> {
    this.transport = new StdioClientTransport({
      command: this.executablePath,
      args: ["serve", "--path", this.workspaceRoot],
    });

    this.client = new Client(
      { name: "codelibrarian-vscode", version: "0.1.0" },
      { capabilities: {} },
    );

    this.transport.onclose = () => {
      this._ready = false;
      this.onClose();
    };

    await this.client.connect(this.transport);
    this._ready = true;
  }

  async callTool<T>(name: string, args: Record<string, unknown>): Promise<T | null> {
    if (!this._ready || !this.client) {
      log.warn(`callTool(${name}): client not ready`);
      return null;
    }
    try {
      log.info(`callTool(${name}) args=${JSON.stringify(args)}`);
      const result = await this.client.callTool({ name, arguments: args });
      const content = result.content;
      if (!Array.isArray(content) || content.length === 0) {
        log.warn(`callTool(${name}): empty content in response`);
        return null;
      }
      const first = content[0];
      if (typeof first === "object" && "text" in first) {
        const parsed = JSON.parse(first.text as string) as T;
        if (parsed && typeof parsed === "object" && "error" in parsed) {
          log.error(`callTool(${name}): server error: ${(parsed as Record<string, unknown>).error}`);
          return null;
        }
        log.info(`callTool(${name}): success`);
        return parsed;
      }
      log.warn(`callTool(${name}): unexpected content format`);
      return null;
    } catch (err) {
      log.error(`callTool(${name}): ${err instanceof Error ? err.message : String(err)}`);
      return null;
    }
  }

  async searchCode(query: string, limit = 20, mode = "hybrid"): Promise<SearchResult[]> {
    return (await this.callTool<SearchResult[]>("search_code", { query, limit, mode })) ?? [];
  }

  async lookupSymbol(name: string): Promise<SymbolRecord[]> {
    return (await this.callTool<SymbolRecord[]>("lookup_symbol", { name })) ?? [];
  }

  async listSymbolsInFile(filePath: string): Promise<SymbolRecord[]> {
    return (await this.callTool<SymbolRecord[]>("list_symbols", { file_path: filePath })) ?? [];
  }

  async countCallers(qualifiedName: string): Promise<number> {
    const r = await this.callTool<CallerCount>("count_callers", {
      qualified_name: qualifiedName,
    });
    return r?.count ?? 0;
  }

  async countCallees(qualifiedName: string): Promise<number> {
    const r = await this.callTool<CallerCount>("count_callees", {
      qualified_name: qualifiedName,
    });
    return r?.count ?? 0;
  }

  async getCallers(qualifiedName: string, depth = 1): Promise<SymbolRecord[]> {
    return (
      (await this.callTool<SymbolRecord[]>("get_callers", {
        qualified_name: qualifiedName,
        depth,
      })) ?? []
    );
  }

  async getCallees(qualifiedName: string, depth = 1): Promise<SymbolRecord[]> {
    return (
      (await this.callTool<SymbolRecord[]>("get_callees", {
        qualified_name: qualifiedName,
        depth,
      })) ?? []
    );
  }

  async getClassHierarchy(className: string): Promise<ClassHierarchy | null> {
    return await this.callTool<ClassHierarchy>("get_class_hierarchy", {
      class_name: className,
    });
  }

  async getFileImports(filePath: string): Promise<FileImports | null> {
    return await this.callTool<FileImports>("get_file_imports", {
      file_path: filePath,
    });
  }

  dispose(): void {
    this._ready = false;
    if (this.transport) {
      this.transport.close().catch(() => {});
    }
    this.client = null;
    this.transport = null;
  }
}
