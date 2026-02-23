import * as vscode from "vscode";
import { spawn } from "child_process";

const SUPPORTED_EXTENSIONS = new Set([
  ".py",
  ".ts",
  ".tsx",
  ".js",
  ".jsx",
  ".mjs",
  ".rs",
  ".java",
  ".cpp",
  ".cc",
  ".cxx",
  ".c",
  ".h",
  ".hpp",
  ".swift",
  ".kt",
  ".kts",
]);

const DEBOUNCE_MS = 2_000;

export class SaveWatcher implements vscode.Disposable {
  private disposable: vscode.Disposable;
  private pendingFiles = new Map<string, ReturnType<typeof setTimeout>>();
  private readonly onIndexed: () => void;

  constructor(
    private readonly executablePath: string,
    private readonly workspaceRoot: string,
    onIndexed: () => void,
  ) {
    this.onIndexed = onIndexed;
    this.disposable = vscode.workspace.onDidSaveTextDocument((doc) => {
      this.handleSave(doc);
    });
  }

  private handleSave(document: vscode.TextDocument): void {
    const config = vscode.workspace.getConfiguration("codelibrarian");
    if (!config.get<boolean>("autoIndexOnSave", true)) return;

    const filePath = document.uri.fsPath;
    if (!filePath.startsWith(this.workspaceRoot)) return;

    const ext = extname(filePath);
    if (!SUPPORTED_EXTENSIONS.has(ext)) return;

    const existing = this.pendingFiles.get(filePath);
    if (existing) clearTimeout(existing);

    this.pendingFiles.set(
      filePath,
      setTimeout(() => {
        this.pendingFiles.delete(filePath);
        this.indexFile(filePath);
      }, DEBOUNCE_MS),
    );
  }

  private indexFile(filePath: string): void {
    const child = spawn(this.executablePath, [
      "index",
      "--files",
      filePath,
      "--path",
      this.workspaceRoot,
    ]);

    child.on("close", () => {
      this.onIndexed();
    });

    child.on("error", () => {
      // Silently ignore — the executable may not be available
    });
  }

  dispose(): void {
    this.disposable.dispose();
    for (const timer of this.pendingFiles.values()) {
      clearTimeout(timer);
    }
    this.pendingFiles.clear();
  }
}

function extname(filePath: string): string {
  const dot = filePath.lastIndexOf(".");
  return dot >= 0 ? filePath.slice(dot).toLowerCase() : "";
}
