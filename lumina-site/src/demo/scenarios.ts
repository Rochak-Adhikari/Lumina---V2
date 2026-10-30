/**
 * Demo scenarios. All files, people, numbers and folders here are fictional example data.
 * The demo never touches the visitor's computer.
 */

export type Permission = 'read' | 'think' | 'low' | 'change';

export const PERMISSION_LABEL: Record<Permission, string> = {
  think: 'Reasoning only',
  read: 'Read-only',
  low: 'Low-risk · confirmation configurable',
  change: 'Changes files · needs your approval',
};

export type StepKind = 'understand' | 'recall' | 'read' | 'plan' | 'approve' | 'act' | 'verify';

export interface StepDef {
  id: string;
  kind: StepKind;
  title: string;
  detail: string;
  permission: Permission;
  /** Simulated duration in ms. */
  duration: number;
  /** Evidence recorded when the step completes. */
  evidence?: string;
  /** Message used when the visitor asks the demo to simulate a problem at this step. */
  failMessage?: string;
  /** Evidence recorded when a retry succeeds after a simulated problem. */
  retryEvidence?: string;
}

export type ParamValue = string | boolean;

export interface ParamDef {
  id: string;
  label: string;
  type: 'select' | 'toggle';
  options?: { value: string; label: string }[];
  default: ParamValue;
  hint?: string;
}

export type Params = Record<string, ParamValue>;

export type ResultBlock =
  | { type: 'text'; text: string }
  | { type: 'list'; items: string[] }
  | { type: 'table'; head: string[]; rows: string[][] };

export interface Result {
  headline: string;
  blocks: ResultBlock[];
}

export interface Understanding {
  goal: string;
  constraints: string[];
  done: string;
}

export interface Approval {
  summary: string;
  items: string[];
  note: string;
}

export interface Scenario {
  id: string;
  label: string;
  request: string;
  keywords: RegExp[];
  params: ParamDef[];
  extract(text: string): Partial<Params>;
  understand(p: Params): Understanding;
  steps(p: Params): StepDef[];
  approval?(p: Params): Approval;
  /** Step id where "simulate a problem" applies, if any for these params. */
  failStep(p: Params): string | null;
  result(p: Params): Result;
  deniedResult?(p: Params): Result;
}

/* ───────────────────────── 1 · Brief ───────────────────────── */

const NOTES = ['Atlas-standup-Mon.md', 'Atlas-review-Wed.docx', 'Atlas-sync-Thu.md'];

const brief: Scenario = {
  id: 'brief',
  label: 'Write a brief',
  request: "Turn this week's Atlas meeting notes into a one-page brief and save it to my Briefs folder.",
  keywords: [/\bbrief\b/i, /summar/i, /meeting notes?/i, /\bnotes\b/i],
  params: [
    {
      id: 'length',
      label: 'Length',
      type: 'select',
      options: [
        { value: 'page', label: 'One page' },
        { value: 'half', label: 'Half a page' },
      ],
      default: 'page',
    },
    {
      id: 'style',
      label: 'Style',
      type: 'select',
      options: [
        { value: 'bullets', label: 'Bullet points' },
        { value: 'prose', label: 'Short paragraphs' },
      ],
      default: 'bullets',
    },
    { id: 'save', label: 'Save as a new file', type: 'toggle', default: true, hint: 'Off: just show the brief, change nothing.' },
  ],
  extract(text) {
    const p: Partial<Params> = {};
    if (/half/i.test(text)) p.length = 'half';
    else if (/one[- ]page|1[- ]page|full page/i.test(text)) p.length = 'page';
    if (/prose|paragraph/i.test(text)) p.style = 'prose';
    else if (/bullet/i.test(text)) p.style = 'bullets';
    if (/don'?t save|do not save|just show|only show/i.test(text)) p.save = false;
    else if (/\bsave\b|folder|file/i.test(text)) p.save = true;
    return p;
  },
  understand(p) {
    return {
      goal: "A brief of this week's Atlas meetings",
      constraints: [
        p.length === 'half' ? 'Half a page' : 'One page',
        p.style === 'prose' ? 'Short paragraphs' : 'Bullet points',
        p.save ? 'Save to Briefs as a new file' : 'Show it; change nothing',
      ],
      done: p.save ? 'The file exists, is the right length and cites every note.' : 'The brief is shown and cites every note.',
    };
  },
  steps(p) {
    const s: StepDef[] = [
      {
        id: 'understand',
        kind: 'understand',
        title: 'Understand the request',
        detail: 'Goal, constraints and what “done” means.',
        permission: 'think',
        duration: 700,
        evidence: 'Interpreted: brief · Atlas · this week',
      },
      {
        id: 'recall',
        kind: 'recall',
        title: 'Recall relevant context',
        detail:
          p.style === 'prose'
            ? 'Stored preference is bullet points — your request says paragraphs, so the request wins.'
            : 'Stored preference: one-page bullet briefs (you said so, 14 Oct).',
        permission: 'read',
        duration: 600,
        evidence: 'Memory: 1 preference, 1 fact (Atlas review moved to 3 Nov)',
      },
      {
        id: 'read',
        kind: 'read',
        title: 'Find and read the notes',
        detail: 'Atlas folder, modified this week.',
        permission: 'read',
        duration: 1000,
        evidence: `Read ${NOTES.length} files: ${NOTES.join(', ')}`,
      },
      {
        id: 'plan',
        kind: 'plan',
        title: 'Plan the brief',
        detail: p.save ? 'Draft → create Briefs\\Atlas-brief-week-43.docx → check it.' : 'Draft → show it here → check citations.',
        permission: 'think',
        duration: 500,
        evidence: p.save ? 'Plan: 3 steps, 1 needs approval' : 'Plan: 2 steps, read-only',
      },
    ];
    if (p.save) {
      s.push({
        id: 'approve',
        kind: 'approve',
        title: 'Your approval',
        detail: 'Creating a file is a change, so Lumina asks first.',
        permission: 'change',
        duration: 0,
      });
      s.push({
        id: 'act',
        kind: 'act',
        title: 'Write the new file',
        detail: 'Written atomically; nothing existing is overwritten.',
        permission: 'change',
        duration: 900,
        evidence: 'Created Briefs\\Atlas-brief-week-43.docx (journaled)',
        failMessage: 'The Briefs folder is open in another program and the write did not happen. Nothing was changed, and Lumina does not retry on its own.',
        retryEvidence: 'Retried after your go-ahead: file created (journaled)',
      });
    } else {
      s.push({
        id: 'act',
        kind: 'act',
        title: 'Compose the brief',
        detail: 'Shown here only — no files touched.',
        permission: 'think',
        duration: 800,
        evidence: `Draft composed from ${NOTES.length} notes`,
      });
    }
    s.push({
      id: 'verify',
      kind: 'verify',
      title: 'Verify the result',
      detail: p.save ? 'Reopen the file read-only; check length and citations.' : 'Check length and that every note is cited.',
      permission: 'read',
      duration: 600,
      evidence: p.save
        ? `File exists · ${p.length === 'half' ? '½ page' : '1 page'} · cites ${NOTES.length}/${NOTES.length} notes`
        : `${p.length === 'half' ? '½ page' : '1 page'} · cites ${NOTES.length}/${NOTES.length} notes`,
    });
    return s;
  },
  approval(p) {
    return {
      summary: 'Create one new file',
      items: [`Briefs\\Atlas-brief-week-43.docx  ·  new, ${p.length === 'half' ? '½ page' : '1 page'}`],
      note: 'No existing file will be changed. Approval covers exactly this file; changing it would need a new approval.',
    };
  },
  failStep(p) {
    return p.save ? 'act' : null;
  },
  result(p) {
    const points = [
      'Atlas design review moved to 3 November; slides due 31 October.',
      'Search latency fixed in staging; release candidate on Tuesday.',
      'Two open risks: vendor contract renewal and QA coverage on Windows 10.',
      'Owners: Maya — slides; Dev — release; Priya — vendor call.',
    ];
    const short = p.length === 'half' ? points.slice(0, 3) : points;
    const blocks: ResultBlock[] =
      p.style === 'prose'
        ? [
            { type: 'text', text: short.slice(0, 2).join(' ') },
            ...(short.length > 2 ? [{ type: 'text' as const, text: short.slice(2).join(' ') }] : []),
          ]
        : [{ type: 'list', items: short }];
    blocks.push({ type: 'text', text: `Sources: ${NOTES.join(' · ')}` });
    return {
      headline: p.save ? 'Saved: Briefs\\Atlas-brief-week-43.docx' : 'Brief ready — nothing was saved',
      blocks,
    };
  },
  deniedResult() {
    return {
      headline: 'Not saved — you declined',
      blocks: [{ type: 'text', text: 'No file was created. The draft stays in this conversation if you want to change it and ask again.' }],
    };
  },
};

/* ───────────────────────── 2 · Compare quotes (read-only) ───────────────────────── */

const QUOTES = [
  { file: 'Quote-Northwind.pdf', vendor: 'Northwind', subtotal: 1240, shipping: 85, days: 6 },
  { file: 'Quote-Aster.pdf', vendor: 'Aster Supply', subtotal: 1180, shipping: 160, days: 3 },
  { file: 'Quote-Kettle.pdf', vendor: 'Kettle & Co', subtotal: 1295, shipping: 0, days: 9 },
];

const money = (n: number) => `$${n.toLocaleString('en-US')}`;

const quotes: Scenario = {
  id: 'quotes',
  label: 'Compare quotes',
  request: 'Compare the three supplier quotes in Downloads and tell me which one is cheapest.',
  keywords: [/quote/i, /compare/i, /cheap/i, /supplier|vendor/i, /price|cost/i],
  params: [
    {
      id: 'criterion',
      label: 'Decide by',
      type: 'select',
      options: [
        { value: 'total', label: 'Lowest price' },
        { value: 'speed', label: 'Fastest delivery' },
      ],
      default: 'total',
    },
    { id: 'shipping', label: 'Include shipping', type: 'toggle', default: true },
  ],
  extract(text) {
    const p: Partial<Params> = {};
    if (/fast|quick|soon|delivery time/i.test(text)) p.criterion = 'speed';
    else if (/cheap|price|cost|lowest/i.test(text)) p.criterion = 'total';
    if (/without shipping|excluding shipping|ignore shipping/i.test(text)) p.shipping = false;
    return p;
  },
  understand(p) {
    return {
      goal: 'Pick the best of three supplier quotes',
      constraints: [p.criterion === 'speed' ? 'Fastest delivery wins' : 'Lowest price wins', p.shipping ? 'Shipping included' : 'Shipping excluded', 'Read-only'],
      done: 'An answer with the numbers it was based on, cross-checked against each quote.',
    };
  },
  steps() {
    return [
      { id: 'understand', kind: 'understand', title: 'Understand the request', detail: 'What “best” means here.', permission: 'think', duration: 600, evidence: 'Interpreted: compare · 3 quotes · Downloads' },
      { id: 'read', kind: 'read', title: 'Find the quotes', detail: 'PDFs in Downloads named like quotes.', permission: 'read', duration: 700, evidence: `Found ${QUOTES.length}: ${QUOTES.map((q) => q.file).join(', ')}` },
      {
        id: 'extract',
        kind: 'read',
        title: 'Extract the line items',
        detail: 'Tables, totals, shipping and delivery terms.',
        permission: 'read',
        duration: 1100,
        evidence: 'Extracted 3 tables · 21 line items',
        failMessage: 'Quote-Kettle.pdf is a scanned image with no text layer. Lumina reports that instead of guessing the numbers.',
        retryEvidence: 'Retried with the page image: 3 tables · 21 line items',
      },
      { id: 'plan', kind: 'plan', title: 'Compare', detail: 'Apply your criterion to like-for-like totals.', permission: 'think', duration: 500, evidence: 'Comparison computed' },
      { id: 'verify', kind: 'verify', title: 'Cross-check', detail: 'Line items must add up to each stated total.', permission: 'read', duration: 600, evidence: '3/3 totals match their line items' },
    ];
  },
  failStep() {
    return 'extract';
  },
  result(p) {
    const rows = QUOTES.map((q) => ({ ...q, total: q.subtotal + (p.shipping ? q.shipping : 0) }));
    const best =
      p.criterion === 'speed' ? [...rows].sort((a, b) => a.days - b.days)[0] : [...rows].sort((a, b) => a.total - b.total)[0];
    const why = p.criterion === 'speed' ? `delivers in ${best.days} days` : `${money(best.total)}${p.shipping ? ' including shipping' : ' before shipping'}`;
    return {
      headline: `${best.vendor} — ${why}`,
      blocks: [
        {
          type: 'table',
          head: ['Supplier', p.shipping ? 'Total (incl. shipping)' : 'Subtotal', 'Delivery'],
          rows: rows.map((r) => [r.vendor, money(r.total), `${r.days} days`]),
        },
        { type: 'text', text: 'Read-only: no files were changed, so nothing needed approval.' },
      ],
    };
  },
};

/* ───────────────────────── 3 · Reminder (low-risk, configurable) ───────────────────────── */

const DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
const TIMES = ['08:00', '09:00', '10:00', '11:00', '12:00', '13:00', '14:00', '15:00', '16:00', '17:00', '18:00'];

function parseTime(text: string): string | null {
  const m = text.match(/\b(?:at\s*)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b/i);
  if (!m || !/\bat\b|am|pm|:/i.test(m[0])) return null;
  let h = Number(m[1]);
  const min = m[2] ?? '00';
  const ap = m[3]?.toLowerCase();
  if (ap === 'pm' && h < 12) h += 12;
  if (ap === 'am' && h === 12) h = 0;
  if (h > 23 || Number(min) > 59) return null;
  return `${String(h).padStart(2, '0')}:${min}`;
}

const reminder: Scenario = {
  id: 'reminder',
  label: 'Set a reminder',
  request: 'Remind me to send the invoice on Friday at 10.',
  keywords: [/remind/i, /reminder/i, /don'?t let me forget/i],
  params: [
    { id: 'day', label: 'Day', type: 'select', options: DAYS.map((d) => ({ value: d, label: d })), default: 'Friday' },
    { id: 'time', label: 'Time', type: 'select', options: TIMES.map((t) => ({ value: t, label: t })), default: '10:00' },
    {
      id: 'confirm',
      label: 'Ask before low-risk actions',
      type: 'toggle',
      default: false,
      hint: 'A preference: low-risk actions can run directly or ask first.',
    },
  ],
  extract(text) {
    const p: Partial<Params> = {};
    const d = DAYS.find((day) => new RegExp(`\\b${day}\\b`, 'i').test(text));
    if (d) p.day = d;
    const t = parseTime(text);
    if (t) p.time = t;
    return p;
  },
  understand(p) {
    return {
      goal: 'Remind you to send the invoice',
      constraints: [`${p.day} at ${p.time}, your local time`, 'Fires once', p.confirm ? 'Ask before saving' : 'Save directly (low-risk)'],
      done: 'The reminder reads back correctly from the reminder store.',
    };
  },
  steps(p) {
    const s: StepDef[] = [
      { id: 'understand', kind: 'understand', title: 'Understand the request', detail: 'What, when, and in which time zone.', permission: 'think', duration: 600, evidence: `Interpreted: “send the invoice” · ${p.day} ${p.time}` },
      { id: 'check', kind: 'read', title: 'Check your schedule', detail: 'Look for a clashing reminder.', permission: 'read', duration: 600, evidence: 'No other reminder at that time' },
    ];
    if (p.confirm)
      s.push({ id: 'approve', kind: 'approve', title: 'Your confirmation', detail: 'You asked to confirm low-risk actions.', permission: 'low', duration: 0 });
    s.push(
      { id: 'act', kind: 'act', title: 'Save the reminder', detail: 'Stored durably so it survives a restart.', permission: 'low', duration: 700, evidence: 'Saved reminder (example id rem-5b21)' },
      { id: 'verify', kind: 'verify', title: 'Read it back', detail: 'Confirm what was stored, not what was intended.', permission: 'read', duration: 500, evidence: `Stored: ${p.day} ${p.time} · once · “send the invoice”` },
    );
    return s;
  },
  approval(p) {
    return {
      summary: 'Save one reminder',
      items: [`${p.day} at ${p.time} — “Send the invoice”`],
      note: 'You can cancel or move it at any time.',
    };
  },
  failStep() {
    return null;
  },
  result(p) {
    return {
      headline: `Reminder set for ${p.day} at ${p.time}`,
      blocks: [
        { type: 'list', items: ['What: send the invoice', `When: ${p.day}, ${p.time} (your local time)`, 'Fires once; survives a restart; cancel any time'] },
      ],
    };
  },
  deniedResult() {
    return { headline: 'No reminder saved', blocks: [{ type: 'text', text: 'You declined, so nothing was stored.' }] };
  },
};

/* ───────────────────────── 4 · Tidy downloads (approval) ───────────────────────── */

const FILES = [
  { name: 'vscode-setup-x64.exe', age: 41 },
  { name: 'python-3.13.1-amd64.exe', age: 52 },
  { name: 'node-v24.12.0-x64.msi', age: 33 },
  { name: 'obs-studio-installer.exe', age: 95 },
  { name: '7z-x64.exe', age: 120 },
  { name: 'zoom-installer.exe', age: 64 },
  { name: 'figma-setup.exe', age: 12 },
  { name: 'chrome-setup.exe', age: 5 },
];

const pickFiles = (p: Params) => FILES.filter((f) => f.age > Number(p.age));

const tidy: Scenario = {
  id: 'tidy',
  label: 'Tidy Downloads',
  request: 'Move installers older than 30 days out of Downloads into an Archive folder.',
  keywords: [/tidy|clean|organi[sz]e/i, /move/i, /installer/i, /download/i, /archive/i],
  params: [
    {
      id: 'age',
      label: 'Older than',
      type: 'select',
      options: [
        { value: '30', label: '30 days' },
        { value: '60', label: '60 days' },
        { value: '90', label: '90 days' },
      ],
      default: '30',
    },
    { id: 'preview', label: 'Preview only', type: 'toggle', default: false, hint: 'On: list what would move, change nothing.' },
  ],
  extract(text) {
    const p: Partial<Params> = {};
    const m = text.match(/(\d{2,3})\s*days?/i);
    if (m) {
      const n = Number(m[1]);
      p.age = n >= 90 ? '90' : n >= 60 ? '60' : '30';
    }
    if (/preview|dry[- ]run|what would|just list|don'?t move/i.test(text)) p.preview = true;
    return p;
  },
  understand(p) {
    return {
      goal: 'Move old installers out of Downloads',
      constraints: [`Installers older than ${p.age} days`, 'Into Downloads\\Archive', p.preview ? 'Preview only — change nothing' : 'Nothing deleted'],
      done: p.preview ? 'A list of what would move.' : 'Every listed file is in Archive and an undo journal exists.',
    };
  },
  steps(p) {
    const n = pickFiles(p).length;
    const s: StepDef[] = [
      { id: 'understand', kind: 'understand', title: 'Understand the request', detail: 'Which files, where to, and what must not happen.', permission: 'think', duration: 600, evidence: `Interpreted: installers · > ${p.age} days · Downloads\\Archive` },
      { id: 'scan', kind: 'read', title: 'Scan Downloads', detail: 'List installers and their ages.', permission: 'read', duration: 900, evidence: `Scanned 8 installers · ${n} older than ${p.age} days` },
      { id: 'plan', kind: 'plan', title: 'Plan the moves', detail: p.preview ? 'Preview only: list the files.' : `Move ${n} files; journal each move for undo.`, permission: 'think', duration: 500, evidence: p.preview ? 'Plan: preview, no changes' : `Plan: ${n} moves, 0 deletions` },
    ];
    if (!p.preview && n > 0) {
      s.push({ id: 'approve', kind: 'approve', title: 'Your approval', detail: 'Moving files changes them, so Lumina asks first.', permission: 'change', duration: 0 });
      s.push({
        id: 'act',
        kind: 'act',
        title: 'Move the files',
        detail: 'One at a time, each move journaled.',
        permission: 'change',
        duration: 1100,
        evidence: `Moved ${n}/${n} files · undo journal written`,
        failMessage: 'zoom-installer.exe is in use by another program. Lumina stopped before moving anything else and reports exactly what happened.',
        retryEvidence: `After you closed the program: moved ${n}/${n} files · undo journal written`,
      });
      s.push({ id: 'verify', kind: 'verify', title: 'Verify', detail: 'Every file is in Archive; none left behind.', permission: 'read', duration: 600, evidence: `${n} files present in Archive · 0 missing` });
    }
    return s;
  },
  approval(p) {
    const files = pickFiles(p);
    return {
      summary: `Move ${files.length} files into Downloads\\Archive`,
      items: files.map((f) => `${f.name}  ·  ${f.age} days old`),
      note: 'Nothing is deleted. Each move is journaled so it can be undone. Approval covers exactly these files.',
    };
  },
  failStep(p) {
    return !p.preview && pickFiles(p).length > 0 ? 'act' : null;
  },
  result(p) {
    const files = pickFiles(p);
    return {
      headline: p.preview ? `${files.length} files would move — nothing changed` : `Moved ${files.length} files into Downloads\\Archive`,
      blocks: [
        { type: 'list', items: files.map((f) => `${f.name} (${f.age} days)`) },
        { type: 'text', text: p.preview ? 'Preview only. Run again without preview to move them.' : 'Undo is available from the journal.' },
      ],
    };
  },
  deniedResult() {
    return { headline: 'Nothing moved — you declined', blocks: [{ type: 'text', text: 'Downloads is exactly as it was.' }] };
  },
};

export const SCENARIOS: Scenario[] = [brief, quotes, reminder, tidy];

export function defaults(s: Scenario): Params {
  const p: Params = {};
  for (const d of s.params) p[d.id] = d.default;
  return p;
}
