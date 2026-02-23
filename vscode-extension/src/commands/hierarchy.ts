import * as vscode from "vscode";
import type { McpSupervisor } from "../mcp/McpSupervisor.js";

export function registerHierarchyCommand(
  context: vscode.ExtensionContext,
  supervisor: McpSupervisor,
): void {
  context.subscriptions.push(
    vscode.commands.registerCommand(
      "codelibrarian.showHierarchy",
      async (className?: string) => {
        const client = supervisor.mcpClient;
        if (!client?.ready) {
          vscode.window.showWarningMessage("Codelibrarian server is not connected.");
          return;
        }

        const name = className ?? await promptClassName();
        if (!name) return;

        const hierarchy = await client.getClassHierarchy(name);
        if (!hierarchy || !hierarchy.class) {
          vscode.window.showInformationMessage(`No class found for "${name}".`);
          return;
        }

        const lines: string[] = [];
        lines.push(`Class: ${hierarchy.class.qualified_name}`);
        lines.push("");

        if (hierarchy.parents.length > 0) {
          lines.push("Parents:");
          for (const p of hierarchy.parents) {
            lines.push(`  - ${p.qualified_name} (${p.relative_path})`);
          }
          lines.push("");
        }

        if (hierarchy.children.length > 0) {
          lines.push("Children:");
          for (const c of hierarchy.children) {
            lines.push(`  - ${c.qualified_name} (${c.relative_path})`);
          }
        }

        if (hierarchy.parents.length === 0 && hierarchy.children.length === 0) {
          lines.push("No known parents or children.");
        }

        const doc = await vscode.workspace.openTextDocument({
          content: lines.join("\n"),
          language: "markdown",
        });
        vscode.window.showTextDocument(doc, { preview: true });
      },
    ),
  );
}

async function promptClassName(): Promise<string | undefined> {
  return vscode.window.showInputBox({
    prompt: "Enter class name or qualified class name",
    placeHolder: "MyClass",
  });
}
