/**
 * Chat webview panel — conversational interface to the FixFleet CLI.
 * User messages go to `fixfleet --chat-json`; any returned action
 * (auto_fix / fix_one) is executed immediately with progress shown in-chat.
 *
 * Transcript + prompt history persist in globalState so chat survives
 * VS Code restarts and mid-fix panel closes.
 *
 * Styling follows the FixFleet brand palette (mirrors welcomeView STYLES):
 * deep forest green gradient, cream text, sage secondary, champagne gold accents.
 */
import * as vscode from 'vscode';
import { AutoFixSummary, FixResult, autoFix, chatMessage, fixBug } from './fixfleetCli';
import { track } from './telemetry';

interface ChatEntry {
    role: 'user' | 'bot' | 'status';
    text: string;
    ts: number;
    error?: boolean;
}

const HISTORY_KEY = 'fixfleet.chatHistory';
const PROMPT_KEY = 'fixfleet.promptHistory';
const HISTORY_CAP = 200;
const PROMPT_CAP = 50;

export class ChatPanel {
    private static current: ChatPanel | undefined;

    public static createOrShow(context: vscode.ExtensionContext) {
        if (ChatPanel.current) {
            ChatPanel.current.panel.reveal();
            return;
        }
        const panel = vscode.window.createWebviewPanel(
            'fixfleetChat',
            '💬 FixFleet Chat',
            vscode.ViewColumn.Beside,
            { enableScripts: true, retainContextWhenHidden: true },
        );
        ChatPanel.current = new ChatPanel(context, panel);
    }

    private history: ChatEntry[] = [];

    private constructor(
        private readonly context: vscode.ExtensionContext,
        private readonly panel: vscode.WebviewPanel,
    ) {
        this.history = context.globalState.get<ChatEntry[]>(HISTORY_KEY, []);
        this.panel.webview.html = this.render();
        panel.onDidDispose(() => (ChatPanel.current = undefined));
        panel.webview.onDidReceiveMessage(msg => this.handleMessage(msg));
    }

    // ── Persistence ────────────────────────────────────────────

    private pushEntry(role: ChatEntry['role'], text: string, error = false) {
        this.history.push({ role, text, ts: Date.now(), error: error || undefined });
        if (this.history.length > HISTORY_CAP) {
            this.history = this.history.slice(-HISTORY_CAP);
        }
        this.context.globalState.update(HISTORY_KEY, this.history);
    }

    private pushPrompt(text: string) {
        const prompts = this.context.globalState.get<string[]>(PROMPT_KEY, []).slice();
        // Dedupe consecutive repeats.
        if (prompts[prompts.length - 1] !== text) prompts.push(text);
        this.context.globalState.update(PROMPT_KEY, prompts.slice(-PROMPT_CAP));
    }

    // ── Webview messaging helpers ──────────────────────────────

    private post(msg: { cmd: string; [k: string]: any }) {
        this.panel.webview.postMessage(msg);
    }

    /** Append + persist a bot bubble. */
    private bot(text: string, error = false) {
        this.pushEntry('bot', text, error);
        this.post({ cmd: 'bot', text, error, ts: Date.now() });
    }

    /** Show (and persist) a working-state bubble; empty text hides it. */
    private status(text: string) {
        if (text) this.pushEntry('status', text);
        this.post({ cmd: 'status', text, ts: Date.now() });
    }

    /** Morph the working bubble in place into a final bot result. */
    private statusDone(text: string, error = false) {
        this.pushEntry('bot', text, error);
        this.post({ cmd: 'statusDone', text, error, ts: Date.now() });
    }

    private async handleMessage(msg: { cmd: string; [k: string]: any }) {
        switch (msg.cmd) {
            case 'ready':
                // Webview script loaded: restore transcript + prompt history.
                this.post({
                    cmd: 'restore',
                    messages: this.history,
                    prompts: this.context.globalState.get<string[]>(PROMPT_KEY, []),
                });
                break;
            case 'send': {
                const text = String(msg.text || '');
                if (!text.trim()) return;
                this.pushEntry('user', text);
                this.pushPrompt(text);
                await this.processUserMessage(text);
                break;
            }
            case 'pickFile':
                await this.pickBugFile();
                break;
            case 'clear':
                this.history = [];
                await this.context.globalState.update(HISTORY_KEY, []);
                this.post({ cmd: 'cleared' });
                break;
        }
    }

    /** 📎 chip: pick an xlsx/docx/pdf and send `load <path>` through chat. */
    private async pickBugFile() {
        const picked = await vscode.window.showOpenDialog({
            canSelectFiles: true,
            canSelectFolders: false,
            canSelectMany: false,
            openLabel: 'Load Bug File',
            filters: { 'Bug files': ['xlsx', 'docx', 'pdf'] },
        });
        if (picked && picked[0]) {
            const text = `load ${picked[0].fsPath}`;
            // Echo it into the chat as a user message, then run the pipeline.
            this.pushEntry('user', text);
            this.post({ cmd: 'user', text, ts: Date.now() });
            await this.processUserMessage(text);
        }
    }

    private async processUserMessage(text: string) {
        this.post({ cmd: 'thinking' });
        try {
            const res = await chatMessage(text);
            this.bot(res.reply || '(no reply)');
            if (res.action) {
                await this.runAction(res.action);
            }
        } catch (e) {
            this.bot(`⚠ ${(e as Error).message}`, true);
        } finally {
            this.post({ cmd: 'done' });
        }
    }

    /** Execute an action object returned by the chat CLI. */
    private async runAction(action: any) {
        const type = String(action?.type || '');
        if (type !== 'auto_fix' && type !== 'fix_one') {
            this.bot(
                `⚠ I received an action I don't know how to run (${type || 'unknown'}). Try updating the FixFleet CLI.`,
                true,
            );
            return;
        }
        track('chat_action_run', { type });

        const cfg = vscode.workspace.getConfiguration('fixfleet');
        const backend = cfg.get<string>('backend') || 'claude';
        const provider = cfg.get<string>('provider') || 'gitlab';
        const token = cfg.get<string>('gitlabToken') || '';
        const projectUrl = cfg.get<string>('projectUrl') || '';
        let projectDir = cfg.get<string>('projectDir') || '';
        if (!projectDir) {
            projectDir = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath || '';
        }

        const file = String(action.file || '');
        const minConfidence =
            typeof action.min_confidence === 'number' ? action.min_confidence : 0.6;

        if (!projectDir) {
            this.bot(
                'I need a project directory to fix code in. Open a workspace folder, or set one in FixFleet settings.',
                true,
            );
            return;
        }
        if (!file && (!token || !projectUrl)) {
            this.bot(
                'Tracker mode needs an access token and project URL. Configure them in FixFleet settings first.',
                true,
            );
            return;
        }

        this.status(
            type === 'auto_fix'
                ? `Running auto-fix with ${backend}… fixing bugs one by one, this can take a few minutes.`
                : `Fixing issue #${action.iid} with ${backend}… this may take 30s–5min.`,
        );

        try {
            if (type === 'auto_fix') {
                const summary = await autoFix({
                    backend,
                    projectDir,
                    minConfidence,
                    file: file || undefined,
                    projectUrl,
                    provider,
                    token,
                });
                this.statusDone(this.summaryText(summary), summary?.ok === false);
            } else if (file) {
                // fix_one, file mode: auto-fix restricted to one issue.
                const summary = await autoFix({
                    backend,
                    projectDir,
                    minConfidence,
                    file,
                    fixIssue: String(action.iid),
                });
                this.statusDone(this.summaryText(summary), summary?.ok === false);
            } else {
                // fix_one, tracker mode: reuse the existing single-issue helper.
                const result: FixResult = await fixBug({
                    issueIid: parseInt(String(action.iid), 10),
                    backend,
                    token,
                    projectUrl,
                    projectDir,
                    provider,
                });
                this.statusDone(this.fixOneText(result), !result.success);
            }
        } catch (e) {
            this.statusDone(`⚠ Action failed: ${(e as Error).message}`, true);
        }
    }

    private summaryText(s: AutoFixSummary): string {
        if (!s || s.ok === false) {
            return `⚠ Auto-fix failed: ${s?.error || 'unknown error'}`;
        }
        const n = (v: any) => (typeof v === 'number' ? v : 0);
        // Human wording only — internal scoring machinery is never surfaced.
        const parts = [`✅ Fixed ${n(s.kept)} bug(s).`];
        if (n(s.reverted) > 0) {
            parts.push(`↩️ ${n(s.reverted)} couldn't be fixed confidently — changes were undone and they're marked for review.`);
        }
        if (n(s.failed) > 0) {
            parts.push(`⚠️ ${n(s.failed)} couldn't be fixed — marked for review.`);
        }
        if (n(s.skipped) > 0) {
            parts.push(`⏭️ ${n(s.skipped)} skipped (already fixed or duplicates).`);
        }
        // QA triage gate: items the CLI declined to touch. The raw verdict
        // tokens (not_a_bug / not_relevant) are never shown — only the
        // user-friendly reason. Text is escaped webview-side before innerHTML.
        const alerts = Array.isArray(s.alerts) ? s.alerts : [];
        if (alerts.length) {
            parts.push('');
            parts.push("🔍 QA check — I didn't touch these:");
            for (const a of alerts) {
                const iid = String(a?.iid ?? '');
                const title = String(a?.title || '');
                const reason = String(a?.reason || '');
                const warn = a?.verdict === 'not_relevant' ? '⚠️ ' : '';
                parts.push(`• #${iid} ${title} — ${warn}${reason}`);
            }
            parts.push('If any of these ARE real bugs for this project, edit their description and try again.');
        }
        return parts.join('\n');
    }

    private fixOneText(r: FixResult): string {
        if (r.success) {
            return '✅ Fix applied — review the diff with git diff when ready.';
        }
        return "↩️ I wasn't sure about this one, so I undid the changes and marked it for review.";
    }

    private esc(s: string): string {
        return (s || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    private render(): string {
        const cfg = vscode.workspace.getConfiguration('fixfleet');
        const backend = this.esc(cfg.get<string>('backend') || 'claude');
        const provider = this.esc(cfg.get<string>('provider') || 'gitlab');

        const styles = `
            :root {
                /* ── FixFleet brand palette (mirrors welcomeView) ── */
                --ff-forest:        #2D4A3E;
                --ff-forest-deep:   #1F3329;
                --ff-cream:         #F0E6D2;
                --ff-cream-soft:    #E8DCC0;
                --ff-sage:          #8AA89A;
                --ff-champagne:     #D4C19C;
                --ff-amber:         #D4A574;
                --ff-burgundy:      #B14F58;
                --ff-emerald:       #5C9472;

                --ff-radius: 12px;
                --ff-border: rgba(240, 230, 210, 0.10);
                --ff-border-strong: rgba(240, 230, 210, 0.18);
                --ff-card: rgba(255, 255, 255, 0.04);
                --ff-gold-border: rgba(212, 193, 156, 0.55);
                /* VS Code vars kept only as fallbacks */
                --ff-focus: var(--ff-champagne, var(--vscode-focusBorder));
            }

            * { box-sizing: border-box; }

            html, body { height: 100%; margin: 0; padding: 0; }

            body {
                font-family: -apple-system, "SF Pro Text", "Inter", system-ui, sans-serif;
                background: linear-gradient(180deg, var(--ff-forest-deep) 0%, #16241D 100%);
                color: var(--ff-cream);
                font-size: 13px;
                line-height: 1.55;
                display: flex;
                flex-direction: column;
            }

            /* ── Header ───────────────────────────────────────── */
            header.bar {
                flex-shrink: 0;
                display: flex;
                align-items: center;
                gap: 10px;
                padding: 12px 16px;
                background: rgba(0, 0, 0, 0.28);
                border-bottom: 1px solid var(--ff-gold-border);
            }
            .bar-title {
                font-weight: 600;
                letter-spacing: 0.2px;
                color: var(--ff-cream);
            }
            .bar-sub {
                font-size: 11px;
                color: var(--ff-sage);
                font-family: "SF Mono", Menlo, monospace;
            }
            #clear-btn {
                margin-left: auto;
                font-family: inherit;
                font-size: 13px;
                padding: 4px 10px;
                border-radius: 6px;
                border: 1px solid var(--ff-border-strong);
                background: var(--ff-card);
                color: var(--ff-cream);
                cursor: pointer;
            }
            #clear-btn:hover { border-color: var(--ff-burgundy); }

            /* ── Message list ─────────────────────────────────── */
            #messages {
                flex: 1;
                overflow-y: auto;
                padding: 18px 16px;
                display: flex;
                flex-direction: column;
                gap: 10px;
                scrollbar-width: thin;
                scrollbar-color: rgba(138, 168, 154, 0.4) transparent;
            }
            #messages::-webkit-scrollbar { width: 6px; }
            #messages::-webkit-scrollbar-track { background: transparent; }
            #messages::-webkit-scrollbar-thumb {
                background: rgba(138, 168, 154, 0.35);
                border-radius: 3px;
            }
            #messages::-webkit-scrollbar-thumb:hover { background: rgba(138, 168, 154, 0.55); }

            .row {
                display: flex;
                align-items: flex-end;
                gap: 8px;
                max-width: 85%;
            }
            .row.user { align-self: flex-end; flex-direction: row-reverse; }
            .row.bot  { align-self: flex-start; }

            .avatar {
                flex-shrink: 0;
                width: 26px; height: 26px;
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 14px;
                background: rgba(212, 193, 156, 0.12);
                border: 1px solid var(--ff-gold-border);
            }

            .bubble {
                padding: 9px 14px;
                border-radius: var(--ff-radius);
                border: 1px solid var(--ff-border-strong);
                word-wrap: break-word;
                overflow-wrap: anywhere;
                min-width: 0;
            }
            .row.user .bubble {
                background: linear-gradient(135deg, var(--ff-champagne), var(--ff-amber));
                color: var(--ff-forest-deep);
                border-color: transparent;
                border-bottom-right-radius: 3px;
            }
            .row.bot .bubble {
                background: var(--ff-card);
                color: var(--ff-cream);
                border-bottom-left-radius: 3px;
            }
            .row.bot.err .bubble {
                border-color: rgba(177, 79, 88, 0.6);
                background: rgba(177, 79, 88, 0.10);
            }

            .ts {
                font-size: 9.5px;
                color: var(--ff-sage);
                opacity: 0.8;
                margin-top: 4px;
                text-align: right;
                font-family: "SF Mono", Menlo, monospace;
            }
            .row.user .ts { color: rgba(31, 51, 41, 0.65); }

            /* ── Working / status bubble ──────────────────────── */
            .row.working .bubble {
                font-style: italic;
                background: var(--ff-card);
                border-color: var(--ff-gold-border);
            }
            .shimmer {
                height: 3px;
                margin-top: 8px;
                border-radius: 2px;
                overflow: hidden;
                background: rgba(212, 193, 156, 0.18);
                position: relative;
            }
            .shimmer::after {
                content: '';
                position: absolute;
                top: 0; left: -40%;
                width: 40%; height: 100%;
                border-radius: 2px;
                background: linear-gradient(90deg, transparent, var(--ff-champagne), transparent);
            }
            .row.status-static .bubble {
                font-style: italic;
                color: var(--ff-sage);
            }

            /* ── Typing indicator ─────────────────────────────── */
            .dots { display: inline-flex; gap: 4px; padding: 3px 0; }
            .dot {
                width: 7px; height: 7px;
                border-radius: 50%;
                background: rgba(212, 193, 156, 0.7);
                display: inline-block;
            }

            /* ── Instruction / guide card ─────────────────────── */
            .row.guide { max-width: 96%; }
            .guide-title {
                font-weight: 600;
                color: var(--ff-champagne);
                margin-bottom: 6px;
                letter-spacing: 0.2px;
            }
            .guide-list {
                margin: 0;
                padding: 0;
                list-style: none;
                display: flex;
                flex-direction: column;
                gap: 5px;
            }
            .guide-list li { font-size: 12.5px; }
            .bubble code {
                background: rgba(0, 0, 0, 0.30);
                color: var(--ff-champagne);
                padding: 1px 5px;
                border-radius: 4px;
                font-family: "SF Mono", Menlo, monospace;
                font-size: 11.5px;
            }
            .guide-tip {
                margin-top: 8px;
                font-size: 11px;
                color: var(--ff-sage);
                font-style: italic;
            }

            /* ── Quick-command chips ──────────────────────────── */
            .chips {
                flex-shrink: 0;
                display: flex;
                flex-wrap: wrap;
                gap: 6px;
                padding: 8px 16px 0;
            }
            .chip {
                font-family: inherit;
                font-size: 11px;
                font-weight: 600;
                padding: 4px 12px;
                border-radius: 999px;
                background: transparent;
                border: 1px solid var(--ff-gold-border);
                color: var(--ff-cream);
                cursor: pointer;
                letter-spacing: 0.2px;
            }
            .chip:hover {
                background: var(--ff-champagne);
                color: var(--ff-forest-deep);
                border-color: var(--ff-champagne);
            }

            /* ── Composer ─────────────────────────────────────── */
            footer.composer {
                flex-shrink: 0;
                display: flex;
                gap: 8px;
                padding: 10px 16px 12px;
            }
            #input {
                flex: 1;
                font-family: inherit;
                font-size: 13px;
                padding: 9px 12px;
                border-radius: 8px;
                border: 1px solid var(--ff-border-strong);
                background: rgba(0, 0, 0, 0.25);
                color: var(--ff-cream);
                outline: none;
            }
            #input::placeholder { color: var(--ff-sage); opacity: 0.7; }
            #input:focus {
                border-color: var(--ff-focus);
                box-shadow: 0 0 0 3px rgba(212, 193, 156, 0.22);
            }

            button.btn {
                font-family: inherit;
                font-size: 13px;
                font-weight: 700;
                padding: 8px 18px;
                border-radius: 8px;
                border: 1px solid transparent;
                cursor: pointer;
            }
            button.btn:disabled { opacity: 0.5; cursor: not-allowed; }
            .btn-primary {
                background: linear-gradient(135deg, var(--ff-champagne), var(--ff-amber));
                color: var(--ff-forest-deep);
                box-shadow: 0 4px 14px rgba(212, 193, 156, 0.25);
            }
            .btn-primary:hover:not(:disabled) {
                filter: brightness(1.08);
                box-shadow: 0 6px 20px rgba(212, 193, 156, 0.4);
            }

            /* ── Animations (skipped entirely for reduced motion) ── */
            @media (prefers-reduced-motion: no-preference) {
                .anim-in {
                    animation: slide-in 180ms ease-out both;
                }
                @keyframes slide-in {
                    from { opacity: 0; transform: translateY(8px); }
                    to   { opacity: 1; transform: translateY(0); }
                }

                .dot { animation: bounce 1.1s ease-in-out infinite; }
                .dot:nth-child(2) { animation-delay: 0.15s; }
                .dot:nth-child(3) { animation-delay: 0.3s; }
                @keyframes bounce {
                    0%, 60%, 100% { transform: translateY(0); opacity: 0.5; }
                    30% { transform: translateY(-5px); opacity: 1; }
                }

                .row.working .bubble {
                    animation: glow 1.6s ease-in-out infinite;
                }
                @keyframes glow {
                    0%, 100% { box-shadow: 0 0 0 0 rgba(212, 193, 156, 0); }
                    50% { box-shadow: 0 0 14px 2px rgba(212, 193, 156, 0.35); }
                }
                .shimmer::after { animation: shimmer 1.4s linear infinite; }
                @keyframes shimmer {
                    from { left: -40%; }
                    to   { left: 100%; }
                }

                .flash .bubble { animation: flash 700ms ease-out 1; }
                @keyframes flash {
                    0% { box-shadow: 0 0 0 3px rgba(212, 193, 156, 0.6); }
                    100% { box-shadow: 0 0 0 0 transparent; }
                }

                button.btn { transition: transform 0.12s ease, box-shadow 0.12s ease, filter 0.12s ease; }
                button.btn:hover:not(:disabled) { transform: scale(1.05); }
                button.btn:active:not(:disabled) { transform: scale(0.95); }
                .chip { transition: transform 0.1s ease, background 0.15s ease, color 0.15s ease; }
                .chip:active { transform: scale(0.94); }
                #input { transition: border-color 0.15s ease, box-shadow 0.15s ease; }
                #messages { transition: opacity 0.2s ease; }
            }
            #messages.fading { opacity: 0; }
        `;

        return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src data: https:;">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>${styles}</style>
</head>
<body>
<header class="bar">
    <div>
        <div class="bar-title">🚀 FixFleet Chat</div>
        <div class="bar-sub">${backend} · ${provider}</div>
    </div>
    <button id="clear-btn" title="Clear chat history">🗑</button>
</header>
<div id="messages"></div>
<div class="chips">
    <button class="chip" data-send="help">Help</button>
    <button class="chip" data-act="pick">📎 Load file</button>
    <button class="chip" data-send="list bugs">List bugs</button>
    <button class="chip" data-send="fix all">✨ Fix all bugs</button>
    <button class="chip" data-send="status">Status</button>
</div>
<footer class="composer">
    <input id="input" type="text" placeholder="e.g. fix all bugs…  (↑↓ for history)" />
    <button class="btn btn-primary" id="send-btn">Send</button>
</footer>

<script>
    const vscode = acquireVsCodeApi();
    const messages = document.getElementById('messages');
    const input = document.getElementById('input');
    const sendBtn = document.getElementById('send-btn');
    const clearBtn = document.getElementById('clear-btn');

    const motionOK = window.matchMedia('(prefers-reduced-motion: no-preference)').matches;

    // Static instruction card shown when the transcript is empty.
    const GUIDE_HTML =
        '<div class="guide-title">What I can do</div>' +
        '<ul class="guide-list">' +
        '<li>📎 Load bugs from Excel / Word / PDF — click the clip or type <code>load &lt;path&gt;</code></li>' +
        '<li>📋 <code>list bugs</code> / <code>status</code> — see everything tracked</li>' +
        '<li>✨ <code>fix #3</code> — fix one bug</li>' +
        '<li>✨ <code>fix all</code> — fixes every open bug; I only keep solid fixes and undo anything uncertain</li>' +
        '</ul>' +
        '<div class="guide-tip">Tip: press ↑ to recall past prompts.</div>';

    function esc(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    // Escape first, then restore newlines as <br>.
    function fmt(s) {
        return esc(s).replace(/\\n/g, '<br>');
    }

    function tsStr(ts) {
        const d = ts ? new Date(ts) : new Date();
        return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }

    function scrollDown(smooth) {
        const last = messages.lastElementChild;
        if (last) last.scrollIntoView({ behavior: smooth && motionOK ? 'smooth' : 'auto', block: 'end' });
    }

    function bubbleHtml(text, ts) {
        return '<div class="bubble">' + fmt(text) + '<div class="ts">' + esc(tsStr(ts)) + '</div></div>';
    }

    // opts: { error, ts, animate (default true), statusStatic }
    function addMsg(role, text, opts) {
        opts = opts || {};
        const row = document.createElement('div');
        const classes = ['row', role === 'user' ? 'user' : 'bot'];
        if (opts.error) classes.push('err');
        if (opts.statusStatic) classes.push('status-static');
        if (opts.animate !== false) classes.push('anim-in');
        row.className = classes.join(' ');
        row.innerHTML = (role === 'user' ? '' : '<div class="avatar">🚀</div>') + bubbleHtml(text, opts.ts);
        messages.appendChild(row);
        scrollDown(opts.animate !== false);
        return row;
    }

    /** Insert the static instruction card as a wide bot bubble. */
    function addGuide() {
        const row = document.createElement('div');
        row.className = 'row bot guide anim-in';
        row.innerHTML = '<div class="avatar">🚀</div><div class="bubble">' + GUIDE_HTML + '</div>';
        messages.appendChild(row);
        scrollDown(false);
    }

    // ── Typing indicator + working-state bubble ────────────────
    let typingEl = null;
    let statusEl = null;

    function setTyping(on) {
        if (on && !typingEl) {
            typingEl = document.createElement('div');
            typingEl.className = 'row bot working anim-in';
            typingEl.innerHTML = '<div class="avatar">🚀</div><div class="bubble"><span class="dots"><span class="dot"></span><span class="dot"></span><span class="dot"></span></span></div>';
            messages.appendChild(typingEl);
            scrollDown(true);
        } else if (!on && typingEl) {
            typingEl.remove();
            typingEl = null;
        }
    }

    function setStatus(text, ts) {
        if (!text) {
            if (statusEl) { statusEl.remove(); statusEl = null; }
            return;
        }
        setTyping(false);
        if (!statusEl) {
            statusEl = document.createElement('div');
            statusEl.className = 'row bot working anim-in';
            messages.appendChild(statusEl);
        }
        statusEl.innerHTML = '<div class="avatar">🚀</div><div class="bubble"><div>' + fmt(text) + '</div><div class="shimmer"></div><div class="ts">' + esc(tsStr(ts)) + '</div></div>';
        scrollDown(true);
    }

    /** Morph the working bubble in place into the final result message. */
    function statusDone(text, error, ts) {
        setTyping(false);
        if (statusEl) {
            const el = statusEl;
            statusEl = null;
            el.className = 'row bot' + (error ? ' err' : '') + ' flash';
            el.innerHTML = '<div class="avatar">🚀</div>' + bubbleHtml(text, ts);
            setTimeout(function () { el.classList.remove('flash'); }, 800);
            scrollDown(true);
        } else {
            addMsg('bot', text, { error: error, ts: ts });
        }
    }

    // ── Busy state + outgoing queue ────────────────────────────
    // The transcript always stays visible and scrollable; while a fix runs
    // the user can keep typing / browsing prompt history and queue messages.
    let busy = false;
    const queue = [];

    function flushQueue() {
        if (busy || !queue.length) return;
        busy = true;
        vscode.postMessage({ cmd: 'send', text: queue.shift() });
    }

    // ── Prompt history recall (terminal-style ↑ / ↓) ───────────
    let prompts = [];
    let histIdx = null;   // null = live input
    let draft = '';

    function rememberPrompt(text) {
        if (prompts[prompts.length - 1] !== text) prompts.push(text);
        if (prompts.length > 50) prompts = prompts.slice(-50);
    }

    function sendText(text) {
        text = String(text || '').trim();
        if (!text) return;
        rememberPrompt(text);
        histIdx = null;
        draft = '';
        addMsg('user', text);
        queue.push(text);
        flushQueue();
    }

    function send() {
        const text = input.value;
        input.value = '';
        sendText(text);
    }

    sendBtn.addEventListener('click', send);
    input.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            send();
        } else if (e.key === 'ArrowUp') {
            if (!prompts.length) return;
            e.preventDefault();
            if (histIdx === null) { draft = input.value; histIdx = prompts.length - 1; }
            else if (histIdx > 0) histIdx--;
            input.value = prompts[histIdx];
        } else if (e.key === 'ArrowDown') {
            if (histIdx === null) return;
            e.preventDefault();
            if (histIdx < prompts.length - 1) {
                histIdx++;
                input.value = prompts[histIdx];
            } else {
                histIdx = null;
                input.value = draft;
            }
        }
    });
    // Typing resets the history cursor back to live input.
    input.addEventListener('input', function () { histIdx = null; });

    // Quick-command chips: send the command through the normal pipeline;
    // the Load-file chip opens the native file picker instead.
    document.querySelectorAll('.chip').forEach(function (chip) {
        chip.addEventListener('click', function () {
            if (chip.dataset.act === 'pick') {
                vscode.postMessage({ cmd: 'pickFile' });
            } else if (chip.dataset.send) {
                sendText(chip.dataset.send);
            }
        });
    });

    clearBtn.addEventListener('click', function () { vscode.postMessage({ cmd: 'clear' }); });

    // ── Messages from the extension ────────────────────────────
    window.addEventListener('message', function (event) {
        const m = event.data;
        if (m.cmd === 'restore') {
            messages.innerHTML = '';
            (m.messages || []).forEach(function (entry) {
                addMsg(entry.role === 'user' ? 'user' : 'bot', entry.text, {
                    error: !!entry.error,
                    ts: entry.ts,
                    animate: false,
                    statusStatic: entry.role === 'status',
                });
            });
            prompts = (m.prompts || []).slice(-50);
            if (!(m.messages || []).length) addGuide();
            scrollDown(false);
        } else if (m.cmd === 'user') {
            addMsg('user', m.text, { ts: m.ts });
        } else if (m.cmd === 'bot') {
            setTyping(false);
            addMsg('bot', m.text, { error: !!m.error, ts: m.ts });
        } else if (m.cmd === 'thinking') {
            setTyping(true);
        } else if (m.cmd === 'done') {
            setTyping(false);
            setStatus('');
            busy = false;
            flushQueue();
        } else if (m.cmd === 'status') {
            setStatus(m.text || '', m.ts);
        } else if (m.cmd === 'statusDone') {
            statusDone(m.text, !!m.error, m.ts);
        } else if (m.cmd === 'cleared') {
            messages.classList.add('fading');
            setTimeout(function () {
                typingEl = null;
                statusEl = null;
                messages.innerHTML = '';
                messages.classList.remove('fading');
                addGuide();
            }, motionOK ? 200 : 0);
        }
    });

    input.focus();
    vscode.postMessage({ cmd: 'ready' });
</script>
</body>
</html>`;
    }
}
