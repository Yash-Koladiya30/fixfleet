/**
 * Thin wrapper around the `fixfleet` Python CLI.
 * Spawns subprocess, parses JSON output.
 */
import * as cp from 'child_process';
import * as vscode from 'vscode';

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

function cliCommand(): string {
    const cfg = vscode.workspace.getConfiguration('fixfleet');
    return cfg.get<string>('cliPath') || 'fixfleet';
}

function pythonCommand(): string {
    const cfg = vscode.workspace.getConfiguration('fixfleet');
    return cfg.get<string>('pythonPath') || 'python3';
}

/**
 * Run fixfleet with JSON args. Try direct binary first, then `python -m bugfixer.json_api`.
 * Strips ANSI noise from stdout, returns last JSON line.
 */
async function runJson(args: string[], timeoutMs = 120_000): Promise<any> {
    const tryRun = (cmd: string, fullArgs: string[]) =>
        new Promise<any>((resolve, reject) => {
            let child: cp.ChildProcessWithoutNullStreams;
            try {
                child = cp.spawn(cmd, fullArgs, {
                    env: { ...process.env, NO_COLOR: '1', PYTHONUNBUFFERED: '1' },
                });
            } catch (err) {
                reject(err);
                return;
            }
            let stdout = '';
            let stderr = '';
            const timer = setTimeout(() => {
                child.kill('SIGTERM');
                reject(new FixFleetError('timeout', 0, `FixFleet CLI timed out after ${Math.round(timeoutMs / 1000)}s.`));
            }, timeoutMs);

            child.stdout.on('data', d => (stdout += d.toString()));
            child.stderr.on('data', d => (stderr += d.toString()));

            child.on('error', err => {
                clearTimeout(timer);
                reject(err);
            });
            child.on('close', code => {
                clearTimeout(timer);
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

    try {
        return await tryRun(cliCommand(), args);
    } catch (e) {
        // ENOENT means binary not found — try the python module fallback.
        const code = (e as any)?.code;
        if (code === 'ENOENT' || code === 'EACCES') {
            try {
                return await tryRun(pythonCommand(), ['-m', 'bugfixer.json_api', ...args]);
            } catch (pyErr) {
                const pyCode = (pyErr as any)?.code;
                if (pyCode === 'ENOENT') {
                    throw new FixFleetError(
                        'cli_missing',
                        0,
                        "FixFleet CLI not installed. Run: pip3 install --user fixfleet",
                    );
                }
                throw pyErr;
            }
        }
        throw e;
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
}): Promise<{ host: string; project_id: string; issues: BugIssue[] }> {
    const args = ['--list-bugs-json', '--token', opts.token, '--project-url', opts.projectUrl];
    if (opts.date) args.push('--date', opts.date);

    const res = await runJson(args, 45_000);
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
