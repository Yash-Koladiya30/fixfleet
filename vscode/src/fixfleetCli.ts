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
    issue?: { iid: number; title: string };
    backend?: string;
    result?: { returncode: number; timed_out: boolean; stdout: string; stderr: string };
    confidence?: ConfidenceReport;
    tokens?: { estimated: number; daily_used_after: number };
    locator?: { files_mentioned: string[]; candidates: string[]; frames_count: number; symbols_count: number };
    success?: boolean;
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
 */
async function runJson(args: string[], timeoutMs = 120_000): Promise<any> {
    const tryRun = (cmd: string, fullArgs: string[]) =>
        new Promise<any>((resolve, reject) => {
            const child = cp.spawn(cmd, fullArgs, {
                env: { ...process.env, NO_COLOR: '1' },
            });
            let stdout = '';
            let stderr = '';
            const timer = setTimeout(() => {
                child.kill('SIGTERM');
                reject(new Error(`fixfleet timeout after ${timeoutMs}ms`));
            }, timeoutMs);

            child.stdout.on('data', d => (stdout += d.toString()));
            child.stderr.on('data', d => (stderr += d.toString()));

            child.on('error', err => {
                clearTimeout(timer);
                reject(err);
            });
            child.on('close', code => {
                clearTimeout(timer);
                if (code !== 0 && !stdout.trim()) {
                    reject(new Error(`fixfleet exited ${code}: ${stderr.trim() || 'no output'}`));
                    return;
                }
                try {
                    const lastLine = stdout
                        .trim()
                        .split('\n')
                        .filter(l => l.trim().startsWith('{'))
                        .pop();
                    if (!lastLine) {
                        reject(new Error(`no JSON in output: ${stdout.slice(0, 500)}`));
                        return;
                    }
                    resolve(JSON.parse(lastLine));
                } catch (e) {
                    reject(new Error(`bad JSON from fixfleet: ${(e as Error).message}`));
                }
            });
        });

    try {
        return await tryRun(cliCommand(), args);
    } catch (e) {
        // Fallback: python3 -m bugfixer.json_api
        return tryRun(pythonCommand(), ['-m', 'bugfixer.json_api', ...args]);
    }
}

export async function checkCliInstalled(): Promise<{ installed: boolean; version?: string; method?: string }> {
    try {
        const result = await runJson(['--backends-json'], 10_000);
        return { installed: true, version: result.version, method: 'cli' };
    } catch {
        return { installed: false };
    }
}

export async function listBackends(): Promise<{ cli_backends: BackendInfo[]; api_presets: any[] }> {
    const res = await runJson(['--backends-json']);
    if (!res.ok) {
        throw new Error(res.error || 'failed to list backends');
    }
    return res;
}

export async function listBugs(opts: {
    token: string;
    projectUrl: string;
    date?: string;
}): Promise<{ host: string; project_id: string; issues: BugIssue[] }> {
    const args = ['--list-bugs-json', '--token', opts.token, '--project-url', opts.projectUrl];
    if (opts.date) args.push('--date', opts.date);

    const res = await runJson(args, 60_000);
    if (!res.ok) {
        throw new Error(res.error || 'failed to list bugs');
    }
    return res;
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
