/**
 * Product content. Every capability status here is traceable to the Lumina project's own records;
 * see docs/CONTENT-SOURCES.md for the evidence behind each line. Do not upgrade a status without new evidence.
 */

export type Status = 'working' | 'dev' | 'roadmap';

export interface Capability {
  id: string;
  name: string;
  desc: string;
  limit?: string;
  status: Status;
}

export const CAPABILITIES: Capability[] = [
  // Working in the private build (recorded implementation + tests, October 2026)
  {
    id: 'voice',
    name: 'Voice conversation',
    desc: 'Real-time spoken conversation with live transcription — and text whenever you prefer.',
    status: 'working',
  },
  {
    id: 'files',
    name: 'Files & documents',
    desc: 'Reads PDF, Word, PowerPoint, Excel, CSV and JSON. Changes go through reviewed, journaled transactions with undo.',
    status: 'working',
  },
  {
    id: 'search',
    name: 'Web search with sources',
    desc: 'Structured results that keep their source and retrieval time. Page content is treated as untrusted evidence.',
    status: 'working',
  },
  {
    id: 'reminders',
    name: 'Reminders',
    desc: 'Time-zone-aware reminders that survive a restart and fire once.',
    status: 'working',
  },
  {
    id: 'browser',
    name: 'Supervised browser',
    desc: 'Navigates, reads, clicks and types in a separate automation profile.',
    limit: 'Submissions, purchases, uploads and downloads stay blocked.',
    status: 'working',
  },
  {
    id: 'screen',
    name: 'Screen context',
    desc: 'Captures a screen, window or region when you ask — never continuously, and never uploaded just because it exists.',
    status: 'working',
  },
  {
    id: 'memory',
    name: 'Memory & continuity',
    desc: 'Local memory with sources, corrections and forgetting, plus an inspector and a knowledge graph.',
    status: 'working',
  },
  {
    id: 'workers',
    name: 'Supervised workers',
    desc: 'Hands longer coding tasks to supervised agent workers you can watch and cancel.',
    status: 'working',
  },
  {
    id: 'proactive',
    name: 'Proactive notices',
    desc: 'Speaks up only for events you set up, like reminders and watches — never escalating into action on its own.',
    status: 'working',
  },
  // In development
  {
    id: 'control',
    name: 'Computer control',
    desc: 'Operating Windows apps with mouse and keyboard.',
    limit: 'Simulation-only until human approval can be authenticated end to end.',
    status: 'dev',
  },
  {
    id: 'skills',
    name: 'Skills',
    desc: 'Installable capabilities with reviewed manifests, declared permissions and sandboxed tests.',
    status: 'dev',
  },
  {
    id: 'resume',
    name: '“Where did we leave off?”',
    desc: 'Restart-proof summaries of the last verified step, the blocker and the next action.',
    status: 'dev',
  },
  // On the roadmap
  {
    id: 'devices',
    name: 'Connected devices',
    desc: 'Reaching Lumina from your phone through a supervised connection to your PC.',
    status: 'roadmap',
  },
  {
    id: 'cloud',
    name: 'Cloud continuity',
    desc: 'Optional, consented sync of reviewed memories across devices.',
    status: 'roadmap',
  },
  {
    id: 'offline',
    name: 'Offline models',
    desc: 'Core capabilities that keep working with local models.',
    status: 'roadmap',
  },
];

export const STATUS_LABEL: Record<Status, string> = {
  working: 'Working in the private build',
  dev: 'In development',
  roadmap: 'On the roadmap',
};

export interface MemoryItem {
  text: string;
  source: string;
  recorded: string;
  confidence: string;
  scope: string;
  history?: string;
}

/** Example memories. Fictional sample data that illustrates the record shape Lumina keeps. */
export const MEMORIES: MemoryItem[] = [
  {
    text: 'Prefers one-page briefs in bullet points.',
    source: 'You said so, in conversation',
    recorded: '14 Oct',
    confidence: 'High — your own words',
    scope: 'Preference · all projects',
  },
  {
    text: 'Atlas design review moved to 3 November.',
    source: 'Meeting notes, Atlas folder',
    recorded: '18 Oct',
    confidence: 'Medium — read from a document',
    scope: 'Fact · project Atlas',
    history: 'Replaced “27 October”. The older value is kept as history, not deleted.',
  },
  {
    text: 'Unfinished: reply to the landlord about the lease.',
    source: 'Task paused before sending',
    recorded: '20 Oct',
    confidence: 'Observed — task record',
    scope: 'Open loop · personal',
  },
  {
    text: 'Edits Python projects in VS Code.',
    source: 'Observed from tool use',
    recorded: '9 Oct',
    confidence: 'Medium — inferred, not stated',
    scope: 'Preference · development',
  },
];

export interface Destination {
  id: string;
  label: string;
  color: string;
  title: string;
  body: string;
  status: Status;
  href: string;
  linkText: string;
  /** Region on the tapestry, world units: [x0, y0, x1, y1]. */
  region: [number, number, number, number];
}

export const DESTINATIONS: Destination[] = [
  {
    id: 'voice',
    label: 'Voice',
    color: '#ffad5c',
    title: 'The amber thread is you.',
    body: 'Every piece of work starts as something you said or typed. Voice comes first, text is always there, and you can interrupt at any time.',
    status: 'working',
    href: '#intent',
    linkText: 'Revisit Intent',
    region: [-4.8, -0.9, -1.6, 0.6],
  },
  {
    id: 'memory',
    label: 'Memory',
    color: '#f3d38b',
    title: 'Knots you can untie.',
    body: 'Remembered preferences, decisions and open loops — each with a source and a confidence. Inspect, correct or forget any of them.',
    status: 'working',
    href: '#memory',
    linkText: 'Open the memory inspector',
    region: [-0.4, -2.9, 2.6, -1.2],
  },
  {
    id: 'plans',
    label: 'Plans',
    color: '#b9d4ff',
    title: 'Steps with checks.',
    body: 'Requests become plans: steps, risks, and how success will be verified. Simple things stay simple; complex work is broken down.',
    status: 'working',
    href: '#execution',
    linkText: 'Replay the loop',
    region: [-4.8, -2.9, -1.6, -1.0],
  },
  {
    id: 'approvals',
    label: 'Approvals',
    color: '#ff8f80',
    title: 'Nothing consequential without you.',
    body: 'File changes and outgoing messages wait for your explicit yes. Native computer control stays simulation-only until approvals can be authenticated end to end.',
    status: 'working',
    href: '#demo',
    linkText: 'Try an approval in the demo',
    region: [2.0, -0.9, 4.8, 0.7],
  },
  {
    id: 'skills',
    label: 'Skills',
    color: '#8fd6b0',
    title: 'New threads, same rules.',
    body: 'Reviewed, sandboxed skills will add capabilities through the same tool contract — permissions, timeouts and evidence included.',
    status: 'dev',
    href: '#capabilities',
    linkText: 'See capability status',
    region: [-1.4, 0.8, 1.8, 2.9],
  },
  {
    id: 'roadmap',
    label: 'Roadmap',
    color: '#9aa7c7',
    title: 'Where the loom grows next.',
    body: 'Phone access through your PC, consented cloud continuity and offline models are on the roadmap — not yet built.',
    status: 'roadmap',
    href: '#capabilities',
    linkText: 'See what is planned',
    region: [2.0, 1.0, 4.8, 2.9],
  },
];
