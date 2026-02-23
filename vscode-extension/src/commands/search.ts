import * as vscode from "vscode";
import type { McpSupervisor } from "../mcp/McpSupervisor.js";
import type { SearchResult } from "../mcp/types.js";

interface SymbolItem extends vscode.QuickPickItem {
  result: SearchResult;
}

export function registerSearchCommand(
  context: vscode.ExtensionContext,
  supervisor: McpSupervisor,
): void {
  context.subscriptions.push(
    vscode.commands.registerCommand("codelibrarian.search", async () => {
      const client = supervisor.mcpClient;
      if (!client?.ready) {
        vscode.window.showWarningMessage("Codelibrarian server is not connected.");
        return;
      }

      const limit = vscode.workspace
        .getConfiguration("codelibrarian")
        .get<number>("searchResultLimit", 20);

      const qp = vscode.window.createQuickPick<SymbolItem>();
      qp.placeholder = "Search code symbols...";
      qp.matchOnDescription = true;
      qp.matchOnDetail = true;

      let debounceTimer: ReturnType<typeof setTimeout> | undefined;

      qp.onDidChangeValue((value) => {
        if (debounceTimer) clearTimeout(debounceTimer);
        if (!value.trim()) {
          qp.items = [];
          return;
        }

        debounceTimer = setTimeout(async () => {
          qp.busy = true;
          const results = await client.searchCode(value, limit);
          qp.items = results.map((r) => toQuickPickItem(r));
          qp.busy = false;
        }, 300);
      });

      qp.onDidAccept(() => {
        const selected = qp.selectedItems[0];
        if (selected) {
          navigateToSymbol(selected.result);
        }
        qp.dispose();
      });

      qp.onDidHide(() => {
        if (debounceTimer) clearTimeout(debounceTimer);
        qp.dispose();
      });

      qp.show();
    }),
  );
}

function toQuickPickItem(r: SearchResult): SymbolItem {
  return {
    label: `$(${kindIcon(r.kind)}) ${r.name}`,
    description: `${r.kind} — ${r.relative_path}:${r.line_start ?? "?"}`,
    detail: r.signature ?? undefined,
    result: r,
  };
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

function navigateToSymbol(sym: SearchResult): void {
  const uri = vscode.Uri.file(sym.file_path);
  const line = (sym.line_start ?? 1) - 1;
  vscode.window.showTextDocument(uri, {
    selection: new vscode.Range(line, 0, line, 0),
  });
}
