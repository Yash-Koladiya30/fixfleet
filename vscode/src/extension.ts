/**
 * FixFleet VSCode extension entry point.
 */
import * as vscode from 'vscode';
import { BugPanel } from './bugPanel';
import { SettingsPanel } from './settingsPanel';
import { FixFleetWebView } from './welcomeView';
import { checkCliInstalled } from './fixfleetCli';

let statusBar: vscode.StatusBarItem;

export function activate(context: vscode.ExtensionContext) {
    // ── Register commands FIRST (before any async ops) ─────────
    // This guarantees the sidebar buttons work even during slow CLI checks.

    const webview = new FixFleetWebView(context);

    context.subscriptions.push(
        vscode.window.registerWebviewViewProvider(FixFleetWebView.viewType, webview),

        vscode.commands.registerCommand('fixfleet.refresh', () => {
            webview.refresh();
            const bugs = webview.getBugs();
            statusBar.text = `$(rocket) FixFleet · ${bugs.length} bugs`;
        }),

        vscode.commands.registerCommand('fixfleet.openSettings', () => {
            SettingsPanel.createOrShow(context);
        }),

        vscode.commands.registerCommand('fixfleet.openBug', (bug: any) => {
            if (bug) BugPanel.createOrShow(context, bug);
        }),

        vscode.commands.registerCommand('fixfleet.fixBug', (bug: any) => {
            if (bug) BugPanel.createOrShow(context, bug);
        }),

        vscode.commands.registerCommand('fixfleet.openInBrowser', (arg: any) => {
            const url = arg?.web_url || arg?.bug?.web_url;
            if (url) vscode.env.openExternal(vscode.Uri.parse(url));
        }),

        vscode.commands.registerCommand('fixfleet.checkInstall', async () => {
            const s = await checkCliInstalled();
            if (s.installed) {
                vscode.window.showInformationMessage(`FixFleet CLI ${s.version} ready ✓`);
            } else {
                vscode.window.showWarningMessage('FixFleet CLI not installed.', 'Install').then(c => {
                    if (c === 'Install') vscode.commands.executeCommand('fixfleet.installCli');
                });
            }
        }),

        vscode.commands.registerCommand('fixfleet.installCli', () => {
            const terminal = vscode.window.createTerminal('Install FixFleet CLI');
            terminal.show();
            terminal.sendText(
                "pip3 install --user fixfleet && echo 'export PATH=\"$(python3 -m site --user-base)/bin:$PATH\"' >> ~/.zshrc && source ~/.zshrc && fixfleet --version",
            );
            vscode.window.showInformationMessage('Installing FixFleet CLI in terminal…');
        }),

        // Refresh sidebar on config changes
        vscode.workspace.onDidChangeConfiguration(e => {
            if (e.affectsConfiguration('fixfleet')) {
                webview.refresh();
            }
        }),
    );

    // ── Status bar ─────────────────────────────────────────────

    statusBar = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
    statusBar.command = 'fixfleet.openSettings';
    statusBar.text = '$(rocket) FixFleet';
    statusBar.tooltip = 'Open FixFleet';
    statusBar.show();
    context.subscriptions.push(statusBar);

    // ── Async CLI check (does NOT block command registration) ──

    checkCliInstalled().then(cliStatus => {
        if (!cliStatus.installed) {
            vscode.window
                .showWarningMessage(
                    'FixFleet CLI not installed. Install it now?',
                    'Install',
                    'Open Settings',
                )
                .then(choice => {
                    if (choice === 'Install') vscode.commands.executeCommand('fixfleet.installCli');
                    else if (choice === 'Open Settings') vscode.commands.executeCommand('fixfleet.openSettings');
                });
        } else {
            statusBar.tooltip = `FixFleet CLI ${cliStatus.version || ''} ready`;
        }
    });
}

export function deactivate() {
    statusBar?.dispose();
}
