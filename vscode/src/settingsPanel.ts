/**
 * Settings webview — premium UI for configuring token, project, backend.
 */
import * as vscode from 'vscode';
import { BackendInfo, listBackends } from './fixfleetCli';

export class SettingsPanel {
    private static current: SettingsPanel | undefined;

    public static createOrShow(context: vscode.ExtensionContext) {
        if (SettingsPanel.current) {
            SettingsPanel.current.panel.reveal();
            return;
        }
        const panel = vscode.window.createWebviewPanel(
            'fixfleetSettings',
            '⚙️ FixFleet Settings',
            vscode.ViewColumn.One,
            { enableScripts: true, retainContextWhenHidden: true },
        );
        SettingsPanel.current = new SettingsPanel(context, panel);
    }

    private constructor(
        private readonly context: vscode.ExtensionContext,
        private readonly panel: vscode.WebviewPanel,
    ) {
        this.render();
        panel.onDidDispose(() => (SettingsPanel.current = undefined));
        panel.webview.onDidReceiveMessage(msg => this.handleMessage(msg));
    }

    private async handleMessage(msg: { cmd: string; [k: string]: any }) {
        const cfg = vscode.workspace.getConfiguration('fixfleet');

        switch (msg.cmd) {
            case 'init':
                await this.sendInitData();
                break;

            case 'save':
                await cfg.update('provider', msg.provider || 'gitlab', vscode.ConfigurationTarget.Global);
                await cfg.update('gitlabToken', msg.gitlabToken || '', vscode.ConfigurationTarget.Global);
                await cfg.update('projectUrl', msg.projectUrl || '', vscode.ConfigurationTarget.Global);
                await cfg.update('projectDir', msg.projectDir || '', vscode.ConfigurationTarget.Global);
                await cfg.update('backend', msg.backend || 'claude', vscode.ConfigurationTarget.Global);
                await cfg.update('dateFilter', msg.dateFilter || '', vscode.ConfigurationTarget.Global);
                vscode.window.showInformationMessage('FixFleet settings saved ✓');
                vscode.commands.executeCommand('fixfleet.refresh');
                this.panel.webview.postMessage({ cmd: 'saved' });
                break;

            case 'pickDir': {
                const picked = await vscode.window.showOpenDialog({
                    canSelectFiles: false,
                    canSelectFolders: true,
                    canSelectMany: false,
                    openLabel: 'Select Project Folder',
                });
                if (picked && picked[0]) {
                    this.panel.webview.postMessage({ cmd: 'dirPicked', path: picked[0].fsPath });
                }
                break;
            }

            case 'useWorkspaceDir': {
                const ws = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
                if (ws) this.panel.webview.postMessage({ cmd: 'dirPicked', path: ws });
                break;
            }

            case 'installCli':
                vscode.commands.executeCommand('fixfleet.installCli');
                break;
        }
    }

    private async sendInitData() {
        const cfg = vscode.workspace.getConfiguration('fixfleet');
        let backends: BackendInfo[] = [];
        try {
            const result = await listBackends();
            backends = result.cli_backends || [];
            // Providers come back inside listBackends() too in v0.4.2+
            const providers = (result as any).providers || [];
            (this as any)._providersCache = providers;
        } catch (e) {
            this.panel.webview.postMessage({
                cmd: 'cliMissing',
                message: (e as Error).message,
            });
            return;
        }

        this.panel.webview.postMessage({
            cmd: 'data',
            settings: {
                provider: cfg.get<string>('provider') || 'gitlab',
                gitlabToken: cfg.get<string>('gitlabToken') || '',
                projectUrl: cfg.get<string>('projectUrl') || '',
                projectDir: cfg.get<string>('projectDir') || '',
                backend: cfg.get<string>('backend') || 'claude',
                dateFilter: cfg.get<string>('dateFilter') || '',
            },
            backends,
            providers: (this as any)._providersCache || [],
            workspaceDir: vscode.workspace.workspaceFolders?.[0]?.uri.fsPath || '',
        });
    }

    private render() {
        const styles = `
            :root {
                --ff-primary: #3d5af1;
                --ff-primary-hover: #2d4ad6;
                --ff-gold: #c8a47e;
                --ff-success: #2d6a4f;
                --ff-danger: #8b2c3d;
                --ff-radius: 12px;
                --ff-glass: rgba(255, 255, 255, 0.04);
                --ff-border: var(--vscode-panel-border, rgba(127, 127, 127, 0.18));
            }
            * { box-sizing: border-box; }
            body {
                font-family: -apple-system, "SF Pro Text", "Inter", system-ui, sans-serif;
                background: var(--vscode-editor-background);
                color: var(--vscode-editor-foreground);
                margin: 0;
                padding: 0;
                font-size: 13px;
                line-height: 1.55;
            }
            .wrap { max-width: 680px; margin: 0 auto; padding: 36px 32px 56px; }

            .brand {
                font-size: 26px;
                font-weight: 700;
                background: linear-gradient(135deg, var(--ff-primary), var(--ff-gold));
                -webkit-background-clip: text;
                background-clip: text;
                color: transparent;
                margin: 0 0 4px;
                letter-spacing: -0.5px;
            }
            .tagline { opacity: 0.6; font-size: 13px; margin-bottom: 32px; }

            .card {
                background: var(--ff-glass);
                border: 1px solid var(--ff-border);
                border-radius: var(--ff-radius);
                padding: 22px 24px;
                margin-bottom: 18px;
                transition: border-color 0.2s ease;
            }
            .card:focus-within {
                border-color: color-mix(in srgb, var(--ff-primary) 50%, var(--ff-border));
            }

            .card-title {
                font-size: 11px;
                text-transform: uppercase;
                letter-spacing: 0.8px;
                font-weight: 700;
                color: var(--ff-gold);
                margin-bottom: 14px;
            }

            label {
                display: block;
                font-size: 13px;
                font-weight: 500;
                margin-bottom: 6px;
            }
            label .hint {
                display: block;
                font-weight: 400;
                opacity: 0.6;
                font-size: 12px;
                margin-bottom: 8px;
            }

            input[type="text"], input[type="password"], select {
                width: 100%;
                font-family: inherit;
                font-size: 13px;
                padding: 9px 12px;
                background: var(--vscode-input-background);
                color: var(--vscode-input-foreground);
                border: 1px solid var(--vscode-input-border, var(--ff-border));
                border-radius: 8px;
                outline: none;
                transition: border-color 0.15s ease, box-shadow 0.15s ease;
            }
            input:focus, select:focus {
                border-color: var(--ff-primary);
                box-shadow: 0 0 0 3px color-mix(in srgb, var(--ff-primary) 18%, transparent);
            }

            .row { display: flex; gap: 10px; align-items: stretch; }
            .row > input { flex: 1; }
            .row button { white-space: nowrap; }

            button.btn {
                font-family: inherit;
                font-size: 13px;
                font-weight: 600;
                padding: 9px 18px;
                border-radius: 8px;
                border: 1px solid transparent;
                cursor: pointer;
                transition: transform 0.12s ease, box-shadow 0.12s ease;
            }
            button.btn:hover:not(:disabled) { transform: translateY(-1px); }

            .btn-primary {
                background: linear-gradient(135deg, var(--ff-primary), var(--ff-primary-hover));
                color: white;
                box-shadow: 0 4px 14px color-mix(in srgb, var(--ff-primary) 30%, transparent);
            }
            .btn-secondary {
                background: var(--ff-glass);
                color: var(--vscode-editor-foreground);
                border-color: var(--ff-border);
            }
            .btn-secondary:hover:not(:disabled) {
                background: color-mix(in srgb, var(--ff-primary) 8%, transparent);
                border-color: var(--ff-primary);
            }

            .backend-grid {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 8px;
                margin-top: 10px;
            }
            .backend-card {
                padding: 12px 14px;
                border: 1px solid var(--ff-border);
                border-radius: 8px;
                cursor: pointer;
                transition: all 0.18s ease;
                background: var(--ff-glass);
                font-size: 12.5px;
                position: relative;
            }
            .backend-card:hover {
                border-color: var(--ff-primary);
                transform: translateY(-1px);
            }
            .backend-card.selected {
                border-color: var(--ff-primary);
                background: color-mix(in srgb, var(--ff-primary) 14%, transparent);
                box-shadow: 0 0 0 1px var(--ff-primary);
            }
            .backend-card.unavailable {
                opacity: 0.45;
                cursor: not-allowed;
            }
            .backend-name { font-weight: 600; }
            .backend-meta { font-size: 11px; opacity: 0.65; margin-top: 2px; }
            .backend-badge {
                position: absolute; top: 8px; right: 10px;
                font-size: 9px; font-weight: 700;
                padding: 2px 6px; border-radius: 3px;
                letter-spacing: 0.5px;
            }
            .badge-installed { background: var(--ff-success); color: white; }
            .badge-missing { background: color-mix(in srgb, var(--ff-danger) 80%, transparent); color: white; }

            .save-bar {
                position: sticky;
                bottom: 0;
                margin: 24px -32px -56px;
                padding: 18px 32px;
                background: color-mix(in srgb, var(--vscode-editor-background) 95%, transparent);
                border-top: 1px solid var(--ff-border);
                backdrop-filter: blur(8px);
                display: flex;
                justify-content: flex-end;
                gap: 10px;
            }

            #install-warning {
                display: none;
                background: color-mix(in srgb, var(--ff-danger) 14%, transparent);
                border: 1px solid var(--ff-danger);
                border-radius: var(--ff-radius);
                padding: 16px 20px;
                margin-bottom: 20px;
            }
            #install-warning.visible { display: block; }

            .help-link {
                color: var(--ff-primary);
                text-decoration: none;
                font-size: 11px;
            }
            .help-link:hover { text-decoration: underline; }

            .save-toast {
                position: fixed;
                top: 24px;
                right: 24px;
                background: var(--ff-success);
                color: white;
                padding: 12px 20px;
                border-radius: 8px;
                font-weight: 600;
                opacity: 0;
                transform: translateY(-10px);
                transition: opacity 0.2s ease, transform 0.2s ease;
                box-shadow: 0 8px 24px rgba(0, 0, 0, 0.2);
                pointer-events: none;
            }
            .save-toast.visible {
                opacity: 1;
                transform: translateY(0);
            }
        `;

        const html = `<!DOCTYPE html>
<html><head>
<meta charset="UTF-8">
<style>${styles}</style>
</head><body>
<div class="wrap">
    <h1 class="brand">🚀 FixFleet</h1>
    <div class="tagline">Premium settings — Fleet of AI agents fixing bugs across any tracker.</div>

    <div id="install-warning">
        <strong>⚠ FixFleet CLI not installed.</strong>
        <p>The VSCode extension is a UI on top of the <code>fixfleet</code> Python CLI. Install it first:</p>
        <pre>pip3 install --user fixfleet</pre>
        <button class="btn btn-primary" onclick="vscode.postMessage({cmd:'installCli'})">Install Now</button>
        <a class="help-link" href="https://github.com/Yash-Koladiya30/fixfleet" target="_blank" style="margin-left:12px;">Install guide →</a>
    </div>

    <section class="card">
        <div class="card-title">🔌 Issue Tracker Provider</div>
        <label>Where do your bugs live?
            <span class="hint">Pick your platform. FixFleet supports 6 trackers — URL is auto-detected.</span>
        </label>
        <div id="provider-grid" class="backend-grid"></div>
        <input type="hidden" id="provider" value="gitlab">
    </section>

    <section class="card">
        <div class="card-title">🔑 Access Token</div>
        <label id="token-label">Personal Access Token
            <span class="hint" id="token-hint">Scope: <code>api</code> or <code>read_api</code>. Get one at <a class="help-link" id="token-link" href="https://gitlab.com/-/user_settings/personal_access_tokens" target="_blank">gitlab.com → Access Tokens</a></span>
        </label>
        <input type="password" id="gitlabToken" placeholder="glpat-xxxxxxxxxxxxxxxxxxxx">
    </section>

    <section class="card">
        <div class="card-title">📦 Project</div>
        <label>Project / Repository URL
            <span class="hint">Paste the full URL from your browser — provider + host + path auto-detected.</span>
        </label>
        <input type="text" id="projectUrl" placeholder="https://github.com/owner/repo  ·  https://gitlab.com/group/project  ·  ...">

        <label style="margin-top:18px;">Local Project Directory
            <span class="hint">Where the AI will edit files. Should be the cloned repo on your Mac.</span>
        </label>
        <div class="row">
            <input type="text" id="projectDir" placeholder="/Users/you/work/project">
            <button class="btn btn-secondary" onclick="vscode.postMessage({cmd:'pickDir'})">Browse…</button>
            <button class="btn btn-secondary" onclick="vscode.postMessage({cmd:'useWorkspaceDir'})">Use Workspace</button>
        </div>
    </section>

    <section class="card">
        <div class="card-title">🤖 AI Backend</div>
        <label>Choose your AI agent
            <span class="hint">Installed = ready to use. Missing = install the CLI separately.</span>
        </label>
        <div id="backend-grid" class="backend-grid"></div>
        <input type="hidden" id="backend">
    </section>

    <section class="card">
        <div class="card-title">📅 Filter (optional)</div>
        <label>Date filter
            <span class="hint">Only show bugs created on this date (YYYY-MM-DD). Leave blank for all.</span>
        </label>
        <input type="text" id="dateFilter" placeholder="2026-04-30">
    </section>

    <div class="save-bar">
        <button class="btn btn-secondary" onclick="window.close ? window.close() : null">Cancel</button>
        <button class="btn btn-primary" id="save-btn">Save Settings</button>
    </div>
</div>

<div class="save-toast" id="toast">Settings saved ✓</div>

<script>
const vscode = acquireVsCodeApi();
const fields = ['provider','gitlabToken','projectUrl','projectDir','backend','dateFilter'];
let backends = [];
let providers = [];

function selectProvider(key) {
    document.getElementById('provider').value = key;
    document.querySelectorAll('#provider-grid .backend-card').forEach(el => {
        el.classList.toggle('selected', el.dataset.providerKey === key);
    });
    // Update token hint based on selected provider.
    // NOTE: do NOT getElementById('token-link') here — it lives inside
    // token-hint and is destroyed by the first innerHTML replacement.
    const p = providers.find(x => x.key === key);
    if (p) {
        document.getElementById('token-hint').innerHTML =
            'Format: <code>' + (p.token_scope_hint || 'see docs') + '</code>. ' +
            (p.token_url ? '<a class="help-link" href="' + p.token_url + '" target="_blank">Generate token →</a>' : '');
        const tokenInput = document.getElementById('gitlabToken');
        if (tokenInput) {
            const placeholders = {
                gitlab: 'glpat-xxxxxxxxxxxxxxxxxxxx',
                github: 'ghp_xxxxxxxxxxxxxxxxxxxx',
                bitbucket: 'username:app-password',
                jira: 'email@example.com:api-token',
                linear: 'lin_api_xxxxxxxxxxxxxxxxxxxx',
                azure: 'azure-devops-pat',
            };
            tokenInput.placeholder = placeholders[key] || 'access token';
        }
    }
}

function renderProviders(list, current) {
    const grid = document.getElementById('provider-grid');
    grid.innerHTML = '';
    (list || []).forEach(p => {
        const card = document.createElement('div');
        const available = p.implemented;
        card.className = 'backend-card' + (available ? '' : ' unavailable') + (p.key === current ? ' selected' : '');
        card.dataset.providerKey = p.key;
        card.innerHTML =
            '<div class="backend-name">' + p.display_name + '</div>' +
            '<div class="backend-meta">' + (p.tagline || '') + '</div>' +
            '<span class="backend-badge ' + (available ? 'badge-installed' : 'badge-missing') + '">' +
            (available ? 'AVAILABLE' : 'COMING SOON') + '</span>';
        if (available) card.onclick = () => selectProvider(p.key);
        grid.appendChild(card);
    });
}

function selectBackend(name) {
    document.getElementById('backend').value = name;
    // Scoped to #backend-grid — unscoped selector would also wipe the
    // provider grid's selection (both use .backend-card).
    document.querySelectorAll('#backend-grid .backend-card').forEach(el => {
        el.classList.toggle('selected', el.dataset.name === name);
    });
}

function renderBackends(list, current) {
    const grid = document.getElementById('backend-grid');
    grid.innerHTML = '';
    list.forEach(b => {
        const card = document.createElement('div');
        const installed = b.installed === true;
        card.className = 'backend-card' + (installed ? '' : ' unavailable') + (b.name === current ? ' selected' : '');
        card.dataset.name = b.name;
        card.innerHTML = \`
            <div class="backend-name">\${b.display_name}</div>
            <div class="backend-meta">\${b.version || 'binary: ' + b.binary}</div>
            <span class="backend-badge \${installed ? 'badge-installed' : 'badge-missing'}">
                \${installed ? 'INSTALLED' : 'NOT INSTALLED'}
            </span>
        \`;
        if (installed) card.onclick = () => selectBackend(b.name);
        grid.appendChild(card);
    });
    // Always add API option
    const apiCard = document.createElement('div');
    apiCard.className = 'backend-card' + (current === 'openai_compat' ? ' selected' : '');
    apiCard.dataset.name = 'openai_compat';
    apiCard.innerHTML = \`
        <div class="backend-name">🌐 OpenAI-Compatible API</div>
        <div class="backend-meta">Groq / Gemini / OpenRouter / Ollama — configure via terminal first</div>
        <span class="backend-badge badge-installed">AVAILABLE</span>
    \`;
    apiCard.onclick = () => selectBackend('openai_compat');
    grid.appendChild(apiCard);
}

window.addEventListener('message', event => {
    const m = event.data;
    if (m.cmd === 'data') {
        fields.forEach(f => {
            const el = document.getElementById(f);
            if (el && m.settings[f] !== undefined) el.value = m.settings[f];
        });
        backends = m.backends;
        providers = m.providers || [];
        renderBackends(backends, m.settings.backend);
        renderProviders(providers, m.settings.provider || 'gitlab');
        selectProvider(m.settings.provider || 'gitlab');
    } else if (m.cmd === 'cliMissing') {
        document.getElementById('install-warning').classList.add('visible');
    } else if (m.cmd === 'dirPicked') {
        document.getElementById('projectDir').value = m.path;
    } else if (m.cmd === 'saved') {
        const t = document.getElementById('toast');
        t.classList.add('visible');
        setTimeout(() => t.classList.remove('visible'), 1800);
    }
});

document.getElementById('save-btn').addEventListener('click', () => {
    const payload = { cmd: 'save' };
    fields.forEach(f => {
        payload[f] = document.getElementById(f).value;
    });
    vscode.postMessage(payload);
});

vscode.postMessage({ cmd: 'init' });
</script>
</body></html>`;

        this.panel.webview.html = html;
    }
}
