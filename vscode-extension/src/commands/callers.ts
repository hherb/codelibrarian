import * as vscode from "vscode";
import type { McpSupervisor } from "../mcp/McpSupervisor.js";
import type { CallGraphProvider } from "../providers/CallGraphProvider.js";

export function registerCallersCommand(
  context: vscode.ExtensionContext,
  supervisor: McpSupervisor,
  callGraphProvider: CallGraphProvider,
): void {
  context.subscriptions.push(
    vscode.commands.registerCommand(
      "codelibrarian.showCallers",
      async (qualifiedName?: string) => {
        const name = qualifiedName ?? (await pickSymbolName(supervisor));
        if (!name) return;

        callGraphProvider.setRoot(name, "callers");
        vscode.commands.executeCommand("codelibrarian.callGraphView.focus");
      },
    ),
  );
}

export function registerCalleesCommand(
  context: vscode.ExtensionContext,
  supervisor: McpSupervisor,
  callGraphProvider: CallGraphProvider,
): void {
  context.subscriptions.push(
    vscode.commands.registerCommand(
      "codelibrarian.showCallees",
      async (qualifiedName?: string) => {
        const name = qualifiedName ?? (await pickSymbolName(supervisor));
        if (!name) return;

        callGraphProvider.setRoot(name, "callees");
        vscode.commands.executeCommand("codelibrarian.callGraphView.focus");
      },
    ),
  );
}

async function pickSymbolName(supervisor: McpSupervisor): Promise<string | undefined> {
  const editor = vscode.window.activeTextEditor;
  if (!editor) return undefined;

  const selection = editor.selection;
  const word = editor.document.getText(
    selection.isEmpty
      ? editor.document.getWordRangeAtPosition(selection.active)
      : selection,
  );

  if (!word) return undefined;

  const client = supervisor.mcpClient;
  if (!client?.ready) return word;

  const symbols = await client.lookupSymbol(word);
  if (symbols.length === 1) {
    return symbols[0].qualified_name;
  }

  if (symbols.length > 1) {
    const picked = await vscode.window.showQuickPick(
      symbols.map((s) => ({
        label: s.qualified_name,
        description: `${s.kind} — ${s.relative_path}:${s.line_start ?? "?"}`,
      })),
      { placeHolder: "Multiple matches — pick a symbol" },
    );
    return picked?.label;
  }

  return word;
}
