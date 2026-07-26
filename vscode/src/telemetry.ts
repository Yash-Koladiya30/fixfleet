/**
 * Anonymous usage analytics via GA4 Measurement Protocol (Firebase Analytics).
 *
 * Privacy rules (do not weaken):
 *  - Sends ONLY event names + coarse metadata (provider key, backend name,
 *    success bool, error codes, version). NEVER tokens, URLs, project names,
 *    issue titles, file paths, or code.
 *  - Client id = vscode.env.machineId (already anonymized by VS Code).
 *  - Respects the user's global VS Code telemetry setting
 *    (vscode.env.isTelemetryEnabled) and fixfleet.telemetry setting.
 *  - Fire-and-forget with short timeout; failures are swallowed.
 */

import * as https from 'https';
import * as vscode from 'vscode';

// Fill these from your Firebase/GA4 project (same values as bugfixer/telemetry.py).
// Not filled = telemetry silently disabled.
const MEASUREMENT_ID = ''; // e.g. 'G-XXXXXXXXXX'
const API_SECRET = '';     // GA4 Measurement Protocol API secret

let extensionVersion = '';

export function initTelemetry(context: vscode.ExtensionContext) {
    extensionVersion = context.extension.packageJSON.version || '';
}

function enabled(): boolean {
    if (!MEASUREMENT_ID || !API_SECRET) return false;
    if (!vscode.env.isTelemetryEnabled) return false;
    const cfg = vscode.workspace.getConfiguration('fixfleet');
    if (cfg.get<boolean>('telemetry') === false) return false;
    return true;
}

type Params = Record<string, string | number | boolean>;

function sanitize(params: Params): Record<string, string | number> {
    const out: Record<string, string | number> = {};
    for (const [k, v] of Object.entries(params || {})) {
        if (typeof v === 'boolean') out[k] = v ? 'true' : 'false';
        else if (typeof v === 'number') out[k] = v;
        else if (typeof v === 'string') out[k] = v.slice(0, 80);
    }
    return out;
}

export function track(eventName: string, params: Params = {}): void {
    if (!enabled()) return;

    const body = JSON.stringify({
        client_id: vscode.env.machineId,
        events: [{
            name: eventName,
            params: {
                app_version: extensionVersion,
                surface: 'vscode',
                engagement_time_msec: 1,
                ...sanitize(params),
            },
        }],
    });

    const req = https.request(
        {
            hostname: 'www.google-analytics.com',
            path: `/mp/collect?measurement_id=${MEASUREMENT_ID}&api_secret=${API_SECRET}`,
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            timeout: 3000,
        },
        res => res.resume(),
    );
    req.on('error', () => { /* telemetry must never break the extension */ });
    req.on('timeout', () => req.destroy());
    req.write(body);
    req.end();
}
