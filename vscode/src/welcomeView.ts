/**
 * Premium WebView for the FixFleet sidebar.
 * Handles 4 states: not-configured / loading / empty-bugs / has-bugs.
 * Color palette derived from extension icon: forest green + cream + walnut + sage.
 */
import * as vscode from 'vscode';
import { BugIssue, FixFleetError, listBugs } from './fixfleetCli';
import { BugPanel } from './bugPanel';

type ViewState =
    | 'not-configured'
    | 'loading'
    | 'empty'
    | 'has-bugs'
    | 'error-auth'
    | 'error-notfound'
    | 'error-network'
    | 'error-cli-missing'
    | 'error-generic';

export class FixFleetWebView implements vscode.WebviewViewProvider {
    public static readonly viewType = 'fixfleet.bugs';

    private view?: vscode.WebviewView;
    private bugs: BugIssue[] = [];
    private currentState: ViewState = 'loading';
    private errorMsg = '';

    constructor(private readonly context: vscode.ExtensionContext) {}

    resolveWebviewView(view: vscode.WebviewView) {
        this.view = view;
        view.webview.options = {
            enableScripts: true,
            localResourceRoots: [vscode.Uri.joinPath(this.context.extensionUri, 'media')],
        };
        view.webview.onDidReceiveMessage(msg => this.handleMessage(msg));
        this.refresh();
    }

    private logoUri(): string {
        if (!this.view) return '';
        return this.view.webview
            .asWebviewUri(vscode.Uri.joinPath(this.context.extensionUri, 'media', 'icon.png'))
            .toString();
    }

    private async handleMessage(msg: { cmd: string; [k: string]: any }) {
        switch (msg.cmd) {
            case 'configure':
                vscode.commands.executeCommand('fixfleet.openSettings');
                break;
            case 'refresh':
                this.refresh();
                break;
            case 'openBug':
                const bug = this.bugs.find(b => b.iid === msg.iid);
                if (bug) BugPanel.createOrShow(this.context, bug);
                break;
            case 'openInBrowser':
                const target = this.bugs.find(b => b.iid === msg.iid);
                if (target?.web_url) vscode.env.openExternal(vscode.Uri.parse(target.web_url));
                break;
            case 'install':
                vscode.commands.executeCommand('fixfleet.installCli');
                break;
            case 'openTokenPage':
                vscode.env.openExternal(
                    vscode.Uri.parse('https://gitlab.com/-/user_settings/personal_access_tokens'),
                );
                break;
            case 'ready':
                this.refresh();
                break;
        }
    }

    private refreshSeq = 0;

    public async refresh() {
        if (!this.view) return;

        const cfg = vscode.workspace.getConfiguration('fixfleet');
        const token = cfg.get<string>('gitlabToken') || '';
        const projectUrl = cfg.get<string>('projectUrl') || '';
        const date = cfg.get<string>('dateFilter') || '';

        if (!token || !projectUrl) {
            this.currentState = 'not-configured';
            this.render();
            return;
        }

        const mySeq = ++this.refreshSeq;
        this.currentState = 'loading';
        this.render();

        // Hard watchdog: if listBugs hasn't resolved in 50s, force-error.
        const watchdog = setTimeout(() => {
            if (this.refreshSeq !== mySeq) return;
            this.currentState = 'error-generic';
            this.errorMsg =
                'Request took too long. Check the FixFleet CLI is installed and your network can reach GitLab.';
            this.render();
        }, 25_000);

        try {
            const result = await listBugs({ token, projectUrl, date: date || undefined });
            if (this.refreshSeq !== mySeq) return; // stale
            this.bugs = result.issues || [];
            this.currentState = this.bugs.length > 0 ? 'has-bugs' : 'empty';
            this.errorMsg = '';
        } catch (e) {
            if (this.refreshSeq !== mySeq) return; // stale
            this.bugs = [];
            if (e instanceof FixFleetError) {
                this.errorMsg = e.message;
                if (e.isAuthError) this.currentState = 'error-auth';
                else if (e.isNotFoundError) this.currentState = 'error-notfound';
                else if (e.isNetworkError) this.currentState = 'error-network';
                else if (e.isCliMissing) this.currentState = 'error-cli-missing';
                else this.currentState = 'error-generic';
            } else {
                this.errorMsg = (e as Error).message || 'Unknown error';
                this.currentState = 'error-generic';
            }
        } finally {
            clearTimeout(watchdog);
        }
        this.render();
    }

    public getBugs() {
        return this.bugs;
    }

    private render() {
        if (!this.view) return;
        this.view.webview.html = this.html();
    }

    private html(): string {
        return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src ${this.view!.webview.cspSource} https:; style-src 'unsafe-inline'; script-src 'unsafe-inline';">
<style>${STYLES}</style>
</head>
<body>
<div class="root">
    ${this.renderBody()}
</div>
<script>
const vscode = acquireVsCodeApi();
function send(cmd, extra) { vscode.postMessage({cmd, ...(extra||{})}); }
window.addEventListener('DOMContentLoaded', () => { send('ready'); });
</script>
</body>
</html>`;
    }

    private renderBody(): string {
        const logo = this.logoUri();
        const header = `
            <header class="hero">
                <img src="${logo}" class="logo" alt="FixFleet" />
                <h1 class="brand">FixFleet</h1>
                <div class="tagline">Fleet of AI agents fixing bugs</div>
            </header>
        `;

        switch (this.currentState) {
            case 'not-configured':
                return header + this.renderNotConfigured();
            case 'loading':
                return header + this.renderLoading();
            case 'empty':
                return header + this.renderEmpty();
            case 'has-bugs':
                return header + this.renderBugs();
            case 'error-auth':
                return header + this.renderErrorAuth();
            case 'error-notfound':
                return header + this.renderErrorNotFound();
            case 'error-network':
                return header + this.renderErrorNetwork();
            case 'error-cli-missing':
                return header + this.renderErrorCliMissing();
            case 'error-generic':
                return header + this.renderErrorGeneric();
        }
    }

    private renderNotConfigured(): string {
        return `
            <div class="onboard">
                <div class="step">
                    <div class="step-num">1</div>
                    <div class="step-body">
                        <div class="step-title">Connect your GitLab</div>
                        <div class="step-text">Paste your token + project URL to start.</div>
                    </div>
                </div>
                <div class="step">
                    <div class="step-num">2</div>
                    <div class="step-body">
                        <div class="step-title">Pick an AI agent</div>
                        <div class="step-text">Claude, Codex, Gemini, Cursor, Aider — bring your own.</div>
                    </div>
                </div>
                <div class="step">
                    <div class="step-num">3</div>
                    <div class="step-body">
                        <div class="step-title">Click any bug → Fix</div>
                        <div class="step-text">AI reads code, fixes locally, scores confidence.</div>
                    </div>
                </div>

                <button class="btn btn-primary btn-block" onclick="send('configure')">
                    ⚙ &nbsp;Configure FixFleet
                </button>

                <div class="muted">Configuration takes 30 seconds.</div>
            </div>
        `;
    }

    private renderLoading(): string {
        return `
            <div class="state-card">
                <div class="loader"></div>
                <div class="state-title">Fetching bugs from GitLab…</div>
                <div class="muted">Pre-narrowing search space for faster fixes.</div>
            </div>
        `;
    }

    private renderEmpty(): string {
        return `
            <div class="state-card">
                <div class="big-emoji">✨</div>
                <div class="state-title">Inbox zero</div>
                <div class="muted">No open <code>Bug</code>-labeled issues. Enjoy the breather.</div>
                <button class="btn btn-secondary" onclick="send('refresh')">
                    ⟳ &nbsp;Refresh
                </button>
                <button class="btn btn-ghost" onclick="send('configure')">
                    ⚙ &nbsp;Settings
                </button>
            </div>
        `;
    }

    private renderErrorAuth(): string {
        return `
            <div class="state-card error-card">
                <div class="big-emoji">🔐</div>
                <div class="state-title">GitLab token rejected</div>
                <div class="error-msg">${this.escape(this.errorMsg)}</div>
                <div class="muted">Your token is invalid, expired, or lacks the required scope.</div>
                <button class="btn btn-primary btn-block" onclick="send('openTokenPage')">
                    🔑 &nbsp;Generate New Token
                </button>
                <button class="btn btn-secondary btn-block" onclick="send('configure')">
                    ⚙ &nbsp;Update Token in Settings
                </button>
                <button class="btn btn-ghost" onclick="send('refresh')">Retry</button>
            </div>
        `;
    }

    private renderErrorNotFound(): string {
        return `
            <div class="state-card error-card">
                <div class="big-emoji">📭</div>
                <div class="state-title">Project not found</div>
                <div class="error-msg">${this.escape(this.errorMsg)}</div>
                <div class="muted">URL may be wrong, or your token doesn't have access to this project.</div>
                <button class="btn btn-primary btn-block" onclick="send('configure')">
                    ⚙ &nbsp;Fix Project URL
                </button>
                <button class="btn btn-ghost" onclick="send('refresh')">Retry</button>
            </div>
        `;
    }

    private renderErrorNetwork(): string {
        return `
            <div class="state-card error-card">
                <div class="big-emoji">🌐</div>
                <div class="state-title">Can't reach GitLab</div>
                <div class="error-msg">${this.escape(this.errorMsg)}</div>
                <div class="muted">Check your internet connection. If using self-hosted GitLab, verify the host is reachable.</div>
                <button class="btn btn-primary btn-block" onclick="send('refresh')">Try again</button>
                <button class="btn btn-ghost" onclick="send('configure')">Open Settings</button>
            </div>
        `;
    }

    private renderErrorCliMissing(): string {
        return `
            <div class="state-card error-card">
                <div class="big-emoji">📦</div>
                <div class="state-title">FixFleet CLI not installed</div>
                <div class="muted">The VSCode extension needs the FixFleet Python CLI installed on your machine.</div>
                <button class="btn btn-primary btn-block" onclick="send('install')">
                    📥 &nbsp;Install FixFleet CLI
                </button>
                <button class="btn btn-ghost" onclick="send('refresh')">Already installed? Retry</button>
            </div>
        `;
    }

    private renderErrorGeneric(): string {
        return `
            <div class="state-card error-card">
                <div class="big-emoji">⚠</div>
                <div class="state-title">Couldn't fetch bugs</div>
                <div class="error-msg">${this.escape(this.errorMsg).slice(0, 300)}</div>
                <button class="btn btn-secondary btn-block" onclick="send('refresh')">Try again</button>
                <button class="btn btn-ghost" onclick="send('configure')">Open Settings</button>
            </div>
        `;
    }

    private renderBugs(): string {
        const priorityRank: Record<string, number> = { High: 0, Medium: 1, Low: 2 };
        const sorted = [...this.bugs].sort((a, b) => {
            const pa = a.labels.find(l => l in priorityRank);
            const pb = b.labels.find(l => l in priorityRank);
            const ra = pa ? priorityRank[pa] : 99;
            const rb = pb ? priorityRank[pb] : 99;
            if (ra !== rb) return ra - rb;
            return (b.created_at || '').localeCompare(a.created_at || '');
        });

        const counts = {
            high: this.bugs.filter(b => b.labels.includes('High')).length,
            med: this.bugs.filter(b => b.labels.includes('Medium')).length,
            low: this.bugs.filter(b => b.labels.includes('Low')).length,
            total: this.bugs.length,
        };

        const summary = `
            <div class="summary">
                <div class="summary-pill total">${counts.total} <span class="pill-label">open</span></div>
                ${counts.high ? `<div class="summary-pill high">${counts.high} High</div>` : ''}
                ${counts.med ? `<div class="summary-pill med">${counts.med} Medium</div>` : ''}
                ${counts.low ? `<div class="summary-pill low">${counts.low} Low</div>` : ''}
            </div>
            <div class="toolbar">
                <button class="icon-btn" onclick="send('refresh')" title="Refresh">⟳</button>
                <button class="icon-btn" onclick="send('configure')" title="Settings">⚙</button>
            </div>
        `;

        const list = sorted
            .map(b => {
                const priority = b.labels.find(l => l in priorityRank) || '';
                const pCls = priority.toLowerCase();
                const fixed = b.already_fixed ? `<span class="badge-fixed">FIXED</span>` : '';
                const date = (b.created_at || '').slice(0, 10);
                return `
                    <div class="bug-card ${b.already_fixed ? 'is-fixed' : ''}" onclick="send('openBug', {iid: ${b.iid}})">
                        <div class="bug-row">
                            <div class="bug-iid">#${b.iid}</div>
                            ${priority ? `<div class="priority-dot dot-${pCls}" title="${priority}"></div>` : ''}
                            ${fixed}
                        </div>
                        <div class="bug-title">${this.escape(b.title)}</div>
                        <div class="bug-meta">
                            <span>📅 ${date}</span>
                            ${b.author ? `<span>👤 ${this.escape(b.author)}</span>` : ''}
                        </div>
                        ${
                            b.labels.filter(l => !(l in priorityRank) && l !== 'Bug').length
                                ? `<div class="bug-labels">${b.labels
                                      .filter(l => !(l in priorityRank) && l !== 'Bug')
                                      .slice(0, 3)
                                      .map(l => `<span class="bug-label">${this.escape(l)}</span>`)
                                      .join('')}</div>`
                                : ''
                        }
                    </div>
                `;
            })
            .join('');

        return `
            ${summary}
            <div class="bug-list">${list}</div>
        `;
    }

    private escape(s: string): string {
        return (s || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }
}


// ── Styles ─────────────────────────────────────────────────────
// Palette extracted from the FixFleet icon:
//   Forest green  #2D4A3E  (primary bg accent)
//   Deep forest   #1F3329  (deeper layer)
//   Cream ivory   #F0E6D2  (FF letters in icon)
//   Walnut brown  #5C3A1E  (rocket in icon)
//   Sage          #8AA88A  (soft accent)
//   Champagne     #D4C19C  (subtle highlights)
//   Burgundy      #722F37  (priority high — warm)
//   Amber         #B08968  (priority medium)

const STYLES = `
    :root {
        --ff-forest:        #2D4A3E;
        --ff-forest-deep:   #1F3329;
        --ff-cream:         #F0E6D2;
        --ff-cream-soft:    #E8DCC0;
        --ff-walnut:        #5C3A1E;
        --ff-walnut-light:  #8B6F47;
        --ff-sage:          #8AA88A;
        --ff-champagne:     #D4C19C;
        --ff-burgundy:      #B14F58;
        --ff-amber:         #D4A574;
        --ff-emerald:       #5C9472;

        --ff-radius: 10px;
        --ff-radius-sm: 6px;
        --ff-border: rgba(240, 230, 210, 0.10);
        --ff-border-strong: rgba(240, 230, 210, 0.18);
        --ff-shadow: 0 4px 16px rgba(0, 0, 0, 0.25);
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }

    body, html {
        font-family: -apple-system, "SF Pro Text", "Inter", system-ui, sans-serif;
        background: linear-gradient(180deg, var(--ff-forest-deep) 0%, #16241D 100%);
        color: var(--ff-cream);
        font-size: 13px;
        line-height: 1.5;
        overflow-x: hidden;
        min-height: 100vh;
    }

    .root {
        padding: 18px 14px 24px;
        min-height: 100vh;
    }

    /* ── Hero / Branding ──────────────────────────────────── */

    .hero {
        text-align: center;
        padding: 8px 0 22px;
        position: relative;
    }
    .hero::after {
        content: '';
        position: absolute;
        left: 50%; bottom: 8px;
        transform: translateX(-50%);
        width: 36px; height: 1px;
        background: linear-gradient(90deg, transparent, var(--ff-champagne), transparent);
    }

    .logo {
        width: 64px; height: 64px;
        border-radius: 16px;
        box-shadow:
            0 8px 24px rgba(0, 0, 0, 0.4),
            0 0 0 1px var(--ff-border-strong),
            inset 0 1px 0 rgba(255, 255, 255, 0.06);
        margin-bottom: 10px;
        transition: transform 0.4s cubic-bezier(0.34, 1.56, 0.64, 1);
    }
    .logo:hover { transform: translateY(-2px) rotate(-2deg); }

    .brand {
        font-size: 19px;
        font-weight: 700;
        letter-spacing: -0.4px;
        background: linear-gradient(135deg, var(--ff-cream) 0%, var(--ff-champagne) 100%);
        -webkit-background-clip: text;
        background-clip: text;
        color: transparent;
        margin-bottom: 2px;
    }

    .tagline {
        font-size: 11px;
        color: var(--ff-sage);
        font-style: italic;
        letter-spacing: 0.2px;
    }

    /* ── Onboarding steps ─────────────────────────────────── */

    .onboard {
        display: flex;
        flex-direction: column;
        gap: 12px;
    }

    .step {
        display: flex;
        gap: 12px;
        padding: 12px 14px;
        background: rgba(240, 230, 210, 0.03);
        border: 1px solid var(--ff-border);
        border-radius: var(--ff-radius);
        transition: all 0.2s ease;
    }
    .step:hover {
        background: rgba(240, 230, 210, 0.05);
        border-color: var(--ff-border-strong);
        transform: translateX(2px);
    }

    .step-num {
        flex-shrink: 0;
        width: 28px; height: 28px;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        font-weight: 700;
        font-size: 12px;
        color: var(--ff-walnut);
        background: linear-gradient(135deg, var(--ff-champagne), var(--ff-cream));
        box-shadow: 0 2px 8px rgba(212, 193, 156, 0.25);
    }

    .step-body { flex: 1; min-width: 0; }
    .step-title {
        font-weight: 600;
        font-size: 13px;
        color: var(--ff-cream);
        margin-bottom: 2px;
    }
    .step-text {
        font-size: 11.5px;
        color: var(--ff-sage);
        line-height: 1.4;
    }

    /* ── Buttons ──────────────────────────────────────────── */

    .btn {
        font-family: inherit;
        font-size: 13px;
        font-weight: 600;
        padding: 10px 16px;
        border-radius: 8px;
        border: 1px solid transparent;
        cursor: pointer;
        transition: transform 0.12s ease, box-shadow 0.12s ease, background 0.2s ease;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        letter-spacing: 0.1px;
    }
    .btn:hover:not(:disabled) { transform: translateY(-1px); }
    .btn:active:not(:disabled) { transform: translateY(0); }

    .btn-block { width: 100%; margin-top: 8px; }

    .btn-primary {
        background: linear-gradient(135deg, var(--ff-champagne) 0%, var(--ff-amber) 100%);
        color: var(--ff-forest-deep);
        box-shadow:
            0 4px 14px rgba(212, 193, 156, 0.25),
            inset 0 1px 0 rgba(255, 255, 255, 0.3);
    }
    .btn-primary:hover:not(:disabled) {
        box-shadow:
            0 6px 20px rgba(212, 193, 156, 0.4),
            inset 0 1px 0 rgba(255, 255, 255, 0.4);
    }

    .btn-secondary {
        background: rgba(240, 230, 210, 0.08);
        color: var(--ff-cream);
        border-color: var(--ff-border-strong);
    }
    .btn-secondary:hover:not(:disabled) {
        background: rgba(240, 230, 210, 0.12);
        border-color: var(--ff-champagne);
    }

    .btn-ghost {
        background: transparent;
        color: var(--ff-sage);
        font-weight: 500;
    }
    .btn-ghost:hover:not(:disabled) {
        color: var(--ff-cream);
        background: rgba(240, 230, 210, 0.04);
    }

    .muted {
        text-align: center;
        font-size: 11px;
        color: var(--ff-sage);
        margin-top: 8px;
        font-style: italic;
    }

    /* ── State cards (loading / empty / error) ────────────── */

    .state-card {
        text-align: center;
        padding: 28px 16px;
        background: rgba(240, 230, 210, 0.03);
        border: 1px solid var(--ff-border);
        border-radius: var(--ff-radius);
    }
    .state-card .btn { margin: 8px 4px 0; }
    .state-card .btn-block { margin: 12px 0 0; }
    .error-card { border-color: rgba(177, 79, 88, 0.3); background: rgba(177, 79, 88, 0.05); }
    .error-msg {
        font-size: 12px;
        color: #E8A8B0;
        margin: 6px 0 10px;
        padding: 8px 12px;
        background: rgba(177, 79, 88, 0.12);
        border-left: 2px solid var(--ff-burgundy);
        border-radius: 4px;
        text-align: left;
        line-height: 1.45;
        font-style: normal;
    }

    .big-emoji { font-size: 32px; margin-bottom: 8px; }

    .state-title {
        font-size: 14px;
        font-weight: 600;
        color: var(--ff-cream);
        margin-bottom: 6px;
    }

    .loader {
        width: 36px; height: 36px;
        border: 3px solid var(--ff-border);
        border-top-color: var(--ff-champagne);
        border-radius: 50%;
        margin: 4px auto 14px;
        animation: spin 0.9s linear infinite;
    }
    @keyframes spin { to { transform: rotate(360deg); } }

    /* ── Bug list ─────────────────────────────────────────── */

    .summary {
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
        margin-bottom: 8px;
    }
    .summary-pill {
        padding: 4px 10px;
        border-radius: 999px;
        font-size: 11px;
        font-weight: 600;
        background: rgba(240, 230, 210, 0.06);
        border: 1px solid var(--ff-border);
        color: var(--ff-cream);
    }
    .summary-pill .pill-label { color: var(--ff-sage); font-weight: 500; margin-left: 2px; }
    .summary-pill.high   { background: rgba(177, 79, 88, 0.18); border-color: rgba(177, 79, 88, 0.45); color: #E8A8B0; }
    .summary-pill.med    { background: rgba(212, 165, 116, 0.18); border-color: rgba(212, 165, 116, 0.45); color: var(--ff-amber); }
    .summary-pill.low    { background: rgba(92, 148, 114, 0.18); border-color: rgba(92, 148, 114, 0.45); color: var(--ff-emerald); }
    .summary-pill.total  { background: linear-gradient(135deg, var(--ff-champagne), var(--ff-amber)); border-color: transparent; color: var(--ff-forest-deep); }

    .toolbar {
        display: flex;
        justify-content: flex-end;
        gap: 4px;
        margin-bottom: 14px;
    }
    .icon-btn {
        font-family: inherit;
        background: rgba(240, 230, 210, 0.04);
        color: var(--ff-sage);
        border: 1px solid var(--ff-border);
        border-radius: 6px;
        padding: 4px 10px;
        font-size: 13px;
        cursor: pointer;
        transition: all 0.15s ease;
    }
    .icon-btn:hover {
        background: rgba(240, 230, 210, 0.08);
        color: var(--ff-cream);
        border-color: var(--ff-champagne);
    }

    .bug-list {
        display: flex;
        flex-direction: column;
        gap: 8px;
    }

    .bug-card {
        padding: 12px 14px;
        background: linear-gradient(135deg, rgba(240, 230, 210, 0.04) 0%, rgba(240, 230, 210, 0.02) 100%);
        border: 1px solid var(--ff-border);
        border-radius: var(--ff-radius);
        cursor: pointer;
        transition: all 0.2s cubic-bezier(0.34, 1.56, 0.64, 1);
        position: relative;
        overflow: hidden;
    }
    .bug-card::before {
        content: '';
        position: absolute;
        top: 0; left: 0;
        width: 3px; height: 100%;
        background: var(--ff-champagne);
        opacity: 0;
        transition: opacity 0.2s ease;
    }
    .bug-card:hover {
        background: linear-gradient(135deg, rgba(240, 230, 210, 0.08) 0%, rgba(240, 230, 210, 0.04) 100%);
        border-color: var(--ff-border-strong);
        transform: translateX(2px);
    }
    .bug-card:hover::before { opacity: 1; }
    .bug-card.is-fixed { opacity: 0.6; }

    .bug-row {
        display: flex;
        align-items: center;
        gap: 8px;
        margin-bottom: 5px;
    }

    .bug-iid {
        font-family: "SF Mono", "JetBrains Mono", Menlo, monospace;
        font-size: 11px;
        font-weight: 700;
        color: var(--ff-champagne);
        letter-spacing: 0.3px;
    }

    .priority-dot {
        width: 8px; height: 8px;
        border-radius: 50%;
        flex-shrink: 0;
    }
    .dot-high    { background: var(--ff-burgundy); box-shadow: 0 0 6px rgba(177, 79, 88, 0.5); }
    .dot-medium  { background: var(--ff-amber); }
    .dot-low     { background: var(--ff-emerald); }

    .badge-fixed {
        margin-left: auto;
        font-size: 9px;
        font-weight: 700;
        letter-spacing: 0.6px;
        background: rgba(92, 148, 114, 0.25);
        color: var(--ff-emerald);
        padding: 2px 6px;
        border-radius: 3px;
        border: 1px solid rgba(92, 148, 114, 0.4);
    }

    .bug-title {
        font-size: 12.5px;
        font-weight: 500;
        line-height: 1.35;
        color: var(--ff-cream);
        margin-bottom: 6px;
        display: -webkit-box;
        -webkit-line-clamp: 2;
        -webkit-box-orient: vertical;
        overflow: hidden;
    }

    .bug-meta {
        display: flex;
        gap: 10px;
        font-size: 10.5px;
        color: var(--ff-sage);
        margin-bottom: 4px;
    }

    .bug-labels {
        display: flex;
        flex-wrap: wrap;
        gap: 4px;
        margin-top: 6px;
    }
    .bug-label {
        font-size: 9.5px;
        padding: 2px 6px;
        background: rgba(212, 193, 156, 0.08);
        color: var(--ff-champagne);
        border-radius: 3px;
        letter-spacing: 0.2px;
    }

    code {
        font-family: "SF Mono", Menlo, monospace;
        background: rgba(240, 230, 210, 0.08);
        padding: 1px 5px;
        border-radius: 3px;
        font-size: 11px;
        color: var(--ff-champagne);
    }
`;
