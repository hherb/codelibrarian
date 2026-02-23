import * as vscode from "vscode";
import { McpClient } from "./McpClient.js";

const MAX_BACKOFF_MS = 30_000;
const STABLE_RESET_MS = 60_000;

export class McpSupervisor implements vscode.Disposable {
  private client: McpClient | null = null;
  private restartCount = 0;
  private restartTimer: ReturnType<typeof setTimeout> | null = null;
  private stableTimer: ReturnType<typeof setTimeout> | null = null;
  private disposed = false;

  private readonly _onDidConnect = new vscode.EventEmitter<void>();
  readonly onDidConnect = this._onDidConnect.event;

  private readonly _onDidDisconnect = new vscode.EventEmitter<void>();
  readonly onDidDisconnect = this._onDidDisconnect.event;

  constructor(
    private readonly executablePath: string,
    private readonly workspaceRoot: string,
    private readonly maxRestarts: number = 5,
  ) {}

  get mcpClient(): McpClient | null {
    return this.client;
  }

  get isConnected(): boolean {
    return this.client?.ready ?? false;
  }

  async start(): Promise<void> {
    await this.connectClient();
  }

  private async connectClient(): Promise<void> {
    if (this.disposed) return;

    this.client?.dispose();
    this.client = new McpClient(this.executablePath, this.workspaceRoot, () => {
      this.handleClose();
    });

    try {
      await this.client.connect();
      this.restartCount = 0;
      this._onDidConnect.fire();
      this.startStableTimer();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      if (msg.includes("ENOENT")) {
        vscode.window
          .showWarningMessage(
            `Codelibrarian executable not found at "${this.executablePath}". Install it or update codelibrarian.executablePath.`,
            "Open Settings",
          )
          .then((choice) => {
            if (choice === "Open Settings") {
              vscode.commands.executeCommand(
                "workbench.action.openSettings",
                "codelibrarian.executablePath",
              );
            }
          });
      } else {
        this.scheduleRestart();
      }
      this._onDidDisconnect.fire();
    }
  }

  private handleClose(): void {
    if (this.disposed) return;
    this.clearStableTimer();
    this._onDidDisconnect.fire();
    this.scheduleRestart();
  }

  private scheduleRestart(): void {
    if (this.disposed) return;
    if (this.restartCount >= this.maxRestarts) {
      this._onDidDisconnect.fire();
      return;
    }

    const delay = Math.min(1000 * Math.pow(2, this.restartCount), MAX_BACKOFF_MS);
    this.restartCount++;

    this.restartTimer = setTimeout(() => {
      this.connectClient();
    }, delay);
  }

  private startStableTimer(): void {
    this.clearStableTimer();
    this.stableTimer = setTimeout(() => {
      this.restartCount = 0;
    }, STABLE_RESET_MS);
  }

  private clearStableTimer(): void {
    if (this.stableTimer) {
      clearTimeout(this.stableTimer);
      this.stableTimer = null;
    }
  }

  resetAndRestart(): void {
    this.restartCount = 0;
    if (this.restartTimer) {
      clearTimeout(this.restartTimer);
      this.restartTimer = null;
    }
    this.connectClient();
  }

  dispose(): void {
    this.disposed = true;
    if (this.restartTimer) {
      clearTimeout(this.restartTimer);
    }
    this.clearStableTimer();
    this.client?.dispose();
    this._onDidConnect.dispose();
    this._onDidDisconnect.dispose();
  }
}
