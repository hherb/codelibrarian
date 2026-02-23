import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import type {
  SymbolRecord,
  SearchResult,
  CallerCount,
  ClassHierarchy,
  FileImports,
} from "./types.js";

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
      return null;
    }
    try {
      const result = await this.client.callTool({ name, arguments: args });
      const content = result.content;
      if (!Array.isArray(content) || content.length === 0) {
        return null;
      }
      const first = content[0];
      if (typeof first === "object" && "text" in first) {
        return JSON.parse(first.text as string) as T;
      }
      return null;
    } catch {
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
