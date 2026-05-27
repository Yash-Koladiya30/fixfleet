/**
 * FixFleet VSCode extension entry point.
 */
import * as vscode from 'vscode';
import { BugProvider, BugTreeItem } from './bugProvider';
import { BugPanel } from './bugPanel';
import { SettingsPanel } from './settingsPanel';
import { checkCliInstalled } from './fixfleetCli';

let statusBar: vscode.StatusBarItem;

export async function activate(context: vscode.ExtensionContext) {
    const provider = new BugProvider();
    vscode.window.registerTreeDataProvider('fixfleet.bugs', provider);

    statusBar = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
    statusBar.command = 'fixfleet.openSettings';
    statusBar.text = '$(rocket) FixFleet';
    statusBar.tooltip = 'Open FixFleet';
    statusBar.show();
    context.subscriptions.push(statusBar);

    // Initial CLI check
    const cliStatus = await checkCliInstalled();
    if (!cliStatus.installed) {
        const choice = await vscode.window.showWarningMessage(
            'FixFleet CLI not installed. Install it now?',
            'Install',
            'Open Settings',
        );
        if (choice === 'Install') {
            vscode.commands.executeCommand('fixfleet.installCli');
        } else if (choice === 'Open Settings') {
            vscode.commands.executeCommand('fixfleet.openSettings');
        }
    } else {
        statusBar.tooltip = `FixFleet CLI ${cliStatus.version || ''} ready`;
    }

    // ── Commands ───────────────────────────────────────────────

    context.subscriptions.push(
        vscode.commands.registerCommand('fixfleet.refresh', async () => {
            provider.refresh();
            const bugs = provider.getBugs();
            statusBar.text = `$(rocket) FixFleet · ${bugs.length} bugs`;
        }),

        vscode.commands.registerCommand('fixfleet.openSettings', () => {
            SettingsPanel.createOrShow(context);
        }),

        vscode.commands.registerCommand('fixfleet.openBug', (bug: any) => {
            BugPanel.createOrShow(context, bug);
        }),

        vscode.commands.registerCommand('fixfleet.fixBug', async (item: BugTreeItem | undefined) => {
            if (!item || !item.bug) {
                vscode.window.showErrorMessage('Right-click a bug in the FixFleet sidebar.');
                return;
            }
            BugPanel.createOrShow(context, item.bug);
            // Auto-fix
            setTimeout(() => {
                // post fix message via webview is simpler from inside BugPanel
            }, 200);
        }),

        vscode.commands.registerCommand('fixfleet.openInBrowser', (item: BugTreeItem | undefined) => {
            if (item?.bug?.web_url) {
                vscode.env.openExternal(vscode.Uri.parse(item.bug.web_url));
            }
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

        vscode.commands.registerCommand('fixfleet.installCli', async () => {
            const terminal = vscode.window.createTerminal('Install FixFleet CLI');
            terminal.show();
            terminal.sendText(
                "pip3 install --user fixfleet && echo 'export PATH=\"$(python3 -m site --user-base)/bin:$PATH\"' >> ~/.zshrc && source ~/.zshrc && fixfleet --version",
            );
            vscode.window.showInformationMessage('Installing FixFleet CLI in terminal…');
        }),

        // React to config changes
        vscode.workspace.onDidChangeConfiguration(e => {
            if (e.affectsConfiguration('fixfleet')) {
                provider.refresh();
            }
        }),
    );

    // Initial fetch
    setTimeout(() => provider.refresh(), 500);
}

export function deactivate() {
    statusBar?.dispose();
}
