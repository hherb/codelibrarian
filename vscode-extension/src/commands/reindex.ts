import * as vscode from "vscode";

export function registerReindexCommand(
  context: vscode.ExtensionContext,
): void {
  context.subscriptions.push(
    vscode.commands.registerCommand("codelibrarian.reindex", () => {
      const config = vscode.workspace.getConfiguration("codelibrarian");
      const exe = config.get<string>("executablePath", "codelibrarian");
      const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
      if (!workspaceRoot) return;

      const terminal = vscode.window.createTerminal("Codelibrarian Index");
      terminal.show();
      terminal.sendText(`${exe} index --path "${workspaceRoot}"`);
    }),
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("codelibrarian.init", () => {
      const config = vscode.workspace.getConfiguration("codelibrarian");
      const exe = config.get<string>("executablePath", "codelibrarian");
      const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
      if (!workspaceRoot) return;

      const terminal = vscode.window.createTerminal("Codelibrarian Init");
      terminal.show();
      terminal.sendText(`${exe} init --path "${workspaceRoot}" && ${exe} index --path "${workspaceRoot}"`);
    }),
  );
}
