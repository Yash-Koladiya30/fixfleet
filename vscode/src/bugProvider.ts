/**
 * TreeView data provider — shows GitLab bugs in the FixFleet sidebar.
 */
import * as vscode from 'vscode';
import { BugIssue, listBugs } from './fixfleetCli';

const PRIORITY_RANK: Record<string, number> = {
    High: 0,
    Medium: 1,
    Low: 2,
};

export class BugTreeItem extends vscode.TreeItem {
    constructor(public readonly bug: BugIssue) {
        super(`#${bug.iid}  ${bug.title}`, vscode.TreeItemCollapsibleState.None);
        this.contextValue = 'bug';
        this.tooltip = this.buildTooltip();
        this.description = this.buildDescription();
        this.iconPath = this.pickIcon();
        this.command = {
            command: 'fixfleet.openBug',
            title: 'Open Bug Detail',
            arguments: [bug],
        };
    }

    private buildTooltip(): vscode.MarkdownString {
        const md = new vscode.MarkdownString('', true);
        md.appendMarkdown(`**#${this.bug.iid}** — ${this.bug.title}\n\n`);
        if (this.bug.labels.length) {
            md.appendMarkdown(`**Labels:** ${this.bug.labels.map(l => `\`${l}\``).join(' ')}\n\n`);
        }
        if (this.bug.author) {
            md.appendMarkdown(`**Author:** ${this.bug.author}\n\n`);
        }
        md.appendMarkdown(`**Created:** ${this.bug.created_at.slice(0, 10)}\n\n`);
        if (this.bug.sections.steps) {
            md.appendMarkdown(`**Steps:**\n${this.bug.sections.steps.slice(0, 300)}\n\n`);
        }
        md.appendMarkdown(`[Open in GitLab](${this.bug.web_url})`);
        return md;
    }

    private buildDescription(): string {
        const priority = this.bug.labels.find(l => l in PRIORITY_RANK) || '';
        const fixed = this.bug.already_fixed ? ' ✓' : '';
        return `${priority}${fixed}`;
    }

    private pickIcon(): vscode.ThemeIcon {
        if (this.bug.already_fixed) {
            return new vscode.ThemeIcon('check', new vscode.ThemeColor('charts.green'));
        }
        const priority = this.bug.labels.find(l => l in PRIORITY_RANK);
        if (priority === 'High') {
            return new vscode.ThemeIcon('flame', new vscode.ThemeColor('charts.red'));
        }
        if (priority === 'Medium') {
            return new vscode.ThemeIcon('warning', new vscode.ThemeColor('charts.yellow'));
        }
        if (priority === 'Low') {
            return new vscode.ThemeIcon('info', new vscode.ThemeColor('charts.blue'));
        }
        return new vscode.ThemeIcon('bug');
    }
}

export class BugProvider implements vscode.TreeDataProvider<BugTreeItem> {
    private _onDidChangeTreeData = new vscode.EventEmitter<void>();
    readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

    private bugs: BugIssue[] = [];
    private lastError: string | null = null;
    private host = '';
    private projectId = '';

    refresh(): void {
        this._onDidChangeTreeData.fire();
    }

    getTreeItem(element: BugTreeItem): vscode.TreeItem {
        return element;
    }

    async getChildren(): Promise<BugTreeItem[]> {
        const cfg = vscode.workspace.getConfiguration('fixfleet');
        const token = cfg.get<string>('gitlabToken') || '';
        const projectUrl = cfg.get<string>('projectUrl') || '';
        const date = cfg.get<string>('dateFilter') || '';

        if (!token || !projectUrl) {
            this.lastError = 'Missing GitLab token or project URL — configure in FixFleet settings.';
            return [];
        }

        try {
            const result = await listBugs({ token, projectUrl, date: date || undefined });
            this.bugs = result.issues || [];
            this.host = result.host;
            this.projectId = result.project_id;
            this.lastError = null;

            // Sort by priority then by created date desc
            this.bugs.sort((a, b) => {
                const pa = a.labels.find(l => l in PRIORITY_RANK);
                const pb = b.labels.find(l => l in PRIORITY_RANK);
                const ra = pa ? PRIORITY_RANK[pa] : 99;
                const rb = pb ? PRIORITY_RANK[pb] : 99;
                if (ra !== rb) return ra - rb;
                return (b.created_at || '').localeCompare(a.created_at || '');
            });

            return this.bugs.map(b => new BugTreeItem(b));
        } catch (e) {
            this.lastError = (e as Error).message;
            vscode.window.showErrorMessage(`FixFleet: ${this.lastError}`);
            return [];
        }
    }

    getProjectMeta() {
        return { host: this.host, projectId: this.projectId };
    }

    getBugs() {
        return this.bugs;
    }

    getError() {
        return this.lastError;
    }
}
