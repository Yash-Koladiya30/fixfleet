/**
 * Webview panel showing one bug in detail with premium UI.
 * Allows triggering the fix from within VSCode.
 */
import * as vscode from 'vscode';
import { BugIssue, FixResult, fixBug } from './fixfleetCli';

export class BugPanel {
    private static activePanels = new Map<number, BugPanel>();

    public static createOrShow(context: vscode.ExtensionContext, bug: BugIssue) {
        const existing = BugPanel.activePanels.get(bug.iid);
        if (existing) {
            existing.panel.reveal(vscode.ViewColumn.Beside);
            existing.update(bug);
            return;
        }

        const panel = vscode.window.createWebviewPanel(
            'fixfleetBug',
            `#${bug.iid} — ${bug.title.slice(0, 60)}`,
            vscode.ViewColumn.Beside,
            {
                enableScripts: true,
                retainContextWhenHidden: true,
                localResourceRoots: [vscode.Uri.joinPath(context.extensionUri, 'media')],
            },
        );

        const instance = new BugPanel(context, panel, bug);
        BugPanel.activePanels.set(bug.iid, instance);
    }

    private constructor(
        private readonly context: vscode.ExtensionContext,
        private readonly panel: vscode.WebviewPanel,
        private bug: BugIssue,
    ) {
        this.update(bug);
        this.panel.onDidDispose(() => BugPanel.activePanels.delete(bug.iid));
        this.panel.webview.onDidReceiveMessage(msg => this.handleMessage(msg));
    }

    private update(bug: BugIssue) {
        this.bug = bug;
        this.panel.title = `#${bug.iid} — ${bug.title.slice(0, 60)}`;
        this.panel.webview.html = this.render();
    }

    private async handleMessage(msg: { cmd: string; [k: string]: any }) {
        switch (msg.cmd) {
            case 'fix':
                await this.runFix();
                break;
            case 'openInBrowser':
                vscode.env.openExternal(vscode.Uri.parse(this.bug.web_url));
                break;
            case 'openSettings':
                vscode.commands.executeCommand('fixfleet.openSettings');
                break;
        }
    }

    private async runFix() {
        const cfg = vscode.workspace.getConfiguration('fixfleet');
        const token = cfg.get<string>('gitlabToken') || '';
        const projectUrl = cfg.get<string>('projectUrl') || '';
        let projectDir = cfg.get<string>('projectDir') || '';
        const backend = cfg.get<string>('backend') || 'claude';

        if (!projectDir) {
            projectDir = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath || '';
        }
        if (!token || !projectUrl || !projectDir) {
            this.panel.webview.postMessage({
                cmd: 'error',
                message: 'Configure GitLab token, project URL, and project dir in FixFleet settings.',
            });
            return;
        }

        this.panel.webview.postMessage({ cmd: 'fixing', backend });

        await vscode.window.withProgress(
            {
                location: vscode.ProgressLocation.Notification,
                title: `FixFleet — fixing #${this.bug.iid} with ${backend}...`,
                cancellable: false,
            },
            async () => {
                try {
                    const result: FixResult = await fixBug({
                        issueIid: this.bug.iid,
                        backend,
                        token,
                        projectUrl,
                        projectDir,
                    });
                    this.panel.webview.postMessage({ cmd: 'fixDone', result });
                    if (result.success) {
                        vscode.window.showInformationMessage(
                            `FixFleet ✓  #${this.bug.iid} fixed (confidence: ${result.confidence?.label || 'n/a'})`,
                        );
                        vscode.commands.executeCommand('fixfleet.refresh');
                    } else {
                        vscode.window.showWarningMessage(
                            `FixFleet — #${this.bug.iid}: ${result.error || 'fix uncertain (' + result.confidence?.label + ')'}`,
                        );
                    }
                } catch (e) {
                    const msg = (e as Error).message;
                    this.panel.webview.postMessage({ cmd: 'error', message: msg });
                    vscode.window.showErrorMessage(`FixFleet error: ${msg}`);
                }
            },
        );
    }

    private esc(s: string): string {
        return (s || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    private sectionBlock(title: string, content: string, lang: string = ''): string {
        if (!content) return '';
        return `
            <section class="card">
                <header class="card-header">
                    <span class="card-title">${this.esc(title)}</span>
                </header>
                <pre class="card-body ${lang ? 'lang-' + lang : ''}"><code>${this.esc(content)}</code></pre>
            </section>
        `;
    }

    private chip(label: string, type: 'priority' | 'label' = 'label'): string {
        const cls = type === 'priority' ? `chip chip-priority chip-${label.toLowerCase()}` : 'chip chip-label';
        return `<span class="${cls}">${this.esc(label)}</span>`;
    }

    private render(): string {
        const bug = this.bug;
        const priorityLabels = ['High', 'Medium', 'Low'];
        const priority = bug.labels.find(l => priorityLabels.includes(l));
        const otherLabels = bug.labels.filter(l => !priorityLabels.includes(l));

        const styles = `
            :root {
                --ff-primary: #3d5af1;
                --ff-primary-hover: #2d4ad6;
                --ff-gold: #c8a47e;
                --ff-success: #2d6a4f;
                --ff-warning: #b08968;
                --ff-danger: #8b2c3d;
                --ff-radius: 10px;
                --ff-shadow: 0 4px 24px rgba(0, 0, 0, 0.08);
                --ff-glass: rgba(255, 255, 255, 0.04);
                --ff-border: var(--vscode-panel-border, rgba(127, 127, 127, 0.18));
            }

            * { box-sizing: border-box; }

            body {
                font-family: -apple-system, "SF Pro Text", "Inter", system-ui, sans-serif;
                background: var(--vscode-editor-background);
                color: var(--vscode-editor-foreground);
                padding: 0;
                margin: 0;
                line-height: 1.55;
                font-size: 13px;
            }

            .container { max-width: 880px; margin: 0 auto; padding: 28px 32px 48px; }

            header.hero {
                position: relative;
                padding: 24px 28px;
                border-radius: var(--ff-radius);
                margin-bottom: 24px;
                background: linear-gradient(135deg,
                    color-mix(in srgb, var(--ff-primary) 12%, transparent),
                    color-mix(in srgb, var(--ff-gold) 6%, transparent));
                border: 1px solid var(--ff-border);
                overflow: hidden;
            }

            header.hero::before {
                content: '';
                position: absolute;
                top: 0; left: 0; right: 0;
                height: 3px;
                background: linear-gradient(90deg, var(--ff-primary), var(--ff-gold));
            }

            .iid-tag {
                display: inline-block;
                font-family: "SF Mono", "JetBrains Mono", Menlo, monospace;
                font-size: 11px;
                font-weight: 600;
                letter-spacing: 0.5px;
                padding: 3px 10px;
                border-radius: 999px;
                background: color-mix(in srgb, var(--ff-primary) 18%, transparent);
                color: var(--ff-primary);
                margin-bottom: 10px;
            }

            h1.title {
                font-size: 22px;
                font-weight: 600;
                margin: 0 0 14px;
                color: var(--vscode-editor-foreground);
                letter-spacing: -0.2px;
            }

            .meta {
                display: flex;
                flex-wrap: wrap;
                gap: 8px 16px;
                font-size: 12px;
                opacity: 0.78;
            }

            .meta-item { display: inline-flex; align-items: center; gap: 4px; }

            .chips { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 12px; }

            .chip {
                display: inline-flex;
                align-items: center;
                padding: 3px 10px;
                border-radius: 999px;
                font-size: 11px;
                font-weight: 500;
                border: 1px solid var(--ff-border);
                background: var(--ff-glass);
            }

            .chip-priority { font-weight: 600; }
            .chip-high   { background: color-mix(in srgb, var(--ff-danger) 18%, transparent); color: var(--ff-danger); border-color: color-mix(in srgb, var(--ff-danger) 40%, transparent); }
            .chip-medium { background: color-mix(in srgb, var(--ff-warning) 18%, transparent); color: var(--ff-warning); border-color: color-mix(in srgb, var(--ff-warning) 40%, transparent); }
            .chip-low    { background: color-mix(in srgb, var(--ff-success) 18%, transparent); color: var(--ff-success); border-color: color-mix(in srgb, var(--ff-success) 40%, transparent); }

            .actions {
                display: flex;
                gap: 10px;
                margin-top: 18px;
                flex-wrap: wrap;
            }

            button.btn {
                font-family: inherit;
                font-size: 13px;
                font-weight: 600;
                padding: 9px 18px;
                border-radius: 8px;
                border: 1px solid transparent;
                cursor: pointer;
                transition: transform 0.12s ease, box-shadow 0.12s ease, background 0.12s ease;
                letter-spacing: 0.1px;
            }
            button.btn:hover:not(:disabled) { transform: translateY(-1px); }
            button.btn:active:not(:disabled) { transform: translateY(0); }
            button.btn:disabled { opacity: 0.5; cursor: not-allowed; }

            .btn-primary {
                background: linear-gradient(135deg, var(--ff-primary), var(--ff-primary-hover));
                color: white;
                box-shadow: 0 4px 14px color-mix(in srgb, var(--ff-primary) 30%, transparent);
            }
            .btn-primary:hover:not(:disabled) {
                box-shadow: 0 6px 20px color-mix(in srgb, var(--ff-primary) 45%, transparent);
            }

            .btn-secondary {
                background: var(--ff-glass);
                color: var(--vscode-editor-foreground);
                border-color: var(--ff-border);
            }
            .btn-secondary:hover:not(:disabled) {
                background: color-mix(in srgb, var(--ff-primary) 10%, transparent);
                border-color: var(--ff-primary);
            }

            .card {
                background: var(--ff-glass);
                border: 1px solid var(--ff-border);
                border-radius: var(--ff-radius);
                margin-bottom: 16px;
                overflow: hidden;
                transition: border-color 0.18s ease;
            }
            .card:hover { border-color: color-mix(in srgb, var(--ff-primary) 28%, var(--ff-border)); }

            .card-header {
                padding: 12px 18px;
                border-bottom: 1px solid var(--ff-border);
                font-weight: 600;
                font-size: 12px;
                letter-spacing: 0.6px;
                text-transform: uppercase;
                color: var(--ff-gold);
                background: color-mix(in srgb, var(--ff-gold) 6%, transparent);
            }

            .card-body {
                padding: 16px 20px;
                margin: 0;
                font-family: "SF Mono", "JetBrains Mono", Menlo, monospace;
                font-size: 12.5px;
                white-space: pre-wrap;
                word-wrap: break-word;
                line-height: 1.6;
                color: var(--vscode-editor-foreground);
            }
            .card-body code { font: inherit; }

            #status {
                margin-top: 18px;
                padding: 14px 18px;
                border-radius: var(--ff-radius);
                border: 1px solid var(--ff-border);
                background: var(--ff-glass);
                font-size: 13px;
                display: none;
            }
            #status.visible { display: block; }
            #status.fixing { border-color: var(--ff-primary); background: color-mix(in srgb, var(--ff-primary) 8%, transparent); }
            #status.success { border-color: var(--ff-success); background: color-mix(in srgb, var(--ff-success) 8%, transparent); }
            #status.error { border-color: var(--ff-danger); background: color-mix(in srgb, var(--ff-danger) 8%, transparent); }

            .pulse {
                display: inline-block;
                width: 8px;
                height: 8px;
                border-radius: 50%;
                background: var(--ff-primary);
                margin-right: 8px;
                animation: pulse 1.2s ease-in-out infinite;
                vertical-align: middle;
            }
            @keyframes pulse {
                0%, 100% { opacity: 1; transform: scale(1); }
                50% { opacity: 0.5; transform: scale(1.4); }
            }

            .confidence {
                margin-top: 16px;
            }
            .conf-row { display: flex; justify-content: space-between; padding: 6px 0; font-size: 12.5px; }
            .conf-key { opacity: 0.7; }
            .conf-val { font-weight: 500; font-family: "SF Mono", Menlo, monospace; }

            .conf-bar {
                height: 8px;
                border-radius: 4px;
                background: color-mix(in srgb, var(--vscode-editor-foreground) 10%, transparent);
                overflow: hidden;
                margin-top: 6px;
            }
            .conf-bar > div {
                height: 100%;
                border-radius: 4px;
                transition: width 0.5s ease;
            }
            .conf-bar-high { background: linear-gradient(90deg, var(--ff-success), color-mix(in srgb, var(--ff-success) 70%, white)); }
            .conf-bar-med  { background: linear-gradient(90deg, var(--ff-warning), color-mix(in srgb, var(--ff-warning) 70%, white)); }
            .conf-bar-low  { background: linear-gradient(90deg, var(--ff-danger), color-mix(in srgb, var(--ff-danger) 70%, white)); }

            .fixed-badge {
                display: inline-block;
                font-size: 10px;
                font-weight: 700;
                color: var(--ff-success);
                background: color-mix(in srgb, var(--ff-success) 14%, transparent);
                padding: 3px 8px;
                border-radius: 4px;
                margin-left: 8px;
                letter-spacing: 0.5px;
            }

            footer.foot {
                margin-top: 36px;
                padding-top: 18px;
                border-top: 1px solid var(--ff-border);
                font-size: 11px;
                opacity: 0.5;
                text-align: center;
            }
        `;

        const html = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>${styles}</style>
</head>
<body>
<div class="container">
    <header class="hero">
        <div class="iid-tag">ISSUE #${bug.iid}${bug.already_fixed ? '<span class="fixed-badge">FIXED</span>' : ''}</div>
        <h1 class="title">${this.esc(bug.title)}</h1>

        <div class="meta">
            <span class="meta-item">📅 ${this.esc(bug.created_at.slice(0, 10))}</span>
            ${bug.author ? `<span class="meta-item">👤 ${this.esc(bug.author)}</span>` : ''}
        </div>

        <div class="chips">
            ${priority ? this.chip(priority, 'priority') : ''}
            ${otherLabels.map(l => this.chip(l)).join('')}
        </div>

        <div class="actions">
            <button class="btn btn-primary" id="fix-btn">✨ Fix This Bug with AI</button>
            <button class="btn btn-secondary" id="open-gitlab">🔗 Open in GitLab</button>
            <button class="btn btn-secondary" id="open-settings">⚙️ Settings</button>
        </div>
    </header>

    ${this.sectionBlock('Description', bug.sections.description)}
    ${this.sectionBlock('Steps to Reproduce', bug.sections.steps)}
    ${this.sectionBlock('Expected Behavior', bug.sections.expected)}
    ${this.sectionBlock('Actual Behavior', bug.sections.actual)}
    ${this.sectionBlock('Environment', bug.sections.environment)}
    ${this.sectionBlock('Logs / Stack Trace', bug.sections.logs)}
    ${this.sectionBlock('Notes', bug.sections.notes)}

    <div id="status"></div>

    <footer class="foot">
        🚀 FixFleet — Fleet of AI agents fixing GitLab bugs
    </footer>
</div>

<script>
    const vscode = acquireVsCodeApi();
    const fixBtn = document.getElementById('fix-btn');
    const status = document.getElementById('status');

    document.getElementById('fix-btn').addEventListener('click', () => {
        fixBtn.disabled = true;
        vscode.postMessage({ cmd: 'fix' });
    });
    document.getElementById('open-gitlab').addEventListener('click', () => {
        vscode.postMessage({ cmd: 'openInBrowser' });
    });
    document.getElementById('open-settings').addEventListener('click', () => {
        vscode.postMessage({ cmd: 'openSettings' });
    });

    function setStatus(html, cls) {
        status.innerHTML = html;
        status.className = 'visible ' + (cls || '');
    }

    function renderConfidence(c) {
        const pct = Math.round(c.final_score * 100);
        const bar = c.final_score >= 0.7 ? 'conf-bar-high'
                  : c.final_score >= 0.45 ? 'conf-bar-med'
                  : 'conf-bar-low';
        return \`
            <div class="confidence">
                <div style="display:flex;justify-content:space-between;align-items:center;">
                    <strong>Confidence:</strong>
                    <span style="font-weight:600;">\${c.label} — \${pct}%</span>
                </div>
                <div class="conf-bar"><div class="\${bar}" style="width:\${pct}%"></div></div>
                <div class="conf-row"><span class="conf-key">Root cause</span><span class="conf-val">\${(c.root_cause || '—').slice(0, 80)}</span></div>
                <div class="conf-row"><span class="conf-key">Self-rating</span><span class="conf-val">\${c.self_rating}/10</span></div>
                <div class="conf-row"><span class="conf-key">Diff focus</span><span class="conf-val">\${c.diff_focus.toFixed(2)}</span></div>
                <div class="conf-row"><span class="conf-key">File relevance</span><span class="conf-val">\${c.file_relevance.toFixed(2)}</span></div>
                <div class="conf-row"><span class="conf-key">Files changed</span><span class="conf-val">\${c.files_changed.length} (\${c.lines_changed} lines)</span></div>
                <div class="conf-row"><span class="conf-key">Tests run</span><span class="conf-val">\${c.tests_run}</span></div>
            </div>
        \`;
    }

    window.addEventListener('message', event => {
        const m = event.data;
        if (m.cmd === 'fixing') {
            setStatus(\`<span class="pulse"></span> <strong>Fixing with \${m.backend}...</strong>  AI agent is reading code, finding the bug, and applying the fix. This may take 30s–5min.\`, 'fixing');
        } else if (m.cmd === 'fixDone') {
            fixBtn.disabled = false;
            const r = m.result;
            if (r.success) {
                setStatus('<strong>✓ Fix applied</strong>' + renderConfidence(r.confidence), 'success');
            } else {
                setStatus(\`<strong>⚠ Fix uncertain</strong> — \${r.error || 'review confidence below'}\` + (r.confidence ? renderConfidence(r.confidence) : ''), 'error');
            }
        } else if (m.cmd === 'error') {
            fixBtn.disabled = false;
            setStatus('<strong>✗ Error:</strong> ' + m.message, 'error');
        }
    });
</script>
</body>
</html>`;
        return html;
    }
}
