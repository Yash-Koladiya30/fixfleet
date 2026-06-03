/**
 * Thin wrapper around the `fixfleet` Python CLI.
 * Spawns subprocess, parses JSON output.
 */
import * as cp from 'child_process';
import * as vscode from 'vscode';
import { output } from './extension';

export interface BugIssue {
    iid: number;
    title: string;
    web_url: string;
    labels: string[];
    created_at: string;
    updated_at: string;
    author: string;
    already_fixed: boolean;
    sections: {
        description: string;
        steps: string;
        expected: string;
        actual: string;
        environment: string;
        logs: string;
        notes: string;
    };
}

export interface BackendInfo {
    name: string;
    display_name: string;
    binary: string;
    version?: string;
    installed: boolean;
}

export interface ConfidenceReport {
    final_score: number;
    label: string;
    self_rating: number;
    root_cause: string;
    diff_focus: number;
    file_relevance: number;
    hedge_density: number;
    tests_run: string;
    files_changed: string[];
    lines_changed: number;
    notes: string[];
}

export interface FixResult {
    ok: boolean;
    error?: string;
    code?: string;
    status?: number;
    issue?: { iid: number; title: string };
    backend?: string;
    result?: { returncode: number; timed_out: boolean; stdout: string; stderr: string };
    confidence?: ConfidenceReport;
    tokens?: { estimated: number; daily_used_after: number };
    locator?: { files_mentioned: string[]; candidates: string[]; frames_count: number; symbols_count: number };
    success?: boolean;
}

/** Structured error from the fixfleet CLI's JSON API. */
export class FixFleetError extends Error {
    constructor(
        public readonly code: string,
        public readonly status: number,
        message: string,
    ) {
        super(message);
        this.name = 'FixFleetError';
    }

    /** True if the user needs to update their GitLab token. */
    get isAuthError(): boolean {
        return this.code === 'token_invalid' || this.code === 'token_forbidden';
    }

    /** True if the project URL is wrong or token has no access. */
    get isNotFoundError(): boolean {
        return this.code === 'project_not_found';
    }

    /** True if network/DNS/timeout. */
    get isNetworkError(): boolean {
        return this.code === 'network_error';
    }

    /** True if FixFleet CLI is missing entirely (binary not found). */
    get isCliMissing(): boolean {
        return this.code === 'cli_missing';
    }
}

import * as os from 'os';
import * as path from 'path';
import * as fs from 'fs';

function cliCommand(): string {
    const cfg = vscode.workspace.getConfiguration('fixfleet');
    return cfg.get<string>('cliPath') || 'fixfleet';
}

function pythonCommand(): string {
    const cfg = vscode.workspace.getConfiguration('fixfleet');
    return cfg.get<string>('pythonPath') || 'python3';
}

/**
 * VSCode child_process.spawn doesn't inherit interactive shell PATH (.zshrc additions).
 * Build an augmented PATH that includes common user-bin locations where fixfleet may be installed.
 */
function augmentedPath(): string {
    const home = os.homedir();
    const candidates = [
        process.env.PATH || '',
        // Standard pip --user bin dirs on macOS for Python 3.9-3.13
        path.join(home, 'Library/Python/3.9/bin'),
        path.join(home, 'Library/Python/3.10/bin'),
        path.join(home, 'Library/Python/3.11/bin'),
        path.join(home, 'Library/Python/3.12/bin'),
        path.join(home, 'Library/Python/3.13/bin'),
        // Linux pip --user
        path.join(home, '.local/bin'),
        // Homebrew
        '/opt/homebrew/bin',
        '/usr/local/bin',
        // pipx
        path.join(home, '.local/pipx/venvs/fixfleet/bin'),
    ];
    const seen = new Set<string>();
    const merged: string[] = [];
    for (const part of candidates.join(':').split(':')) {
        if (part && !seen.has(part)) {
            seen.add(part);
            merged.push(part);
        }
    }
    return merged.join(':');
}

/** Resolve the actual fixfleet binary path, scanning PATH + common user-bin dirs. */
function resolveCli(): string | null {
    const cfg = vscode.workspace.getConfiguration('fixfleet');
    const cliPath = cfg.get<string>('cliPath') || 'fixfleet';

    if (cliPath.includes('/') && fs.existsSync(cliPath)) return cliPath;

    for (const dir of augmentedPath().split(':')) {
        const candidate = path.join(dir, cliPath);
        try {
            if (fs.existsSync(candidate)) return candidate;
        } catch {
            // ignore
        }
    }
    return null;
}

/**
 * Run fixfleet with JSON args. Try direct binary first, then `python -m bugfixer.json_api`.
 * Strips ANSI noise from stdout, returns last JSON line.
 */
async function runJson(args: string[], timeoutMs = 120_000): Promise<any> {
    const argsForLog = args.map(a => (a.startsWith('glpat-') ? 'glpat-***REDACTED***' : a)).join(' ');

    const tryRun = (cmd: string, fullArgs: string[]) =>
        new Promise<any>((resolve, reject) => {
            output.appendLine(`[spawn] ${cmd} ${argsForLog}`);
            let child: cp.ChildProcessWithoutNullStreams;
            try {
                child = cp.spawn(cmd, fullArgs, {
                    env: {
                        ...process.env,
                        NO_COLOR: '1',
                        PYTHONUNBUFFERED: '1',
                        PATH: augmentedPath(),
                    },
                });
            } catch (err) {
                output.appendLine(`[spawn error] ${(err as Error).message}`);
                reject(err);
                return;
            }
            let stdout = '';
            let stderr = '';
            const timer = setTimeout(() => {
                output.appendLine(`[timeout] killing ${cmd} after ${timeoutMs}ms`);
                try { child.kill('SIGKILL'); } catch { /* ignore */ }
                reject(new FixFleetError('timeout', 0, `FixFleet CLI timed out after ${Math.round(timeoutMs / 1000)}s. The Python process may be hung — try restarting Cursor.`));
            }, timeoutMs);

            child.stdout.on('data', d => (stdout += d.toString()));
            child.stderr.on('data', d => (stderr += d.toString()));

            child.on('error', err => {
                output.appendLine(`[child error] ${(err as Error).message}`);
                clearTimeout(timer);
                reject(err);
            });
            child.on('close', code => {
                clearTimeout(timer);
                output.appendLine(`[child closed] exit=${code} stdout=${stdout.length}B stderr=${stderr.length}B`);
                if (stderr.trim()) output.appendLine(`[stderr] ${stderr.trim().slice(0, 500)}`);
                const lastJsonLine = stdout
                    .trim()
                    .split('\n')
                    .map(l => l.trim())
                    .filter(l => l.startsWith('{'))
                    .pop();

                if (lastJsonLine) {
                    try {
                        const parsed = JSON.parse(lastJsonLine);
                        resolve(parsed);
                        return;
                    } catch {
                        // fall through
                    }
                }

                if (code !== 0) {
                    reject(new FixFleetError('cli_error', 0, `FixFleet CLI exited with code ${code}. ${stderr.trim() || ''}`.trim()));
                    return;
                }
                reject(new FixFleetError('bad_output', 0, `Couldn't parse output from FixFleet CLI.`));
            });
        });

    const resolved = resolveCli();
    output.appendLine(`[resolve] cliPath=${cliCommand()} resolved=${resolved || 'NOT FOUND'}`);
    if (resolved) {
        try {
            return await tryRun(resolved, args);
        } catch (e) {
            const code = (e as any)?.code;
            output.appendLine(`[fallback] primary failed code=${code} msg=${(e as Error).message}`);
            if (code !== 'ENOENT' && code !== 'EACCES') throw e;
        }
    }
    // Fallback: python -m bugfixer.json_api (works if user installed via pip but PATH broken)
    try {
        return await tryRun(pythonCommand(), ['-m', 'bugfixer.json_api', ...args]);
    } catch (pyErr) {
        const pyCode = (pyErr as any)?.code;
        if (pyCode === 'ENOENT') {
            throw new FixFleetError(
                'cli_missing',
                0,
                "FixFleet CLI not found on PATH. Install: pip3 install --user fixfleet",
            );
        }
        throw pyErr;
    }
}

/** Unwrap a JSON API response, throwing a FixFleetError on `ok: false`. */
function unwrap<T>(res: any): T {
    if (!res || res.ok === false) {
        const code = res?.code || 'generic';
        const status = res?.status || 0;
        const msg = res?.error || 'Unknown error from FixFleet CLI.';
        throw new FixFleetError(code, status, msg);
    }
    return res as T;
}

export async function checkCliInstalled(): Promise<{ installed: boolean; version?: string }> {
    try {
        const result = await runJson(['--backends-json'], 10_000);
        return { installed: true, version: result.version };
    } catch {
        return { installed: false };
    }
}

export async function listBackends(): Promise<{ cli_backends: BackendInfo[]; api_presets: any[] }> {
    const res = await runJson(['--backends-json']);
    return unwrap(res);
}

export async function listBugs(opts: {
    token: string;
    projectUrl: string;
    date?: string;
    dateFrom?: string;
    dateTo?: string;
}): Promise<{ host: string; project_id: string; issues: BugIssue[] }> {
    const args = ['--list-bugs-json', '--token', opts.token, '--project-url', opts.projectUrl];
    if (opts.dateFrom) args.push('--date-from', opts.dateFrom);
    if (opts.dateTo) args.push('--date-to', opts.dateTo);
    if (opts.date && !opts.dateFrom && !opts.dateTo) args.push('--date', opts.date);

    const res = await runJson(args, 20_000);
    return unwrap(res);
}

export async function fixBug(opts: {
    issueIid: number;
    backend: string;
    token: string;
    projectUrl: string;
    projectDir: string;
}): Promise<FixResult> {
    const args = [
        '--fix-issue', String(opts.issueIid),
        '--backend', opts.backend,
        '--token', opts.token,
        '--project-url', opts.projectUrl,
        '--project-dir', opts.projectDir,
    ];
    return runJson(args, 900_000);
}
