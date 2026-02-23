import * as vscode from "vscode";
import type { McpSupervisor } from "../mcp/McpSupervisor.js";
import type { SymbolRecord } from "../mcp/types.js";

type CallGraphNode = GroupNode | SymbolNode;

class GroupNode {
  constructor(
    public readonly label: string,
    public readonly qualifiedName: string,
    public readonly direction: "callers" | "callees",
  ) {}
}

class SymbolNode {
  constructor(public readonly symbol: SymbolRecord) {}
}

export class CallGraphProvider implements vscode.TreeDataProvider<CallGraphNode> {
  private readonly _onDidChangeTreeData = new vscode.EventEmitter<void>();
  readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

  private rootQualifiedName: string | null = null;
  private rootDirection: "callers" | "callees" = "callers";

  constructor(private readonly supervisor: McpSupervisor) {}

  setRoot(qualifiedName: string, direction: "callers" | "callees"): void {
    this.rootQualifiedName = qualifiedName;
    this.rootDirection = direction;
    this._onDidChangeTreeData.fire();
  }

  refresh(): void {
    this._onDidChangeTreeData.fire();
  }

  getTreeItem(element: CallGraphNode): vscode.TreeItem {
    if (element instanceof GroupNode) {
      const item = new vscode.TreeItem(
        element.label,
        vscode.TreeItemCollapsibleState.Expanded,
      );
      item.iconPath = new vscode.ThemeIcon(
        element.direction === "callers" ? "call-incoming" : "call-outgoing",
      );
      return item;
    }

    const sym = element.symbol;
    const item = new vscode.TreeItem(
      sym.name,
      vscode.TreeItemCollapsibleState.Collapsed,
    );
    item.description = `${sym.kind} — ${sym.relative_path}:${sym.line_start ?? "?"}`;
    item.tooltip = sym.signature ?? sym.qualified_name;
    item.iconPath = new vscode.ThemeIcon(kindIcon(sym.kind));

    if (sym.line_start != null) {
      item.command = {
        title: "Go to Symbol",
        command: "vscode.open",
        arguments: [
          vscode.Uri.file(sym.file_path),
          {
            selection: new vscode.Range(
              sym.line_start - 1, 0,
              sym.line_start - 1, 0,
            ),
          },
        ],
      };
    }

    return item;
  }

  async getChildren(element?: CallGraphNode): Promise<CallGraphNode[]> {
    const client = this.supervisor.mcpClient;
    if (!client?.ready) return [];

    if (!element) {
      if (!this.rootQualifiedName) return [];
      return [
        new GroupNode(
          `${this.rootDirection === "callers" ? "Callers of" : "Callees of"} ${this.rootQualifiedName}`,
          this.rootQualifiedName,
          this.rootDirection,
        ),
      ];
    }

    if (element instanceof GroupNode) {
      const symbols =
        element.direction === "callers"
          ? await client.getCallers(element.qualifiedName)
          : await client.getCallees(element.qualifiedName);
      return symbols.map((s) => new SymbolNode(s));
    }

    if (element instanceof SymbolNode) {
      const sym = element.symbol;
      const nodes: CallGraphNode[] = [];

      const callers = await client.getCallers(sym.qualified_name);
      if (callers.length > 0) {
        nodes.push(new GroupNode("Callers", sym.qualified_name, "callers"));
      }

      const callees = await client.getCallees(sym.qualified_name);
      if (callees.length > 0) {
        nodes.push(new GroupNode("Callees", sym.qualified_name, "callees"));
      }

      return nodes;
    }

    return [];
  }

  dispose(): void {
    this._onDidChangeTreeData.dispose();
  }
}

function kindIcon(kind: string): string {
  switch (kind) {
    case "function":
      return "symbol-function";
    case "method":
      return "symbol-method";
    case "class":
      return "symbol-class";
    case "module":
      return "symbol-module";
    default:
      return "symbol-misc";
  }
}
