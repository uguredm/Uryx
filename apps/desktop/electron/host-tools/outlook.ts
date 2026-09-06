/** Klasik Outlook COM — Graph / New Outlook / model PowerShell yok. */

import { sanitizeSingleLine } from '../security';
import { runPowerShell } from './process';

const MISSING = { found: false, provider: null, items: [] as Record<string, unknown>[] };

interface OutlookItem {
  title: string;
  start: string;
  end: string;
  location: string;
}

function clampInt(value: unknown, fallback: number, min: number, max: number): number {
  const n = Number(value ?? fallback);
  if (!Number.isFinite(n)) return fallback;
  return Math.max(min, Math.min(Math.trunc(n), max));
}

function parseOutlookPayload(raw: string): Record<string, unknown> {
  const text = raw.trim();
  if (!text) return { ...MISSING };
  try {
    const parsed = JSON.parse(text) as {
      found?: boolean;
      provider?: string | null;
      items?: unknown;
    };
    if (!parsed.found) return { ...MISSING };
    const items: OutlookItem[] = (Array.isArray(parsed.items) ? parsed.items : []).flatMap(
      (row) => {
        if (!row || typeof row !== 'object') return [];
        const item = row as Record<string, unknown>;
        return [
          {
            title: sanitizeSingleLine(item.title ?? '', 200),
            start: sanitizeSingleLine(item.start ?? '', 40),
            end: sanitizeSingleLine(item.end ?? '', 40),
            location: sanitizeSingleLine(item.location ?? '', 160),
          },
        ];
      },
    );
    return { found: true, provider: 'outlook', items };
  } catch {
    return { ...MISSING };
  }
}

function outlookComScript(folder: 9 | 13, days: number, limit: number): string {
  const dateProp = folder === 9 ? 'Start' : 'DueDate';
  const endProp = folder === 9 ? 'End' : 'DueDate';
  const locExpr = folder === 9 ? '[string]$it.Location' : "''";
  return (
    `$ErrorActionPreference = 'Stop'; ` +
    `try { $ol = New-Object -ComObject Outlook.Application } catch { ` +
    `'{"found":false,"provider":null,"items":[]}'; exit 0 }; ` +
    `try { $ns = $ol.GetNamespace('MAPI'); $folder = $ns.GetDefaultFolder(${folder}); ` +
    `$items = $folder.Items; $items.IncludeRecurrences = $true; $items.Sort('[${dateProp}]'); ` +
    `$culture = [cultureinfo]::GetCultureInfo('en-US'); $start = Get-Date; $end = $start.AddDays(${days}); ` +
    `$filter = "[${dateProp}] >= '" + $start.ToString('g', $culture) + "' AND [${dateProp}] <= '" + $end.ToString('g', $culture) + "'"; ` +
    `$restricted = $items.Restrict($filter); $out = @(); $n = 0; ` +
    `foreach ($it in $restricted) { ` +
    `  if ($n -ge ${limit}) { break }; ` +
    `  $title = [string]$it.Subject; ` +
    `  $s = ''; try { $s = ([datetime]$it.${dateProp}).ToString('o') } catch {}; ` +
    `  $e = ''; try { $e = ([datetime]$it.${endProp}).ToString('o') } catch {}; ` +
    `  $loc = ''; try { $loc = ${locExpr} } catch {}; ` +
    `  $out += [pscustomobject]@{ title = $title; start = $s; end = $e; location = $loc }; $n++ ` +
    `}; ` +
    `[pscustomobject]@{ found = $true; provider = 'outlook'; items = @($out) } | ConvertTo-Json -Compress -Depth 4 ` +
    `} catch { '{"found":false,"provider":null,"items":[]}' }`
  );
}

/** `list_calendar_events` — GetDefaultFolder(9), gövde yok. */
export async function listCalendarEvents(
  args: Record<string, unknown> = {},
): Promise<Record<string, unknown>> {
  if (process.env.VITEST || process.env.URYX_TEST_ROOT) return { ...MISSING };
  const days = clampInt(args.days, 7, 1, 31);
  const limit = clampInt(args.limit, 20, 1, 50);
  const result = await runPowerShell(outlookComScript(9, days, limit), { timeoutMs: 15_000 });
  return parseOutlookPayload(result.stdout);
}

/** `list_outlook_tasks` — GetDefaultFolder(13), gövde yok. */
export async function listOutlookTasks(
  args: Record<string, unknown> = {},
): Promise<Record<string, unknown>> {
  if (process.env.VITEST || process.env.URYX_TEST_ROOT) return { ...MISSING };
  const limit = clampInt(args.limit, 20, 1, 50);
  const result = await runPowerShell(outlookComScript(13, 31, limit), { timeoutMs: 15_000 });
  return parseOutlookPayload(result.stdout);
}
