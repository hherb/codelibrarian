import * as vscode from "vscode";
import { McpSupervisor } from "./mcp/McpSupervisor.js";
import { CodeLibrarianCodeLensProvider } from "./providers/CodeLensProvider.js";
import { CallGraphProvider } from "./providers/CallGraphProvider.js";
import { registerSearchCommand } from "./commands/search.js";
import { registerCallersCommand, registerCalleesCommand } from "./commands/callers.js";
import { registerHierarchyCommand } from "./commands/hierarchy.js";
import { registerReindexCommand } from "./commands/reindex.js";
import { SaveWatcher } from "./autoindex/SaveWatcher.js";
import { StatusBarManager } from "./statusbar/StatusBarManager.js";

const CODELENS_LANGUAGES = [
  "python",
  "typescript",
  "javascript",
  "typescriptreact",
  "javascriptreact",
  "rust",
  "java",
  "cpp",
  "c",
  "swift",
  "kotlin",
];

export async function activate(context: vscode.ExtensionContext): Promise<void> {
  const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
  if (!workspaceRoot) return;

  const config = vscode.workspace.getConfiguration("codelibrarian");
  const executablePath = config.get<string>("executablePath", "codelibrarian");

  // Set context for when-clauses
  vscode.commands.executeCommand("setContext", "codelibrarian.isActive", true);

  // MCP supervisor with crash recovery
  const supervisor = new McpSupervisor(executablePath, workspaceRoot);
  context.subscriptions.push(supervisor);

  // Status bar
  const statusBar = new StatusBarManager(supervisor);
  context.subscriptions.push(statusBar);

  // CodeLens
  const codeLensProvider = new CodeLibrarianCodeLensProvider(supervisor);
  if (config.get<boolean>("codeLensEnabled", true)) {
    const selector = CODELENS_LANGUAGES.map((lang) => ({
      language: lang,
      scheme: "file",
    }));
    context.subscriptions.push(
      vscode.languages.registerCodeLensProvider(selector, codeLensProvider),
    );
  }
  context.subscriptions.push(codeLensProvider);

  // Call Graph tree view
  const callGraphProvider = new CallGraphProvider(supervisor);
  context.subscriptions.push(
    vscode.window.registerTreeDataProvider(
      "codelibrarian.callGraphView",
      callGraphProvider,
    ),
  );
  context.subscriptions.push(callGraphProvider);

  context.subscriptions.push(
    vscode.commands.registerCommand("codelibrarian.refreshCallGraph", () => {
      callGraphProvider.refresh();
    }),
  );

  // Commands
  registerSearchCommand(context, supervisor);
  registerCallersCommand(context, supervisor, callGraphProvider);
  registerCalleesCommand(context, supervisor, callGraphProvider);
  registerHierarchyCommand(context, supervisor);
  registerReindexCommand(context);

  // Auto-index on save
  const saveWatcher = new SaveWatcher(executablePath, workspaceRoot, () => {
    codeLensProvider.invalidateCache();
  });
  context.subscriptions.push(saveWatcher);

  // Start MCP connection
  await supervisor.start();
}

export function deactivate(): void {
  // All disposables registered on context.subscriptions are auto-disposed
}
