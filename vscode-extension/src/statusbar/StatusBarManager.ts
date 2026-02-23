import * as vscode from "vscode";
import type { McpSupervisor } from "../mcp/McpSupervisor.js";

export class StatusBarManager implements vscode.Disposable {
  private item: vscode.StatusBarItem;
  private disposables: vscode.Disposable[] = [];

  constructor(supervisor: McpSupervisor) {
    this.item = vscode.window.createStatusBarItem(
      vscode.StatusBarAlignment.Left,
      50,
    );
    this.item.name = "Codelibrarian";

    this.disposables.push(
      supervisor.onDidConnect(() => this.setConnected()),
      supervisor.onDidDisconnect(() => this.setDisconnected()),
    );

    this.item.command = "codelibrarian.search";
    this.setDisconnected();
    this.item.show();
  }

  private setConnected(): void {
    this.item.text = "$(database) Codelibrarian";
    this.item.tooltip = "Codelibrarian: connected — click to search";
    this.item.backgroundColor = undefined;
  }

  private setDisconnected(): void {
    this.item.text = "$(warning) Codelibrarian";
    this.item.tooltip = "Codelibrarian: disconnected — click to search";
    this.item.backgroundColor = new vscode.ThemeColor(
      "statusBarItem.warningBackground",
    );
  }

  dispose(): void {
    this.item.dispose();
    for (const d of this.disposables) {
      d.dispose();
    }
  }
}
