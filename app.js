/* 建模议事厅 · frontend-only MVP
 * The mock event stream mirrors agent-collab/v1 envelopes. Replace dispatch()
 * with WebSocket/SSE calls when the FastAPI gateway is connected.
 */

const queryParams = new URLSearchParams(window.location.search);
function resolveLiveApi(raw) {
  if (!raw && !queryParams.has('live')) return '';
  const candidate = raw || window.location.origin;
  try {
    const url = new URL(candidate, window.location.origin);
    const loopback = new Set(['localhost', '127.0.0.1', '[::1]', '::1']).has(url.hostname);
    if (url.origin === window.location.origin || loopback) return url.origin;
  } catch (_) { /* the caller receives a visible blocked-state toast below */ }
  return '';
}
const requestedLiveApi = queryParams.get('api') || (queryParams.has('live') ? window.location.origin : '');
const LIVE_API = resolveLiveApi(requestedLiveApi);
const LIVE_API_BLOCKED = Boolean(requestedLiveApi && !LIVE_API);
// Fixture revisions are intentionally human-readable and are not hashes of a
// real contest input. A live snapshot replaces all three values with the
// server-issued manifest/control revisions.
const DEMO_INPUT_REVISION = 'fixture:2016-2025-exemplar-sample-v1';
const LIVE_PROJECT = 'HGC-MF-2026-001';
const DEMO_CONTEXT = Object.freeze({
  projectId: 'HGC-MF-2026-001',
  runId: 'RUN-MF-2026-0831',
  inputRevision: DEMO_INPUT_REVISION,
  worktreeRevision: 'fixture:modeling-first-ui-v2',
  controlRevision: 'fixture:run-bootstrap-v1',
  mode: 'simulated',
  sourceStatus: 'fixture',
  sourceLabel: 'SIMULATED · fixture',
});
let runtimeContext = { ...DEMO_CONTEXT, mode: LIVE_API ? 'live' : 'simulated', sourceStatus: LIVE_API ? 'connecting' : 'fixture', sourceLabel: LIVE_API ? 'LIVE · connecting' : DEMO_CONTEXT.sourceLabel };
let liveSocket = null;
let liveRevision = null;
let liveSeq = 0;
let liveReconnectTimer = null;
let liveConnected = false;
const seenLiveEvents = new Set();
const pendingLiveEvents = new Map();
let replayPromise = null;
const seenSnapshotMessages = new Set();
let knowledgeState = { summary: null, results: [], query: '', loading: false, indexRevision: null };
// Versioned repository context is mounted separately from the user's private
// materials pack.  Keeping the two snapshots distinct prevents a skill/README
// pointer from being mistaken for a mathematical source claim.
let workspaceState = { catalog: null, results: [], query: '', loading: false, revision: null, integrity: null };
let capabilityState = {
  catalog: null,
  loading: false,
  revision: null,
  mode: 'standard',
  assembly: { nodes: [], edges: [], presetId: null, archetypeId: null, validation: null, revision: null, diff: null, previousNodes: [], previousEdges: [], committedRevision: null, innovationCard: null, previousInnovationCard: null, contentPackIds: [], previousContentPackIds: [], contentPackEvidenceRefs: [], contentPackEvidenceByPack: {}, contentPackIndexRevision: null, contentPackResolutionRevision: null, methodBlockWarnings: [] },
  problemContract: null,
};
// Share one in-flight catalogue request across the compact legacy panel and
// the full puzzle studio.  The local materials index can be large; duplicate
// refreshes during the fixture→live handoff only add latency and can make two
// callers observe different revisions.
let capabilityCatalogPromise = null;
// Monotonic client-side fence: several UI actions can trigger compose calls
// close together (preset change + content-pack toggle + explicit check).  An
// older response must never overwrite the newer graph's validation/diff.
let assemblyValidationEpoch = 0;

// The shell has several social-chat surfaces (conversation tabs, channels,
// threads and an event stream).  Keep their view state in one small client
// projection so a click always changes something observable and the same
// state can be reconstructed after a live snapshot.  These values never
// masquerade as server facts: local-only changes are labelled as such in the
// UI and are intentionally not sent to an external provider.
let activeConversationFilter = 'all';
let activeChannel = '主议事群';
let collaborationPaused = false;
let eventRows = [];
let localApprovals = [];
let localAttachments = [];
let localChannels = [];
let threadRoots = [];
let notificationRead = false;
let modalReturnFocus = null;

function newClientId(prefix = 'ui') {
  try {
    if (window.crypto?.randomUUID) return `${prefix}-${window.crypto.randomUUID()}`;
  } catch (_) { /* old browsers / restricted contexts */ }
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function localStoreGet(key, fallback) {
  try {
    const value = window.localStorage.getItem(key);
    return value === null ? fallback : JSON.parse(value);
  } catch (_) {
    return fallback;
  }
}

function localStoreSet(key, value) {
  try { window.localStorage.setItem(key, JSON.stringify(value)); } catch (_) { /* private mode */ }
}

try {
  activeChannel = String(localStoreGet('qingjia.activeChannel', activeChannel) || activeChannel);
  activeConversationFilter = String(localStoreGet('qingjia.conversationFilter', activeConversationFilter) || activeConversationFilter);
  collaborationPaused = Boolean(localStoreGet('qingjia.collaborationPaused', false));
  localChannels = Array.isArray(localStoreGet('qingjia.localChannels', [])) ? localStoreGet('qingjia.localChannels', []) : [];
} catch (_) { /* keep deterministic defaults */ }

const capabilityContentPacks = [
  { id: 'problem-evidence', title: '题面证据', note: '题面、附件、单位与约束', query: '历年赛题 附件 约束 单位' },
  { id: 'paper-structure', title: '范文结构', note: '问题分析、模型链、验证章节', query: '优秀论文 问题分析 模型假设 验证' },
  { id: 'method-code', title: '方法与代码', note: '算法入口、参数与复现线索', query: '模型算法 代码 参数 复现' },
  { id: 'counterexample', title: '反例与边界', note: '敏感性、失败模式、禁用条件', query: '敏感性分析 误差 适用条件 反例' },
  { id: 'paper-template', title: '写作模板', note: '摘要、三线表、排版与答辩', query: '论文模板 写作规范 三线表 答辩' },
];

// The Xiao-Qinglong IP is the visual language for all dynamic UI symbols.
// Keep the paths local and deterministic: these are decoration only, while
// the adjacent text remains the accessible source of truth for identity and
// status.  The static shell uses the same asset family.
const DRAGON_ASSETS = Object.freeze({
  mark: 'assets/ip/xiao-qinglong-mark-v1.png',
  face: 'assets/ip/xiao-qinglong-face-v3.png',
  avatar: 'assets/ip/xiao-qinglong-avatar-v1.png',
  mascot: 'assets/ip/xiao-qinglong-mascot-v1.png',
  data: 'assets/ip/xiao-qinglong-data-v1.png',
  question: 'assets/ip/xiao-qinglong-question-v1.png',
  thinking: 'assets/ip/xiao-qinglong-thinking-v1.png',
  verified: 'assets/ip/xiao-qinglong-verified-v1.png',
});

// Motion is deliberately kept separate from the static icon map.  The v3
// clip is a short, cleaned candidate asset: it is suitable for a one-shot
// identity preview, but its seam has not been accepted as a permanent loop.
const DRAGON_MOTION_ASSETS = Object.freeze({
  idle: Object.freeze({
    src: 'assets/ip/xiao-qinglong-idle-v3.mp4',
    poster: 'assets/ip/xiao-qinglong-idle-v3-poster.png',
    loop: false,
    review: 'candidate:one-shot',
  }),
});

const DRAGON_MEMBER_ASSETS = Object.freeze({
  // Identity surfaces use the same simplified face; affordances/statuses use
  // the companion line mark. This keeps the IP legible without turning every
  // row into a large illustration.
  scope: 'question',
  data: 'data',
  routeA: 'thinking',
  routeB: 'avatar',
  critic: 'question',
  validator: 'verified',
  owner: 'face',
});

const DRAGON_STATUS_ASSETS = Object.freeze({
  pass: 'mark',
  verified: 'mark',
  accepted: 'mark',
  released: 'mark',
  produced: 'mark',
  active: 'mark',
  in_progress: 'mark',
  review: 'mark',
  ready_for_review: 'mark',
  warn: 'mark',
  unverified: 'mark',
  blocked: 'mark',
  wait: 'mark',
  queued: 'mark',
  pending: 'mark',
  pending_relay: 'mark',
  local_pending: 'mark',
});

const members = [
  { id: 'scope', name: 'Scope-Lock', title: '题面哨兵 · 范围锁定', model: 'Claude · Opus（独立上下文）', shortModel: 'Claude Opus', avatar: 'S', color: 'agent-blue', state: '在线', presence: 'online', task: 'G1 题面契约' },
  { id: 'data', name: 'Data-Auditor', title: '数据工程 · 质量审计', model: 'Qoder · Tool/Code Profile', shortModel: 'Qoder', avatar: 'D', color: 'agent-teal', state: '工作中', presence: 'busy', task: 'G3 数据体检' },
  { id: 'routeA', name: 'Model-A', title: '独立方案 A · 机制路线', model: 'Codex · GPT-5.6 Terra', shortModel: 'GPT-5.6 Terra', avatar: 'A', color: 'agent-violet', state: '工作中', presence: 'busy', task: 'G6-A 路线提案' },
  { id: 'routeB', name: 'Model-B', title: '独立方案 B · 统计路线', model: 'Claude · Independent Reasoner', shortModel: 'Claude Independent', avatar: 'B', color: 'agent-amber', state: '待审查', presence: 'online', task: 'G6-B 路线提案' },
  { id: 'critic', name: 'Critic', title: '对抗审查 · 反例构造', model: 'Antigravity · Gemini（待 relay）', shortModel: 'Gemini', avatar: 'C', color: 'agent-rose', state: '待 relay', presence: 'pending', task: 'G7 方案评分' },
  { id: 'validator', name: 'Validator', title: '独立验证 · 不确定性', model: 'Codex · GPT-5.5', shortModel: 'GPT-5.5', avatar: 'V', color: 'agent-slate', state: '等待集成', presence: 'online', task: 'G14 验证门' },
];

const tasks = [
  { id: 'G1', title: '题面契约与覆盖表', owner: 'Scope-Lock', meta: 'fixture 投影 · 题面未导入，不能核验', state: 'produced', status: 'PRODUCED', subproblemId: 'Q1', icon: '·' },
  { id: 'G3', title: '数据质量与泄漏审计', owner: 'Data-Auditor', meta: '正在处理 · 68%', state: 'active', status: 'IN_PROGRESS', subproblemId: 'Q2', icon: '↗' },
  { id: 'G5', title: '子问题数学化与接口契约', owner: 'Coordinator', meta: '等待 G3/G4 汇合', state: 'wait', status: 'QUEUED', subproblemId: 'Q2', icon: '·' },
  { id: 'G6-A', title: '独立路线 A：机制 + 优化', owner: 'Model-A', meta: '等待关键参数', state: 'wait', status: 'QUEUED', subproblemId: 'Q3', icon: '…' },
  { id: 'G6-B', title: '独立路线 B：统计 + 仿真', owner: 'Model-B', meta: '提案已提交 · READY_FOR_REVIEW', state: 'review', status: 'READY_FOR_REVIEW', subproblemId: 'Q3', icon: '✓' },
  { id: 'G7', title: 'Critic 评分与反例', owner: 'Critic', meta: '3 个 P1 风险', state: 'blocked', status: 'BLOCKED', subproblemId: 'Q4', icon: '!' },
  { id: 'G9', title: '群主路线审批', owner: '你 · Owner', meta: '需要你的裁决', state: 'wait', status: 'QUEUED', subproblemId: 'Q3', icon: '◆' },
  { id: 'G10', title: '数据管线与基线实现', owner: 'Data-Auditor', meta: '未开始', state: 'wait', status: 'QUEUED', subproblemId: 'Q2', icon: '·' },
];

const decisions = [
  { id: 'dec-1', title: '是否采用路线 B 作为主线？', body: 'Critic 认为 B 的可解释性更好，但对极端样本的外推仍需敏感性实验。', agent: 'C', color: 'agent-rose', label: '路线裁决' },
  { id: 'dec-2', title: '接受参数 θ 的先验范围吗？', body: 'Domain 专家给出 [0.15, 0.35]，来源已附 DOI；需要确认是否纳入主模型。', agent: 'D', color: 'agent-teal', label: '假设审批' },
  { id: 'dec-3', title: '批准将 Antigravity 加入独立审查？', body: '当前 relay 尚未完成身份与输入哈希确认，批准后才会发送冻结快照。', agent: 'A', color: 'antigravity-color', label: '外部授权' },
];

const evidence = [
  { icon: '§', title: 'problem_contract.yaml', status: 'PRODUCED', source: 'fixture', meta: 'Scope-Lock · fixture · 未独立复核', claimRefs: ['C-Q1-01'] },
  { icon: '▦', title: 'data_quality_report.md', status: 'READY_FOR_REVIEW', source: 'fixture', meta: 'Data-Auditor · 4 个异常待处理', claimRefs: ['C-DATA-02'] },
  { icon: '∑', title: 'route_B_spec.md', status: 'READY_FOR_REVIEW', source: 'fixture', meta: 'Model-B · 3 个复现入口 · 未验收', claimRefs: ['C-Q2-03'] },
  { icon: '⚑', title: 'critic_findings.json', status: 'BLOCKED', source: 'fixture', meta: 'Critic · 3 × P1 未关闭', claimRefs: ['C-17'] },
  { icon: '⌁', title: 'relay_antigravity.yaml', status: 'PENDING_RELAY', source: 'fixture', meta: '外部协作 · 输入哈希待 ACK', claimRefs: [] },
];

// These are deliberately generic fixture entities, not facts about a real
// contest problem.  The UI uses them to demonstrate the minimum modeling
// trace that a real problem must populate before a paper claim can pass a
// release gate.
const subproblems = [
  { id: 'Q1', title: '目标与边界', prompt: '等待真实题面：把目标、决策对象与硬约束逐句映射', deliverable: '问题契约 + 约束表', state: 'unverified', stateLabel: '题面待导入', coverage: '0/6 可核对', risk: 'prompt_refs 缺失', focus: 'scope', sourceStatus: 'fixture', promptRefs: [], variables: ['utility', 'cost'] },
  { id: 'Q2', title: '参数与机制', prompt: '等待真实题面：识别状态、参数、观测量及其可识别范围', deliverable: '变量/单位/假设登记', state: 'unverified', stateLabel: '来源待复核', coverage: '2/6 字段', risk: 'θ 先验待来源', focus: 'routeA', sourceStatus: 'fixture', promptRefs: [], variables: ['theta', 'cost'] },
  { id: 'Q3', title: '方案与算法', prompt: '等待真实题面：比较 baseline、主路线与 fallback 的接口', deliverable: '路线 spec + 算法入口', state: 'unverified', stateLabel: '接口待复核', coverage: '3/7 字段', risk: 'A/B 接口未对齐', focus: 'routeB', sourceStatus: 'fixture', promptRefs: [], variables: ['utility', 'violation'] },
  { id: 'Q4', title: '验证与决策', prompt: '等待真实题面：用题型匹配的检查支撑可写入论文的结论', deliverable: 'clean-run + claim map', state: 'blocked', stateLabel: 'P0 阻断', coverage: '0/6 可核对', risk: '题面与 clean-run 缺失', focus: 'critic', sourceStatus: 'fixture', promptRefs: [], variables: ['violation'] },
];

const modelChain = [
  { id: 'prompt', label: '题面句', detail: '待导入原文 / 页码', state: 'blocked' },
  { id: 'q', label: '小问 Q2', detail: '交付物待锁定', state: 'current' },
  { id: 'vars', label: '变量/单位', detail: 'θ · 元/期 · %', state: 'current' },
  { id: 'assumption', label: '假设', detail: '适用域 / 禁用条件', state: 'current' },
  { id: 'route', label: '路线 A/B', detail: 'baseline + fallback', state: 'current' },
  { id: 'algorithm', label: '算法', detail: '入口 / 容差 / 失败模式', state: 'current' },
  { id: 'validation', label: '验证', detail: '2 类互补检查', state: 'blocked' },
  { id: 'claim', label: '论文 claim', detail: '不可发布', state: 'blocked' },
];

const routeSpecs = [
  {
    id: 'routeA', name: '路线 A · 机制 + 优化', role: 'primary', badge: '候选主线',
    objective: '显式约束下最大化综合效用', baseline: '线性/规则 baseline',
    units: '效用 1 · 成本 元 · 覆盖率 %', provenance: '参数 θ：待 DOI/附件',
    applicability: '常规区间；边界情形需情景扰动', fallback: '退回可行基线 + 上下界',
    validation: '可行性 + 敏感性', status: 'IN_PROGRESS', warning: '量纲与 θ 来源尚未闭合',
    problemType: 'optimization',
    interfaces: { inputs: ['θ:无量纲', 'cost:元/期'], outputs: ['utility:无量纲', 'violation_rate:%'], granularity: '决策日 × 方案', provenance: 'fixture:data_dictionary-v2', disabledWhen: 'θ 来源或单位未核验' },
    validationChecks: [
      { kind: 'feasibility', label: '可行性/约束违反率', scope: '全场景', threshold: '≤ 5%', exitCode: null, resultHash: null },
      { kind: 'sensitivity', label: '参数敏感性', scope: 'θ ± 20%', threshold: '方向不反转', exitCode: null, resultHash: null },
    ],
  },
  {
    id: 'routeB', name: '路线 B · 统计 + 仿真', role: 'fallback', badge: '独立方案',
    objective: '在约束违反率 ≤ 5% 时稳健评估策略', baseline: '分层回归 baseline',
    units: '收益 元/期 · 违反率 % · 时间 日', provenance: 'data_dictionary v2（fixture）',
    applicability: '样本覆盖区间；极端样本禁用', fallback: '分位数规则 + 保守策略',
    validation: '滚动回测 + 10,000 次扰动', status: 'READY_FOR_REVIEW', warning: '极端外推仍有 P1 finding',
    problemType: 'simulation',
    interfaces: { inputs: ['x:观测量', 'horizon:日'], outputs: ['utility:元/期', 'risk:%'], granularity: '个体 × 时间窗', provenance: 'fixture:data_dictionary-v2', disabledWhen: '样本超出覆盖区间' },
    validationChecks: [
      { kind: 'rolling_backtest', label: '滚动回测', scope: '按时间隔离', threshold: '相对 baseline 不恶化', exitCode: 0, resultHash: null },
      { kind: 'perturbation', label: '扰动仿真', scope: '10,000 次；常规区间', threshold: '风险分位数可报告', exitCode: null, resultHash: null },
    ],
  },
];

// Structured modeling entities are deliberately separate from display text.
// A real snapshot must replace the fixture rows with prompt refs and hashes;
// missing fields remain visible as UNVERIFIED instead of being inferred.
const variableRegistry = [
  { id: 'theta', symbol: 'θ', role: '参数', unit: '无量纲', domain: '[0.15, 0.35]', sourceStatus: 'UNVERIFIED', provenance: 'fixture:data_dictionary-v2', evidenceRefs: [] },
  { id: 'cost', symbol: 'c', role: '成本', unit: '元/期', domain: '≥ 0', sourceStatus: 'UNVERIFIED', provenance: 'fixture:problem-contract', evidenceRefs: [] },
  { id: 'utility', symbol: 'U', role: '目标', unit: '无量纲', domain: '需题面定义', sourceStatus: 'UNVERIFIED', provenance: 'fixture:problem-contract', evidenceRefs: [] },
  { id: 'violation', symbol: 'r_v', role: '约束指标', unit: '%', domain: '[0, 100%]', sourceStatus: 'UNVERIFIED', provenance: 'fixture:validation-plan', evidenceRefs: [] },
];

const modelEdges = [
  { from: 'prompt', to: 'q', field: 'deliverable', unit: '—', granularity: '小问', provenance: 'fixture:problem-contract', status: 'UNVERIFIED' },
  { from: 'q', to: 'vars', field: 'variables/constraints', unit: 'mixed', granularity: 'Q2', provenance: 'fixture:problem-contract', status: 'UNVERIFIED' },
  { from: 'vars', to: 'route', field: 'θ,c,U,r_v', unit: 'mixed', granularity: '决策日 × 方案', provenance: 'fixture:data_dictionary-v2', status: 'UNVERIFIED' },
  { from: 'route', to: 'validation', field: 'result + baseline', unit: '元/期,%', granularity: '时间窗/场景', provenance: 'fixture:validation-plan', status: 'BLOCKED' },
  { from: 'validation', to: 'claim', field: 'metric + uncertainty', unit: '需定义', granularity: '报告范围', provenance: 'none', status: 'BLOCKED' },
];

const validationPlans = [
  { id: 'V-OPT-01', problemType: 'optimization', checkKinds: ['feasibility', 'sensitivity'], scope: '全部可行场景', threshold: '违反率 ≤ 5%；方向不反转', cleanRun: { command: '未接入真实题面', exitCode: null, resultHash: null }, status: 'UNVERIFIED' },
  { id: 'V-SIM-01', problemType: 'simulation', checkKinds: ['rolling_backtest', 'perturbation'], scope: '时间隔离 + 常规覆盖区间', threshold: '相对 baseline 不恶化；报告风险分位数', cleanRun: { command: '未接入真实题面', exitCode: null, resultHash: null }, status: 'BLOCKED' },
];

const problemContract = {
  sourceStatus: 'fixture',
  promptRefs: [],
  note: '演示不包含真实题面；导入 problem_contract 后才允许逐小问进入 VERIFIED。',
};

let releaseGate = { status: 'BLOCKED', paperClaims: { total: 0, unverified: 0 }, blockingTasks: ['fixture: no live release gate'], reason: 'SIMULATED fixture' };

const gateMatrix = [
  { id: 'scope', label: '题面覆盖', detail: '真实 problem_contract 尚未导入；不能从标题推断覆盖', status: 'unverified', statusLabel: 'UNVERIFIED' },
  { id: 'math', label: '数学化与量纲', detail: 'Q2 有 2 个单位/来源字段待补', status: 'warn', statusLabel: '待补齐' },
  { id: 'route', label: '路线接口', detail: 'A/B baseline、fallback 已列；接口待复核', status: 'warn', statusLabel: '待复核' },
  { id: 'finding', label: 'P0/P1 finding', detail: 'F-G7-01：极端外推未验证', status: 'blocked', statusLabel: '阻断' },
  { id: 'validation', label: '题型验证', detail: '需两类互补检查 + clean-run', status: 'blocked', statusLabel: '阻断' },
  { id: 'paper', label: '论文 claim 覆盖', detail: 'fixture claim 不具备 manifest provenance', status: 'blocked', statusLabel: '不可写入' },
  { id: 'release', label: '发布审计', detail: 'Owner approval + 清洁环境复现', status: 'blocked', statusLabel: '锁定' },
];

const FIXTURE_MODELING = JSON.parse(JSON.stringify({ subproblems, modelChain, routeSpecs, variableRegistry, modelEdges, validationPlans, gateMatrix }));

function restoreFixtureModeling() {
  subproblems.splice(0, subproblems.length, ...JSON.parse(JSON.stringify(FIXTURE_MODELING.subproblems)));
  modelChain.splice(0, modelChain.length, ...JSON.parse(JSON.stringify(FIXTURE_MODELING.modelChain)));
  routeSpecs.splice(0, routeSpecs.length, ...JSON.parse(JSON.stringify(FIXTURE_MODELING.routeSpecs)));
  variableRegistry.splice(0, variableRegistry.length, ...JSON.parse(JSON.stringify(FIXTURE_MODELING.variableRegistry)));
  modelEdges.splice(0, modelEdges.length, ...JSON.parse(JSON.stringify(FIXTURE_MODELING.modelEdges)));
  validationPlans.splice(0, validationPlans.length, ...JSON.parse(JSON.stringify(FIXTURE_MODELING.validationPlans)));
  gateMatrix.splice(0, gateMatrix.length, ...JSON.parse(JSON.stringify(FIXTURE_MODELING.gateMatrix)));
}

const modelingMetrics = [
  { value: '4/4', label: '小问骨架（非题面）', tone: 'warn' },
  { value: '0/4', label: '题面 prompt 已核验', tone: 'risk' },
  { value: '2/5', label: '互补验证已准备', tone: 'warn' },
  { value: 'BLOCKED', label: '发布 readiness', tone: 'risk' },
];

let messages = [
  { type: 'system', text: 'Coordinator 已创建 RUN-MF-2026-0831。输入快照已冻结；当前为 SIMULATED fixture，revision 仅用于演示链路。' },
  { type: 'date', text: '今天 14:18' },
  { id: 'm1', member: 'scope', time: '14:19', kind: '证据', text: '<strong>题面范围已锁定。</strong> A 题共 4 个小问，交付物包括最优策略、敏感性分析和可解释图表；附件 2 的单位与题干存在一处疑点，我已标为 <code>BLOCKED-1</code>。', tags: [['题面契约', 'blue'], ['BLOCKED-1', 'rose']], actions: ['查看原文映射', '打开 evidence'] },
  { id: 'm2', member: 'data', time: '14:21', kind: '进展', text: '数据表共 18,426 行、12 列。发现 2.1% 缺失、17 个重复键和一列疑似目标泄漏。我不会直接删除样本，先提交三种清洗方案及其影响。', tags: [['数据审计', 'teal'], ['泄漏风险', 'rose']] },
  { id: 'm3', member: 'routeB', time: '14:24', kind: '提案', text: '<strong>路线 B（统计 + 仿真）已提交。</strong> 以分层回归作为 baseline，以状态空间模型解释动态过程，最后用蒙特卡洛评估策略稳健性。所有参数均连接到 <code>data_dictionary v2</code>。', quote: { title: '独立方案 B · route_B_spec.md', text: '目标：在约束违反率 ≤ 5% 的条件下最大化综合效用；验证：滚动回测 + 10,000 次扰动。' }, tags: [['ROUTE-B', 'violet'], ['3 个验收命令', 'teal']], actions: ['比较 A/B', '查看公式'] },
  { id: 'm4', member: 'routeA', time: '14:27', kind: '提案', text: '<strong>路线 A 仍在推导。</strong> 我把机制约束写成混合整数模型，正在检查“成本”和“覆盖率”是否能在同一目标函数中合法归一。预计 14:36 提交。', tags: [['ROUTE-A', 'blue'], ['量纲检查中', 'amber']] },
  { id: 'm5', member: 'critic', time: '14:29', kind: '质疑', text: '<strong>发现 P1：路线 B 的极端样本外推没有证据。</strong> 当前回测只覆盖常规区间；若题目要求“最不利情形”，需要补充分位数敏感性或给出禁用条件。请 Model-B 在同一输入 revision 上回应。', tags: [['P1', 'rose'], ['需要反例', 'amber']], actions: ['发起反驳线程', '定位 claim C-17'] },
  { id: 'm6', member: 'validator', time: '14:31', kind: '验证', text: '我已从干净快照复跑路线 B 的 baseline：结果一致，随机种子 <code>20260831</code>，但状态空间模型尚未集成，当前只能标记为 <code>PRODUCED</code>，不能写入论文结论。', tags: [['clean snapshot', 'teal'], ['PRODUCED ≠ VERIFIED', 'amber']] },
  { id: 'm7', member: 'owner', time: '14:32', kind: '群主', text: '先不合并。@Data-Auditor 优先处理泄漏列，@Model-A 继续量纲检查；@Critic 请把 P1 的最小反例写进审查工件。等三项证据齐了我再裁决主路线。', tags: [['Owner 指令', 'blue'], ['冻结合并', 'amber']] },
];

const kindClass = { '提案': 'violet', '质疑': 'rose', '证据': 'teal', '验证': 'teal', '进展': 'blue', '群主': 'blue', '决策': 'amber', '审查': 'rose', '修复': 'teal', '外部协作': 'amber', '外部 ACK': 'teal', '复跑': 'violet', '派发': 'blue', '交接': 'amber', '心跳': 'teal', '回执': 'teal', '群聊': 'blue', '装配': 'violet', '待同步': 'amber' };

const defaultTaskByMember = { scope: 'G1', data: 'G3', routeA: 'G6-A', routeB: 'G6-B', critic: 'G7', validator: 'G14', owner: 'G9' };
const defaultQuestionByMember = { scope: 'Q1', data: 'Q2', routeA: 'Q3', routeB: 'Q3', critic: 'Q4', validator: 'Q4', owner: 'Q4' };

const VALID_CLAIM_CLASSES = new Set(['observed', 'derived', 'hypothesis']);
const VALID_PROVENANCE_STATUSES = new Set(['RECEIVED', 'PRODUCED', 'READY_FOR_REVIEW', 'VERIFIED', 'ACCEPTED', 'RELEASED', 'UNVERIFIED', 'BLOCKED', 'PENDING_RELAY', 'LOCAL_PENDING']);

function isSafeWorkspaceRef(value) {
  const candidate = String(value || '').trim();
  if (!candidate.toLowerCase().startsWith('repo:')) return false;
  const rel = candidate.slice(5);
  if (!rel || rel.length > 300 || rel.includes('\\') || rel.includes('\0') || rel.startsWith('/')) return false;
  const parts = rel.split('/');
  const roots = new Set(['README.md', 'TASKS.md', 'AGENTS.md', 'app.js', 'index.html', 'styles.css', 'docker-compose.yml', 'docs', 'skills', 'notes', 'workflows', 'models', 'paper', 'viz', 'scripts', 'experiments', 'backend', 'assets']);
  const sensitive = /(?:^|[._-])(secret|secrets|credential|credentials|password|passwd|token|api[_-]?key|private[_-]?key)(?:[._-]|$)/i;
  return Boolean(parts.length && roots.has(parts[0]) && parts.every(part => part && part !== '.' && part !== '..' && !part.startsWith('.') && !sensitive.test(part)));
}

function sanitizeEvidenceRefs(value) {
  if (!Array.isArray(value)) return [];
  const pattern = /^(?:artifact|run|claim|review|fixture):[^\s]+$|^kbdoc:kbdoc_[0-9a-f]{16}(?:#p\d+)?$|^kbchunk:kbchunk_kbdoc_[0-9a-f]{16}_\d+(?:#p\d+)?$/i;
  return value.filter(ref => typeof ref === 'string' && (pattern.test(ref.trim()) || isSafeWorkspaceRef(ref))).map(ref => ref.trim());
}

function normalizeProvenance(message, source = 'fixture') {
  const rawClass = message.claimClass ?? message.claim_class;
  const rawStatus = message.status;
  const claimClass = VALID_CLAIM_CLASSES.has(rawClass) ? rawClass : 'unknown';
  const evidenceRefs = sanitizeEvidenceRefs(message.evidenceRefs ?? message.evidence_refs);
  let status = VALID_PROVENANCE_STATUSES.has(rawStatus) ? rawStatus : 'UNVERIFIED';
  // A fixture has no artifact manifest. Never let a copied status badge turn
  // into a verified paper claim merely because it came from static data.
  if (source === 'fixture' && ['VERIFIED', 'ACCEPTED', 'RELEASED'].includes(status)) status = 'PRODUCED';
  // Live status is also fail-closed in the browser: the server must explicitly
  // attest that the referenced artifact manifest was checked before a release
  // state is shown. A bare status string is not evidence.
  if (['VERIFIED', 'ACCEPTED', 'RELEASED'].includes(status) && !(message.manifestLinked || message.manifest_linked) && evidenceRefs.length === 0) status = 'UNVERIFIED';
  return {
    ...message,
    source,
    sourceLabel: message.sourceLabel || (source === 'live' ? 'LIVE EVENT' : source === 'snapshot' ? 'LIVE SNAPSHOT' : source === 'local_pending' ? 'LOCAL_PENDING' : 'SIMULATED · fixture'),
    status,
    claimClass,
    evidenceRefs,
    targetRevision: message.targetRevision || message.target_revision || 'UNVERIFIED',
  };
}

function normalizeFixtureMessages(items) {
  return items.map((message, index) => {
    if (message.type === 'system' || message.type === 'date') return message;
    const member = getMember(message.member);
    const kind = message.kind || '进展';
    return normalizeProvenance({
      ...message,
      taskId: message.taskId || defaultTaskByMember[message.member] || `G${index + 1}`,
      subproblemId: message.subproblemId || defaultQuestionByMember[message.member] || 'Q1',
      modelProfile: message.modelProfile || member.shortModel || member.model,
      targetRevision: message.targetRevision || DEMO_INPUT_REVISION,
    }, 'fixture');
  });
}

messages = normalizeFixtureMessages(messages);

function escapeHTML(value) {
  return String(value ?? '').replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
}

/**
 * Render a local Xiao-Qinglong image as a decorative UI symbol.
 *
 * Dynamic rows still carry their human-readable labels and state text; the
 * image is intentionally hidden from assistive technology so it cannot
 * compete with that source of truth.  Pass { decorative: false, alt } only
 * when an image itself conveys information that is not present in nearby
 * text.  `className` is limited to internal, static class names and is
 * escaped before being inserted into HTML.
 */
function dragonIcon(kind = 'avatar', options = {}) {
  const opts = typeof options === 'string' ? { className: options } : (options || {});
  const key = Object.prototype.hasOwnProperty.call(DRAGON_ASSETS, kind) ? kind : 'face';
  const className = ['dragon-icon', `dragon-icon-${key}`, opts.className].filter(Boolean).join(' ');
  const decorative = opts.decorative !== false;
  const alt = decorative ? '' : String(opts.alt || '');
  const title = opts.title ? ` title="${escapeHTML(opts.title)}"` : '';
  const loading = opts.loading ? ` loading="${escapeHTML(opts.loading)}"` : '';
  return `<img class="${escapeHTML(className)}" data-dragon-asset="${escapeHTML(key)}" src="${escapeHTML(DRAGON_ASSETS[key])}" alt="${escapeHTML(alt)}"${decorative ? ' aria-hidden="true"' : ''}${title}${loading} decoding="async">`;
}

function dragonMemberAsset(memberOrId) {
  const id = typeof memberOrId === 'string' ? memberOrId : memberOrId?.id;
  return DRAGON_MEMBER_ASSETS[id] || 'face';
}

function dragonStatusAsset(status) {
  const key = String(status || '').trim().toLowerCase().replace(/\s+/g, '_');
  return DRAGON_STATUS_ASSETS[key] || 'mark';
}

function dragonEvidenceAsset(item, status) {
  // Evidence rows are intentionally quiet: the same monoline dragon mark
  // keeps the icon family coherent while filename/status text carries the
  // actual document semantics.
  return dragonStatusAsset(status);
}

function dragonDecisionMember(item) {
  const color = String(item?.color || '').toLowerCase();
  if (color.includes('antigravity')) return 'critic';
  const byInitial = { C: 'critic', D: 'data', A: 'routeA', B: 'routeB', V: 'validator', Z: 'owner' };
  return byInitial[String(item?.agent || '').trim().toUpperCase()] || 'owner';
}

// Expose the tiny adapter for future HTML fragments and test harnesses while
// keeping the canonical asset map immutable.
window.DRAGON_ASSETS = DRAGON_ASSETS;
window.DRAGON_MOTION_ASSETS = DRAGON_MOTION_ASSETS;
window.dragonIcon = dragonIcon;

/**
 * Mount the Xiao-Qinglong motion asset on identity surfaces only.
 *
 * The video is muted/autoplay/inline, pauses while the tab is hidden, and
 * falls back to the static face for reduced-motion preferences, autoplay
 * failures, media errors, and the end of this non-looping candidate clip.
 * Keeping this adapter in one place prevents every message/avatar from
 * starting a separate animation and leaves the larger modeling canvas quiet.
 */
function initDragonMotion() {
  const nodes = [...document.querySelectorAll('[data-dragon-motion]')];
  if (!nodes.length) return;

  const reducedQuery = typeof window.matchMedia === 'function'
    ? window.matchMedia('(prefers-reduced-motion: reduce)')
    : null;

  const setFallback = (node, state) => {
    node.classList.add('is-fallback');
    node.classList.remove('is-ended');
    if (state) node.dataset.motionState = state;
  };

  const setReduced = (node, video) => {
    video.pause();
    node.classList.add('motion-reduced', 'is-fallback');
    node.dataset.motionState = 'reduced-motion';
  };

  const playNode = (node, video) => {
    if (reducedQuery?.matches || node.classList.contains('is-ended')) return;
    const playResult = video.play();
    if (playResult && typeof playResult.catch === 'function') {
      playResult.catch(() => setFallback(node, 'autoplay-blocked'));
    }
  };

  nodes.forEach(node => {
    const video = node.querySelector('.brand-motion-video');
    if (!video) return;
    const key = node.dataset.dragonMotion || 'idle';
    const config = DRAGON_MOTION_ASSETS[key] || DRAGON_MOTION_ASSETS.idle;
    const poster = node.querySelector('.brand-motion-poster');

    video.muted = true;
    video.defaultMuted = true;
    video.playsInline = true;
    video.loop = node.dataset.motionLoop
      ? node.dataset.motionLoop === 'true'
      : config.loop === true;
    if (!video.getAttribute('poster')) video.setAttribute('poster', config.poster);
    if (poster && !poster.getAttribute('src')) poster.setAttribute('src', config.poster);
    node.dataset.motionReview = config.review;
    node.dataset.motionState = 'loading';
    node.classList.add('is-fallback');

    video.addEventListener('loadeddata', () => {
      if (reducedQuery?.matches) {
        setReduced(node, video);
        return;
      }
      node.classList.remove('is-fallback', 'motion-reduced', 'is-ended');
      node.dataset.motionState = 'playing';
      playNode(node, video);
    });
    video.addEventListener('playing', () => {
      if (!reducedQuery?.matches) {
        node.classList.remove('is-fallback', 'motion-reduced');
        node.dataset.motionState = 'playing';
      }
    });
    video.addEventListener('ended', () => {
      if (video.loop) return;
      video.pause();
      node.classList.add('is-ended', 'is-fallback');
      node.dataset.motionState = 'ended-fallback';
    });
    video.addEventListener('error', () => setFallback(node, 'media-error'));
    if (reducedQuery?.matches) setReduced(node, video);
    else playNode(node, video);
  });

  const onReducedChange = () => nodes.forEach(node => {
    const video = node.querySelector('.brand-motion-video');
    if (!video) return;
    if (reducedQuery?.matches) setReduced(node, video);
    else if (!node.classList.contains('is-ended')) {
      node.classList.remove('motion-reduced', 'is-fallback');
      node.dataset.motionState = 'resuming';
      playNode(node, video);
    }
  });
  if (reducedQuery?.addEventListener) reducedQuery.addEventListener('change', onReducedChange);
  else if (reducedQuery?.addListener) reducedQuery.addListener(onReducedChange);

  document.addEventListener('visibilitychange', () => {
    nodes.forEach(node => {
      const video = node.querySelector('.brand-motion-video');
      if (!video || reducedQuery?.matches) return;
      if (document.hidden) {
        video.pause();
        if (!node.classList.contains('is-ended')) node.dataset.motionState = 'paused-hidden';
      } else if (!node.classList.contains('is-ended') && !['media-error', 'autoplay-blocked'].includes(node.dataset.motionState)) {
        if (video.readyState >= 2) node.classList.remove('is-fallback');
        playNode(node, video);
      }
    });
  });
}

function getMember(id) {
  if (id === 'owner') return { id: 'owner', name: '你 · 群主', title: '裁决 / 发布 / 授权', model: 'Human Owner', shortModel: 'Owner', avatar: 'Z', color: 'owner-color' };
  return members.find(member => member.id === id) || members[0];
}

function compactRevision(value, length = 18) {
  const text = String(value || 'UNVERIFIED');
  return text.length > length ? `${text.slice(0, length)}…` : text;
}

function contextModeLabel() {
  if (runtimeContext.mode === 'live' && runtimeContext.sourceStatus === 'local_event_store') return 'LIVE · 本地事件源';
  if (runtimeContext.mode === 'live') return 'LIVE · 同步中';
  return 'SIMULATED · fixture';
}

function renderRuntimeContext() {
  const root = document.getElementById('runtimeContext');
  if (!root) return;
  root.dataset.projectId = runtimeContext.projectId || DEMO_CONTEXT.projectId;
  root.dataset.runId = runtimeContext.runId || DEMO_CONTEXT.runId;
  const source = document.getElementById('sourcePill');
  const revision = document.getElementById('contextRevision');
  const runId = document.getElementById('runIdLabel');
  const input = document.getElementById('inputRevisionLabel');
  const worktree = document.getElementById('worktreeRevisionLabel');
  const control = document.getElementById('controlRevisionLabel');
  if (source) {
    source.textContent = contextModeLabel();
    source.classList.toggle('live-source', runtimeContext.mode === 'live' && runtimeContext.sourceStatus === 'local_event_store');
  }
  if (revision) revision.textContent = `input ${compactRevision(runtimeContext.inputRevision)} · control ${compactRevision(runtimeContext.controlRevision)}`;
  if (runId) runId.textContent = runtimeContext.runId || 'UNVERIFIED';
  if (input) input.textContent = compactRevision(runtimeContext.inputRevision, 22);
  if (worktree) worktree.textContent = compactRevision(runtimeContext.worktreeRevision, 22);
  if (control) control.textContent = compactRevision(runtimeContext.controlRevision, 22);
  const heroStatus = document.getElementById('heroSourceStatus');
  const heroNote = document.getElementById('heroEmptyNote');
  const heroDot = document.querySelector('.hero-status-dot');
  if (heroStatus) {
    const hasPrompt = subproblems.some(item => Array.isArray(item.promptRefs) && item.promptRefs.length > 0);
    heroStatus.textContent = hasPrompt ? '题面已关联' : (runtimeContext.mode === 'live' ? '真实题面待导入' : '演示题面 · 未核验');
    if (heroDot) heroDot.classList.toggle('linked', hasPrompt);
  }
  if (heroNote) {
    heroNote.textContent = runtimeContext.mode === 'live' ? '导入 PDF → 抽取变量 → 审批路线' : '锁定题面 → 登记变量 → 比较路线';
  }
}

function setRuntimeContext(patch) {
  runtimeContext = { ...runtimeContext, ...patch };
  renderRuntimeContext();
  renderModelingOverview();
}

function routeAudit(route) {
  const interfaceData = route.interfaces || {};
  const requiredInterface = [interfaceData.inputs, interfaceData.outputs, interfaceData.granularity, interfaceData.provenance, interfaceData.disabledWhen];
  const missingInterface = requiredInterface.filter(value => !value || (Array.isArray(value) && value.length === 0)).length;
  const checks = Array.isArray(route.validationChecks) ? route.validationChecks : [];
  const completeChecks = checks.filter(check => Number(check.exitCode) === 0 && typeof check.resultHash === 'string' && /^[0-9a-f]{64}$/i.test(check.resultHash) && check.scope && check.threshold);
  const kinds = new Set(checks.map(check => check.kind).filter(Boolean));
  return { missingInterface, checks, completeChecks, distinctKinds: kinds.size, ready: missingInterface === 0 && completeChecks.length >= 2 && kinds.size >= 2 };
}

function routeFieldValue(value) {
  if (Array.isArray(value)) return value.join(' · ');
  if (value && typeof value === 'object') return value.label || value.value || JSON.stringify(value);
  return value || 'UNVERIFIED';
}

function renderValidationChecks(route) {
  const audit = routeAudit(route);
  return audit.checks.map(check => {
    const passed = Number(check.exitCode) === 0 && typeof check.resultHash === 'string' && /^[0-9a-f]{64}$/i.test(check.resultHash);
    return `<span class="validation-chip ${passed ? 'pass' : 'blocked'}"><b>${escapeHTML(check.kind || 'unknown')}</b><small>${escapeHTML(check.scope || 'scope UNVERIFIED')} · ${escapeHTML(check.threshold || 'threshold UNVERIFIED')} · ${passed ? 'hash linked' : 'clean-run/hash 待补'}</small></span>`;
  }).join('');
}

function renderModelingOverview() {
  const metricRoot = document.getElementById('modelingMetrics');
  const questionRoot = document.getElementById('subproblemStrip');
  const chainRoot = document.getElementById('modelChainStrip');
  const variableRoot = document.getElementById('variableStrip');
  if (!metricRoot || !questionRoot || !chainRoot) return;
  metricRoot.innerHTML = modelingMetrics.map(item => `<div class="modeling-metric ${item.tone}"><strong>${escapeHTML(item.value)}</strong><span>${escapeHTML(item.label)}</span></div>`).join('');
  const selected = subproblems.find(item => item.id === (window.selectedSubproblem || 'Q2')) || subproblems[1];
  questionRoot.innerHTML = subproblems.map(item => {
    const fullStateLabel = item.stateLabel || item.state || 'UNVERIFIED';
    const compactStateLabel = item.state === 'blocked'
      ? '阻断'
      : item.state === 'unverified'
        ? (String(fullStateLabel).includes('待') ? '待复核' : '未核验')
        : String(fullStateLabel).slice(0, 8);
    return `<button class="subproblem-card ${item.id === selected.id ? 'active' : ''}" data-subproblem="${escapeHTML(item.id)}" title="${escapeHTML(`${item.id} · ${fullStateLabel} · ${item.deliverable || ''}`)}"><span class="subproblem-card-head"><span class="subproblem-id">${escapeHTML(item.id)}</span><span class="subproblem-state ${item.state}" aria-label="${escapeHTML(fullStateLabel)}">${escapeHTML(compactStateLabel)}</span></span><strong>${escapeHTML(item.title)}</strong><span>${escapeHTML(item.coverage)} · ${escapeHTML(item.risk)}</span><em>${item.promptRefs?.length ? 'prompt linked' : 'prompt_refs UNVERIFIED'}</em></button>`;
  }).join('');
  chainRoot.innerHTML = modelChain.map((node, index) => `${index ? '<span class="chain-arrow">›</span>' : ''}<button class="chain-node ${node.state}" data-chain-node="${node.id}"><strong>${escapeHTML(node.label)}</strong><span>${escapeHTML(node.detail)}</span></button>`).join('');
  if (variableRoot) variableRoot.innerHTML = variableRegistry.slice(0, 8).map(item => `<div class="variable-pill"><b>${escapeHTML(item.symbol || item.id)}</b><span>${escapeHTML(item.unit || 'unit UNVERIFIED')}</span><em>${escapeHTML(item.sourceStatus || 'UNVERIFIED')}</em></div>`).join('');
  renderFocusCard(selected);
  renderRouteCompare();
  renderGateMatrix();
}

function renderFocusCard(selected) {
  const root = document.getElementById('focusCard');
  if (!root) return;
  const promptStatus = selected.promptRefs?.length ? 'linked' : 'UNVERIFIED · no prompt_refs';
  const variableNames = (selected.variables || []).map(id => variableRegistry.find(item => item.id === id)?.symbol || id).join(' · ') || 'UNVERIFIED';
  root.innerHTML = `<div class="focus-card-kicker"><span>当前小问 · ${escapeHTML(selected.id)}</span><span class="tag amber">${escapeHTML(selected.stateLabel)}</span></div><h3>${escapeHTML(selected.title)}</h3><p>${escapeHTML(selected.prompt)}</p><div class="focus-fields"><div class="focus-field"><span>题面来源</span><strong>${escapeHTML(promptStatus)}</strong></div><div class="focus-field"><span>交付物</span><strong>${escapeHTML(selected.deliverable)}</strong></div><div class="focus-field"><span>变量候选</span><strong>${escapeHTML(variableNames)}</strong></div><div class="focus-field"><span>责任 Agent</span><strong>${escapeHTML(getMember(selected.focus).name)}</strong></div><div class="focus-field risk"><span>最大阻断</span><strong>${escapeHTML(selected.risk)}</strong></div></div>`;
}

function renderRouteCompare() {
  const root = document.getElementById('routeCompare');
  if (!root) return;
  root.innerHTML = routeSpecs.map(route => {
    const audit = routeAudit(route);
    const interfaceData = route.interfaces || {};
    const interfaceText = `${routeFieldValue(interfaceData.inputs)} → ${routeFieldValue(interfaceData.outputs)}`;
    return `<article class="route-card ${route.role === 'primary' ? 'primary' : ''}"><div class="route-card-head"><strong>${escapeHTML(route.name)}</strong><span class="route-badge ${route.role === 'fallback' ? 'fallback' : ''}">${escapeHTML(route.badge)}</span></div><p>${escapeHTML(route.objective)}</p><div class="route-fields"><div class="route-field"><span>Baseline</span><b>${escapeHTML(route.baseline)}</b></div><div class="route-field"><span>接口（输入 → 输出）</span><b>${escapeHTML(interfaceText)}</b></div><div class="route-field"><span>单位/粒度</span><b>${escapeHTML(`${route.units} · ${interfaceData.granularity || 'UNVERIFIED'}`)}</b></div><div class="route-field"><span>参数 provenance</span><b>${escapeHTML(interfaceData.provenance || route.provenance || 'UNVERIFIED')}</b></div><div class="route-field"><span>适用/禁用</span><b>${escapeHTML(`${route.applicability}；${interfaceData.disabledWhen || '禁用条件 UNVERIFIED'}`)}</b></div><div class="route-field"><span>Fallback</span><b>${escapeHTML(route.fallback)}</b></div></div><div class="validation-checks">${renderValidationChecks(route)}</div><div class="route-warning">${escapeHTML(route.warning)} · ${escapeHTML(route.status)} · ${audit.ready ? '结构可审查' : `不可审批：接口缺 ${audit.missingInterface} 项 / clean-run ${audit.completeChecks.length}/2`}</div></article>`;
  }).join('');
}

function renderGateMatrix() {
  const root = document.getElementById('gateMatrix');
  if (!root) return;
  const blocked = gateMatrix.filter(item => item.status === 'blocked').length;
  const label = document.getElementById('gateCriticalLabel');
  if (label) label.textContent = `${blocked} 项阻断`;
  root.innerHTML = gateMatrix.map(gate => `<div class="gate-row"><span class="gate-icon ${gate.status}">${dragonIcon(dragonStatusAsset(gate.status), { className: 'dragon-gate-icon' })}</span><span class="gate-copy"><strong>${escapeHTML(gate.label)}</strong><span>${escapeHTML(gate.detail)}</span></span><span class="gate-status ${gate.status}">${escapeHTML(gate.statusLabel)}</span></div>`).join('');
  const progress = document.querySelector('.stage-progress');
  if (progress) {
    const total = gateMatrix.length || 1;
    const passed = gateMatrix.filter(item => item.status === 'pass').length;
    const width = releaseGate.status === 'READY' ? 100 : Math.max(12, Math.round((passed / total) * 100));
    progress.style.width = `${width}%`;
    progress.setAttribute('aria-valuenow', String(width));
  }
}

function renderMembers() {
  const list = document.getElementById('memberList');
  if (!list) return;
  const presenceClass = member => member.presence === 'busy' ? 'busy' : member.presence === 'pending' ? 'pending' : '';
  list.innerHTML = members.map(member => `
      <button class="member-item ${member.id === 'critic' ? 'active' : ''}" data-member="${member.id}" title="${escapeHTML(`${member.name} · ${member.title} · ${member.state}`)}">
      <div class="avatar ${member.color}">${dragonIcon(member.dragonAsset || dragonMemberAsset(member), { className: 'dragon-avatar' })}<span class="status-dot ${presenceClass(member)}"></span></div>
      <div class="member-copy"><strong>${escapeHTML(member.name)}</strong><span>${escapeHTML(member.title)}</span></div>
      <span class="member-presence ${presenceClass(member)}" title="${escapeHTML(member.state)}"></span>
    </button>`).join('');
}

/*
 * The reference layout keeps the current group roster close to the message
 * stream, like a social chat header.  This is a compact projection of the
 * same canonical `members` array used by the left roster: it never invents a
 * second identity source and remains keyboard/assistive-technology friendly.
 */
function renderMemberStrip() {
  const strip = document.getElementById('memberStrip');
  if (!strip) return;
  const roster = ['owner', ...members.map(member => member.id)];
  strip.innerHTML = roster.map(id => {
    const member = getMember(id);
    const isOwner = id === 'owner';
    const label = isOwner ? '青禾' : member.name;
    const role = isOwner ? '群主' : String(member.title || '').split('·')[0].trim();
    const state = isOwner ? '裁决 / 发布 / 授权' : `${member.state || '状态待同步'} · ${member.shortModel || member.model || '模型待标注'}`;
    const presence = isOwner ? 'online' : (member.presence === 'busy' ? 'busy' : member.presence === 'pending' ? 'pending' : 'online');
    const stateLabel = isOwner ? '在线' : (member.state || '待同步');
    return `<button type="button" class="member-strip-item is-${presence} ${isOwner ? 'is-owner' : ''}" data-member="${escapeHTML(id)}" data-presence="${escapeHTML(presence)}" title="${escapeHTML(`${member.title || label} · ${state}`)}" aria-label="${escapeHTML(`${label}，${role}，${state}`)}"><span class="member-strip-avatar ${escapeHTML(member.color || '')}">${dragonIcon(member.dragonAsset || dragonMemberAsset(member), { className: 'dragon-strip-avatar' })}<i></i></span><span class="member-strip-copy"><strong>${escapeHTML(label)}</strong><small>${escapeHTML(role)}<em>${escapeHTML(stateLabel)}</em></small></span></button>`;
  }).join('');
}

function renderTasks() {
  document.getElementById('taskList').innerHTML = tasks.map(task => `
    <button class="task-item" data-task="${escapeHTML(task.id)}">
      <span class="task-state ${task.state}">${dragonIcon(task.dragonAsset || dragonStatusAsset(task.state || task.status), { className: 'dragon-task-icon' })}</span>
      <span class="task-copy"><strong>${escapeHTML(task.id)} · ${escapeHTML(task.title)}</strong><span>${escapeHTML(task.owner)} · ${escapeHTML(task.meta)}${task.subproblemId ? ` · ${escapeHTML(task.subproblemId)}` : ''}</span></span>
      <span class="task-arrow">${dragonIcon('mark', { className: 'dragon-affordance' })}</span>
    </button>`).join('');
}

function taskUiState(status) {
  return ({ VERIFIED: 'verified', ACCEPTED: 'accepted', RELEASED: 'released', IN_PROGRESS: 'active', CLAIMED: 'active', READY_FOR_REVIEW: 'review', PRODUCED: 'produced', UNVERIFIED: 'unverified', BLOCKED: 'blocked', FAILED: 'blocked', TIMEOUT: 'blocked', QUEUED: 'wait' })[status] || 'unverified';
}

function mergeSnapshotTasks(serverTasks) {
  (serverTasks || []).forEach(serverTask => {
    const existing = tasks.find(task => task.id === serverTask.id);
    const hasManifestEvidence = Boolean(serverTask.manifest_linked || serverTask.result?.manifest_linked || serverTask.result?.validation_gate?.ready && (serverTask.result?.artifact_refs || []).length);
    let safeStatus = serverTask.status;
    if (['VERIFIED', 'ACCEPTED', 'RELEASED'].includes(safeStatus) && !hasManifestEvidence) safeStatus = 'UNVERIFIED';
    const mapped = { state: taskUiState(safeStatus), owner: serverTask.owner || serverTask.claimed_by || 'Coordinator', meta: safeStatus === 'UNVERIFIED' ? `${serverTask.status} · provenance 未闭合` : (serverTask.status || '已同步'), status: safeStatus, rawStatus: serverTask.status, subproblemId: serverTask.subproblem_id || serverTask.subproblemId, rawTask: JSON.parse(JSON.stringify(serverTask)) };
    if (existing) Object.assign(existing, mapped);
    else tasks.push({ id: serverTask.id, title: serverTask.title || '未命名任务', icon: mapped.state === 'verified' || mapped.state === 'accepted' || mapped.state === 'released' ? '✓' : mapped.state === 'blocked' ? '!' : '·', ...mapped });
  });
  renderTasks();
  const completed = tasks.filter(task => ['verified', 'accepted', 'released'].includes(task.state)).length;
  const metric = document.getElementById('completedMetric');
  if (metric) metric.textContent = `${completed}/14`;
}

function projectLiveControl(payload) {
  const body = payload?.payload || {};
  if (payload?.revision) setRuntimeContext({ controlRevision: payload.revision });
  if (body.task) mergeSnapshotTasks([body.task]);
  if (payload?.type === 'ASSEMBLY_UPDATED' || body.assembly_revision) {
    capabilityState.assembly.committedRevision = body.assembly_revision || capabilityState.assembly.committedRevision;
    capabilityState.assembly.revision = body.assembly_revision || capabilityState.assembly.revision;
    if (Object.prototype.hasOwnProperty.call(body, 'innovation_card')) {
      capabilityState.assembly.innovationCard = body.innovation_card ? JSON.parse(JSON.stringify(body.innovation_card)) : null;
      capabilityState.assembly.previousInnovationCard = capabilityState.assembly.innovationCard ? JSON.parse(JSON.stringify(capabilityState.assembly.innovationCard)) : null;
      renderInnovationSummary();
    }
    if (Array.isArray(body.content_pack_ids)) {
      capabilityState.assembly.contentPackIds = [...body.content_pack_ids];
      capabilityState.assembly.previousContentPackIds = [...body.content_pack_ids];
      capabilityState.assembly.contentPackEvidenceRefs = Array.isArray(body.content_pack_evidence_refs) ? [...body.content_pack_evidence_refs] : [];
      capabilityState.assembly.contentPackIndexRevision = body.content_pack_index_revision || null;
      capabilityState.assembly.contentPackResolutionRevision = body.content_pack_resolution_revision || null;
      renderCapabilityCatalog(capabilityState.catalog);
    }
    if (Array.isArray(body.method_block_warnings)) capabilityState.assembly.methodBlockWarnings = JSON.parse(JSON.stringify(body.method_block_warnings));
    capabilityState.assembly.validation = body.status === 'BLOCKED' ? { valid: false, errors: ['ASSEMBLY_GATE_BLOCKED'] } : capabilityState.assembly.validation;
    renderAssemblyGate();
  }
  if (body.approval) {
    const button = document.getElementById('approveAllBtn');
    if (button) button.innerHTML = '审批已记录 · 查看队列 <span>→</span>';
  }
  if (payload?.type === 'RELAY' || body.relay_id) {
    const state = document.querySelector('.external-member .relay-state');
    const subtitle = document.querySelector('.external-member .member-copy span');
    if (state) state.textContent = body.status || 'PENDING';
    if (subtitle) subtitle.textContent = body.input_hash ? `冻结包 ${String(body.input_hash).slice(0, 18)}…` : '等待外部 ACK';
  }
}

function projectLiveSnapshotCollections(snapshot) {
  const approvals = snapshot.approvals || [];
  // Keep the server projection separate from local decision labels.  The
  // approval queue can therefore show exactly what was recorded and what is
  // still only a UI draft.
  localApprovals = Array.isArray(approvals) ? JSON.parse(JSON.stringify(approvals)) : [];
  if (approvals.length) {
    const button = document.getElementById('approveAllBtn');
    if (button) button.innerHTML = `审批已记录 · ${approvals.length} 项 <span>→</span>`;
  }
  const latestRelay = (snapshot.relays || []).slice(-1)[0];
  if (latestRelay) {
    const state = document.querySelector('.external-member .relay-state');
    const subtitle = document.querySelector('.external-member .member-copy span');
    if (state) state.textContent = latestRelay.status || 'PENDING_RELAY';
    if (subtitle) subtitle.textContent = latestRelay.input_hash ? `冻结包 ${String(latestRelay.input_hash).slice(0, 18)}…` : '等待外部 ACK';
  }
  const savedAssembly = snapshot.assembly || snapshot.assemblies?.main;
  if (savedAssembly && typeof savedAssembly === 'object') {
    assemblyValidationEpoch += 1;
    capabilityState.assembly = {
      nodes: Array.isArray(savedAssembly.nodes) ? JSON.parse(JSON.stringify(savedAssembly.nodes)) : [],
      edges: Array.isArray(savedAssembly.edges) ? JSON.parse(JSON.stringify(savedAssembly.edges)) : [],
      presetId: savedAssembly.preset_id || null,
      archetypeId: savedAssembly.archetype_id || null,
      validation: savedAssembly.validation || null,
      revision: savedAssembly.assembly_revision || null,
      diff: savedAssembly.diff || null,
      previousNodes: Array.isArray(savedAssembly.nodes) ? JSON.parse(JSON.stringify(savedAssembly.nodes)) : [],
      previousEdges: Array.isArray(savedAssembly.edges) ? JSON.parse(JSON.stringify(savedAssembly.edges)) : [],
      committedRevision: savedAssembly.assembly_revision || null,
      innovationCard: savedAssembly.innovation_card ? JSON.parse(JSON.stringify(savedAssembly.innovation_card)) : null,
      previousInnovationCard: savedAssembly.innovation_card ? JSON.parse(JSON.stringify(savedAssembly.innovation_card)) : null,
      contentPackIds: Array.isArray(savedAssembly.content_pack_ids) ? [...savedAssembly.content_pack_ids] : [],
      previousContentPackIds: Array.isArray(savedAssembly.content_pack_ids) ? [...savedAssembly.content_pack_ids] : [],
      contentPackEvidenceRefs: Array.isArray(savedAssembly.content_pack_evidence_refs) ? [...savedAssembly.content_pack_evidence_refs] : [],
      contentPackEvidenceByPack: {},
      contentPackIndexRevision: savedAssembly.content_pack_index_revision || null,
      contentPackResolutionRevision: savedAssembly.content_pack_resolution_revision || null,
      methodBlockWarnings: Array.isArray(savedAssembly.method_block_warnings) ? JSON.parse(JSON.stringify(savedAssembly.method_block_warnings)) : [],
    };
    renderInnovationSummary();
    renderCapabilityCatalog(capabilityState.catalog);
    renderAssemblyCanvas();
    renderAssemblyGate();
  }
  const findingList = Object.values(snapshot.findings || {}).flat();
  const openCritical = findingList.filter(item => item.status === 'open' && ['P0', 'P1', 'CRITICAL'].includes(String(item.severity || '').toUpperCase())).length;
  const g7 = tasks.find(task => task.id === 'G7');
  if (g7 && openCritical === 0 && g7.state === 'blocked') {
    g7.meta = '关键 finding 已关闭 · 等待独立审查';
    g7.state = 'active';
    g7.icon = '↗';
    renderTasks();
  }
  if (snapshot.release_gate && typeof snapshot.release_gate === 'object') {
    releaseGate = snapshot.release_gate;
    const paperGate = gateMatrix.find(item => item.id === 'paper');
    const release = gateMatrix.find(item => item.id === 'release');
    if (paperGate) {
      const claims = releaseGate.paper_claims || releaseGate.paperClaims || {};
      paperGate.detail = `${claims.total || 0} 个 claim；${claims.unverified || 0} 个未验证`;
      paperGate.status = claims.unverified ? 'blocked' : 'warn';
      paperGate.statusLabel = claims.unverified ? '不可写入' : '待 Owner 审批';
    }
    if (release) {
      release.status = releaseGate.status === 'READY' ? 'pass' : 'blocked';
      release.statusLabel = releaseGate.status === 'READY' ? '可申请发布' : '锁定';
      release.detail = releaseGate.blocking_tasks?.length ? `阻断任务：${releaseGate.blocking_tasks.join('、')}` : (releaseGate.reason || '服务端门禁');
    }
    renderGateMatrix();
  }
}

function renderDecisions() {
  document.getElementById('decisionList').innerHTML = decisions.map(item => `
    <article class="decision-card" data-decision="${item.id}">
      <h4>${escapeHTML(item.title)}</h4><p>${escapeHTML(item.body)}</p>
      <div class="decision-meta"><span class="mini-avatar ${item.color}">${dragonIcon(dragonMemberAsset(dragonDecisionMember(item)), { className: 'dragon-mini-avatar' })}</span><span>${escapeHTML(item.label)} · 需要群主决定</span></div>
      <div class="decision-actions"><button class="decision-approve" data-action="approve" ${item.decision ? 'disabled' : ''}>${escapeHTML(item.decision === 'reject' ? '已拒绝' : item.decision === 'approve' ? '已批准' : '批准')}</button><button class="decision-reject" data-action="reject" ${item.decision ? 'disabled' : ''}>拒绝</button><button class="decision-more" data-action="inspect">展开证据</button></div>
      ${item.decision ? `<div class="decision-recorded"><span class="tag ${item.decision === 'approve' ? 'teal' : 'rose'}">${escapeHTML(item.decision === 'approve' ? '已记录批准' : '已记录拒绝')}</span><small>${escapeHTML(item.decisionSource || '本地视图')}</small></div>` : ''}
    </article>`).join('');
}

function renderEvidence() {
  document.getElementById('evidenceList').innerHTML = evidence.map(item => {
    const rawStatus = item.status || 'UNVERIFIED';
    const status = item.source === 'fixture' && ['VERIFIED', 'ACCEPTED', 'RELEASED'].includes(rawStatus) ? 'PRODUCED' : rawStatus;
    return `<button class="evidence-row" data-evidence="${escapeHTML(item.title)}"><span class="evidence-icon">${dragonIcon(item.dragonAsset || dragonEvidenceAsset(item, status), { className: 'dragon-evidence-icon' })}</span><span><strong>${escapeHTML(item.title)}</strong><span>${escapeHTML(item.meta)}</span></span><span class="evidence-status ${String(status).toLowerCase()}">${escapeHTML(status)}</span><span class="evidence-ok">${dragonIcon('mark', { className: 'dragon-affordance' })}</span></button>`;
  }).join('');
}

function messageClockMinutes(value) {
  const text = String(value ?? '').trim();
  const match = text.match(/(?:^|\D)(\d{1,2}):(\d{2})(?:\D|$)/);
  if (!match) return null;
  const hour = Number(match[1]);
  const minute = Number(match[2]);
  if (!Number.isInteger(hour) || !Number.isInteger(minute) || hour > 23 || minute > 59) return null;
  return hour * 60 + minute;
}

function isSameMessageGroup(previous, current) {
  if (!previous || !current) return false;
  if (previous.type === 'system' || previous.type === 'date' || current.type === 'system' || current.type === 'date') return false;
  if (!previous.member || !current.member || previous.member !== current.member) return false;
  const previousMinutes = messageClockMinutes(previous.time || previous.timestamp || previous.createdAt);
  const currentMinutes = messageClockMinutes(current.time || current.timestamp || current.createdAt);
  if (previousMinutes === null || currentMinutes === null) return false;
  let delta = Math.abs(currentMinutes - previousMinutes);
  if (delta > 720) delta = 1440 - delta;
  return delta <= 2;
}

function canonicalChannelLabel(value) {
  const raw = String(value || '').trim();
  const aliases = {
    main: '主议事群',
    总控: '主议事群',
    '主议事群': '主议事群',
    data: '题面与数据',
    '题面与数据': '题面与数据',
    modeling: '建模方案',
    '建模方案': '建模方案',
    algorithm: '算法与仿真',
    '算法与仿真': '算法与仿真',
    verify: '验证与质疑',
    '验证与质疑': '验证与质疑',
    paper: '论文与答辩',
    '论文与答辩': '论文与答辩',
    knowledge: '资料库',
    '资料库': '资料库',
  };
  return aliases[raw] || raw || '主议事群';
}

function inferredMessageChannel(message) {
  const explicit = message?.channel || message?.channelName;
  if (explicit) return canonicalChannelLabel(explicit);
  if (message?.type === 'system' || message?.type === 'date') return '主议事群';
  const member = String(message?.member || '').toLowerCase();
  const kind = String(message?.kind || '');
  if (member === 'data' || member === 'scope' || /题面|数据|泄漏/.test(String(message?.text || ''))) return '题面与数据';
  if (member === 'routea' || member === 'routeb' || /路线|模型|方案|量纲/.test(String(message?.text || ''))) return '建模方案';
  if (member === 'validator' || member === 'critic' || /验证|质疑|反例|finding|回测/.test(String(message?.text || ''))) return '验证与质疑';
  if (kind === '装配' || kind === '复跑') return '算法与仿真';
  if (kind === '论文' || kind === '答辩') return '论文与答辩';
  return '主议事群';
}

function messageMatchesView(message) {
  if (message?.type === 'system' || message?.type === 'date') return true;
  const filter = activeConversationFilter;
  if (filter === 'private') return message.private === true || message.visibility === 'private' || message.channel === 'private';
  if (filter === 'mentions') {
    const text = String(message.text || '');
    return message.member === 'owner' || Array.isArray(message.mentions) && message.mentions.some(item => ['owner', 'user'].includes(String(item))) || /@(?:我|owner|群主|青禾)/i.test(text);
  }
  if (filter === 'group' && (message.private === true || message.visibility === 'private' || message.channel === 'private')) return false;
  if (!activeChannel || activeChannel === '主议事群' || activeChannel === '总控') return true;
  return inferredMessageChannel(message) === canonicalChannelLabel(activeChannel);
}

function visibleMessages() {
  return messages.filter(messageMatchesView);
}

function activeViewLabel() {
  const labels = { all: '全部', group: '群组', private: '私聊', mentions: '@我' };
  return labels[activeConversationFilter] || '全部';
}

function setActiveConversationFilter(filter) {
  const allowed = new Set(['all', 'group', 'private', 'mentions']);
  activeConversationFilter = allowed.has(filter) ? filter : 'all';
  localStoreSet('qingjia.conversationFilter', activeConversationFilter);
  document.querySelectorAll('.conversation-tab').forEach(tab => {
    const selected = tab.dataset.filter === activeConversationFilter;
    tab.classList.toggle('active', selected);
    tab.setAttribute('aria-selected', String(selected));
  });
  renderMessages();
  showToast(`已切换到${activeViewLabel()}视图 · ${visibleMessages().filter(item => !['system', 'date'].includes(item.type)).length} 条消息`);
}

function setActiveChannel(channel, options = {}) {
  const label = canonicalChannelLabel(channel);
  activeChannel = label;
  localStoreSet('qingjia.activeChannel', activeChannel);
  document.querySelectorAll('.channel-item').forEach(item => {
    item.classList.toggle('active', canonicalChannelLabel(item.dataset.channel) === label);
  });
  const title = document.querySelector('.chat-title-wrap h2');
  const subtitle = document.querySelector('.chat-title-wrap span');
  if (title) title.textContent = label;
  if (subtitle) subtitle.textContent = label === '主议事群' ? '所有关键结论都必须留下证据' : `频道摘要 · ${label} 的任务与证据`;
  document.querySelector('.chat-panel')?.setAttribute('data-active-channel', label);
  renderMessages();
  if (label === '资料库') openKnowledgePanel();
  if (!options.silent) showToast(`已切换到 #${label}`);
}

function safeMessageAttachmentUrl(value) {
  const raw = String(value || '').trim();
  if (!raw || typeof URL === 'undefined') return '';
  try {
    const parsed = new URL(raw, window.location.href);
    if (!['http:', 'https:'].includes(parsed.protocol)) return '';
    const allowedOrigins = new Set([window.location.origin]);
    if (LIVE_API) allowedOrigins.add(new URL(LIVE_API, window.location.href).origin);
    return allowedOrigins.has(parsed.origin) ? parsed.href : '';
  } catch (_) {
    return '';
  }
}

function renderMessageAttachments(attachments) {
  const source = Array.isArray(attachments) ? attachments : (attachments ? [attachments] : []);
  const cards = source.slice(0, 4).map(item => {
    const record = typeof item === 'string' ? { name: item, path: item } : (item && typeof item === 'object' ? item : null);
    if (!record) return '';
    const name = String(record.name || record.title || record.filename || record.path || '未命名附件');
    const url = safeMessageAttachmentUrl(record.url || record.href || record.path);
    const mime = String(record.mimeType || record.mime_type || '').toLowerCase();
    const type = String(record.type || record.kind || '').toLowerCase();
    const isImage = type === 'image' || mime.startsWith('image/');
    const status = String(record.status || 'UNVERIFIED');
    const refs = sanitizeEvidenceRefs(record.evidenceRefs || record.evidence_refs || (record.evidenceRef ? [record.evidenceRef] : []));
    const meta = [status, refs[0]].filter(Boolean).join(' · ');
    if (isImage && url) {
      return '<a class="attachment-card attachment-image" href="' + escapeHTML(url) + '" target="_blank" rel="noreferrer noopener"><img src="' + escapeHTML(url) + '" alt="' + escapeHTML(name) + '" loading="lazy" /><span><strong>' + escapeHTML(name) + '</strong>' + (meta ? '<em>' + escapeHTML(meta) + '</em>' : '') + '</span></a>';
    }
    const open = url
      ? '<a class="attachment-card attachment-file" href="' + escapeHTML(url) + '" target="_blank" rel="noreferrer noopener">'
      : '<div class="attachment-card attachment-file is-unlinked" title="附件地址未通过安全校验">';
    const close = url ? '</a>' : '</div>';
    return open + '<span class="attachment-file-mark" aria-hidden="true">件</span><span><strong>' + escapeHTML(name) + '</strong>' + (meta ? '<em>' + escapeHTML(meta) + '</em>' : '') + '</span>' + close;
  }).filter(Boolean).join('');
  return cards ? '<div class="message-attachments" aria-label="消息附件">' + cards + '</div>' : '';
}

function renderMessages() {
  const feed = document.getElementById('chatFeed');
  if (!feed) return;
  const viewMessages = visibleMessages();
  feed.innerHTML = viewMessages.map((message, messageIndex) => {
    if (message.type === 'system') return `<div class="system-note"><span class="system-icon">${dragonIcon('mark', { className: 'dragon-system-icon' })}</span><span>${escapeHTML(message.text)}</span></div>`;
    if (message.type === 'date') return `<div class="date-divider">${escapeHTML(message.text)}</div>`;
    const previousMessage = viewMessages[messageIndex - 1];
    const isContinuation = isSameMessageGroup(previousMessage, message);
    const member = getMember(message.member);
    const tagHtml = (message.tags || []).map(([label, color]) => `<span class="tag ${color}">${escapeHTML(label)}</span>`).join('');
    const actionHtml = (message.actions || []).map(action => `<button class="message-action" data-message-action="${escapeHTML(action)}">${escapeHTML(action)} ${dragonIcon('mark', { className: 'dragon-affordance' })}</button>`).join('');
    const quoteHtml = message.quote ? `<div class="quote-card"><b>${escapeHTML(message.quote.title)}</b>${escapeHTML(message.quote.text)}</div>` : '';
    const attachmentHtml = renderMessageAttachments(message.attachments || message.files || message.attachment);
    const kind = message.kind || '进展';
    const isOwner = message.member === 'owner';
    const statusClass = member.presence === 'busy' ? 'busy' : member.presence === 'pending' ? 'pending' : '';
    const claimClass = message.claimClass || 'unknown';
    const source = message.sourceLabel || (message.source === 'live' ? 'LIVE EVENT' : message.source === 'snapshot' ? 'LIVE SNAPSHOT' : 'SIMULATED');
    const evidenceRefs = sanitizeEvidenceRefs(message.evidenceRefs);
    const evidenceHtml = evidenceRefs.length
      ? evidenceRefs.slice(0, 2).map(ref => `<span class="evidence-chip">${escapeHTML(String(ref))}</span>`).join('') + (evidenceRefs.length > 2 ? `<span class="evidence-chip">+${evidenceRefs.length - 2} refs</span>` : '')
      : '<span class="evidence-chip missing">evidence: none · UNVERIFIED</span>';
    const status = message.status || 'UNVERIFIED';
    const sourceTone = message.source === 'live' || message.source === 'snapshot' ? 'live' : message.source === 'local_pending' ? 'pending' : 'fixture';
    const assemblyMeta = message.assemblyRevision || message.assembly_revision;
    const capabilityMeta = message.capabilityRevision || message.capability_revision;
    const auditHtml = `<div class="message-audit"><span class="audit-source ${sourceTone}">${escapeHTML(source)}</span><span class="audit-claim ${claimClass}">${escapeHTML(claimClass)}</span><span>${escapeHTML(message.taskId || 'task:unassigned')}</span><span>${escapeHTML(message.subproblemId || 'Q—')}</span><span title="${escapeHTML(message.targetRevision || '')}">${escapeHTML(compactRevision(message.targetRevision, 16))}</span>${assemblyMeta ? `<span class="audit-assembly" title="${escapeHTML(assemblyMeta)}">assembly ${escapeHTML(compactRevision(assemblyMeta, 13))}</span>` : ''}${capabilityMeta ? `<span class="audit-capability" title="${escapeHTML(capabilityMeta)}">cap ${escapeHTML(compactRevision(capabilityMeta, 13))}</span>` : ''}<span class="audit-status ${String(status).toLowerCase()}">${escapeHTML(status)}</span></div>`;
    // Keep the evidence contract available without making every message read
    // like a log line.  The summary is intentionally short; the full audit,
    // tags, refs and actions remain in the native disclosure for keyboard and
    // screen-reader users.
    const displayName = isOwner ? '你' : member.name;
    const roleText = isOwner ? '群主' : (message.modelProfile || member.shortModel || member.model || 'model unknown');
    const metaTitle = isOwner ? '群主 · ' + (message.modelProfile || 'Owner') : member.title + ' · ' + roleText;
    const articleClasses = ['message', isOwner ? 'owner-message' : '', isContinuation ? 'is-continuation' : '', 'agent-' + escapeHTML(message.member || 'unknown')].filter(Boolean).join(' ');
    const showMeta = isContinuation ? 'false' : 'true';
    const showAvatar = isContinuation ? 'false' : 'true';
    const evidenceSummary = evidenceRefs.length ? `${evidenceRefs.length} refs` : 'no evidence';
    const provenanceHtml = `<details class="message-provenance" data-provenance-status="${escapeHTML(String(status).toLowerCase())}"><summary><span class="provenance-summary"><span class="provenance-sigil" aria-hidden="true">卜</span><span>证据链</span><em>${escapeHTML(source)} · ${escapeHTML(status)} · ${escapeHTML(evidenceSummary)}</em></span><span class="provenance-toggle" aria-hidden="true">+</span></summary><div class="provenance-body">${auditHtml}<div class="message-tags">${tagHtml}${evidenceHtml}</div><div class="message-actions">${actionHtml}</div></div></details>`;
    return `<article class="${articleClasses}" data-message-id="${escapeHTML(message.id || '')}" data-member="${escapeHTML(message.member || 'unknown')}" data-message-kind="${escapeHTML(kind)}" data-show-meta="${showMeta}" data-show-avatar="${showAvatar}">
      <div class="avatar message-avatar ${member.color}" aria-hidden="${isContinuation ? 'true' : 'false'}" title="${escapeHTML(metaTitle)}">${dragonIcon(member.dragonAsset || dragonMemberAsset(member), { className: 'dragon-avatar' })}<span class="status-dot ${statusClass}"></span></div>
      <div class="message-body"><div class="message-meta" title="${escapeHTML(metaTitle)}"><span class="message-name">${escapeHTML(displayName)}</span><span class="message-role">${escapeHTML(roleText)}</span><span class="message-time">${escapeHTML(message.time || '')}</span></div>
      <div class="message-bubble"><p><span class="tag message-kind-tag ${kindClass[kind] || 'blue'}">${escapeHTML(kind)}</span>${message.text || ''}</p>${quoteHtml}${attachmentHtml}${provenanceHtml}</div></div></article>`;
  }).join('');
  if (!viewMessages.some(message => message.type !== 'system' && message.type !== 'date')) {
    feed.innerHTML = `<div class="filtered-empty"><span class="filtered-empty-mark">${dragonIcon('mark', { className: 'dragon-empty-icon' })}</span><strong>当前视图暂无消息</strong><p>${escapeHTML(activeConversationFilter === 'private' ? '暂无私聊记录；切换到“群组”查看协作消息。' : `#${activeChannel} 暂无可显示的消息；切换频道或视图继续浏览。`)}</p></div>`;
  }
  // Font loading and responsive reflow can change the feed height a frame
  // after the HTML is painted.  Align once now and once after layout so the
  // latest Owner message is actually visible on a small screen, rather than
  // leaving a clipped provenance row at the bottom.
  const alignLatest = () => {
    if (!feed) return;
    // Chat rooms open at the newest message, but a narrow viewport should not
    // make the first visible bubble look sliced by the hard scroll edge.  Keep
    // a small, bounded reading inset when there is enough breathing room below
    // the latest message; desktop remains bottom-aligned like a normal chat.
    feed.scrollTop = feed.scrollHeight;
    if (window.innerWidth > 850) return;
    const feedRect = feed.getBoundingClientRect();
    const articles = [...feed.querySelectorAll('.message')];
    const latest = articles[articles.length - 1];
    if (!latest) return;
    const latestRect = latest.getBoundingClientRect();
    const spareBelow = Math.max(0, feedRect.bottom - latestRect.bottom - 10);
    const clipped = articles.find(article => {
      const rect = article.getBoundingClientRect();
      return rect.bottom > feedRect.top && rect.top < feedRect.top + 2;
    });
    if (!clipped || spareBelow <= 0) return;
    const clip = Math.max(0, feedRect.top + 10 - clipped.getBoundingClientRect().top);
    const inset = Math.min(36, clip, spareBelow);
    if (inset > 0) feed.scrollTop = Math.max(0, feed.scrollTop - inset);
  };
  alignLatest();
  if (typeof window.requestAnimationFrame === 'function') window.requestAnimationFrame(alignLatest);
  window.setTimeout(alignLatest, 80);
}

function showToast(text) {
  const toast = document.getElementById('toast');
  const feed = document.querySelector('.chat-feed');
  // On a narrow screen a notice gets a temporary reserved band above the
  // composer.  Prepare the band first, re-align only when the reader was
  // already near the end, then reveal the pill.  This prevents the first
  // animation frame from sitting on top of the newest bubble.
  // A successful socket handshake is already represented by the LIVE control
  // and revision chip in the top bar.  Keeping that informational toast out of
  // the reading plane on every viewport preserves the latest bubble's tactile
  // surface; failures and user actions still use the normal transient notice.
  if (String(text).startsWith('已连接事件源')) {
    window.clearTimeout(showToast.timer);
    window.clearTimeout(showToast.revealTimer);
    toast.classList.remove('show', 'prepare');
    toast.setAttribute('aria-hidden', 'true');
    toast.textContent = text;
    return;
  }
  toast.removeAttribute('aria-hidden');
  const wasNearBottom = feed ? feed.scrollHeight - feed.scrollTop - feed.clientHeight < 48 : false;
  const align = () => {
    if (feed && wasNearBottom) feed.scrollTop = feed.scrollHeight;
  };
  window.clearTimeout(showToast.timer);
  window.clearTimeout(showToast.revealTimer);
  toast.textContent = text;
  toast.classList.remove('show');
  toast.classList.add('prepare');
  align();
  let revealed = false;
  const reveal = () => {
    if (revealed) return;
    revealed = true;
    window.clearTimeout(showToast.revealTimer);
    align();
    toast.classList.remove('prepare');
    toast.classList.add('show');
    if (typeof window.requestAnimationFrame === 'function') window.requestAnimationFrame(align);
  };
  const entranceMotion = [...document.querySelectorAll('.message, .topbar, .chat-panel')]
    .some(node => typeof node.getAnimations === 'function' && node.getAnimations().some(animation => animation.playState === 'running'));
  const revealDelay = entranceMotion ? 420 : 42;
  // A bounded timer covers background-tab throttling without leaving a
  // prepared toast stranded forever.  When the shell is still entering, the
  // extra beat lets message-in motion finish before the pill becomes visible.
  showToast.revealTimer = window.setTimeout(() => {
    if (typeof window.requestAnimationFrame === 'function') window.requestAnimationFrame(reveal);
    else reveal();
  }, revealDelay);
  showToast.timer = window.setTimeout(() => {
    toast.classList.remove('show', 'prepare');
    align();
  }, 3200);
}

/*
 * Local knowledge-base projection.
 * The browser only receives bounded metadata/snippets and a citation ref. The
 * original material directory stays on the local machine; opening a source is
 * a deliberate second click and never turns a retrieved suggestion into a
 * verified paper claim.
 */
let knowledgePendingRefs = [];

function kbEndpoint(path = '') {
  return LIVE_API ? `${LIVE_API}/api/projects/${LIVE_PROJECT}/knowledge${path}` : '';
}

function kbErrorMessage(payload, fallback = '知识库请求失败') {
  const detail = payload?.detail;
  if (typeof detail === 'string') return detail;
  if (detail && typeof detail === 'object') return detail.message || detail.code || fallback;
  return fallback;
}

function kbFormatBytes(value) {
  const bytes = Number(value);
  if (!Number.isFinite(bytes) || bytes < 0) return '—';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
}

function kbFacetOptions(value) {
  if (Array.isArray(value)) {
    return value.map(item => {
      if (item && typeof item === 'object') return { value: String(item.value ?? item.id ?? item.name ?? ''), label: String(item.label ?? item.name ?? item.value ?? item.id ?? ''), count: item.count };
      return { value: String(item), label: String(item) };
    }).filter(item => item.value);
  }
  if (value && typeof value === 'object') return Object.entries(value).map(([key, count]) => ({ value: key, label: key, count }));
  return [];
}

function kbFillSelect(id, placeholder, values) {
  const select = document.getElementById(id);
  if (!select) return;
  const current = select.value;
  select.innerHTML = `<option value="">${escapeHTML(placeholder)}</option>${kbFacetOptions(values).map(item => `<option value="${escapeHTML(item.value)}">${escapeHTML(item.label)}${item.count !== undefined ? ` · ${escapeHTML(item.count)}` : ''}</option>`).join('')}`;
  if (current && [...select.options].some(option => option.value === current)) select.value = current;
}

function setPanelDrawerOpen(open) {
  const isOpen = Boolean(open);
  document.body.classList.toggle('panel-drawer-open', isOpen);
  const toggle = document.getElementById('panelToggleBtn');
  if (toggle) toggle.setAttribute('aria-expanded', String(isOpen));
  const sidebar = document.querySelector('.right-sidebar');
  if (sidebar) sidebar.setAttribute('aria-hidden', String(!isOpen));
  const backdrop = document.getElementById('panelBackdrop');
  if (backdrop) backdrop.hidden = !isOpen;
}

function selectRightPanel(panel) {
  document.querySelectorAll('.right-tab').forEach(tab => tab.classList.toggle('active', tab.dataset.panel === panel));
  const panels = { modeling: 'modelingPanel', tasks: 'tasksPanel', evidence: 'evidencePanel', knowledge: 'knowledgePanel', assembly: 'assemblyPanel' };
  Object.entries(panels).forEach(([key, id]) => {
    const node = document.getElementById(id);
    if (node) node.hidden = key !== panel;
  });
  // Selecting any control surface is an explicit request to open the
  // progressive-disclosure drawer.  CSS owns the animation/width; JS only
  // exposes the state to assistive technology and the close controls.
  if (panel) setPanelDrawerOpen(true);
}

/* The desktop shell mirrors the reference board: the task/workbench context
 * is visible beside the conversation, while small screens retain a clean
 * chat-first surface and open the workbench only on demand. */
function initTemplateShell() {
  renderMemberStrip();
  const media = typeof window.matchMedia === 'function' ? window.matchMedia('(min-width: 851px)') : null;
  const syncViewport = () => {
    const desktop = !media || media.matches;
    if (desktop) {
      if (!document.body.classList.contains('panel-drawer-open')) selectRightPanel('tasks');
    } else {
      setPanelDrawerOpen(false);
    }
  };
  syncViewport();
  if (media?.addEventListener) media.addEventListener('change', syncViewport);
  else if (media?.addListener) media.addListener(syncViewport);
}

function renderKnowledgeSummary(summary) {
  knowledgeState.summary = summary || null;
  knowledgeState.indexRevision = summary?.index_revision || summary?.indexRevision || null;
  const status = String(summary?.source_status || summary?.sourceStatus || 'UNAVAILABLE').toUpperCase();
  const indexed = summary?.indexed_count ?? summary?.valid_count ?? summary?.file_count ?? summary?.files ?? summary?.document_count ?? 0;
  const pending = summary?.pending_count ?? summary?.temporary_count ?? summary?.temp_count ?? 0;
  const rootLabel = summary?.root_label || summary?.rootLabel || '本地资料包';
  const statusLabel = document.getElementById('kbStatusLabel');
  const statusMeta = document.getElementById('kbStatusMeta');
  const dot = document.querySelector('.knowledge-status-card .knowledge-dot');
  if (statusLabel) statusLabel.textContent = status === 'UNAVAILABLE' ? '资料索引 · 未连接' : (status === 'LOCAL_PENDING' ? `${rootLabel} · 同步中` : `${rootLabel} · 已建立索引`);
  if (statusMeta) {
    const scanned = summary?.last_scan_at || summary?.scanned_at || summary?.indexed_at;
    const scanText = scanned ? `扫描快照 ${String(scanned).replace('T', ' ').slice(0, 19)}` : '尚未扫描';
    const note = summary?.catalog_consistent === false ? '说明页数字与当前盘面不一致，以本次扫描为准。' : '原始文件只读；索引随本地同步快照更新。';
    const extraction = summary?.extractability || {};
    const rate = Number(extraction.extractability_rate);
    const extractionText = Number.isFinite(rate) ? `可正文抽取约 ${(rate * 100).toFixed(1)}%` : '可正文抽取率待计算';
    statusMeta.textContent = `${scanText} · ${note} · ${extractionText}`;
  }
  if (dot) dot.classList.toggle('pending', status === 'LOCAL_PENDING');
  const stats = document.getElementById('kbStats');
  if (stats) stats.innerHTML = `<div><b>${escapeHTML(indexed)}</b><span>可检索文件</span></div><div><b>${escapeHTML(pending)}</b><span>同步中</span></div><div><b>${escapeHTML(kbFormatBytes(summary?.indexed_bytes ?? summary?.bytes ?? summary?.total_bytes))}</b><span>索引范围</span></div>`;
  const badgeText = indexed > 9999 ? `${Math.round(indexed / 1000)}k` : (indexed || '—');
  ['kbTabBadge', 'knowledgeChannelBadge'].forEach(id => { const el = document.getElementById(id); if (el) el.textContent = String(badgeText); });
  kbFillSelect('kbModuleFilter', '全部模块', summary?.facets?.modules || summary?.modules);
  kbFillSelect('kbKindFilter', '全部类型', summary?.facets?.kinds || summary?.facets?.types || summary?.kinds || summary?.types);
  kbFillSelect('kbYearFilter', '年份', summary?.facets?.years || summary?.years);
  const card = document.querySelector('.knowledge-status-card');
  if (card) card.dataset.status = status.toLowerCase();
}

function renderKnowledgeResults(payload) {
  const root = document.getElementById('kbResults');
  if (!root) return;
  const results = payload?.results || payload?.items || [];
  knowledgeState.results = results;
  knowledgeState.indexRevision = payload?.index_revision || payload?.indexRevision || knowledgeState.indexRevision;
  const meta = document.getElementById('kbResultMeta');
  if (meta) {
    const total = payload?.total_candidates ?? payload?.total ?? results.length;
    const returned = payload?.returned_count ?? results.length;
    const warning = Array.isArray(payload?.warnings) && payload.warnings.length ? ` · ${payload.warnings[0]}` : '';
    const boundary = payload?.metadata_candidates != null ? ` · 候选 ${payload.metadata_candidates} / 正文检查 ${payload.body_examined ?? '—'}` : '';
    const hitText = payload?.truncated ? `${returned}/${total} 个命中（受限扫描）` : `${total} 个命中`;
    meta.textContent = `${hitText}${boundary}${knowledgeState.indexRevision ? ` · ${compactRevision(knowledgeState.indexRevision, 17)}` : ''}${warning}`;
  }
  if (!results.length) {
    root.innerHTML = `<div class="kb-empty"><span>∅</span><strong>没有可安全引用的命中</strong><p>换一个题号、年份或方法词；扫描中的临时文件不会进入结果。</p></div>`;
    return;
  }
  root.innerHTML = results.map(item => {
    const docId = item.doc_id || item.docId || item.id;
    if (!docId) return '';
    const title = item.title || item.name || '未命名资料';
    const path = item.path_rel_masked || item.path_rel || item.path || '相对路径未提供';
    const kind = item.kind || item.content_class || 'other';
    const module = item.module_label || item.module || '未分类';
    const years = Array.isArray(item.years) ? item.years.join('、') : (item.year || '—');
    const tags = Array.isArray(item.tags) ? item.tags.slice(0, 4) : [];
    const excerpt = item.snippet || item.excerpt || (String(item.extract_status || '').toLowerCase() === 'ocr_required' ? '扫描型 PDF 尚未完成 OCR；可打开原文件人工核对。' : '仅有文件元数据，等待按需抽取。');
    const status = String(item.source_status || item.sourceStatus || 'LOCAL_INDEXED').toUpperCase();
    const citation = item.citation_ref || item.citationRef || `kbdoc:${docId}`;
    const fileUrl = LIVE_API ? `${kbEndpoint(`/documents/${encodeURIComponent(docId)}/file`)}` : '';
    const extraction = item.extract_status || item.extraction_status || 'metadata_only';
    const hashStatus = item.hash_status || item.hashStatus || 'DEFERRED';
    return `<article class="kb-result" data-kb-doc="${escapeHTML(docId)}"><div class="kb-result-head"><span class="kb-kind">${escapeHTML(kind)}</span><span class="kb-module">${escapeHTML(module)}</span><span class="kb-source ${status.toLowerCase()}">${escapeHTML(status)}</span></div><strong class="kb-result-title">${escapeHTML(title)}</strong><span class="kb-result-path">${escapeHTML(path)}</span><p class="kb-result-excerpt">${escapeHTML(excerpt)}</p><div class="kb-result-meta"><span>${escapeHTML(years)} · ${escapeHTML(kbFormatBytes(item.size_bytes ?? item.size))}</span><em>${escapeHTML(extraction)}</em><em>${escapeHTML(hashStatus)}</em>${tags.map(tag => `<em>${escapeHTML(tag)}</em>`).join('')}</div><div class="kb-result-actions"><button type="button" data-kb-action="view">查看片段</button><button type="button" data-kb-action="cite">引用到群聊</button>${fileUrl ? `<a href="${escapeHTML(fileUrl)}" target="_blank" rel="noreferrer">打开原文件 ↗</a>` : ''}</div><span class="kb-citation-ref">${escapeHTML(citation)}</span></article>`;
  }).join('');
}

async function loadKnowledgeSummary(force = false) {
  if (!LIVE_API) {
    renderKnowledgeSummary({ source_status: 'UNAVAILABLE', indexed_count: 0, pending_count: 0, root_label: '本地资料包未连接' });
    return null;
  }
  try {
    const suffix = force ? '?refresh=true' : '';
    const response = await fetch(`${kbEndpoint('/summary')}${suffix}`);
    const payload = await response.json();
    if (!response.ok) throw new Error(kbErrorMessage(payload, 'KB_SUMMARY_ERROR'));
    renderKnowledgeSummary(payload);
    return payload;
  } catch (error) {
    renderKnowledgeSummary({ source_status: 'UNAVAILABLE', indexed_count: 0, pending_count: 0, root_label: '本地资料包不可用' });
    showToast(`资料库状态读取失败（${error.message || 'unknown'}）`);
    return null;
  }
}

async function runKnowledgeSearch(queryOverride, announce = false) {
  const input = document.getElementById('kbSearchInput');
  const query = String(queryOverride ?? input?.value ?? '').trim();
  if (input && queryOverride !== undefined) input.value = query;
  if (!LIVE_API) { showToast('当前没有连接本地知识库服务'); return; }
  const params = new URLSearchParams({ q: query, top_k: '12', with_preview: 'true' });
  ['kbModuleFilter', 'kbKindFilter', 'kbYearFilter'].forEach(id => { const value = document.getElementById(id)?.value; if (value) params.set(id === 'kbModuleFilter' ? 'module' : id === 'kbKindFilter' ? 'kind' : 'year', value); });
  const root = document.getElementById('kbResults');
  if (root) root.innerHTML = '<div class="kb-loading"><span></span><span></span><span></span>正在从本地索引检索…</div>';
  try {
    const response = await fetch(`${kbEndpoint('/search')}?${params.toString()}`);
    const payload = await response.json();
    if (!response.ok) throw new Error(kbErrorMessage(payload, 'KB_SEARCH_ERROR'));
    knowledgeState.query = query;
    renderKnowledgeResults(payload);
    if (announce) {
      const status = knowledgeState.summary?.source_status || 'LOCAL_INDEXED';
      const returned = payload?.returned_count ?? (payload?.results || []).length;
      const candidates = payload?.total_candidates ?? payload?.total ?? returned;
      const warning = Array.isArray(payload?.warnings) && payload.warnings.length ? `；${payload.warnings[0]}` : '';
      messages.push({ type: 'system', text: `知识库检索 · “${query}” · 返回 ${returned}/${candidates} · ${status} · ${compactRevision(payload?.index_revision, 18)}${warning}` });
      renderMessages();
    }
  } catch (error) {
    if (root) root.innerHTML = `<div class="kb-empty"><span>!</span><strong>检索暂不可用</strong><p>${escapeHTML(error.message || '请稍后重试')}</p></div>`;
    showToast(`资料库检索失败（${error.message || 'unknown'}）`);
  }
}

async function openKnowledgeDocument(docId, fallback) {
  if (!LIVE_API || !docId) return;
  try {
    const response = await fetch(`${kbEndpoint(`/documents/${encodeURIComponent(docId)}`)}?include_preview=true`);
    const payload = await response.json();
    if (!response.ok) throw new Error(kbErrorMessage(payload, 'KB_DOCUMENT_ERROR'));
    const doc = payload.document || payload;
    // The adapter currently returns a bounded preview string.  Accept the
    // object-shaped variant as well so future chunk/page adapters can expose
    // ``{text, page}`` without regressing the current modal.
    const preview = (typeof doc.preview === 'string' ? doc.preview : doc.preview?.text) || doc.preview_text || doc.snippet || doc.excerpt || '当前文件没有可抽取的短文本；请打开原文件核对。';
    const citation = doc.citation_ref || doc.citationRef || fallback?.citation_ref || `kbdoc:${docId}`;
    const fileUrl = `${kbEndpoint(`/documents/${encodeURIComponent(docId)}/file`)}`;
    const hashNote = doc.hash_status === 'DEFERRED_LARGE' ? `大文件哈希延后（${doc.hash_deferred_reason || '超过按需上限'}）` : `哈希状态：${doc.hash_status || 'DEFERRED'}`;
    const pageNote = doc.preview_pages ? ` · 预览前 ${doc.preview_pages} 页${doc.page_count ? ` / 共 ${doc.page_count} 页` : ''}` : '';
    showModal(`资料片段 · ${doc.title || fallback?.title || '未命名资料'}`, `<p><span class="tag teal">${escapeHTML(doc.source_status || 'LOCAL_INDEXED')}</span> <span class="tag violet">${escapeHTML(doc.kind || fallback?.kind || '资料')}</span> <span class="tag amber">${escapeHTML(doc.extract_status || doc.quality || 'metadata')}</span></p><p class="kb-modal-path">${escapeHTML(doc.path_rel_masked || doc.path_rel || fallback?.path_rel || '相对路径未提供')}</p><pre class="kb-preview">${escapeHTML(String(preview).slice(0, 8000))}</pre><p><span class="tag blue">引用：${escapeHTML(citation)}</span> <a href="${escapeHTML(fileUrl)}" target="_blank" rel="noreferrer">Owner 打开原文件 ↗</a></p><p class="kb-modal-note">${escapeHTML(hashNote)}${escapeHTML(pageNote)}。短片段仅用于检索与质疑；不自动写入论文，也不替代题面、页码和独立复核。</p>`);
  } catch (error) {
    showToast(`资料片段读取失败（${error.message || 'unknown'}）`);
  }
}

function renderPendingKbCitations() {
  const hint = document.getElementById('kbCitationHint');
  if (!hint) return;
  hint.hidden = knowledgePendingRefs.length === 0;
  const workspaceCount = knowledgePendingRefs.filter(ref => String(ref).toLowerCase().startsWith('repo:')).length;
  const kbCount = knowledgePendingRefs.length - workspaceCount;
  const labels = [];
  if (kbCount) labels.push(`${kbCount} 条资料`);
  if (workspaceCount) labels.push(`${workspaceCount} 条工程上下文`);
  hint.textContent = labels.length ? `已挂 ${labels.join(' · ')}` : '';
}

function citeKnowledgeItem(item) {
  const docId = item?.doc_id || item?.docId || item?.id;
  if (!docId) return;
  const citation = item.citation_ref || item.citationRef || `kbdoc:${docId}`;
  if (!knowledgePendingRefs.includes(citation)) knowledgePendingRefs.push(citation);
  const input = document.getElementById('messageInput');
  const title = item.title || item.name || '资料';
  const prefix = input.value.trim() ? `${input.value.trim()}\n` : '';
  input.value = `${prefix}@知识库 请核对「${title}」（${citation}），返回原文定位、适用边界与可能反例。`;
  input.focus();
  renderPendingKbCitations();
  showToast(`已把 ${title} 挂到下一条群聊消息`);
}

function openKnowledgePanel() {
  selectRightPanel('knowledge');
  if (!knowledgeState.summary) loadKnowledgeSummary();
}

/*
 * Versioned workspace mount.
 *
 * This is deliberately a small, progressive-disclosure surface next to the
 * private materials KB.  The catalog endpoint returns only allowlisted repo
 * metadata and bounded lexical snippets; a `repo:` ref is a context pointer,
 * never a mathematical fact or a release-proof artifact.
 */
function workspaceEndpoint(path = '') {
  return LIVE_API ? `${LIVE_API}/api/projects/${LIVE_PROJECT}/workspace${path}` : '';
}

function workspaceErrorMessage(payload, fallback = '工程上下文请求失败') {
  const detail = payload?.detail;
  if (typeof detail === 'string') return detail;
  if (detail && typeof detail === 'object') return detail.message || detail.code || fallback;
  return fallback;
}

function workspaceCounts(catalog) {
  const counts = catalog?.counts || {};
  return {
    items: Number.isFinite(Number(counts.items)) ? Number(counts.items) : 0,
    searchable: Number.isFinite(Number(counts.searchable)) ? Number(counts.searchable) : 0,
    assets: Number.isFinite(Number(counts.asset)) ? Number(counts.asset) : 0,
  };
}

function renderWorkspaceMount(catalog) {
  const root = document.getElementById('workspaceMountStrip');
  if (!root) return;
  const ready = Boolean(catalog && catalog.schema_version === 'workspace-catalog/v1');
  const counts = workspaceCounts(catalog);
  root.dataset.status = ready ? 'ready' : (LIVE_API ? 'pending' : 'blocked');
  root.setAttribute('aria-label', ready ? `工程上下文已挂载，${counts.items} 个来源` : '工程上下文尚未挂载');
  const meta = document.getElementById('workspaceMountMeta');
  const count = document.getElementById('workspaceMountCount');
  const inline = document.getElementById('workspaceInlineStatus');
  if (ready) {
    const revision = compactRevision(catalog.manifest_sha || catalog.manifest_sha256, 17);
    const integrity = String(workspaceState.integrity?.status || '').toUpperCase();
    const integrityNote = integrity === 'STALE_DECLARATION' ? ' · 声明待更新' : '';
    if (meta) meta.textContent = `${counts.searchable} 可检索 · ${counts.assets} 个视觉资产 · runtime mount · ${revision}${integrityNote}`;
    if (count) count.textContent = String(counts.items);
    if (inline) {
      // Keep the persistent chip quiet; the detailed panel carries the
      // declaration warning and the title exposes it to assistive readers.
      inline.textContent = `工程上下文 · ${counts.items}`;
      inline.dataset.status = integrity === 'STALE_DECLARATION' ? 'stale' : 'ready';
      inline.title = `版本化工程上下文：${counts.items} 个来源，${counts.searchable} 个可检索${integrity === 'STALE_DECLARATION' ? '；声明待更新' : ''}`;
    }
  } else {
    if (meta) meta.textContent = LIVE_API ? '正在读取白名单工作区 · 只读上下文' : '实时服务未连接 · 仅保留演示界面';
    if (count) count.textContent = '—';
    if (inline) {
      inline.textContent = LIVE_API ? '工程上下文 · 读取中' : '工程上下文 · 未连接';
      inline.dataset.status = LIVE_API ? 'pending' : 'blocked';
      inline.title = LIVE_API ? '正在读取版本化工程上下文' : '实时服务未连接';
    }
  }
}

function workspaceResultMarkup(item) {
  const path = item?.path_rel || item?.path || '';
  if (!path) return '';
  const ref = item.source_ref || `repo:${path}`;
  const kind = item.kind || 'source';
  const match = item.match_source && item.match_source !== 'browse' ? item.match_source : 'workspace';
  const snippet = item.snippet || (item.text_searchable ? '文本源 · 可按关键词检索' : '资源目录项 · 按需核对原文件');
  const hash = item.hash_status === 'HASHED' ? 'hash linked' : (item.hash_status || 'metadata');
  return `<article class="workspace-result" data-workspace-path="${escapeHTML(path)}"><div class="workspace-result-head"><span class="workspace-result-kind">${escapeHTML(kind)}</span><span class="workspace-result-match">${escapeHTML(match)}</span><button type="button" data-workspace-cite="${escapeHTML(path)}">挂到群聊</button></div><strong>${escapeHTML(path)}</strong><p>${escapeHTML(snippet)}</p><small>${escapeHTML(ref)} · ${escapeHTML(hash)} · ${escapeHTML(kbFormatBytes(item.size_bytes ?? item.size))}</small></article>`;
}

function renderWorkspaceResults(results, root = document.getElementById('workspaceResults')) {
  if (!root) return;
  const rows = Array.isArray(results) ? results : [];
  if (!rows.length) {
    root.innerHTML = '<div class="workspace-empty"><span>⌁</span><strong>当前快照没有命中</strong><p>换一个文件名、目录或能力关键词。</p></div>';
    return;
  }
  root.innerHTML = rows.slice(0, 24).map(workspaceResultMarkup).join('');
}

async function loadWorkspaceCatalog(force = false) {
  if (!LIVE_API) {
    renderWorkspaceMount(null);
    return null;
  }
  workspaceState.loading = true;
  try {
    const response = await fetch(`${workspaceEndpoint('/catalog')}${force ? `?refresh=${Date.now()}` : ''}`);
    const payload = await response.json();
    if (!response.ok) throw new Error(workspaceErrorMessage(payload, 'WORKSPACE_CATALOG_ERROR'));
    workspaceState.catalog = payload;
    workspaceState.revision = payload.manifest_sha || payload.manifest_sha256 || null;
    workspaceState.results = Array.isArray(payload.items) ? payload.items.slice(0, 24) : [];
    renderWorkspaceMount(payload);
    return payload;
  } catch (error) {
    workspaceState.catalog = null;
    workspaceState.results = [];
    workspaceState.integrity = null;
    renderWorkspaceMount(null);
    showToast(`工程上下文读取失败（${error.message || 'unknown'}）`);
    return null;
  } finally {
    workspaceState.loading = false;
  }
}

async function runWorkspaceSearch(queryOverride = '', targetRoot = null) {
  const input = document.getElementById('workspaceSearchInput');
  const query = String(queryOverride ?? input?.value ?? '').trim();
  if (input && queryOverride !== undefined) input.value = query;
  const root = targetRoot || document.getElementById('workspaceResults');
  if (!LIVE_API) {
    if (root) root.innerHTML = '<div class="workspace-empty"><strong>实时服务未连接</strong><p>当前只显示演示界面，未挂载工作区。</p></div>';
    return null;
  }
  if (root) root.innerHTML = '<div class="workspace-loading"><i></i><i></i><i></i><span>读取当前工作区…</span></div>';
  try {
    const params = new URLSearchParams({ q: query, top_k: '24' });
    const response = await fetch(`${workspaceEndpoint('/search')}?${params.toString()}`);
    const payload = await response.json();
    if (!response.ok) throw new Error(workspaceErrorMessage(payload, 'WORKSPACE_SEARCH_ERROR'));
    workspaceState.query = query;
    workspaceState.revision = payload.manifest_sha || payload.manifest_sha256 || workspaceState.revision;
    workspaceState.results = Array.isArray(payload.results || payload.items) ? (payload.results || payload.items) : [];
    renderWorkspaceResults(workspaceState.results, root);
    const meta = root?.parentElement?.querySelector('.workspace-browser-meta');
    if (meta) meta.textContent = `${payload.returned_count ?? workspaceState.results.length} 个命中 · ${compactRevision(payload.manifest_sha || workspaceState.revision, 17)} · 仅白名单上下文`;
    return payload;
  } catch (error) {
    if (root) root.innerHTML = `<div class="workspace-empty"><strong>检索暂不可用</strong><p>${escapeHTML(error.message || '请稍后重试')}</p></div>`;
    showToast(`工程上下文检索失败（${error.message || 'unknown'}）`);
    return null;
  }
}

function citeWorkspaceItem(item) {
  const path = item?.path_rel || item?.path;
  const ref = item?.source_ref || (path ? `repo:${path}` : '');
  if (!path || !isSafeWorkspaceRef(ref)) {
    showToast('该路径不在工程白名单内');
    return;
  }
  if (!knowledgePendingRefs.includes(ref)) knowledgePendingRefs.push(ref);
  const input = document.getElementById('messageInput');
  const prefix = input.value.trim() ? `${input.value.trim()}\n` : '';
  input.value = `${prefix}@工程上下文 请核对「${path}」（${ref}），说明它能支持的工作流边界、版本与待复核风险。`;
  input.focus();
  renderPendingKbCitations();
  closeModal();
  showToast(`已把 ${path} 挂到下一条群聊消息`);
}

async function openWorkspaceBrowser() {
  if (!workspaceState.catalog && LIVE_API) await loadWorkspaceCatalog();
  const catalog = workspaceState.catalog;
  const counts = workspaceCounts(catalog);
  const revision = compactRevision(catalog?.manifest_sha || workspaceState.revision, 17);
  showModal('工程上下文 · 只读挂载', `<div class="workspace-browser"><p class="workspace-browser-intro">当前工程的版本化 skills、notes、docs、代码与视觉资产。这里只提供候选上下文；不会把仓库说明自动当成数学事实。</p><form id="workspaceSearchForm" class="workspace-search-form"><input id="workspaceSearchInput" type="search" autocomplete="off" placeholder="搜文件名、能力、流程或关键词…" aria-label="搜索工程上下文"><button type="submit">检索</button></form><div class="workspace-browser-meta">${catalog ? `${counts.items} 个来源 · ${counts.searchable} 可检索 · ${revision}` : (LIVE_API ? '工作区暂不可用' : '实时服务未连接')}</div><div id="workspaceResults" class="workspace-results"></div><p class="workspace-browser-note">repo: 引用只证明上下文位置；进入模型或论文前仍需题面锁定、参数来源、独立验证与 Owner 审批。</p></div>`);
  const root = document.getElementById('workspaceResults');
  renderWorkspaceResults(workspaceState.results.length ? workspaceState.results : (catalog?.items || []).slice(0, 24), root);
  const form = document.getElementById('workspaceSearchForm');
  if (form) form.addEventListener('submit', event => { event.preventDefault(); runWorkspaceSearch(undefined, root); });
  if (root) root.addEventListener('click', event => {
    const button = event.target.closest('[data-workspace-cite]');
    if (!button) return;
    const path = button.dataset.workspaceCite;
    const item = workspaceState.results.find(row => (row.path_rel || row.path) === path) || catalog?.items?.find(row => (row.path_rel || row.path) === path);
    citeWorkspaceItem(item || { path_rel: path, source_ref: `repo:${path}` });
  });
  document.getElementById('workspaceSearchInput')?.focus();
}

/*
 * Capability studio projection.
 * The catalog is deliberately separate from the document search results: a
 * method card is a reusable hypothesis with an interface, not a copied paper
 * conclusion.  The browser can compose and inspect a graph, while the server
 * performs the authoritative typed-DAG check.
 */
function capabilityEndpoint(path = '') {
  return LIVE_API ? `${LIVE_API}/api/projects/${LIVE_PROJECT}/capabilities${path}` : '';
}

function capabilityErrorMessage(payload, fallback = '能力目录请求失败') {
  const detail = payload?.detail;
  if (typeof detail === 'string') return detail;
  if (detail && typeof detail === 'object') return detail.message || detail.code || fallback;
  return fallback;
}

function capabilityBlocks() { return capabilityState.catalog?.workflow_blocks || []; }
function capabilityMethods() { return capabilityState.catalog?.methods || []; }
function capabilityPresets() { return capabilityState.catalog?.workflow_presets || []; }
function capabilityArchetypes() { return capabilityState.catalog?.problem_archetypes || []; }
function capabilityBlock(id) { return capabilityBlocks().find(item => item.id === id); }
function capabilityMethod(id) { return capabilityMethods().find(item => item.id === id); }
function capabilityPacks() { return capabilityState.catalog?.content_packs || capabilityContentPacks; }

function renderCapabilitySource(catalog) {
  const root = document.getElementById('capabilitySourceStrip');
  if (!root) return;
  const source = catalog?.source || {};
  const status = String(source.source_status || 'UNAVAILABLE').toUpperCase();
  const count = source.indexed_count ?? source.valid_count ?? 0;
  const signals = source.asset_signals || {};
  const rev = compactRevision(catalog?.capability_revision || source.index_revision, 17);
  const pending = status === 'LOCAL_PENDING' || status === 'UNAVAILABLE';
  root.classList.toggle('pending', pending);
  root.innerHTML = `<span class="knowledge-dot ${pending ? 'pending' : ''}"></span><span>${escapeHTML(status)} · ${escapeHTML(count)} 个资料候选 · 论文线索 ${escapeHTML(signals.paper_candidates ?? '—')} · 能力 revision ${escapeHTML(rev)}</span>`;
}

function renderCapabilityCatalog(catalog) {
  const nextRevision = catalog?.capability_revision || catalog?.source?.index_revision || null;
  const revisionChanged = Boolean(capabilityState.revision && nextRevision && capabilityState.revision !== nextRevision);
  if (revisionChanged && capabilityState.assembly?.nodes?.length) {
    // A validation report is scoped to the capability catalogue revision that
    // produced it.  Do not leave a green gate/send action alive after refresh.
    capabilityState.assembly.validation = null;
    capabilityState.assembly.revision = null;
    capabilityState.assembly.diff = null;
    capabilityState.assembly.methodBlockWarnings = [];
    assemblyValidationEpoch += 1;
  }
  capabilityState.catalog = catalog || null;
  capabilityState.revision = nextRevision;
  renderCapabilitySource(catalog);
  const badge = document.getElementById('capabilityBadge');
  if (badge) badge.textContent = catalog?.methods?.length ? String(catalog.methods.length) : '—';
  const archetypeSelect = document.getElementById('capabilityArchetypeSelect');
  if (archetypeSelect) {
    const current = archetypeSelect.value;
    archetypeSelect.innerHTML = `<option value="">自动识别 / 先不限定</option>${capabilityArchetypes().map(item => `<option value="${escapeHTML(item.id)}">${escapeHTML(item.title)}</option>`).join('')}`;
    if (current && [...archetypeSelect.options].some(option => option.value === current)) archetypeSelect.value = current;
  }
  const presetSelect = document.getElementById('capabilityPresetSelect');
  if (presetSelect) {
    const current = presetSelect.value;
    presetSelect.innerHTML = capabilityPresets().map(item => `<option value="${escapeHTML(item.id)}">${escapeHTML(item.title)}</option>`).join('') || '<option value="">暂无标准模板</option>';
    if (current && [...presetSelect.options].some(option => option.value === current)) presetSelect.value = current;
  }
  const applyPresetButton = document.getElementById('applyPresetBtn');
  if (applyPresetButton) {
    applyPresetButton.disabled = capabilityPresets().length === 0;
    applyPresetButton.setAttribute('aria-disabled', String(applyPresetButton.disabled));
  }
  const presetRoot = document.getElementById('presetList');
  if (presetRoot) {
    const blocks = new Map(capabilityBlocks().map(item => [item.id, item]));
    presetRoot.innerHTML = capabilityPresets().map(preset => {
      const flow = (preset.block_ids || []).map(id => blocks.get(id)?.title || id).slice(0, 9);
      return `<article class="preset-card"><div class="preset-card-head"><strong>${escapeHTML(preset.title)}</strong><em>${escapeHTML((preset.archetype_ids || []).length)} 类题型</em></div><p>${escapeHTML(preset.description)}</p><div class="preset-flow">${flow.map((name, index) => `${index ? '<i>›</i>' : ''}<span>${escapeHTML(name)}</span>`).join('')}</div></article>`;
    }).join('') || '<div class="assembly-loading">能力模板目录为空。</div>';
  }
  const blockRoot = document.getElementById('blockPalette');
  if (blockRoot) {
    blockRoot.innerHTML = capabilityBlocks().map(block => `<button type="button" class="assembly-item ${block.required ? 'required-item' : ''}" data-assembly-add-type="block" data-assembly-add-id="${escapeHTML(block.id)}" title="输入：${escapeHTML(Object.keys(block.input_ports || {}).join(', ') || '无')}；输出：${escapeHTML(Object.keys(block.output_ports || {}).join(' · ') || '无')}"><strong>${escapeHTML(block.title)}${block.required ? ' · 必选' : ''}</strong><span>${escapeHTML(block.kind)} · ${escapeHTML(Object.keys(block.output_ports || {}).join(' · ') || '无输出')}</span>${block.evidence_output ? `<em>证据输出</em>` : ''}</button>`).join('') || '<div class="assembly-loading">工作块目录为空。</div>';
  }
  const methodRoot = document.getElementById('methodPalette');
  if (methodRoot) {
    methodRoot.innerHTML = capabilityMethods().map(method => `<button type="button" class="assembly-item" data-assembly-add-type="method" data-assembly-add-id="${escapeHTML(method.id)}" title="适用：${escapeHTML((method.applicability || []).join('；'))}；禁用：${escapeHTML((method.prohibitions || []).join('；'))}"><strong>${escapeHTML(method.title)}</strong><span>${escapeHTML(method.family)} · ${(method.validation || []).slice(0, 2).map(escapeHTML).join(' + ')}</span><em>候选卡 · ${escapeHTML(method.source_kind || 'curated/inferred')}</em></button>`).join('') || '<div class="assembly-loading">方法卡目录为空。</div>';
  }
  const packRoot = document.getElementById('contentPackPalette');
  if (packRoot) {
    const selectedPacks = new Set(capabilityState.assembly?.contentPackIds || []);
    packRoot.innerHTML = capabilityPacks().map(pack => { const selected = selectedPacks.has(pack.id); const evidenceCount = (capabilityState.assembly?.contentPackEvidenceByPack?.[pack.id] || []).length; const evidenceNote = selected && evidenceCount ? ` · ${evidenceCount}条候选` : ''; return `<button type="button" class="content-pack ${selected ? 'selected' : ''}" data-content-pack="${escapeHTML(pack.id)}" aria-pressed="${selected ? 'true' : 'false'}" title="${selected ? '点击卸载；' : '点击挂载；'}检索：${escapeHTML(pack.query || '')}"><span>${escapeHTML(pack.title)}</span><em>${escapeHTML(pack.note)}</em><b>${selected ? `已挂载${evidenceNote} · 点击卸载` : '未挂载 · 点击挂载'}</b></button>`; }).join('') || '<div class="assembly-loading">内容包尚未加载。</div>';
  }
  renderAssemblyCanvas();
  // The optional full-screen puzzle studio listens for this projection event.
  // Keep the existing sidebar renderer as the source of truth; the new layer
  // is only a view and never becomes a second capability catalogue.
  try { window.dispatchEvent(new CustomEvent('qingjia:capability-catalog', { detail: { catalog } })); } catch (_) { /* older host */ }
}

function setAssemblyMode(mode) {
  capabilityState.mode = mode === 'free' ? 'free' : 'standard';
  document.querySelectorAll('.assembly-mode').forEach(button => button.classList.toggle('active', button.dataset.assemblyMode === capabilityState.mode));
  document.querySelectorAll('[data-assembly-view]').forEach(section => { section.hidden = section.dataset.assemblyView !== capabilityState.mode; });
}

function rebuildContentPackEvidence() {
  const assembly = capabilityState.assembly;
  const selected = new Set(assembly.contentPackIds || []);
  const byPack = assembly.contentPackEvidenceByPack || {};
  const currentSourceRevision = capabilityState.catalog?.source?.index_revision || null;
  const refs = [];
  const revisions = [];
  selected.forEach(id => {
    const entry = byPack[id];
    if (!entry || !Array.isArray(entry.refs) || !entry.refs.length) return;
    // Do not carry a resolver result across a refreshed KB snapshot.
    if (currentSourceRevision && entry.indexRevision && entry.indexRevision !== currentSourceRevision) return;
    refs.push(...entry.refs);
    if (entry.indexRevision) revisions.push(entry.indexRevision);
  });
  assembly.contentPackEvidenceRefs = [...new Set(refs)].sort();
  assembly.contentPackIndexRevision = revisions.length ? revisions[0] : null;
  assembly.contentPackResolutionRevision = selected.size ? (selected.values().next().value && byPack[selected.values().next().value]?.resolutionRevision) || null : null;
}

async function resolveContentPackEvidence(pack) {
  if (!LIVE_API || !pack?.id) return null;
  const assembly = capabilityState.assembly;
  const params = new URLSearchParams({ top_k: '4', with_preview: 'true' });
  try {
    const response = await fetch(`${capabilityEndpoint(`/content-packs/${encodeURIComponent(pack.id)}/resolve`)}?${params.toString()}`);
    const payload = await response.json();
    if (!response.ok) throw new Error(capabilityErrorMessage(payload, 'CONTENT_PACK_RESOLVE_ERROR'));
    if (assembly !== capabilityState.assembly || !(assembly.contentPackIds || []).includes(pack.id)) return payload;
    assembly.contentPackEvidenceByPack = assembly.contentPackEvidenceByPack || {};
    assembly.contentPackEvidenceByPack[pack.id] = {
      refs: Array.isArray(payload.evidence_refs) ? [...payload.evidence_refs] : [],
      indexRevision: payload.index_revision || null,
      resolutionRevision: payload.resolution_revision || null,
      coverage: payload.coverage || null,
    };
    rebuildContentPackEvidence();
    assembly.revision = null;
    assembly.validation = null;
    assembly.diff = null;
    assembly.methodBlockWarnings = [];
    assemblyValidationEpoch += 1;
    renderCapabilityCatalog(capabilityState.catalog);
    renderAssemblyGate();
    renderAssemblyDiff(null);
    if (assembly.nodes.length) validateAssembly();
    const count = assembly.contentPackEvidenceByPack[pack.id].refs.length;
    showToast(`${pack.title} 已绑定 ${count} 条当前快照候选；页级定位仍需人工核对`);
    return payload;
  } catch (error) {
    if (assembly === capabilityState.assembly && (assembly.contentPackIds || []).includes(pack.id)) showToast(`${pack.title} 证据解析失败：${error.message || 'unknown'}`);
    return null;
  }
}

function toggleContentPack(pack) {
  const ids = new Set(capabilityState.assembly.contentPackIds || []);
  if (ids.has(pack.id)) {
    ids.delete(pack.id);
    if (capabilityState.assembly.contentPackEvidenceByPack) delete capabilityState.assembly.contentPackEvidenceByPack[pack.id];
    showToast(`已卸载内容包：${pack.title}`);
  } else {
    ids.add(pack.id);
    showToast(`已挂载内容包：${pack.title}；检索结果仍需回到原文核验`);
  }
  capabilityState.assembly.contentPackIds = [...ids].sort();
  capabilityState.assembly.revision = null;
  capabilityState.assembly.validation = null;
  capabilityState.assembly.diff = null;
  capabilityState.assembly.methodBlockWarnings = [];
  rebuildContentPackEvidence();
  assemblyValidationEpoch += 1;
  renderCapabilityCatalog(capabilityState.catalog);
  renderAssemblyDiff(null);
  if (capabilityState.assembly.nodes.length) validateAssembly();
  if (ids.has(pack.id)) resolveContentPackEvidence(pack);
}

function selectedCapabilityArchetype() {
  const id = document.getElementById('capabilityArchetypeSelect')?.value;
  return capabilityArchetypes().find(item => item.id === id) || capabilityArchetypes()[0] || null;
}

function selectedCapabilityPreset() {
  const id = document.getElementById('capabilityPresetSelect')?.value;
  return capabilityPresets().find(item => item.id === id) || capabilityPresets()[0] || null;
}

function methodForArchetype(archetype) {
  const id = archetype?.id || '';
  const wanted = id === 'optimization' ? ['linear-programming', 'integer-programming'] : id === 'mechanism' ? ['runge-kutta-ode', 'finite-difference-pde'] : id === 'simulation' ? ['monte-carlo', 'discrete-event-simulation'] : id === 'policy-decision' ? ['nsga2-multiobjective', 'monte-carlo'] : ['linear-regression', 'logistic-regression'];
  return wanted.map(id => capabilityMethod(id)).find(Boolean) || capabilityMethods()[0] || null;
}

function blockForMethod(method) {
  const family = String(method?.family || '').toLowerCase();
  if (family === 'optimization') return 'optimization';
  if (family === 'mechanism') return 'mechanism-model';
  if (family === 'simulation') return 'simulation';
  if (family === 'validation') return 'sensitivity';
  return 'baseline-model';
}

function makeAssemblyNode(blockId, index, methodId = null) {
  const block = capabilityBlock(blockId);
  return { node_id: `${blockId.replace(/[^A-Za-z0-9]+/g, '-')}-${index + 1}`, block_id: blockId, method_id: methodId, label: block?.title || blockId, config: {} };
}

function buildPresetAssembly(options = {}) {
  const preset = selectedCapabilityPreset();
  const archetype = selectedCapabilityArchetype();
  if (!preset) return null;
  // The full-screen puzzle studio passes the exact previewed block list.  A
  // fixed route must not silently shrink between preview and application;
  // archetype-based tailoring remains available to the compact legacy panel
  // when no explicit list is supplied.
  const exactBlockIds = Array.isArray(options.block_ids) ? options.block_ids.map(String) : null;
  if (exactBlockIds) {
    const known = new Set(capabilityBlocks().map(item => String(item.id)));
    const unknown = exactBlockIds.filter(id => !known.has(id));
    const duplicate = exactBlockIds.filter((id, index) => exactBlockIds.indexOf(id) !== index);
    if (unknown.length || duplicate.length) {
      showToast(`固定方案清单无效${unknown.length ? ` · 未知块 ${unknown.slice(0, 2).join('、')}` : ''}${duplicate.length ? ' · 存在重复块' : ''}`);
      return null;
    }
  }
  let ids = exactBlockIds ? [...exactBlockIds] : [...(preset.block_ids || [])];
  const archetypeId = archetype?.id || '';
  // The catalog's standard preset is a superset.  Keep the visible chain
  // focused on the selected problem family while retaining the mandatory
  // baseline/validation/writing gates.
  if (!exactBlockIds && preset.id === 'standard-cumcm') {
    const core = ['problem-decomposition', 'data-audit', 'parameter-contract', 'baseline-model', 'validation', 'critic-challenger', 'sensitivity', 'writing'];
    const main = archetypeId === 'mechanism' ? ['scenario-contract', 'mechanism-model', 'simulation'] : archetypeId === 'simulation' ? ['scenario-contract', 'simulation'] : archetypeId === 'optimization' || archetypeId === 'policy-decision' ? ['optimization'] : [];
    // The transparent baseline must precede any solver/simulation block: the
    // latter consume a typed ``model`` port.  Keeping the order here makes the
    // auto-link proposal valid for every archetype instead of silently
    // producing a BLOCKED graph for optimisation/simulation starts.
    ids = [...core.slice(0, 3), 'baseline-model', ...main, ...core.slice(4)];
    if (archetypeId === 'mechanism' || archetypeId === 'simulation' || archetypeId === 'policy-decision') ids.push('defense');
  }
  const method = methodForArchetype(archetype);
  const mainBlock = method ? blockForMethod(method) : null;
  const seen = new Set();
  const nodes = [];
  ids.forEach(id => {
    if (seen.has(id) || !capabilityBlock(id)) return;
    seen.add(id);
    const attach = id === mainBlock ? method?.id : null;
    nodes.push(makeAssemblyNode(id, nodes.length, attach));
  });
  const defaultPacks = capabilityPacks().map(pack => pack.id);
  capabilityState.assembly = { nodes, edges: autoLinkAssembly(nodes), presetId: preset.id, archetypeId: archetype?.id || null, validation: null, revision: null, diff: null, previousNodes: [], previousEdges: [], committedRevision: null, innovationCard: null, previousInnovationCard: null, contentPackIds: defaultPacks, previousContentPackIds: [], contentPackEvidenceRefs: [], contentPackEvidenceByPack: {}, contentPackIndexRevision: null, contentPackResolutionRevision: null, methodBlockWarnings: [] };
  assemblyValidationEpoch += 1;
  renderAssemblyCanvas();
  renderInnovationSummary();
  renderCapabilityCatalog(capabilityState.catalog);
  setAssemblyMode('free');
  showToast(`已载入「${preset.title}」；现在可以替换或追加方法卡`);
  validateAssembly();
  return capabilityState.assembly;
}

function autoLinkAssembly(nodes) {
  const edges = [];
  const seen = new Set();
  const blockMap = new Map(capabilityBlocks().map(item => [item.id, item]));
  nodes.forEach((targetNode, targetIndex) => {
    const target = blockMap.get(targetNode.block_id);
    if (!target) return;
    const incoming = new Set();
    Object.entries(target.input_ports || {}).forEach(([targetPort, targetType]) => {
      // Search nearest prior provider first.  One output may feed multiple
      // consumers; this is a mapping proposal, not an execution plan.
      for (let sourceIndex = targetIndex - 1; sourceIndex >= 0; sourceIndex -= 1) {
        const sourceNode = nodes[sourceIndex];
        const source = blockMap.get(sourceNode.block_id);
        const candidate = Object.entries(source?.output_ports || {}).find(([port, type]) => type === targetType && !seen.has(`${sourceNode.node_id}:${port}->${targetNode.node_id}:${targetPort}`));
        if (!candidate) continue;
        const [sourcePort] = candidate;
        const key = `${sourceNode.node_id}:${sourcePort}->${targetNode.node_id}:${targetPort}`;
        if (!seen.has(key)) { edges.push({ source: sourceNode.node_id, source_port: sourcePort, target: targetNode.node_id, target_port: targetPort }); seen.add(key); incoming.add(targetPort); }
        break;
      }
    });
  });
  return edges;
}

function renderAssemblyCanvas() {
  const root = document.getElementById('assemblyCanvas');
  const count = document.getElementById('assemblyCount');
  const nodes = capabilityState.assembly?.nodes || [];
  if (count) count.textContent = `${nodes.length} 个节点`;
  const sendButton = document.getElementById('sendAssemblyBtn');
  if (sendButton) {
    sendButton.disabled = nodes.length === 0;
    sendButton.setAttribute('aria-disabled', nodes.length === 0 ? 'true' : 'false');
    sendButton.title = nodes.length === 0 ? '先加入工作块或方法卡' : '提交结构审查并同步到群聊';
  }
  if (!root) return;
  if (!nodes.length) {
    root.innerHTML = `<div class="assembly-empty"><span>${dragonIcon('mark', { className: 'dragon-affordance' })}</span><strong>节点尚未编排</strong><p>建议链路：题面 → 数据/机制 → baseline → 方法 → 验证 → claim。</p></div>`;
    return;
  }
  root.innerHTML = nodes.map((node, index) => {
    const method = node.method_id ? capabilityMethod(node.method_id) : null;
    const block = capabilityBlock(node.block_id);
    const subtitle = method ? `${method.title} · ${method.family}` : `${block?.kind || 'block'} · ${Object.keys(block?.output_ports || {}).join(' + ') || '待定义输出'}`;
    return `<div class="assembly-node" data-assembly-node-index="${index}"><span class="assembly-node-index">${index + 1}</span><button type="button" class="assembly-node-copy" data-assembly-node-view="${index}"><strong>${escapeHTML(node.label || block?.title || node.block_id)}</strong><span>${escapeHTML(subtitle)}</span></button><button type="button" class="assembly-node-remove" data-assembly-node-remove="${index}" aria-label="移除节点">${dragonIcon('mark', { className: 'dragon-affordance' })}</button></div>`;
  }).join('');
  try { window.dispatchEvent(new CustomEvent('qingjia:assembly-updated', { detail: { assembly: capabilityState.assembly } })); } catch (_) { /* older host */ }
}

function addAssemblyItem(type, id) {
  let blockId = id;
  let methodId = null;
  if (type === 'method') {
    const method = capabilityMethod(id);
    if (!method) return;
    methodId = method.id;
    blockId = blockForMethod(method);
  }
  if (!capabilityBlock(blockId)) { showToast('这个能力卡暂时没有兼容的工作块'); return; }
  const nodes = capabilityState.assembly.nodes || [];
  const node = makeAssemblyNode(blockId, nodes.length, methodId);
  node.label = methodId ? `${capabilityMethod(methodId)?.title || id}` : node.label;
  nodes.push(node);
  capabilityState.assembly.edges = autoLinkAssembly(nodes);
  capabilityState.assembly.validation = null;
  capabilityState.assembly.revision = null;
  capabilityState.assembly.diff = null;
  capabilityState.assembly.methodBlockWarnings = [];
  assemblyValidationEpoch += 1;
  renderAssemblyCanvas();
  renderAssemblyGate();
  renderAssemblyDiff(null);
  renderInnovationSummary();
}

function removeAssemblyNode(index) {
  const nodes = capabilityState.assembly.nodes || [];
  if (!nodes[index]) return;
  nodes.splice(index, 1);
  nodes.forEach((node, i) => { node.node_id = `${node.block_id.replace(/[^A-Za-z0-9]+/g, '-')}-${i + 1}`; });
  capabilityState.assembly.edges = autoLinkAssembly(nodes);
  capabilityState.assembly.validation = null;
  capabilityState.assembly.revision = null;
  capabilityState.assembly.diff = null;
  capabilityState.assembly.methodBlockWarnings = [];
  assemblyValidationEpoch += 1;
  renderAssemblyCanvas();
  renderAssemblyGate();
  renderAssemblyDiff(null);
  renderInnovationSummary();
}

function renderAssemblyGate(payload = null, local = false) {
  const root = document.getElementById('assemblyGate');
  if (!root) return;
  const validation = payload?.validation || capabilityState.assembly.validation;
  if (!validation) { root.className = 'assembly-gate neutral'; root.innerHTML = `<span class="gate-icon">${dragonIcon('mark', { className: 'dragon-gate-icon' })}</span><div><strong>尚未检查链路</strong><p>当前图谱发生了变化；重新检查后才会生成新的 assembly revision、差异和适配提示。</p></div>`; renderAssemblyDiff(null); return; }
  const valid = validation.valid === true;
  const errors = validation.errors || [];
  const cls = valid ? 'pass' : (errors.length > 2 ? 'blocked' : 'warn');
  const missing = validation.missing_required_blocks || validation.hard_gate?.missing || [];
  const warnings = payload?.method_block_warnings || capabilityState.assembly.methodBlockWarnings || [];
  const title = valid ? '结构可审 · 尚不等于数值已验证' : `需要修复 ${errors.length} 个结构门`;
  const detail = valid ? `拓扑 ${validation.node_count || 0} 节点 / ${validation.edge_count || 0} 条边${local ? ' · 本地预览' : ''}${missing.length ? ` · 缺必选 ${missing.length}` : ''}${warnings.length ? ` · ${warnings.length} 个方法适配提示` : ''}` : errors.slice(0, 3).join('；');
  root.className = `assembly-gate ${cls}`;
  const warningText = warnings.slice(0, 3).map(item => `${item.method_id || '方法'} → 建议 ${item.suggested_block || '兼容工作块'}`).join('；');
  root.innerHTML = `<span class="gate-icon">${dragonIcon('mark', { className: 'dragon-gate-icon' })}</span><div><strong>${escapeHTML(title)}</strong><p>${escapeHTML(detail)}</p>${missing.length ? `<small>必选：${escapeHTML(missing.join(' · '))}</small>` : ''}${warnings.length ? `<small class="assembly-warning">适配提示：${escapeHTML(warningText)}${warnings.length > 3 ? '；…' : ''}（不自动改写你的选择）</small>` : ''}</div>`;
  renderAssemblyDiff(payload?.diff || capabilityState.assembly.diff);
}

function renderAssemblyDiff(diff) {
  const root = document.getElementById('assemblyDiff');
  if (!root) return;
  if (!diff) { root.hidden = true; root.innerHTML = ''; return; }
  const added = (diff.added_nodes || []).length;
  const removed = (diff.removed_nodes || []).length;
  const changed = (diff.changed_nodes || []).length;
  const edgeDelta = (diff.added_edges || []).length + (diff.removed_edges || []).length;
  const missing = diff.missing_required_blocks || [];
  root.hidden = false;
  root.className = `assembly-diff ${missing.length ? 'blocked' : 'ready'}`;
  const innovationChanged = Boolean(diff.innovation_changed);
  const innovationGateState = diff.innovation_gate || innovationGate(capabilityState.assembly.innovationCard);
  const novelty = innovationChanged ? `创新卡${innovationGateState?.ready ? '已具备审查字段' : '仍是草稿'}` : '创新卡未变化';
  const packAdded = diff.content_pack_added || [];
  const packRemoved = diff.content_pack_removed || [];
  const packText = packAdded.length || packRemoved.length ? `内容包：+${packAdded.length} / −${packRemoved.length}` : '内容包未变化';
  const evidenceCount = (capabilityState.assembly.contentPackEvidenceRefs || []).length;
  const evidenceText = evidenceCount ? `已绑定 ${evidenceCount} 条候选来源` : '尚未绑定内容包来源';
  root.innerHTML = `<div class="assembly-diff-head"><strong>装配差异 · ${diff.changed ? '有变化' : '无变化'}</strong><span>${missing.length ? `缺 ${missing.length} 个必选块` : '硬门齐全'}</span></div><div class="assembly-diff-stats"><span><b>+${added}</b> 新增</span><span><b>−${removed}</b> 移除</span><span><b>${changed}</b> 修改</span><span><b>${edgeDelta}</b> 条边变化</span><span><b>${innovationChanged ? '是' : '否'}</b> ${escapeHTML(novelty)}</span></div>${missing.length ? `<p>先补齐：${escapeHTML(missing.join(' · '))}</p>` : `<p>这是结构差异，不是模型效果差异；${escapeHTML(packText)}；${escapeHTML(evidenceText)}；发送群聊前仍需提交审查。</p>`}`;
}

function innovationGate(card) {
  const fields = ['baseline', 'difference', 'necessity', 'boundary', 'validation'];
  const missing = fields.filter(field => !String(card?.[field] || '').trim());
  return { present: Boolean(card), ready: Boolean(card) && missing.length === 0, status: card && missing.length === 0 ? 'READY_FOR_REVIEW' : 'DRAFT_UNVERIFIED', missing, claim_class: 'hypothesis' };
}

function renderInnovationSummary() {
  const root = document.getElementById('innovationSummary');
  if (!root) return;
  const card = capabilityState.assembly?.innovationCard;
  if (!card) {
    root.hidden = true;
    root.innerHTML = '';
    return;
  }
  const gate = innovationGate(card);
  root.hidden = false;
  root.className = `innovation-summary ${gate.ready ? 'ready' : 'draft'}`;
  const preview = String(card.difference || card.necessity || '').slice(0, 120);
  root.innerHTML = `<div><strong>创新差异卡</strong><span>${gate.ready ? 'READY_FOR_REVIEW · 仍需独立验证' : 'DRAFT_UNVERIFIED · 字段未齐'}</span></div><p>${escapeHTML(preview || '尚未填写差异')}</p>${gate.missing.length ? `<small>待补：${escapeHTML(gate.missing.join(' · '))}</small>` : '<small>已绑定小问：' + escapeHTML(card.subproblem_id || window.selectedSubproblem || 'Q2') + ' · claim_class=hypothesis</small>'}`;
}

function localAssemblyValidation() {
  const nodes = capabilityState.assembly.nodes || [];
  const errors = [];
  const blockIds = nodes.map(node => node.block_id);
  const required = ['problem-decomposition', 'baseline-model', 'validation', 'writing'];
  required.forEach(id => { if (!blockIds.includes(id)) errors.push(`required_block_missing:${id}`); });
  if (!nodes.some(node => node.block_id === 'validation')) errors.push('required_validation_node_missing');
  const paperIndex = blockIds.indexOf('writing');
  const validationIndex = blockIds.indexOf('validation');
  if (paperIndex >= 0 && validationIndex < 0) errors.push('evidence_chain_missing:validation_to_writing');
  if (paperIndex >= 0 && validationIndex > paperIndex) errors.push('evidence_chain_order_invalid');
  const methodCompatibility = assemblyMethodCompatibilityIssues(nodes);
  methodCompatibility.forEach(item => errors.push(`method_block_mismatch:${item.node_id}:${item.method_id}:${item.selected_block}`));
  return { valid: errors.length === 0, errors, topological_order: nodes.map(node => node.node_id), node_count: nodes.length, edge_count: capabilityState.assembly.edges.length, missing_required_blocks: required.filter(id => !blockIds.includes(id)), required_block_ids: required, method_block_mismatches: methodCompatibility, hard_gate: { ready: errors.length === 0, missing: required.filter(id => !blockIds.includes(id)) } };
}

function assemblyMethodCompatibilityIssues(nodes = []) {
  const familyDefaultBlock = {
    statistical: 'baseline-model', classification: 'baseline-model', ensemble: 'baseline-model',
    'time-series': 'baseline-model', survival: 'baseline-model', optimization: 'optimization',
    mechanism: 'mechanism-model', simulation: 'simulation', validation: 'sensitivity',
  };
  return (nodes || []).flatMap(node => {
    if (!node?.method_id) return [];
    const method = capabilityMethod(node.method_id);
    const block = capabilityBlock(node.block_id);
    if (!method || !block) return [];
    const typedKinds = Array.isArray(method.compatible_block_kinds) ? method.compatible_block_kinds.filter(Boolean).map(String) : [];
    const family = String(method.family || '').toLowerCase();
    const accepted = typedKinds.length ? typedKinds : (familyDefaultBlock[family] ? [String(capabilityBlock(familyDefaultBlock[family])?.kind || '')] : []);
    if (!accepted.length || accepted.includes(String(block.kind))) return [];
    return [{ node_id: node.node_id, method_id: node.method_id, family, selected_block: node.block_id, selected_kind: block.kind, accepted_kinds: accepted }];
  });
}

async function validateAssembly() {
  const assembly = capabilityState.assembly;
  const epoch = ++assemblyValidationEpoch;
  if (!assembly.nodes.length) {
    assembly.validation = localAssemblyValidation();
    assembly.diff = localAssemblyDiff();
    renderAssemblyGate(null, !LIVE_API);
    return { validation: assembly.validation, diff: assembly.diff, error: 'empty_assembly' };
  }
  if (!LIVE_API) { assembly.validation = localAssemblyValidation(); assembly.diff = localAssemblyDiff(); renderAssemblyGate(null, true); return assembly.validation; }
  if (!capabilityState.revision) {
    const validation = { valid: false, errors: ['capability_revision_missing'], node_count: assembly.nodes.length, edge_count: assembly.edges.length };
    assembly.validation = validation;
    renderAssemblyGate();
    showToast('能力目录尚未同步，暂不能检查链路');
    return { validation, error: 'capability_revision_missing' };
  }
  try {
    const response = await fetch(`${capabilityEndpoint('/compose')}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ nodes: assembly.nodes, edges: assembly.edges, previous_nodes: assembly.previousNodes || [], previous_edges: assembly.previousEdges || [], innovation_card: assembly.innovationCard || undefined, previous_innovation_card: assembly.previousInnovationCard || undefined, content_pack_ids: assembly.contentPackIds || [], previous_content_pack_ids: assembly.previousContentPackIds || [], content_pack_evidence_refs: assembly.contentPackEvidenceRefs || [], content_pack_index_revision: assembly.contentPackIndexRevision || undefined, content_pack_resolution_revision: assembly.contentPackResolutionRevision || undefined, preset_id: assembly.presetId, archetype_id: assembly.archetypeId, scope: [window.selectedSubproblem || 'Q2'], base_revision: capabilityState.revision, idempotency_key: `assembly-${Date.now()}` }) });
    const payload = await response.json();
    if (!response.ok) throw new Error(capabilityErrorMessage(payload, 'CAPABILITY_COMPOSE_ERROR'));
    if (epoch !== assemblyValidationEpoch || assembly !== capabilityState.assembly) {
      return { validation: { valid: false, errors: ['validation_superseded'], node_count: capabilityState.assembly.nodes.length, edge_count: capabilityState.assembly.edges.length }, error: 'validation_superseded', superseded: true };
    }
    const remoteValidation = payload.validation || null;
    const methodCompatibility = assemblyMethodCompatibilityIssues(assembly.nodes);
    if (methodCompatibility.length) {
      payload.validation = {
        ...(remoteValidation || {}),
        valid: false,
        errors: [...(remoteValidation?.errors || []), ...methodCompatibility.map(item => `method_block_mismatch:${item.node_id}:${item.method_id}:${item.selected_block}`)],
        method_block_mismatches: methodCompatibility,
      };
      payload.status = 'BLOCKED';
    }
    assembly.validation = payload.validation || null;
    assembly.revision = payload.assembly_revision || null;
    assembly.diff = payload.diff || null;
    assembly.methodBlockWarnings = Array.isArray(payload.method_block_warnings) ? JSON.parse(JSON.stringify(payload.method_block_warnings)) : [];
    assembly.contentPackIds = Array.isArray(payload.content_pack_ids) ? [...payload.content_pack_ids] : (assembly.contentPackIds || []);
    assembly.contentPackEvidenceRefs = Array.isArray(payload.content_pack_evidence_refs) ? [...payload.content_pack_evidence_refs] : (assembly.contentPackEvidenceRefs || []);
    assembly.contentPackIndexRevision = payload.content_pack_index_revision || assembly.contentPackIndexRevision || null;
    assembly.contentPackResolutionRevision = payload.content_pack_resolution_revision || assembly.contentPackResolutionRevision || null;
    renderAssemblyGate(payload);
    return payload;
  } catch (error) {
    if (epoch !== assemblyValidationEpoch || assembly !== capabilityState.assembly) {
      return { validation: { valid: false, errors: ['validation_superseded'], node_count: capabilityState.assembly.nodes.length, edge_count: capabilityState.assembly.edges.length }, error: 'validation_superseded', superseded: true };
    }
    assembly.validation = { valid: false, errors: [error.message || 'CAPABILITY_COMPOSE_ERROR'], node_count: assembly.nodes.length, edge_count: assembly.edges.length };
    assembly.diff = null;
    assembly.methodBlockWarnings = [];
    renderAssemblyGate();
    showToast(`链路检查失败（${error.message || 'unknown'}）`);
    return { validation: assembly.validation, error: error.message || 'CAPABILITY_COMPOSE_ERROR' };
  }
}

function localAssemblyDiff() {
  const before = new Map((capabilityState.assembly.previousNodes || []).map(node => [node.node_id, JSON.stringify(node)]));
  const after = new Map((capabilityState.assembly.nodes || []).map(node => [node.node_id, JSON.stringify(node)]));
  const added = [...after.keys()].filter(id => !before.has(id));
  const removed = [...before.keys()].filter(id => !after.has(id));
  const changed = [...after.keys()].filter(id => before.has(id) && before.get(id) !== after.get(id));
  const missing = ['problem-decomposition', 'baseline-model', 'validation', 'writing'].filter(id => !(capabilityState.assembly.nodes || []).some(node => node.block_id === id));
  const beforeInnovation = JSON.stringify(capabilityState.assembly.previousInnovationCard || null);
  const afterInnovation = JSON.stringify(capabilityState.assembly.innovationCard || null);
  const beforePacks = new Set(capabilityState.assembly.previousContentPackIds || []);
  const afterPacks = new Set(capabilityState.assembly.contentPackIds || []);
  const packAdded = [...afterPacks].filter(id => !beforePacks.has(id)).sort();
  const packRemoved = [...beforePacks].filter(id => !afterPacks.has(id)).sort();
  return { schema_version: 'assembly-diff/v1', changed: Boolean(added.length || removed.length || changed.length || beforeInnovation !== afterInnovation || packAdded.length || packRemoved.length), added_nodes: added.map(id => capabilityState.assembly.nodes.find(node => node.node_id === id)), removed_nodes: removed.map(id => capabilityState.assembly.previousNodes.find(node => node.node_id === id)), changed_nodes: changed.map(id => ({ node_id: id })), added_edges: [], removed_edges: [], missing_required_blocks: missing, innovation_changed: beforeInnovation !== afterInnovation, innovation_gate: innovationGate(capabilityState.assembly.innovationCard), content_pack_added: packAdded, content_pack_removed: packRemoved, content_pack_changed: Boolean(packAdded.length || packRemoved.length), content_pack_ids: [...afterPacks].sort(), status: missing.length ? 'BLOCKED' : 'READY_FOR_REVIEW', claim_class: 'derived' };
}

async function commitAssembly(action = 'SUBMIT_REVIEW') {
  const assembly = capabilityState.assembly;
  if (!LIVE_API) {
    assembly.committedRevision = assembly.revision || 'fixture:assembly-draft';
    assembly.previousNodes = JSON.parse(JSON.stringify(assembly.nodes || []));
    assembly.previousEdges = JSON.parse(JSON.stringify(assembly.edges || []));
    showToast('已保存演示装配；未写入事实源');
    return true;
  }
  if (!assembly.revision || !capabilityState.revision || !liveRevision) {
    showToast('装配或事件源 revision 尚未齐全');
    return false;
  }
  try {
    const response = await fetch(`${capabilityEndpoint('/commit')}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ actor_id: 'owner', nodes: assembly.nodes, edges: assembly.edges, innovation_card: assembly.innovationCard || undefined, previous_innovation_card: assembly.previousInnovationCard || undefined, content_pack_ids: assembly.contentPackIds || [], previous_content_pack_ids: assembly.previousContentPackIds || [], content_pack_evidence_refs: assembly.contentPackEvidenceRefs || [], content_pack_index_revision: assembly.contentPackIndexRevision || undefined, content_pack_resolution_revision: assembly.contentPackResolutionRevision || undefined, preset_id: assembly.presetId, archetype_id: assembly.archetypeId, scope: [window.selectedSubproblem || 'Q2'], assembly_revision: assembly.revision, capability_revision: capabilityState.revision, source_revision: runtimeContext.inputRevision && String(runtimeContext.inputRevision).startsWith('kb:') ? runtimeContext.inputRevision : undefined, base_revision: liveRevision, previous_assembly_revision: assembly.committedRevision || undefined, action, idempotency_key: `assembly-commit-${Date.now()}` }) });
    const payload = await response.json();
    if (!response.ok) throw new Error(capabilityErrorMessage(payload, 'ASSEMBLY_COMMIT_ERROR'));
    const committed = payload.assembly || {};
    assembly.committedRevision = committed.assembly_revision || assembly.revision;
    assembly.previousNodes = JSON.parse(JSON.stringify(assembly.nodes || []));
    assembly.previousEdges = JSON.parse(JSON.stringify(assembly.edges || []));
    assembly.contentPackEvidenceRefs = Array.isArray(committed.content_pack_evidence_refs) ? [...committed.content_pack_evidence_refs] : (assembly.contentPackEvidenceRefs || []);
    assembly.contentPackIndexRevision = committed.content_pack_index_revision || assembly.contentPackIndexRevision || null;
    assembly.contentPackResolutionRevision = committed.content_pack_resolution_revision || assembly.contentPackResolutionRevision || null;
    assembly.innovationCard = committed.innovation_card ? JSON.parse(JSON.stringify(committed.innovation_card)) : assembly.innovationCard;
    assembly.previousInnovationCard = assembly.innovationCard ? JSON.parse(JSON.stringify(assembly.innovationCard)) : null;
    assembly.previousContentPackIds = [...(assembly.contentPackIds || [])];
    renderInnovationSummary();
    liveRevision = payload.revision || liveRevision;
    setRuntimeContext({ controlRevision: liveRevision });
    if (payload.event) ingestLiveEvent(payload.event, LIVE_API);
    showToast(action === 'SUBMIT_REVIEW' ? '装配已提交独立审查，并同步到事件流' : '装配草稿已保存到事件源');
    return true;
  } catch (error) {
    showToast(`装配未同步（${error.message || 'unknown'}）`);
    return false;
  }
}

function applyProblemContractDraft(contract) {
  capabilityState.problemContract = contract;
  const rows = Array.isArray(contract?.subproblems) ? contract.subproblems : [];
  if (!rows.length) return;
  const mapped = rows.map((row, index) => {
    const excerpt = row.prompt_excerpt?.value || row.prompt_excerpt || '题面片段待复核';
    const verbs = row.delivery_verbs?.value || row.deliverable_verbs?.value || [];
    const variables = row.variables?.value || [];
    return {
      id: String(row.id || `Q${index + 1}`), title: `待确认小问 ${String(row.id || `Q${index + 1}`)}`, prompt: String(excerpt), deliverable: Array.isArray(verbs) && verbs.length ? verbs.join('、') : '交付物待 Scope-Lock 确认', state: 'blocked', stateLabel: 'DRAFT · 待核验', coverage: '0/6 可核对', risk: '单位、语义与来源尚未核验', focus: 'scope', sourceStatus: 'draft_unverified', promptRefs: (contract.source_refs || []).map(ref => ({ ref, claimClass: 'observed' })), variables: Array.isArray(variables) ? variables.filter(item => typeof item === 'string') : [], claimClass: 'observed', evidenceRefs: contract.source_refs || [],
    };
  });
  subproblems.splice(0, subproblems.length, ...mapped);
  window.selectedSubproblem = mapped[0].id;
  renderModelingOverview();
}

async function draftProblemContract() {
  const input = document.getElementById('problemDraftInput');
  const text = input?.value?.trim();
  if (!text) { showToast('先粘贴一段题面'); return; }
  if (!LIVE_API) { showToast('演示模式未连接抽取服务；请打开 ?live=1'); return; }
  const button = document.getElementById('draftProblemContractBtn');
  if (button) { button.disabled = true; button.textContent = '抽取中…'; }
  try {
    const response = await fetch(`${capabilityEndpoint('/problem-contract')}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text, source_refs: [] }) });
    const payload = await response.json();
    if (!response.ok) throw new Error(capabilityErrorMessage(payload, 'PROBLEM_CONTRACT_ERROR'));
    applyProblemContractDraft(payload);
    const result = document.getElementById('problemContractResult');
    const suggestions = (payload.archetype_cue_suggestions || []).filter(item => item.score > 0).slice(0, 3).map(item => item.id).join(' · ') || '暂无明显 cue';
    if (result) { result.hidden = false; result.innerHTML = `<strong>${escapeHTML(payload.subproblems?.length || 0)} 个动态小问 · ${escapeHTML(payload.status || 'DRAFT_UNVERIFIED')}</strong><span>题型线索：${escapeHTML(suggestions)}</span><small>revision ${escapeHTML(compactRevision(payload.revision, 18))} · 所有字段仍需人工核验</small>`; }
    const state = document.getElementById('problemContractState'); if (state) state.textContent = `${payload.status || 'DRAFT_UNVERIFIED'} · ${payload.subproblems?.length || 0} 个小问`;
    const meta = document.getElementById('problemContractMeta'); if (meta) meta.textContent = '已生成 lexical draft；Scope-Lock 需补页码、单位、硬约束和事实核对';
    showToast(`已生成 ${payload.subproblems?.length || 0} 个小问草稿`);
  } catch (error) { showToast(`题面契约失败（${error.message || 'unknown'}）`); }
  finally { if (button) { button.disabled = false; button.textContent = '生成契约草稿'; } }
}

async function loadCapabilityCatalog(force = false) {
  if (!LIVE_API) {
    renderCapabilitySource({ source: { source_status: 'UNAVAILABLE', indexed_count: 0 }, methods: [], workflow_blocks: [], workflow_presets: [], problem_archetypes: [] });
    return null;
  }
  if (capabilityCatalogPromise) return capabilityCatalogPromise;
  capabilityState.loading = true;
  capabilityCatalogPromise = (async () => {
    try {
      const response = await fetch(`${capabilityEndpoint('/catalog')}${force ? '?refresh=true' : ''}`);
      const payload = await response.json();
      if (!response.ok) throw new Error(capabilityErrorMessage(payload, 'CAPABILITY_CATALOG_ERROR'));
      renderCapabilityCatalog(payload);
      return payload;
    } catch (error) {
      renderCapabilitySource({ source: { source_status: 'UNAVAILABLE', indexed_count: 0 } });
      showToast(`能力目录读取失败（${error.message || 'unknown'}）`);
      return null;
    }
  })();
  try { return await capabilityCatalogPromise; }
  finally { capabilityState.loading = false; capabilityCatalogPromise = null; }
}

function capabilityNodeModal(index) {
  const node = capabilityState.assembly.nodes[index];
  if (!node) return;
  const block = capabilityBlock(node.block_id) || {};
  const method = node.method_id ? capabilityMethod(node.method_id) : null;
  const source = method || block;
  const rows = [
    ['节点', node.label || node.block_id],
    ['输入 → 输出', `${Object.keys(block.input_ports || {}).join(' · ') || '无'} → ${Object.keys(block.output_ports || {}).join(' · ') || '无'}`],
    ['适用条件', (method?.applicability || ['由题面契约决定']).join('；')],
    ['禁用条件', (method?.prohibitions || ['接口/来源未核验时不得推进']).join('；')],
    ['假设', (method?.assumptions || ['需绑定当前题面与数据']).join('；')],
    ['验证族', (method?.validation || ['结构检查 + 独立 clean-run']).join('；')],
    ['回退', (method?.fallback || ['退回透明 baseline 或 BLOCKED']).join('；')],
    ['来源层', method ? `${method.source_kind || 'curated/inferred'} · ${ (method.evidence_refs || []).join('、') }` : 'workflow block · playbook contract'],
  ];
  showModal(`能力卡 · ${source.title || node.block_id}`, `<p>这是可插拔候选，不是自动选模结论。任何字段进入论文前都要回到题面、参数来源和验证门。</p><div class="trace-modal-list">${rows.map(row => `<div class="trace-modal-row"><b>${escapeHTML(row[0])}</b><span>${escapeHTML(row[1])}</span></div>`).join('')}</div><p><span class="tag amber">${escapeHTML(capabilityState.assembly.validation?.valid ? '结构可审' : '待检查')}</span> <span class="tag violet">${escapeHTML(capabilityState.revision || 'UNVERIFIED')}</span></p>`);
}

function saveInnovationCard() {
  const fields = ['baseline', 'difference', 'necessity', 'boundary', 'validation'];
  const card = { subproblem_id: window.selectedSubproblem || 'Q2', claim_class: 'hypothesis' };
  fields.forEach(field => {
    const input = document.querySelector(`[data-innovation-field="${field}"]`);
    const value = String(input?.value || '').trim();
    if (value) card[field] = value.slice(0, 2000);
  });
  if (!fields.some(field => card[field])) {
    capabilityState.assembly.innovationCard = null;
    showToast('创新卡为空，已保持未创建状态');
  } else {
    capabilityState.assembly.innovationCard = card;
    const gate = innovationGate(card);
    showToast(gate.ready ? '创新差异卡已保存为待审草稿' : `创新卡已保存；还缺 ${gate.missing.length} 个审查字段`);
  }
  capabilityState.assembly.revision = null;
  capabilityState.assembly.validation = null;
  capabilityState.assembly.diff = null;
  capabilityState.assembly.methodBlockWarnings = [];
  assemblyValidationEpoch += 1;
  renderAssemblyGate();
  renderAssemblyDiff(null);
  renderInnovationSummary();
  closeModal();
  if (capabilityState.assembly.nodes.length) validateAssembly();
}

function innovationModal() {
  const card = capabilityState.assembly.innovationCard || {};
  const value = field => escapeHTML(card[field] || '');
  showModal('创新差异卡 · 不鼓励模型堆叠', `<p>把创新写成可审计的差异，而不是“用了更复杂的模型”。完成后可将这张卡作为群主讨论草稿，并随装配 revision 留痕。</p><div class="innovation-form"><label>基线<textarea data-innovation-field="baseline" placeholder="当前最透明、可复现的 baseline…">${value('baseline')}</textarea></label><label>差异<textarea data-innovation-field="difference" placeholder="新增了什么机制、数据、约束或验证？">${value('difference')}</textarea></label><label>必要性<textarea data-innovation-field="necessity" placeholder="它解决题面中的哪一条困难？">${value('necessity')}</textarea></label><label>代价与边界<textarea data-innovation-field="boundary" placeholder="复杂度、数据需求、禁用条件和失败回退…">${value('boundary')}</textarea></label><label>可运行验证<textarea data-innovation-field="validation" placeholder="具体的 clean-run、对照、阈值或复现实验…">${value('validation')}</textarea></label></div><div class="assembly-note"><span>审查门</span><p>创新候选必须连到一个小问、一个 baseline、一个可运行验证和一个边界说明；未齐字段保持 DRAFT_UNVERIFIED，不进入论文结论。</p></div><p><button type="button" id="saveInnovationBtn" class="approve-button">保存为讨论草稿 →</button></p>`);
  document.getElementById('saveInnovationBtn')?.addEventListener('click', saveInnovationCard);
}

function openAssemblyPanel() {
  selectRightPanel('assembly');
  setAssemblyMode(capabilityState.mode);
  if (!capabilityState.catalog) loadCapabilityCatalog();
}

async function sendAssemblyToChat() {
  const nodes = capabilityState.assembly.nodes || [];
  if (!nodes.length) { showToast('先加入至少一个工作块或方法卡'); return { sent: false, error: 'empty_assembly' }; }
  // Recompute even when the prior graph was valid: selected subproblem,
  // catalog revision, and the diff baseline are part of the assembly hash.
  const checked = await validateAssembly();
  if (!checked) { showToast('链路检查没有返回可用报告；暂不发送'); return { sent: false, error: 'validation_unavailable' }; }
  const validation = checked?.validation || (Object.prototype.hasOwnProperty.call(checked, 'valid') ? checked : null);
  const valid = validation?.valid === true;
  if (!valid || (LIVE_API && !capabilityState.assembly.revision)) { showToast('链路仍有阻断；修复后才能同步到群聊'); return { sent: false, error: valid ? 'assembly_revision_missing' : 'validation_blocked', validation }; }
  const names = nodes.map(node => node.label || node.block_id).slice(0, 8).join(' → ');
  const assemblyRevision = capabilityState.assembly.revision || 'fixture:assembly-draft';
  const novelty = innovationGate(capabilityState.assembly.innovationCard);
  const noveltyText = novelty.present ? `创新差异卡=${novelty.ready ? '字段齐全·待审' : '草稿·缺 ' + novelty.missing.join('/')}` : '创新差异卡=未创建';
  const packNames = (capabilityState.assembly.contentPackIds || []).map(id => capabilityPacks().find(pack => pack.id === id)?.title || id).slice(0, 5);
  const packText = packNames.length ? `内容包=${packNames.join('、')}` : '内容包=未挂载';
  const text = `能力装配已提交讨论：${names}${nodes.length > 8 ? ' → …' : ''}。结构门已通过，数值/证据仍待独立验证；${noveltyText}；${packText}。assembly=${assemblyRevision}`;
  const metadata = { assemblyRevision, capabilityRevision: capabilityState.revision || null, innovationStatus: novelty.status };
  if (LIVE_API) {
    if (!liveRevision) { showToast('事件源 revision 尚未同步，暂不能发群聊'); return { sent: false, error: 'live_revision_missing' }; }
    const committed = await commitAssembly('SUBMIT_REVIEW');
    if (!committed) return { sent: false, error: 'assembly_commit_failed' };
    const posted = await postLiveMessage(text, 'full', [], metadata);
    return { sent: posted === true, error: posted === true ? null : 'message_post_failed', assembly_revision: assemblyRevision };
  } else {
    addOwnerMessage(text, [], metadata);
    showToast('已加入演示群聊（SIMULATED；未写入事实源）');
    return { sent: true, simulated: true, assembly_revision: assemblyRevision };
  }
}

function showModal(title, body) {
  const modalBody = document.getElementById('modalBody');
  const backdrop = document.getElementById('modalBackdrop');
  if (!modalBody || !backdrop) return;
  modalReturnFocus = document.activeElement;
  modalBody.innerHTML = `<h2 id="modalTitle">${escapeHTML(title)}</h2>${body}`;
  backdrop.hidden = false;
  document.body.classList.add('modal-open');
  const firstControl = modalBody.querySelector('input, textarea, select, button:not(.modal-close), a[href]');
  window.setTimeout(() => firstControl?.focus(), 0);
}

function closeModal() {
  const backdrop = document.getElementById('modalBackdrop');
  if (!backdrop) return;
  backdrop.hidden = true;
  document.body.classList.remove('modal-open');
  try { modalReturnFocus?.focus?.(); } catch (_) { /* detached control */ }
  modalReturnFocus = null;
}

function openMobileMoreModal() {
  showModal('群聊更多功能', `<p class="mobile-more-intro">常用的群聊入口收在这里，保持主界面专注于当前讨论。</p><div class="mobile-more-actions" role="menu" aria-label="群聊更多功能"><button type="button" class="mobile-more-action" data-mobile-more-action="threads" role="menuitem"><span class="mobile-more-action-icon">↯</span><span><strong>线程</strong><small>查看质疑与回应</small></span><span>›</span></button><button type="button" class="mobile-more-action" data-mobile-more-action="events" role="menuitem"><span class="mobile-more-action-icon">⟲</span><span><strong>事件流</strong><small>回放协作事实源</small></span><span>›</span></button><button type="button" class="mobile-more-action" data-mobile-more-action="filter" role="menuitem"><span class="mobile-more-action-icon">⌁</span><span><strong>会话筛选</strong><small>全部 · 群组 · 私聊 · @我</small></span><span>›</span></button><button type="button" class="mobile-more-action" data-mobile-more-action="channels" role="menuitem"><span class="mobile-more-action-icon">☷</span><span><strong>频道管理</strong><small>切换或新建协作频道</small></span><span>›</span></button></div>`);
}

function apiErrorCode(error, fallback = 'REQUEST_FAILED') {
  const detail = error?.payload?.detail;
  if (detail && typeof detail === 'object') return String(detail.code || detail.message || fallback);
  return String(detail || error?.message || fallback);
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  let payload = null;
  try { payload = await response.json(); } catch (_) { /* empty/non-json response */ }
  if (!response.ok) {
    const error = new Error(apiErrorCode({ payload }, `HTTP_${response.status}`));
    error.status = response.status;
    error.payload = payload;
    throw error;
  }
  return payload || {};
}

function plainText(value) {
  const node = document.createElement('div');
  node.innerHTML = String(value || '');
  return node.textContent || node.innerText || '';
}

function parseSearchQuery(query) {
  const raw = String(query || '').trim();
  const filters = {};
  const rest = raw.replace(/(?:^|\s)(task|status|agent|claim|channel):("[^"]+"|[^\s]+)/gi, (whole, key, value) => {
    filters[String(key).toLowerCase()] = String(value || '').replace(/^"|"$/g, '').toLowerCase();
    return ' ';
  }).replace(/\s+/g, ' ').trim().toLowerCase();
  return { raw, filters, terms: rest ? rest.split(' ').filter(Boolean) : [] };
}

function searchableMessageText(message) {
  return [message.member, message.kind, message.text, message.taskId, message.task_id, message.subproblemId, message.subproblem_id, ...(message.evidenceRefs || []), ...(((message.tags || []).flat?.() || []))].filter(Boolean).join(' ');
}

function runLocalSearch(query) {
  const parsed = parseSearchQuery(query);
  const matches = [];
  const add = (kind, id, title, detail, target) => {
    const haystack = `${title} ${detail} ${id}`.toLowerCase();
    if (parsed.filters.task && !haystack.includes(parsed.filters.task) && !String(target?.taskId || '').toLowerCase().includes(parsed.filters.task)) return;
    if (parsed.filters.status && !haystack.includes(parsed.filters.status)) return;
    if (parsed.filters.agent && !haystack.includes(parsed.filters.agent)) return;
    if (parsed.filters.claim && !haystack.includes(parsed.filters.claim)) return;
    if (parsed.filters.channel && !haystack.includes(parsed.filters.channel)) return;
    if (parsed.terms.some(term => !haystack.includes(term))) return;
    matches.push({ kind, id: String(id || newClientId('result')), title, detail, target });
  };
  messages.filter(item => item.type !== 'system' && item.type !== 'date').forEach(item => add('消息', item.id, `${getMember(item.member).name} · ${item.kind || '进展'}`, plainText(item.text), { messageId: item.id, taskId: item.taskId || item.task_id }));
  tasks.forEach(item => add('任务', item.id, `${item.id} · ${item.title}`, `${item.status || item.state || ''} · ${item.owner || ''} · ${item.meta || ''}`, { taskId: item.id }));
  evidence.forEach(item => add('证据', item.title, item.title, `${item.status || 'UNVERIFIED'} · ${item.meta || ''}`, { evidence: item.title }));
  (knowledgeState.results || []).forEach(item => {
    const id = item.doc_id || item.docId || item.id;
    add('资料', id, item.title || item.name || id, item.snippet || item.path || item.module || '', { kbDoc: id, kbItem: item });
  });
  eventRows.slice(-200).forEach(item => add('事件', item.event_id, `${item.type || 'EVENT'} · ${item.actor_id || ''}`, eventText(item.payload || {}), { eventId: item.event_id, taskId: item.task_id }));
  return { parsed, matches: matches.slice(0, 80) };
}

function renderSearchResults(query) {
  const root = document.getElementById('searchResults');
  const meta = document.getElementById('searchResultMeta');
  if (!root) return;
  const { parsed, matches } = runLocalSearch(query);
  if (meta) meta.textContent = query ? `${matches.length} 条本地匹配 · ${contextModeLabel()}` : '输入关键词开始搜索';
  if (!query.trim()) {
    root.innerHTML = '<div class="search-empty"><strong>搜索群聊与证据</strong><span>支持 task:G7 · status:P1 · agent:Critic · claim:C-17</span></div>';
    return;
  }
  if (!matches.length) {
    root.innerHTML = `<div class="search-empty"><strong>没有匹配结果</strong><span>已按当前消息、任务、证据、已载入资料和事件索引检索。</span><button type="button" class="decision-more" data-search-kb="${escapeHTML(parsed.terms.join(' '))}">在资料库继续检索</button></div>`;
    return;
  }
  root.innerHTML = matches.map(item => {
    const targetAttrs = item.target?.messageId ? `data-search-message="${escapeHTML(item.target.messageId)}"` : item.target?.taskId ? `data-search-task="${escapeHTML(item.target.taskId)}"` : item.target?.evidence ? `data-search-evidence="${escapeHTML(item.target.evidence)}"` : item.target?.kbDoc ? `data-search-kb-doc="${escapeHTML(item.target.kbDoc)}"` : item.target?.eventId ? `data-search-event="${escapeHTML(item.target.eventId)}"` : '';
    return `<button type="button" class="search-result-row" ${targetAttrs}><span class="search-result-kind">${escapeHTML(item.kind)}</span><span class="search-result-copy"><strong>${escapeHTML(item.title)}</strong><small>${escapeHTML(item.detail.slice(0, 180))}</small></span><span class="search-result-arrow">${dragonIcon('mark', { className: 'dragon-affordance' })}</span></button>`;
  }).join('');
}

function openSearch(initial = '') {
  showModal('搜索群聊与证据', `<form id="globalSearchForm" class="global-search-form"><div class="global-search-input-row"><input id="globalSearchInput" name="q" autofocus autocomplete="off" value="${escapeHTML(initial)}" placeholder="搜索 claim、task_id、文件名或 Agent…"/><button type="submit" class="approve-button">搜索</button></div><p class="search-syntax">支持：claim:C-17 · task:G7 · status:P1 · agent:Critic · 关键词</p></form><div class="search-result-meta" id="searchResultMeta"></div><div id="searchResults" class="search-results"></div>`);
  renderSearchResults(initial);
}

function focusMessage(messageId) {
  const target = document.querySelector(`[data-message-id="${CSS.escape(String(messageId))}"]`);
  if (!target) {
    // The target can be hidden by a channel/filter.  Return to the main view so
    // a search result never appears to do nothing.
    activeConversationFilter = 'all';
    activeChannel = '主议事群';
    setActiveConversationFilter('all');
    setActiveChannel('主议事群', { silent: true });
  }
  const visible = document.querySelector(`[data-message-id="${CSS.escape(String(messageId))}"]`);
  if (visible) {
    visible.scrollIntoView({ behavior: 'smooth', block: 'center' });
    visible.classList.add('search-focus');
    window.setTimeout(() => visible.classList.remove('search-focus'), 1600);
  }
}

function eventRowMarkup(row) {
  const payload = row?.payload || {};
  const status = payload.status || payload.provenance_status || row?.status || 'RECORDED';
  const task = row?.task_id || payload.task_id || '—';
  return `<div class="event-row"><div class="event-row-top"><span class="event-seq">#${escapeHTML(row?.seq || '—')}</span><strong>${escapeHTML(row?.type || 'EVENT')}</strong><span class="event-actor">${escapeHTML(row?.actor_id || 'unknown')}</span><time>${escapeHTML(timeFromTimestamp(row?.timestamp))}</time></div><div class="event-row-body"><span>${escapeHTML(eventText(payload))}</span><span class="event-status">${escapeHTML(status)}</span></div><div class="event-row-meta"><code>${escapeHTML(row?.event_id || '—')}</code><span>task ${escapeHTML(task)}</span><code title="${escapeHTML(row?.event_hash || '')}">${escapeHTML(compactRevision(row?.event_hash || row?.revision || 'UNVERIFIED', 18))}</code></div></div>`;
}

function renderEventModalRows() {
  const root = document.getElementById('eventRows');
  const meta = document.getElementById('eventModalMeta');
  if (!root) return;
  const rows = [...eventRows].sort((a, b) => Number(a.seq || 0) - Number(b.seq || 0)).slice(-300);
  if (meta) meta.textContent = `${rows.length} 条 · ${LIVE_API ? (liveConnected ? 'LIVE · 已连接' : 'LIVE · 等待连接') : 'SIMULATED · fixture'}`;
  root.innerHTML = rows.length ? rows.map(eventRowMarkup).join('') : `<div class="search-empty"><strong>暂无事件</strong><span>${LIVE_API ? '事实源尚无可回放事件。' : '演示事件会在发送消息或操作工作台后出现。'}</span></div>`;
}

async function openEventsModal() {
  showModal('事件流 · append-only', `<div class="modal-toolbar"><span id="eventModalMeta">读取中…</span><button type="button" class="decision-more" id="refreshEventsBtn">刷新</button></div><p>事件流是协作事实源，群聊只是它的可读投影。每一行都显示序号、操作者、任务、状态和哈希；缺口不会被静默填补。</p><div id="eventRows" class="event-rows"><div class="search-empty"><strong>正在读取事件</strong></div></div>`);
  if (LIVE_API) {
    try {
      const payload = await fetchJson(`${LIVE_API}/api/projects/${LIVE_PROJECT}/events?after_seq=0&limit=500`);
      (payload.events || []).forEach(row => {
        if (row?.event_id && !eventRows.some(existing => existing.event_id === row.event_id)) eventRows.push(row);
      });
    } catch (error) {
      const root = document.getElementById('eventRows');
      if (root) root.innerHTML = `<div class="search-empty"><strong>事件读取失败</strong><span>${escapeHTML(apiErrorCode(error, 'EVENT_REPLAY_UNAVAILABLE'))} · 将保留本地已收事件</span></div>`;
    }
  } else if (!eventRows.length) {
    // Build an explicitly simulated projection from fixture messages.  It is
    // useful for learning the protocol, but never presented as a server log.
    eventRows = messages.filter(item => item.type !== 'system' && item.type !== 'date').map((item, index) => ({ event_id: item.id || `fixture-${index}`, seq: index + 1, timestamp: item.time, actor_id: item.member, type: item.kind || 'MESSAGE', payload: { text: plainText(item.text), task_id: item.taskId, status: item.status || 'PRODUCED' }, event_hash: 'fixture:unverified' }));
  }
  renderEventModalRows();
  document.getElementById('refreshEventsBtn')?.addEventListener('click', () => openEventsModal());
}

function threadCandidates() {
  return messages.filter(item => item.type !== 'system' && item.type !== 'date' && (item.actions?.length || item.kind === '质疑' || item.kind === '审查' || /@/.test(String(item.text || '')) || item.threadRootId));
}

function threadRowMarkup(item) {
  return `<button type="button" class="thread-row" data-thread-root="${escapeHTML(item.id)}"><span class="thread-avatar">${dragonIcon(dragonMemberAsset(getMember(item.member)), { className: 'dragon-mini-avatar' })}</span><span class="thread-copy"><strong>${escapeHTML(getMember(item.member).name)} · ${escapeHTML(item.kind || '讨论')}</strong><small>${escapeHTML(plainText(item.text).slice(0, 150))}</small><em>${escapeHTML(item.taskId || 'task:unassigned')} · ${escapeHTML(item.status || 'UNVERIFIED')}</em></span><span class="search-result-arrow">${dragonIcon('mark', { className: 'dragon-affordance' })}</span></button>`;
}

function openThreadsModal(rootId = '') {
  const candidates = threadCandidates();
  const selected = candidates.find(item => item.id === rootId) || candidates[0];
  const rows = candidates.map(threadRowMarkup).join('');
  const selectedText = selected ? `<div class="thread-root-card"><span class="tag rose">根消息</span><p>${escapeHTML(plainText(selected.text))}</p><small>${escapeHTML(getMember(selected.member).name)} · ${escapeHTML(selected.taskId || 'unassigned')}</small></div>` : '<div class="search-empty"><strong>暂无开放线程</strong><span>对消息执行“发起反驳线程”即可建立一个本地可追踪讨论。</span></div>';
  showModal('线程 · 质疑与回应', `<div class="modal-toolbar"><span>${candidates.length} 个待跟进讨论 · ${contextModeLabel()}</span><button type="button" class="decision-more" id="refreshThreadsBtn">刷新</button></div><div class="thread-layout"><div class="thread-list">${rows || '<div class="search-empty"><strong>暂无线程</strong></div>'}</div><div class="thread-detail">${selectedText}${selected ? `<form id="threadReplyForm" class="thread-reply-form" data-thread-root="${escapeHTML(selected.id)}"><label>回复这条讨论<textarea name="reply" rows="3" placeholder="写下反例、验证计划或需要 Owner 裁决的点…" required></textarea></label><button type="submit" class="approve-button">发送回应</button><small>LIVE 会写入事件源；SIMULATED 仅加入本地演示群聊。</small></form>` : ''}</div></div>`);
  document.getElementById('refreshThreadsBtn')?.addEventListener('click', () => openThreadsModal(rootId));
  // The reply form also carries `data-thread-root`; binding the row handler to
  // every matching element would rebuild the modal on submit before the
  // delegated submit listener could run.  Restrict this listener to thread
  // navigation rows and leave the form lifecycle untouched.
  document.querySelectorAll('.thread-row[data-thread-root]').forEach(button => button.addEventListener('click', () => openThreadsModal(button.dataset.threadRoot)));
}

async function submitThreadReply(form) {
  const rootId = form.dataset.threadRoot;
  const input = form.querySelector('textarea');
  const text = input?.value.trim();
  if (!text || collaborationPaused) {
    if (collaborationPaused) showToast('协作已暂停；线程回应暂存前请先恢复协作');
    return;
  }
  const root = messages.find(item => item.id === rootId);
  const taskId = root?.taskId || 'G7';
  // A reply is part of the conversation the Owner is currently reading.  The
  // old prototype always wrote ``main`` here, so a reply made from a scoped
  // channel was accepted but immediately disappeared behind that channel's
  // filter.  Preserve the canonical server spelling for the main room while
  // carrying an explicit label for every other channel.
  const replyChannel = activeChannel === '主议事群' ? 'main' : activeChannel;
  if (LIVE_API) {
    if (!liveRevision) { showToast('事件源 revision 尚未同步，暂不能回复线程'); return; }
    const ok = await postLiveMessage(text, document.getElementById('composerMode')?.value || 'full', [], { threadRootId: rootId, taskId, channel: replyChannel });
    if (ok) { closeModal(); showToast('线程回应已写入事件源'); }
    return;
  }
  messages.push(normalizeProvenance({ id: newClientId('thread'), member: 'owner', time: timeFromTimestamp(), kind: '群聊', channel: replyChannel, text: escapeHTML(text), tags: [['线程回应', 'violet']], status: 'PRODUCED', claimClass: 'hypothesis', taskId, subproblemId: root?.subproblemId || 'Q4', targetRevision: runtimeContext.controlRevision, evidenceRefs: [], threadRootId: rootId }, 'fixture'));
  renderMessages();
  closeModal();
  showToast('线程回应已加入本地演示群聊 · SIMULATED');
}

function taskOwnerOptions(selected = 'coordinator') {
  const rows = [{ id: 'coordinator', label: 'Coordinator（可由适配器领取）' }, ...members.map(member => ({ id: member.id, label: `${member.name} · ${member.shortModel || member.model}` }))];
  return rows.map(row => `<option value="${escapeHTML(row.id)}" ${row.id === selected ? 'selected' : ''}>${escapeHTML(row.label)}</option>`).join('');
}

function openNewTaskModal() {
  const maxTaskNumber = Math.max(10, ...tasks.map(item => Number(String(item.id).replace(/\D/g, '')) || 0));
  const nextId = `G${maxTaskNumber + 1}`;
  showModal('新建协作任务', `<form id="newTaskForm" class="task-form"><p>群主定义目标后，Coordinator 会生成可追踪的 task envelope。${LIVE_API ? '当前为 LIVE：提交会写入本地事实源。' : '当前为 SIMULATED：提交只写入本地浏览器视图。'}</p><div class="form-grid"><label>任务 ID<input name="taskId" value="${escapeHTML(nextId)}" pattern="[A-Za-z0-9][A-Za-z0-9_.\\-]{0,39}" required></label><label>负责人<select name="ownerId">${taskOwnerOptions()}</select></label><label class="form-span">标题<input name="title" placeholder="例如：补充 Q3 的敏感性验证" required maxlength="300"></label><label class="form-span">目标<textarea name="objective" rows="3" placeholder="写清输入、交付物、验收条件和停止条件…" required maxlength="5000"></textarea></label><label>模式<select name="mode"><option value="full">FULL 协作</option><option value="lite">LITE 审查</option><option value="solo">SOLO 单 Agent</option></select></label><label>依赖<input name="dependsOn" placeholder="G3, G5（可留空）"></label><label class="form-span">写集<input name="writeSet" value="artifacts/${escapeHTML(nextId)}" placeholder="artifacts/G10"></label></div><div class="form-actions"><button type="button" class="decision-more" data-modal-cancel>取消</button><button type="submit" class="approve-button">创建任务</button></div><p class="form-note">写集只允许相对路径；不会自动执行模型或修改原始资料。</p></form>`);
}

function parseCsv(value) {
  return String(value || '').split(',').map(item => item.trim()).filter(Boolean);
}

async function submitNewTask(form) {
  if (collaborationPaused) { showToast('协作已暂停；恢复后再创建任务'); return; }
  const data = new FormData(form);
  const task = {
    task_id: String(data.get('taskId') || '').trim(),
    title: String(data.get('title') || '').trim(),
    owner_id: String(data.get('ownerId') || 'coordinator').trim(),
    reviewer_id: 'validator',
    objective: String(data.get('objective') || '').trim(),
    depends_on: parseCsv(data.get('dependsOn')),
    write_set: parseCsv(data.get('writeSet')),
    capabilities: { source: 'ui', requested: ['bounded_write', 'evidence_trace'] },
    acceptance: ['返回 task/result envelope', '至少一条可复核证据', '独立审查后再进入 VERIFIED'],
    input_revision: runtimeContext.inputRevision,
    base_revision: liveRevision || runtimeContext.controlRevision,
    mode: String(data.get('mode') || 'full'),
    requested_by: 'owner',
    idempotency_key: newClientId('dispatch'),
  };
  if (!task.task_id || !task.title || !task.objective) { showToast('请补全任务 ID、标题和目标'); return; }
  if (LIVE_API) {
    if (!liveRevision || !/^manifest:[0-9a-f]{64}$/i.test(String(task.input_revision || ''))) { showToast('实时输入/控制 revision 尚未就绪，暂不能派发'); return; }
    try {
      const payload = await fetchJson(`${LIVE_API}/api/projects/${LIVE_PROJECT}/dispatch`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(task) });
      liveRevision = payload.revision || liveRevision;
      setRuntimeContext({ controlRevision: liveRevision });
      mergeSnapshotTasks([payload.task]);
      if (payload.event) ingestLiveEvent(payload.event, LIVE_API, false);
      closeModal();
      showToast(`任务 ${task.task_id} 已写入事件源，等待 ${task.owner_id} 领取`);
    } catch (error) {
      if (apiErrorCode(error) === 'STALE_REVISION') await refreshLiveSnapshotWithNotice('版本已变化，已刷新快照；请确认后重试');
      else showToast(`任务派发失败：${apiErrorCode(error)}`);
    }
    return;
  }
  const localTask = { id: task.task_id, title: task.title, owner: task.owner_id, meta: '刚创建 · 等待本地适配器', status: 'QUEUED', state: 'wait', subproblemId: window.selectedSubproblem || 'Q2', source: 'local_ui', rawTask: task };
  const existing = tasks.find(item => item.id === localTask.id);
  if (existing) { showToast(`任务 ID ${localTask.id} 已存在`); return; }
  tasks.push(localTask);
  renderTasks();
  messages.push(normalizeProvenance({ id: newClientId('dispatch'), member: 'owner', time: timeFromTimestamp(), kind: '派发', text: escapeHTML(`已创建任务 ${task.task_id}：${task.title}。等待 ${task.owner_id} 领取。`), tags: [['TASK_DISPATCHED', 'blue'], ['SIMULATED', 'amber']], status: 'PRODUCED', claimClass: 'derived', taskId: task.task_id, subproblemId: window.selectedSubproblem || 'Q2', targetRevision: runtimeContext.controlRevision, evidenceRefs: [] }, 'fixture'));
  renderMessages();
  closeModal();
  showToast(`任务 ${task.task_id} 已加入本地队列 · SIMULATED`);
}

async function refreshLiveSnapshotWithNotice(notice = '') {
  if (!LIVE_API) return false;
  try {
    const snapshot = await fetchJson(`${LIVE_API}/api/projects/${LIVE_PROJECT}/snapshot`);
    applyLiveSnapshot(snapshot);
    if (notice) showToast(notice);
    return true;
  } catch (error) {
    showToast(`快照刷新失败：${apiErrorCode(error)}`);
    return false;
  }
}

async function requeueTask(task) {
  if (!task || !['blocked', 'failed', 'timeout'].includes(String(task.state || task.status || '').toLowerCase())) {
    showToast('只有 BLOCKED / FAILED / TIMEOUT 任务可以重新排队');
    return;
  }
  const reason = window.prompt('重新排队原因（会写入审计记录）', '已补充缺失证据，等待重新执行');
  if (!reason?.trim()) return;
  if (collaborationPaused) { showToast('协作已暂停；恢复后再重新排队'); return; }
  const taskId = task.id;
  if (LIVE_API) {
    if (!liveRevision) { showToast('控制 revision 尚未同步'); return; }
    try {
      const payload = await fetchJson(`${LIVE_API}/api/tasks/${encodeURIComponent(taskId)}/requeue`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ actor_id: 'owner', reason: reason.trim(), evidence_refs: [], target_revision: liveRevision, idempotency_key: newClientId('requeue') }) });
      liveRevision = payload.revision || liveRevision;
      setRuntimeContext({ controlRevision: liveRevision });
      if (payload.task) mergeSnapshotTasks([payload.task]);
      if (payload.event) ingestLiveEvent(payload.event, LIVE_API, false);
      closeModal();
      showToast(`${taskId} 已重新排队`);
    } catch (error) {
      if (apiErrorCode(error) === 'STALE_REVISION') await refreshLiveSnapshotWithNotice('任务版本已变化，已刷新快照');
      else showToast(`重新排队失败：${apiErrorCode(error)}`);
    }
    return;
  }
  task.status = 'QUEUED'; task.state = 'wait'; task.meta = '已重新排队 · 等待本地适配器';
  renderTasks(); renderMessages(); closeModal(); showToast(`${taskId} 已重新排队 · SIMULATED`);
}

function decisionScope(item) {
  const scopes = { 'dec-1': 'route:routeB', 'dec-2': 'assumption:theta', 'dec-3': 'external:antigravity' };
  return scopes[item?.id] || `decision:${item?.id || 'unknown'}`;
}

function decisionState(item) {
  return item?.decision || localApprovals.find(row => row.scope === decisionScope(item))?.decision || '';
}

function approvalRowMarkup(item) {
  const decision = decisionState(item);
  const stateLabel = decision ? (decision === 'approve' ? '已批准' : decision === 'reject' ? '已拒绝' : '已记录') : '待决定';
  return `<article class="approval-queue-row" data-approval-decision="${escapeHTML(item.id)}"><div><span class="tag ${decision === 'approve' ? 'teal' : decision === 'reject' ? 'rose' : 'amber'}">${escapeHTML(stateLabel)}</span><strong>${escapeHTML(item.title)}</strong><p>${escapeHTML(item.body)}</p><small>scope: ${escapeHTML(decisionScope(item))}</small></div><div class="approval-queue-actions"><button type="button" class="decision-approve" data-approval-action="approve" ${decision ? 'disabled' : ''}>批准</button><button type="button" class="decision-reject" data-approval-action="reject" ${decision ? 'disabled' : ''}>拒绝</button><button type="button" class="decision-more" data-approval-action="inspect">证据</button></div></article>`;
}

function renderApprovalQueueRows() {
  const root = document.getElementById('approvalQueueRows');
  const meta = document.getElementById('approvalQueueMeta');
  if (!root) return;
  const recorded = localApprovals.length;
  if (meta) meta.textContent = `${decisions.length} 项决策 · ${recorded} 条服务端记录 · ${contextModeLabel()}`;
  root.innerHTML = decisions.map(approvalRowMarkup).join('');
}

function openApprovalQueue() {
  showModal('群主审批队列', `<div class="modal-toolbar"><span id="approvalQueueMeta">读取中…</span><button type="button" class="decision-more" id="refreshApprovalsBtn">刷新</button></div><p>批准只记录 Owner 决策，不会自动发布、执行模型或向外部平台发送数据。外部 relay 仍需单独的范围与版本校验。</p><div id="approvalQueueRows" class="approval-queue-rows"></div>`);
  renderApprovalQueueRows();
  document.getElementById('refreshApprovalsBtn')?.addEventListener('click', async () => {
    if (LIVE_API) await refreshLiveSnapshotWithNotice('审批快照已刷新');
    renderApprovalQueueRows();
  });
}

async function recordDecision(itemId, verdict) {
  const item = decisions.find(row => row.id === itemId);
  if (!item) return;
  if (collaborationPaused) { showToast('协作已暂停；Owner 审批仍可查看，但请恢复后记录'); return; }
  const scope = decisionScope(item);
  const decision = verdict === 'approve' ? 'approve' : 'reject';
  if (LIVE_API) {
    if (!liveRevision || !/^manifest:[0-9a-f]{64}$/i.test(String(liveRevision))) { showToast('控制 revision 尚未就绪，暂不能记录审批'); return; }
    try {
      const payload = await fetchJson(`${LIVE_API}/api/projects/${LIVE_PROJECT}/approvals`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ owner_id: 'owner', scope, decision, target_revision: liveRevision, base_revision: liveRevision, note: `UI decision ${item.id}: ${item.title}`, idempotency_key: newClientId('approval') }) });
      localApprovals.push(payload.approval || { scope, decision, target_revision: liveRevision, status: 'RECORDED' });
      item.decision = decision; item.decisionSource = 'LIVE · 事件源';
      liveRevision = payload.revision || liveRevision;
      setRuntimeContext({ controlRevision: liveRevision });
      if (payload.event) ingestLiveEvent(payload.event, LIVE_API, false);
      renderDecisions(); renderApprovalQueueRows();
      showToast(`已记录 Owner ${decision === 'approve' ? '批准' : '拒绝'}：${item.title}`);
    } catch (error) {
      if (apiErrorCode(error) === 'STALE_REVISION') await refreshLiveSnapshotWithNotice('审批版本已变化，已刷新快照');
      else showToast(`审批记录失败：${apiErrorCode(error)}`);
    }
    return;
  }
  item.decision = decision;
  item.decisionSource = 'SIMULATED · 本地视图';
  localApprovals.push({ approval_id: newClientId('approval'), owner_id: 'owner', scope, decision, target_revision: runtimeContext.controlRevision, status: 'LOCAL_ONLY' });
  renderDecisions(); renderApprovalQueueRows();
  showToast(`已记录本地 Owner ${decision === 'approve' ? '批准' : '拒绝'} · SIMULATED`);
}

function allChannelLabels() {
  const base = ['主议事群', '题面与数据', '建模方案', '算法与仿真', '验证与质疑', '论文与答辩', '资料库'];
  return [...new Set([...base, ...localChannels.map(item => String(item.name || item).trim()).filter(Boolean)])];
}

function renderLocalChannels() {
  const root = document.querySelector('.channel-list');
  if (!root) return;
  root.querySelectorAll('[data-local-channel="true"]').forEach(node => node.remove());
  localChannels.forEach(item => {
    const label = String(item.name || item).trim();
    if (!label || allChannelLabels().slice(0, 7).includes(label)) return;
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'channel-item local-channel-item';
    button.dataset.channel = label;
    button.dataset.localChannel = 'true';
    button.innerHTML = `<img class="channel-icon" src="assets/ip/xiao-qinglong-mark-v1.png" alt="" /><strong>${escapeHTML(label)}</strong><em>${channelCount(label) || ''}</em>`;
    button.addEventListener('click', () => setActiveChannel(label));
    root.appendChild(button);
  });
  root.querySelectorAll('.channel-item').forEach(node => {
    node.classList.toggle('active', canonicalChannelLabel(node.dataset.channel) === canonicalChannelLabel(activeChannel));
  });
}

function channelCount(label) {
  return messages.filter(item => item.type !== 'system' && item.type !== 'date' && inferredMessageChannel(item) === canonicalChannelLabel(label)).length;
}

function renderChannelManagementRows(actionAttr = 'channel-manage-select') {
  return allChannelLabels().map(label => `<button type="button" class="channel-manage-row ${canonicalChannelLabel(label) === canonicalChannelLabel(activeChannel) ? 'active' : ''}" data-${actionAttr}="${escapeHTML(label)}"><span class="channel-manage-mark">${escapeHTML(label.slice(0, 1))}</span><span><strong>#${escapeHTML(label)}</strong><small>${channelCount(label)} 条本地消息${label === '资料库' ? ' · 打开资料面板' : ''}</small></span><em>${canonicalChannelLabel(label) === canonicalChannelLabel(activeChannel) ? '当前' : '切换'}</em></button>`).join('');
}

function openConversationManager() {
  showModal('会话管理', `<p>会话筛选只改变当前阅读视图，不删除事实源消息。选择频道后会同步左侧高亮和聊天标题。</p><div class="conversation-manage-tabs"><button type="button" class="decision-more" data-manage-filter="all">全部</button><button type="button" class="decision-more" data-manage-filter="group">群组</button><button type="button" class="decision-more" data-manage-filter="private">私聊</button><button type="button" class="decision-more" data-manage-filter="mentions">@我</button></div><div class="channel-manage-list">${renderChannelManagementRows()}</div><form id="newChannelForm" class="new-channel-form"><label>添加本地视图频道<input name="channel" maxlength="40" placeholder="例如：模型复盘"></label><button type="submit" class="approve-button">添加</button><small>仅保存当前浏览器视图，不创建服务端频道。</small></form>`);
}

function openChannelSettings() {
  showModal('频道管理', `<div class="modal-toolbar"><span>当前频道：#${escapeHTML(activeChannel)}</span><span class="tag amber">本地视图设置</span></div><p>这里的切换会立即过滤群聊消息；服务端仍以 event.channel 为准。资料库频道会打开知识库面板。</p><div class="channel-manage-list">${renderChannelManagementRows('channel-settings-select')}</div><label class="channel-mute-toggle"><input type="checkbox" id="channelMuteToggle" ${localStoreGet(`qingjia.muted.${activeChannel}`, false) ? 'checked' : ''}> 静默本频道的提示 toast（不影响事件接收）</label>`);
  document.getElementById('channelMuteToggle')?.addEventListener('change', event => localStoreSet(`qingjia.muted.${activeChannel}`, event.target.checked));
}

function addLocalChannel(name) {
  const clean = String(name || '').trim();
  if (!clean || clean.length > 40) { showToast('频道名称需为 1—40 个字符'); return; }
  if (allChannelLabels().some(item => item === clean)) { showToast('该频道已存在'); return; }
  localChannels.push({ name: clean, createdAt: new Date().toISOString() });
  localStoreSet('qingjia.localChannels', localChannels);
  renderLocalChannels();
  closeModal();
  setActiveChannel(clean);
  showToast(`已添加本地视图频道 #${clean}`);
}

function openNotifications() {
  const items = [
    { id: 'n1', tone: 'rose', title: 'Critic 提交了 P1 质疑', detail: '路线 B 的极端样本外推仍缺少证据。', action: () => { closeModal(); setActiveChannel('验证与质疑'); focusMessage('m5'); } },
    { id: 'n2', tone: 'teal', title: 'Validator 完成 baseline 复跑', detail: '结果一致，但状态空间模型尚未集成。', action: () => { closeModal(); setActiveChannel('验证与质疑'); focusMessage('m6'); } },
    { id: 'n3', tone: 'amber', title: '外部 relay 等待授权', detail: 'Antigravity 尚未获得输入哈希确认。', action: () => { closeModal(); openInviteModal(); } },
  ];
  showModal('通知中心', `<div class="modal-toolbar"><span>${notificationRead ? '已读' : '3 条待处理通知'}</span><button type="button" class="decision-more" id="markNotificationsRead">全部标为已读</button></div><div class="notification-list">${items.map(item => `<button type="button" class="notification-row" data-notification="${item.id}"><span class="notification-dot ${item.tone}"></span><span><strong>${escapeHTML(item.title)}</strong><small>${escapeHTML(item.detail)}</small></span><span>›</span></button>`).join('')}</div>`);
  document.getElementById('markNotificationsRead')?.addEventListener('click', () => { notificationRead = true; const badge = document.querySelector('.notification-badge'); if (badge) badge.hidden = true; openNotifications(); });
  document.querySelectorAll('[data-notification]').forEach(button => button.addEventListener('click', () => items.find(item => item.id === button.dataset.notification)?.action()));
}

function openInviteModal() {
  const targetOptions = ['critic', 'validator', 'antigravity', 'qoder', 'claude'].map(id => `<option value="${id}" ${id === 'antigravity' ? 'selected' : ''}>${id === 'antigravity' ? 'Antigravity · 外部审查' : id}</option>`).join('');
  showModal('邀请协作成员', `<p>先选择能力和目标，再生成一个可审计的 relay 冻结包。生成 relay 不等于外部 Agent 已连接；ACK 仍需由目标端返回。</p><form id="inviteForm" class="invite-form"><label>目标 Agent<select name="target">${targetOptions}</select></label><label>目标类型<select name="targetKind"><option value="local">local · 本机适配器</option><option value="external">external · 需要 Owner approval</option></select></label><label>任务<select name="task"><option value="G7">G7 · Critic 评分与反例</option><option value="G9">G9 · 群主路线审批</option></select></label><div class="form-actions"><button type="button" class="decision-more" data-modal-cancel>取消</button><button type="submit" class="approve-button">生成冻结包</button></div><small id="inviteStatus">${LIVE_API ? 'LIVE · 生成后写入 relay 事件' : 'SIMULATED · 只在本地显示待 relay 状态'}</small></form>`);
}

async function submitInvite(form) {
  if (collaborationPaused) { showToast('协作已暂停；恢复后再生成 relay'); return; }
  const data = new FormData(form);
  const toAgent = String(data.get('target') || 'antigravity');
  const targetKind = String(data.get('targetKind') || 'external');
  const taskId = String(data.get('task') || 'G7');
  if (LIVE_API) {
    if (!liveRevision || !/^manifest:[0-9a-f]{64}$/i.test(String(runtimeContext.inputRevision || ''))) { showToast('输入/控制 revision 尚未同步'); return; }
    try {
      const payload = await fetchJson(`${LIVE_API}/api/relays`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ from_agent_id: 'owner', to_agent_id: toAgent, task_id: taskId, input_revision: runtimeContext.inputRevision, base_revision: liveRevision, payload: { purpose: 'independent_review', requested_capabilities: ['counterexample', 'paper_audit'] }, approval_ref: targetKind === 'external' ? (localApprovals.find(item => item.scope === 'external:antigravity' && item.decision === 'approve')?.approval_id || null) : null, target_kind: targetKind, idempotency_key: newClientId('relay') }) });
      liveRevision = payload.revision || liveRevision; setRuntimeContext({ controlRevision: liveRevision });
      if (payload.event) ingestLiveEvent(payload.event, LIVE_API, false);
      const state = document.querySelector('.external-member .relay-state'); if (state) state.textContent = payload.relay?.status || 'PENDING_RELAY';
      closeModal(); showToast(`relay 冻结包已记录：${toAgent} · 等待 ACK`);
    } catch (error) { showToast(`relay 未生成：${apiErrorCode(error)}（外部目标需先批准范围）`); }
    return;
  }
  const relay = { relay_id: newClientId('relay'), to_agent_id: toAgent, task_id: taskId, target_kind: targetKind, status: 'PENDING_RELAY', source: 'SIMULATED' };
  eventRows.push({ event_id: relay.relay_id, seq: eventRows.length + 1, timestamp: new Date().toISOString(), actor_id: 'owner', type: 'RELAY', payload: relay });
  const state = document.querySelector('.external-member .relay-state'); if (state) state.textContent = 'PENDING';
  closeModal(); showToast(`已生成本地 relay 冻结包 · ${toAgent} · SIMULATED`);
}

function ensureComposerAttachmentRoot() {
  let root = document.getElementById('composerAttachments');
  if (root) return root;
  const tools = document.querySelector('.composer-tools');
  if (!tools) return null;
  root = document.createElement('div');
  root.id = 'composerAttachments';
  root.className = 'composer-attachments';
  tools.parentElement?.insertBefore(root, tools.nextSibling);
  return root;
}

function renderComposerAttachments() {
  const root = ensureComposerAttachmentRoot();
  if (!root) return;
  root.hidden = !localAttachments.length;
  root.innerHTML = localAttachments.map((item, index) => `<span class="composer-attachment" title="${escapeHTML(item.name)} · ${escapeHTML(item.status)}"><span class="attachment-file-mark">件</span><span>${escapeHTML(item.name)}</span><small>${escapeHTML(kbFormatBytes(item.size))} · ${escapeHTML(item.status)}</small><button type="button" data-remove-attachment="${index}" aria-label="移除 ${escapeHTML(item.name)}">×</button></span>`).join('');
}

function openAttachmentPicker() {
  const input = document.createElement('input');
  input.type = 'file';
  input.multiple = true;
  // Materials can include the short IP/video references used during a
  // modeling briefing.  The picker still stores metadata only; it never
  // claims that a binary was uploaded to the local API.
  input.accept = '.pdf,.doc,.docx,.xls,.xlsx,.csv,.txt,.md,.png,.jpg,.jpeg,.mp4,.webm,.mov';
  input.setAttribute('aria-label', '选择要暂存的材料');
  input.addEventListener('change', () => {
    const files = [...(input.files || [])].slice(0, 8);
    if (!files.length) return;
    const known = new Set(localAttachments.map(item => `${item.name}:${item.size}`));
    files.forEach(file => {
      const key = `${file.name}:${file.size}`;
      if (known.has(key)) return;
      localAttachments.push({ name: file.name, size: file.size, type: file.type || 'application/octet-stream', status: LIVE_API ? 'LOCAL_PENDING · 未上传' : 'LOCAL_ONLY · 暂存', lastModified: file.lastModified });
    });
    renderComposerAttachments();
    showToast(`${files.length} 个材料已暂存；发送前仍不会伪称已上传`);
    input.remove();
  });
  input.style.position = 'fixed'; input.style.left = '-10000px'; input.style.width = '1px'; input.style.height = '1px';
  document.body.appendChild(input);
  input.click();
}

function attachmentSummary() {
  return localAttachments.length ? `\n\n附件（${localAttachments.length} 个，仅元数据）：${localAttachments.map(item => `${item.name} [${item.status}]`).join('、')}` : '';
}

function memberModal(member) {
  showModal(member.name, `<p>${escapeHTML(member.title)}</p><div class="modal-grid"><div class="stat-box"><strong>当前模型</strong><span>${escapeHTML(member.model)}</span></div><div class="stat-box"><strong>当前任务</strong><span>${escapeHTML(member.task || '未分配')}</span></div><div class="stat-box"><strong>权限边界</strong><span>只读题面与批准工件；写入专属目录</span></div><div class="stat-box"><strong>状态</strong><span>${escapeHTML(member.state || '在线')} · lease 还剩 18 分钟</span></div></div><h3>角色验收</h3><ul><li>每个主张必须标注 observed / derived / hypothesis。</li><li>不得修改其他 Agent 的写集，也不能自行改变验收条件。</li><li>失败或数据不足时发送 BLOCKED，而不是补造事实。</li></ul>`);
}

function taskModal(task) {
  if (!task) { showToast('任务不存在或已从当前快照移除'); return; }
  const stateText = { verified: 'VERIFIED · 可进入集成', accepted: 'ACCEPTED · 已获 Owner 范围批准', released: 'RELEASED · 已通过发布门', active: 'IN_PROGRESS · 进行中', review: 'READY_FOR_REVIEW · 待独立复核', produced: 'PRODUCED · 不等于 VERIFIED', wait: 'QUEUED · 等待依赖 / 审批', blocked: 'BLOCKED · 有关键风险' }[task.state] || task.status || task.state;
  const blocked = ['blocked', 'failed', 'timeout'].includes(String(task.state || task.status || '').toLowerCase());
  const raw = task.rawTask || task;
  showModal(`${task.id} · ${task.title}`, `<p>任务负责人：<strong>${escapeHTML(task.owner || raw.owner_id || 'Coordinator')}</strong> · <span class="tag ${blocked ? 'rose' : 'amber'}">${escapeHTML(stateText)}</span></p><div class="modal-grid"><div class="stat-box"><strong>输入 revision</strong><span>${escapeHTML(raw.input_revision || runtimeContext.inputRevision || 'UNVERIFIED')}</span></div><div class="stat-box"><strong>控制 revision</strong><span>${escapeHTML(runtimeContext.controlRevision || 'UNVERIFIED')}</span></div><div class="stat-box"><strong>写集</strong><span>${escapeHTML((raw.write_set || [`artifacts/${task.id}`]).join(' · '))}</span></div><div class="stat-box"><strong>验收</strong><span>${escapeHTML((raw.acceptance || ['命令、证据、独立复核']).join(' · '))} · ${escapeHTML(task.subproblemId || '共享节点')}</span></div><div class="stat-box"><strong>来源</strong><span>${escapeHTML(task.source === 'local_ui' ? 'LOCAL_UI · 未写入服务端' : runtimeContext.sourceLabel || 'UNVERIFIED')}</span></div><div class="stat-box"><strong>下一步</strong><span>${escapeHTML(task.meta || '等待状态同步')}</span></div></div><h3>群主可执行动作</h3><div class="task-modal-actions"><button type="button" class="approve-button" data-task-nudge="${escapeHTML(task.id)}">生成催办草稿</button><button type="button" class="decision-more" data-task-snapshot="${escapeHTML(task.id)}">生成审查快照</button>${blocked ? `<button type="button" class="decision-more" data-task-requeue="${escapeHTML(task.id)}">重新排队</button>` : ''}</div><p class="form-note">催办和审查快照会先在本地生成可复制文本；重新排队在 LIVE 模式写入服务端并保留 CAS/幂等校验。</p>`);
}

function taskNudge(taskId) {
  const task = tasks.find(item => item.id === taskId);
  if (!task) return;
  const text = `请 ${task.owner || '负责人'} 更新 ${task.id}：${task.title}。回执需包含当前 revision、验收命令、结果 hash 和未解决风险。`;
  if (LIVE_API) {
    if (collaborationPaused) { showToast('协作已暂停；催办草稿未发送'); return; }
    postLiveMessage(text, 'lite', [], { taskId }).then(ok => { if (ok) closeModal(); });
  } else {
    closeModal();
    addOwnerMessage(text, [], { taskId, subproblemId: task.subproblemId || window.selectedSubproblem || 'Q2' });
    showToast('催办已加入本地演示群聊 · SIMULATED');
  }
}

function taskAuditSnapshot(taskId) {
  const task = tasks.find(item => item.id === taskId);
  if (!task) return;
  const raw = task.rawTask || task;
  const snapshot = [`task_id: ${task.id}`, `status: ${task.status || task.state || 'UNVERIFIED'}`, `owner: ${task.owner || raw.owner_id || 'UNVERIFIED'}`, `input_revision: ${raw.input_revision || runtimeContext.inputRevision || 'UNVERIFIED'}`, `control_revision: ${runtimeContext.controlRevision || 'UNVERIFIED'}`, `write_set: ${(raw.write_set || []).join(', ') || 'UNVERIFIED'}`, `source: ${task.source === 'local_ui' ? 'LOCAL_UI' : contextModeLabel()}`, `next_action: ${task.meta || 'UNVERIFIED'}`].join('\n');
  showModal(`审查快照 · ${task.id}`, `<p>以下是只读、可复制的当前投影；它不会替代 worker result 或独立 review。</p><pre>${escapeHTML(snapshot)}</pre><button type="button" class="approve-button" data-copy-text="${escapeHTML(snapshot)}">复制快照</button>`);
}

function handleMessageAction(action, messageId) {
  const message = messages.find(item => item.id === messageId);
  const normalized = String(action || '').trim();
  if (normalized.includes('原文映射')) { window.selectedSubproblem = message?.subproblemId || 'Q1'; renderModelingOverview(); selectRightPanel('modeling'); showToast(`已定位 ${window.selectedSubproblem} 的题面映射`); return; }
  if (normalized.includes('打开 evidence') || normalized.includes('证据')) { selectRightPanel('evidence'); if (message?.evidenceRefs?.[0]) evidenceModal(message.evidenceRefs[0]); else showToast('该消息没有可打开的 evidence ref，保持 UNVERIFIED'); return; }
  if (normalized.includes('比较 A/B')) { routeCompareModal(); return; }
  if (normalized.includes('公式')) { chainNodeModal('route'); return; }
  if (normalized.includes('反驳线程')) { threadRoots = [...new Set([...threadRoots, messageId])]; openThreadsModal(messageId); return; }
  if (normalized.includes('claim')) { openSearch(normalized.match(/claim\s+(.+)/i)?.[1] || 'claim:C-17'); return; }
  if (message?.taskId) { taskModal(tasks.find(item => item.id === message.taskId)); return; }
  showToast(`已执行消息动作：${normalized}`);
}

function evidenceModal(name) {
  const item = evidence.find(entry => entry.title === name) || { status: 'UNVERIFIED', source: 'unknown', meta: '没有 artifact manifest' };
  const rawStatus = item.status || 'UNVERIFIED';
  const status = item.source === 'fixture' && ['VERIFIED', 'ACCEPTED', 'RELEASED'].includes(rawStatus)
    ? 'PRODUCED'
    : (['VERIFIED', 'ACCEPTED', 'RELEASED'].includes(rawStatus) && !item.manifestLinked ? 'UNVERIFIED' : rawStatus);
  const safeRevision = runtimeContext.inputRevision || 'UNVERIFIED';
  showModal(name, `<p>只读证据预览。状态由 artifact manifest 决定；当前 ${escapeHTML(contextModeLabel())}，没有 manifest 的条目不会被渲染为 VERIFIED。</p><pre>protocol_version: agent-collab/v1\nartifact: ${escapeHTML(name)}\nsource: ${escapeHTML(item.source || 'unknown')}\nrevision: ${escapeHTML(safeRevision)}\nstatus: ${escapeHTML(status)}\nmanifest_linked: ${item.manifestLinked === true ? 'true' : 'false'}\nprovenance: ${status === 'VERIFIED' || status === 'ACCEPTED' ? 'manifest-linked' : 'not-yet-verified'}\nclaim_refs: ${(item.claimRefs || []).join(', ') || 'none'}\nsource_note: ${escapeHTML(item.meta || 'unknown')}</pre><p><span class="tag ${status === 'BLOCKED' || status === 'UNVERIFIED' ? 'rose' : 'amber'}">${escapeHTML(status)}</span> <span class="tag blue">${escapeHTML(item.source === 'fixture' ? 'SIMULATED fixture' : 'LIVE artifact')}</span></p>`);
}

function addOwnerMessage(text, evidenceRefs = [], metadata = {}) {
  messages.push(normalizeProvenance({ id: newClientId('owner'), member: 'owner', time: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }), kind: metadata.kind || '群主', text: escapeHTML(text), tags: [['Owner 指令', 'blue']], status: 'PRODUCED', claimClass: 'hypothesis', taskId: metadata.taskId || metadata.task_id || 'G9', subproblemId: metadata.subproblemId || metadata.subproblem_id || window.selectedSubproblem || 'Q2', modelProfile: 'Human Owner', targetRevision: runtimeContext.controlRevision, evidenceRefs, channel: metadata.channel || activeChannel, attachments: metadata.attachments || [], ...metadata }, 'fixture'));
  renderMessages();
}

function timeFromTimestamp(timestamp) {
  if (!timestamp) return new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
  const match = String(timestamp).match(/T(\d{2}:\d{2})/);
  return match ? match[1] : String(timestamp).slice(0, 5);
}

function memberForActor(actorId) {
  if (actorId === 'owner' || actorId === 'user') return 'owner';
  if (members.some(member => member.id === actorId)) return actorId;
  if (String(actorId).includes('critic')) return 'critic';
  if (String(actorId).includes('data')) return 'data';
  if (String(actorId).includes('routeA') || String(actorId).includes('model-a')) return 'routeA';
  if (String(actorId).includes('routeB') || String(actorId).includes('model-b')) return 'routeB';
  if (String(actorId).includes('validator')) return 'validator';
  if (String(actorId).includes('antigravity') || String(actorId).includes('challenger')) return 'critic';
  return 'scope';
}

function eventKind(type) {
  return ({ MESSAGE: '群聊', TASK_DISPATCHED: '派发', TASK_CLAIMED: '进展', TASK_RESULT: '回执', TASK_HEARTBEAT: '心跳', TASK_HANDOFF: '交接', REVIEW: '审查', CRITIQUE: '质疑', FINDING_CLOSED: '修复', APPROVAL: '审批', RELAY: '外部协作', RELAY_ACK: '外部 ACK', RERUN_REQUESTED: '复跑', ASSEMBLY_UPDATED: '装配' })[type] || '事件';
}

function eventText(payload) {
  if (!payload) return '';
  if (payload.text) return payload.text;
  if (payload.summary) return payload.summary;
  if (payload.assembly_revision) return `能力装配 ${String(payload.assembly_revision).slice(0, 22)}… 已更新，等待独立审查。`;
  if (payload.objective) return `已派发：${payload.objective}`;
  if (payload.task_id) return `任务 ${payload.task_id} 状态已更新。`;
  return '事件已写入事实源，等待对应工件回执。';
}

function simulateAgentReply(text, mode) {
  const typing = document.getElementById('typingLine');
  const typingText = document.getElementById('typingText');
  typingText.textContent = mode === 'solo' ? 'Model-A 正在处理单 Agent 请求…' : 'Coordinator 正在分派并等待 Agent 回执…';
  typing.hidden = false;
  window.setTimeout(() => {
    typing.hidden = true;
    const lower = text.toLowerCase();
    const reply = lower.includes('反例') || text.includes('质疑')
      ? { member: 'critic', kind: '质疑', text: '收到。我会把问题拆成最小可复现反例，并在当前 revision 上补一条审查记录；在证据齐全前不会给出 accept。', tags: [['CRITIQUE', 'rose'], ['等待证据', 'amber']] }
      : lower.includes('数据')
        ? { member: 'data', kind: '进展', text: '已领取数据审计任务。我会先返回编码、缺失、重复、泄漏和清洗前后计数，再请求群主批准任何样本变换。', tags: [['DATA-AUDIT', 'teal'], ['需要审批', 'amber']] }
        : { member: 'scope', kind: '回执', text: 'Coordinator 已记录你的指令，并为相关节点生成了任务包。下一条更新会附 task_id、input revision、验收命令和预计回执时间。', tags: [['ACK', 'blue'], ['agent-collab/v1', 'violet']] };
    messages.push(normalizeProvenance({ id: `reply-${Date.now()}`, time: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }), status: reply.member === 'critic' ? 'READY_FOR_REVIEW' : 'PRODUCED', claimClass: reply.member === 'critic' ? 'hypothesis' : 'derived', taskId: defaultTaskByMember[reply.member] || 'unassigned', subproblemId: defaultQuestionByMember[reply.member] || window.selectedSubproblem || 'Q2', modelProfile: getMember(reply.member).shortModel, targetRevision: runtimeContext.controlRevision, evidenceRefs: [], ...reply }, 'fixture'));
    renderMessages();
    showToast('已收到 Agent 回执；右侧任务面板已同步');
  }, 1050);
}

async function postLiveMessage(text, mode, evidenceRefs = [], metadata = {}) {
  const endpoint = `${LIVE_API}/api/projects/${LIVE_PROJECT}/messages`;
  const selected = subproblems.find(item => item.id === (window.selectedSubproblem || 'Q2')) || subproblems[1];
  if (collaborationPaused) { showToast('协作已暂停；消息保留在编辑区，恢复后再发送'); return false; }
  try {
    const payload = await fetchJson(endpoint, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text, mode, sender_id: 'owner', channel: metadata.channel || (activeChannel === '主议事群' ? 'main' : activeChannel), claim_class: 'hypothesis', task_id: metadata.taskId || metadata.task_id || 'G9', subproblem_id: metadata.subproblemId || metadata.subproblem_id || selected.id, evidence_refs: evidenceRefs, target_revision: runtimeContext.inputRevision, base_revision: liveRevision, assembly_revision: metadata.assemblyRevision || metadata.assembly_revision || undefined, capability_revision: metadata.capabilityRevision || metadata.capability_revision || undefined, idempotency_key: metadata.idempotencyKey || newClientId('message') }) });
    liveRevision = payload.revision;
    setRuntimeContext({ controlRevision: payload.revision });
    ingestLiveEvent(payload.event, LIVE_API);
    knowledgePendingRefs = knowledgePendingRefs.filter(ref => !evidenceRefs.includes(ref));
    renderPendingKbCitations();
    showToast('已写入事件源，等待真实 Coordinator 回执');
    return true;
  } catch (error) {
    if (error.message === 'STALE_REVISION') {
      try {
        const refreshed = await fetch(`${LIVE_API}/api/projects/${LIVE_PROJECT}/snapshot`).then(response => response.json());
        applyLiveSnapshot(refreshed);
        showToast('事件源版本已变化；已刷新快照，请确认后重发');
      } catch (_) {
        showToast('事件源版本已变化；快照刷新失败，请稍后重试');
      }
    } else {
    addLocalPendingMessage(text, evidenceRefs, metadata);
      showToast(`实时写入失败（${error.message}）；已标记为 LOCAL_PENDING，不生成伪造回执`);
    }
    return false;
  }
}

function addLocalPendingMessage(text, evidenceRefs = [], metadata = {}) {
  messages.push({ id: newClientId('local'), member: 'owner', time: timeFromTimestamp(), kind: '待同步', text: escapeHTML(text), tags: [['LOCAL_PENDING', 'amber'], ['未写入事实源', 'rose']], source: 'local_pending', sourceLabel: 'LOCAL_PENDING', status: 'UNVERIFIED', claimClass: 'hypothesis', taskId: metadata.taskId || metadata.task_id || 'unassigned', subproblemId: metadata.subproblemId || metadata.subproblem_id || window.selectedSubproblem || 'Q2', modelProfile: 'Human Owner', targetRevision: runtimeContext.controlRevision, evidenceRefs: sanitizeEvidenceRefs(evidenceRefs), attachments: metadata.attachments || [] });
  renderMessages();
}

function appendLiveEvent(payload) {
  if (!payload || !payload.event_id || seenLiveEvents.has(payload.event_id)) return;
  seenLiveEvents.add(payload.event_id);
  if (!eventRows.some(row => row && row.event_id === payload.event_id)) eventRows.push(payload);
  const eventSeq = Number(payload.seq || 0);
  const advancesCursor = eventSeq >= liveSeq;
  liveSeq = Math.max(liveSeq, eventSeq);
  // REST replay and WebSocket delivery may interleave.  Never let an older
  // replayed event move the CAS revision behind the newest applied event.
  if (payload.revision && advancesCursor) liveRevision = payload.revision;
  const body = payload.payload || {};
  projectLiveControl(payload);
  const member = memberForActor(payload.actor_id);
  const kind = payload.actor_id === 'owner' ? '群主' : eventKind(payload.type);
  messages.push(normalizeProvenance({
    id: payload.event_id,
    member,
    time: timeFromTimestamp(payload.timestamp),
    kind,
    // Preserve the authoritative event channel in the UI projection.  Without
    // this field a message sent from a non-main channel was re-inferred from
    // its text/actor and could disappear from the channel it was just written
    // to (a successful write with no visible feedback).
    channel: payload.channel || body.channel || 'main',
    text: escapeHTML(eventText(body)),
    tags: [['LIVE EVENT', 'teal'], [payload.event_id, 'blue']],
    status: body.status || body.provenance_status || payload.status || payload.provenance_status,
    claimClass: body.claim_class || body.claimClass,
    taskId: payload.task_id || body.task_id || 'unassigned',
    subproblemId: body.subproblem_id || body.subproblemId || '—',
    modelProfile: (payload.sender && payload.sender.model) || body.model_profile || getMember(member).shortModel,
    targetRevision: payload.revision || payload.base_revision || runtimeContext.controlRevision,
    evidenceRefs: body.evidence_refs || body.artifact_refs || [],
    assemblyRevision: body.assembly_revision || body.assemblyRevision,
    capabilityRevision: body.capability_revision || body.capabilityRevision,
    eventSeq,
    eventHash: payload.event_hash || '',
  }, 'live'));
  renderMessages();
}

function consumeContiguousEvent(payload) {
  if (!payload || !payload.event_id) return;
  const eventSeq = Number(payload.seq || 0);
  if (seenSnapshotMessages.has(payload.event_id)) {
    // The message projection was already rendered by HTTP snapshot.  It is
    // still a consumed event for sequencing purposes; otherwise a later
    // control event would remain buffered forever behind an invisible message.
    seenSnapshotMessages.delete(payload.event_id);
    seenLiveEvents.add(payload.event_id);
    liveSeq = Math.max(liveSeq, eventSeq);
    if (payload.revision) liveRevision = payload.revision;
    return;
  }
  appendLiveEvent(payload);
}

function ingestLiveEvent(payload, httpBase = LIVE_API, requestReplay = true) {
  if (!payload || !payload.event_id) return;
  if (seenLiveEvents.has(payload.event_id)) return;
  const eventSeq = Number(payload.seq || 0);
  // Legacy/non-sequenced messages can still be rendered, but every v1 event
  // with a sequence number is buffered until all earlier events are present.
  if (!Number.isFinite(eventSeq) || eventSeq <= 0) {
    appendLiveEvent(payload);
    return;
  }
  if (eventSeq <= liveSeq) {
    seenLiveEvents.add(payload.event_id);
    return;
  }
  pendingLiveEvents.set(eventSeq, payload);
  let next = liveSeq + 1;
  while (pendingLiveEvents.has(next)) {
    const contiguous = pendingLiveEvents.get(next);
    pendingLiveEvents.delete(next);
    consumeContiguousEvent(contiguous);
    next += 1;
  }
  if (requestReplay && eventSeq > liveSeq + 1 && httpBase) {
    replayLiveEvents(httpBase).catch(() => showToast('事件序号存在缺口；补发失败，仍保留待同步状态'));
  }
}

function normalizeLiveSubproblem(record, index) {
  const promptRefs = Array.isArray(record.prompt_refs || record.promptRefs) ? (record.prompt_refs || record.promptRefs).filter(ref => ref && typeof ref === 'object') : [];
  const sourceStatus = String(record.source_status || record.sourceStatus || (promptRefs.length ? 'verified' : 'unavailable')).toLowerCase();
  const blocked = !promptRefs.length || ['image_only', 'unavailable', 'blocked'].includes(sourceStatus);
  return {
    ...(subproblems[index] || {}),
    ...record,
    id: String(record.id || record.subproblem_id || `Q${index + 1}`),
    prompt: String(record.prompt || record.title || '题面句待解析'),
    promptRefs,
    sourceStatus,
    state: blocked ? 'blocked' : (record.state || 'ready'),
    stateLabel: blocked ? 'BLOCKED · 题面来源不足' : (record.state_label || record.stateLabel || '待复核'),
    coverage: record.coverage || (blocked ? '0/6 可核对' : '待计算'),
    risk: record.risk || (blocked ? 'prompt_refs 未满足' : '待审查'),
  };
}

function mergeLiveModeling(snapshot) {
  const modeling = snapshot.modeling || snapshot.problem_contract || {};
  const sourceStatusValue = String(modeling.source_status || modeling.sourceStatus || '').toLowerCase();
  const sourceUnavailable = ['unavailable', 'image_only', 'blocked'].includes(sourceStatusValue);
  if (modeling.source_status || modeling.sourceStatus) {
    const sourceStatus = sourceStatusValue;
    const suppliedQuestions = modeling.subproblems || modeling.questions;
    if (['unavailable', 'image_only', 'blocked'].includes(sourceStatus) && (!Array.isArray(suppliedQuestions) || suppliedQuestions.length === 0)) {
      subproblems.forEach(item => {
        item.sourceStatus = sourceStatus;
        item.promptRefs = [];
        item.state = 'blocked';
        item.stateLabel = `BLOCKED · ${sourceStatus}`;
        item.coverage = '0/6 可核对';
        item.risk = '真实 problem_contract 未提供';
      });
      routeSpecs.forEach(route => {
        route.status = 'UNVERIFIED';
        route.warning = 'live 快照未提供 route_spec；仅保留界面骨架';
      });
      modelChain.forEach(node => { if (node.id !== 'prompt') node.state = 'blocked'; });
    }
  }
  const incomingQuestions = modeling.subproblems || modeling.questions;
  if (Array.isArray(incomingQuestions)) {
    incomingQuestions.slice(0, 12).forEach((record, index) => {
      if (!record || typeof record !== 'object') return;
      const normalized = normalizeLiveSubproblem(record, index);
      const existingIndex = subproblems.findIndex(item => item.id === normalized.id);
      if (existingIndex >= 0) subproblems[existingIndex] = normalized;
      else subproblems.push(normalized);
    });
  }
  if (Array.isArray(modeling.variables)) {
    modeling.variables.slice(0, 100).forEach(record => {
      if (!record || typeof record !== 'object') return;
      const id = String(record.id || record.symbol || 'unknown');
      const existing = variableRegistry.find(item => item.id === id);
      const normalized = { ...record, id, evidenceRefs: sanitizeEvidenceRefs(record.evidence_refs || record.evidenceRefs), sourceStatus: record.source_status || record.sourceStatus || 'UNVERIFIED' };
      if (existing) Object.assign(existing, normalized);
      else variableRegistry.push(normalized);
    });
  }
  const incomingEdges = modeling.model_edges || modeling.modelEdges;
  // An unavailable live contract is an explicit absence of source data, not
  // an instruction to erase the visible audit skeleton. Preserve fixture
  // edges/plans/gates so the user can still see exactly what is blocked.
  if (Array.isArray(incomingEdges) && (incomingEdges.length || !sourceUnavailable)) {
    modelEdges.splice(0, modelEdges.length, ...incomingEdges.filter(edge => edge && typeof edge === 'object').slice(0, 100).map(edge => ({ ...edge, status: edge.status || 'UNVERIFIED' })));
  }
  if (Array.isArray(modeling.routes)) {
    modeling.routes.slice(0, 8).forEach(record => {
      if (!record || typeof record !== 'object') return;
      const existing = routeSpecs.find(route => route.id === record.id);
      if (existing) Object.assign(existing, record);
      else routeSpecs.push(record);
    });
  }
  const incomingPlans = modeling.validation_plans || modeling.validationPlans;
  if (Array.isArray(incomingPlans) && (incomingPlans.length || !sourceUnavailable)) validationPlans.splice(0, validationPlans.length, ...incomingPlans.filter(plan => plan && typeof plan === 'object'));
  if (Array.isArray(modeling.gates) && (modeling.gates.length || !sourceUnavailable)) {
    gateMatrix.splice(0, gateMatrix.length, ...modeling.gates.filter(gate => gate && typeof gate === 'object').map(gate => ({ ...gate, status: gate.status || 'blocked', statusLabel: gate.status_label || gate.statusLabel || 'UNVERIFIED' })));
  }
}

function applyLiveSnapshot(snapshot) {
  if (!snapshot) return;
  workspaceState.integrity = snapshot.source_integrity || snapshot.context?.source_integrity || workspaceState.integrity;
  if (workspaceState.catalog) renderWorkspaceMount(workspaceState.catalog);
  mergeLiveModeling(snapshot);
  liveRevision = snapshot.revision || liveRevision;
  const snapshotContext = snapshot.context || {};
  setRuntimeContext({
    projectId: snapshotContext.project_id || snapshot.project_id || runtimeContext.projectId,
    runId: snapshotContext.run_id || snapshot.run_id || runtimeContext.runId,
    mode: 'live',
    sourceStatus: snapshotContext.source_status || 'local_event_store',
    sourceLabel: 'LIVE · 本地事件源',
    inputRevision: snapshotContext.input_revision || snapshot.input_revision || runtimeContext.inputRevision,
    worktreeRevision: snapshotContext.worktree_revision || snapshot.worktree_revision || snapshotContext.input_revision || runtimeContext.worktreeRevision,
    controlRevision: snapshotContext.control_revision || snapshot.revision || runtimeContext.controlRevision,
  });
  // The snapshot projection contains only the latest messages (not every
  // control event), so its next_seq is a server hint, not an acknowledged
  // event cursor.  Advancing liveSeq here would skip TASK/REVIEW/APPROVAL
  // events that happened while the browser was disconnected.  The WebSocket
  // handshake below replays from the last locally applied sequence instead.
  (snapshot.messages || []).forEach(record => {
    const id = record.message_id || record.event_ref;
    if (!id || seenSnapshotMessages.has(id) || seenLiveEvents.has(id)) return;
    seenSnapshotMessages.add(id);
    const member = memberForActor(record.sender_id);
    messages.push(normalizeProvenance({ id, member, time: timeFromTimestamp(record.timestamp), kind: record.sender_id === 'owner' ? '群主' : '群聊', channel: record.channel || 'main', text: escapeHTML(record.text || ''), tags: [['SNAPSHOT', 'teal'], [record.channel || 'main', 'blue']], status: record.status, claimClass: record.claim_class, taskId: record.task_id || 'unassigned', subproblemId: record.subproblem_id || '—', modelProfile: record.model_profile || getMember(member).shortModel, targetRevision: record.target_revision || snapshot.revision, evidenceRefs: record.evidence_refs || [], assemblyRevision: record.assembly_revision, capabilityRevision: record.capability_revision }, 'snapshot'));
  });
  if (Array.isArray(snapshot.events)) {
    snapshot.events.forEach(event => {
      if (event?.event_id && !eventRows.some(row => row.event_id === event.event_id)) eventRows.push(event);
    });
  }
  mergeSnapshotTasks(snapshot.tasks);
  projectLiveSnapshotCollections(snapshot);
  renderMessages();
}

async function replayLiveEvents(httpBase, afterSeq = liveSeq) {
  if (replayPromise) return replayPromise;
  replayPromise = (async () => {
    let cursor = Math.max(0, Number(afterSeq) || 0);
    for (let page = 0; page < 20; page += 1) {
      const response = await fetch(`${httpBase}/api/projects/${LIVE_PROJECT}/events?after_seq=${cursor}&limit=500`);
      if (!response.ok) throw new Error('EVENT_REPLAY_UNAVAILABLE');
      const payload = await response.json();
      const pageEvents = payload.events || [];
      pageEvents.forEach(event => ingestLiveEvent(event, httpBase, false));
      if (!payload.has_more || !pageEvents.length) break;
      const nextCursor = Number(payload.next_after_seq || pageEvents[pageEvents.length - 1].seq || cursor);
      if (nextCursor <= cursor) break;
      cursor = nextCursor;
    }
  })().finally(() => { replayPromise = null; });
  return replayPromise;
}

function scheduleLiveReconnect(httpBase) {
  if (liveReconnectTimer || !LIVE_API) return;
  liveReconnectTimer = window.setTimeout(() => {
    liveReconnectTimer = null;
    connectLiveTransport(httpBase);
  }, 2200);
}

function connectLiveTransport(baseOverride) {
  if (!LIVE_API) return;
  const httpBase = baseOverride || LIVE_API || window.location.origin;
  fetch(`${httpBase}/api/projects/${LIVE_PROJECT}/snapshot`).then(response => {
    if (!response.ok) throw new Error('SNAPSHOT_UNAVAILABLE');
    return response.json();
  }).then(snapshot => {
    applyLiveSnapshot(snapshot);
    const demo = document.querySelector('.demo-pill');
    if (demo) demo.textContent = 'LIVE · 本地事件源';
    liveConnected = true;
    showToast(`已连接事件源 · revision ${(liveRevision || '').slice(0, 19)}…`);
    const wsUrl = httpBase.replace(/^http/, 'ws') + `/ws/projects/${LIVE_PROJECT}`;
    liveSocket = new WebSocket(wsUrl);
    liveSocket.addEventListener('open', () => { liveConnected = true; });
    liveSocket.addEventListener('message', event => {
      let payload;
      try { payload = JSON.parse(event.data); } catch (_) { showToast('收到无法解析的事件；已忽略并保留审计边界'); return; }
      if (payload.type === 'snapshot') {
        // Keep the locally acknowledged cursor and backfill the gap between
        // the HTTP snapshot and this WebSocket handshake.  Do not jump to
        // after_seq before replaying, otherwise non-message events disappear.
        replayLiveEvents(httpBase, liveSeq).catch(() => showToast('事件补发失败；下次重连将继续尝试'));
        return;
      }
      if (payload.type === 'MESSAGE' || payload.type === 'message') ingestLiveEvent(payload, httpBase);
      else if (payload.event_id) ingestLiveEvent(payload, httpBase);
    });
    liveSocket.addEventListener('close', () => { liveConnected = false; showToast('事件源连接已断开；恢复后按 seq 补发'); scheduleLiveReconnect(httpBase); });
    liveSocket.addEventListener('error', () => { liveConnected = false; });
  }).catch(() => { liveConnected = false; restoreFixtureModeling(); setRuntimeContext({ ...DEMO_CONTEXT, mode: 'simulated', sourceStatus: 'fixture', sourceLabel: 'SIMULATED · fixture' }); showToast('未找到实时 API；当前使用 SIMULATED 演示事件流'); scheduleLiveReconnect(httpBase); });
}

function parseKnowledgeCommand(text) {
  const match = String(text || '').match(/^@知识库(?:\s+|[:：])(.+)$/i);
  return match ? match[1].trim() : '';
}

function sendMessage() {
  const input = document.getElementById('messageInput');
  const text = input.value.trim();
  if (!text) return;
  if (collaborationPaused) {
    showToast('协作已暂停；消息仍保留在编辑区，点击顶部“继续协作”后发送');
    return;
  }
  const mode = document.getElementById('composerMode').value;
  const evidenceRefs = [...knowledgePendingRefs];
  const attachments = localAttachments.map(item => ({ ...item }));
  // A bare @知识库 command is a local retrieval action.  Once a result has
  // been cited, the pending kbdoc ref makes the same text a normal auditable
  // group message instead of silently swallowing the owner's challenge.
  const knowledgeQuery = evidenceRefs.length === 0 ? parseKnowledgeCommand(text) : '';
  if (knowledgeQuery) {
    input.value = '';
    input.style.height = 'auto';
    openKnowledgePanel();
    runKnowledgeSearch(knowledgeQuery, true);
    showToast(`已调用本地知识库：${knowledgeQuery.slice(0, 36)}${knowledgeQuery.length > 36 ? '…' : ''}`);
    return;
  }
  if (LIVE_API) {
    if (!liveRevision) {
      showToast('正在同步事件源；请等 revision 出现后再发送');
      return;
    }
    input.value = '';
    input.style.height = 'auto';
    const outboundText = text + attachmentSummary();
    postLiveMessage(outboundText, mode, evidenceRefs, { attachments, taskId: 'G9', channel: activeChannel === '主议事群' ? 'main' : activeChannel }).then(ok => {
      if (ok) { localAttachments = []; renderComposerAttachments(); }
    });
  } else {
    input.value = '';
    input.style.height = 'auto';
    knowledgePendingRefs = [];
    renderPendingKbCitations();
    addOwnerMessage(text + attachmentSummary(), evidenceRefs, { attachments, channel: activeChannel });
    localAttachments = [];
    renderComposerAttachments();
    simulateAgentReply(text, mode);
  }
}

function modelTraceModal() {
  const selected = subproblems.find(item => item.id === (window.selectedSubproblem || 'Q2')) || subproblems[1];
  const rows = [
    ['1 · 题面覆盖', selected.prompt, '原题句 / 页码 / source_status'],
    ['2 · 数学化', '变量、状态、参数、目标、约束、边界条件', '符号 + 单位 + 粒度 + provenance'],
    ['3 · 假设', 'observed / derived / hypothesis 分层', '适用域 / 禁用条件 / 可识别性'],
    ['4 · 路线', 'baseline → primary → fallback', '接口字段、算法、复杂度、失败模式'],
    ['5 · 验证', '按题型选择互补检查', 'clean-run、退出码、结果 hash'],
    ['6 · 论文', '只引用 VERIFIED / ACCEPTED claim', '指标定义、限制、外部有效性'],
  ];
  const variableRows = (selected.variables || []).map(id => variableRegistry.find(item => item.id === id)).filter(Boolean).map(item => `<div class="trace-modal-row"><b>${escapeHTML(item.symbol)} · ${escapeHTML(item.role)}</b><span>${escapeHTML(item.unit)} · ${escapeHTML(item.domain)}</span><em>${escapeHTML(item.sourceStatus)} · ${escapeHTML(item.provenance)}</em></div>`).join('');
  const edgeRows = modelEdges.map(edge => `<div class="trace-modal-row"><b>${escapeHTML(edge.from)} → ${escapeHTML(edge.to)}</b><span>${escapeHTML(edge.field)} · ${escapeHTML(edge.unit)} · ${escapeHTML(edge.granularity)}</span><em>${escapeHTML(edge.status)} · ${escapeHTML(edge.provenance)}</em></div>`).join('');
  showModal(`完整建模链 · ${selected.id}`, `<p>这是当前 <strong>${escapeHTML(selected.title)}</strong> 的只读追踪视图。演示实体不是实际赛题结论；缺来源时必须保持 BLOCKED/UNVERIFIED。</p><div class="trace-modal-list">${rows.map(row => `<div class="trace-modal-row"><b>${escapeHTML(row[0])}</b><span>${escapeHTML(row[1])}</span><em>${escapeHTML(row[2])}</em></div>`).join('')}</div><h3>变量登记（结构化）</h3><div class="trace-modal-list">${variableRows || '<div class="trace-modal-row"><b>UNVERIFIED</b><span>尚无变量登记</span><em>等待 problem_contract</em></div>'}</div><h3>链边接口审计</h3><div class="trace-modal-list">${edgeRows}</div><h3>硬门</h3><ul><li>模型链长度不加分；接口单位、粒度和来源必须对齐。</li><li>预测、优化、仿真/物理、机制题使用不同验证族，至少两类互补检查。</li><li>开放 P0/P1、缺 hash 或未获 Owner approval 时，不得进入 ACCEPTED / RELEASED。</li></ul>`);
}

function chainNodeModal(nodeId) {
  const node = modelChain.find(item => item.id === nodeId);
  if (!node) return;
  const relatedEdges = modelEdges.filter(edge => edge.from === nodeId || edge.to === nodeId);
  const edgeHtml = relatedEdges.length ? relatedEdges.map(edge => `<div class="trace-modal-row"><b>${escapeHTML(edge.from)} → ${escapeHTML(edge.to)}</b><span>${escapeHTML(edge.field || 'field UNVERIFIED')} · ${escapeHTML(edge.unit || 'unit UNVERIFIED')} · ${escapeHTML(edge.granularity || '粒度 UNVERIFIED')}</span><em>${escapeHTML(edge.status || 'UNVERIFIED')} · ${escapeHTML(edge.provenance || 'provenance UNVERIFIED')}</em></div>`).join('') : '<div class="trace-modal-row"><b>UNVERIFIED</b><span>没有已登记的链边</span><em>等待 artifact manifest</em></div>';
  showModal(`建模链节点 · ${node.label}`, `<p>${escapeHTML(node.detail)}。节点状态：<span class="tag ${node.state === 'blocked' ? 'rose' : 'amber'}">${escapeHTML(node.state.toUpperCase())}</span></p><h3>相邻接口</h3><div class="trace-modal-list">${edgeHtml}</div><p><span class="tag amber">${escapeHTML(contextModeLabel())}</span> 缺失题面或 provenance 时只读，不推进状态。</p>`);
}

function routeCompareModal() {
  const rows = [['题型', routeSpecs[0].problemType, routeSpecs[1].problemType], ['目标', routeSpecs[0].objective, routeSpecs[1].objective], ['Baseline', routeSpecs[0].baseline, routeSpecs[1].baseline], ['输入 → 输出', routeSpecs[0].interfaces?.inputs?.join(' · ') + ' → ' + routeSpecs[0].interfaces?.outputs?.join(' · '), routeSpecs[1].interfaces?.inputs?.join(' · ') + ' → ' + routeSpecs[1].interfaces?.outputs?.join(' · ')], ['单位/粒度', routeSpecs[0].units + ' · ' + (routeSpecs[0].interfaces?.granularity || 'UNVERIFIED'), routeSpecs[1].units + ' · ' + (routeSpecs[1].interfaces?.granularity || 'UNVERIFIED')], ['参数 provenance', routeSpecs[0].interfaces?.provenance || routeSpecs[0].provenance, routeSpecs[1].interfaces?.provenance || routeSpecs[1].provenance], ['适用/禁用', routeSpecs[0].applicability + '；' + routeSpecs[0].interfaces?.disabledWhen, routeSpecs[1].applicability + '；' + routeSpecs[1].interfaces?.disabledWhen], ['验证检查', routeSpecs[0].validationChecks?.map(check => check.kind).join(' + '), routeSpecs[1].validationChecks?.map(check => check.kind).join(' + ')]];
  showModal('路线对照 · 证据字段', `<p>路线排序只提供决策支持，不按模型数量或标题数量加分。每一项验证必须有 scope、threshold、exit_code=0 和结果 hash 才能进入候选审批。</p><div class="route-modal-table"><div class="route-modal-head"><span>字段</span><b>路线 A</b><b>路线 B</b></div>${rows.map(row => `<div class="route-modal-row"><span>${escapeHTML(row[0])}</span><b>${escapeHTML(row[1] || 'UNVERIFIED')}</b><b>${escapeHTML(row[2] || 'UNVERIFIED')}</b></div>`).join('')}</div><p><span class="tag amber">当前：${escapeHTML(contextModeLabel())}</span> <span class="tag rose">P1 未关闭不可审批</span></p>`);
}

function exemplarStudyModal() {
  showModal('2016—2025 范文基线 · 设计依据', `<p>本工作台使用一个有边界的公开样本：2016—2025 年高教社杯/CUMCM 本科组公开展示与二次文字镜像，共 13 条来源记录。它是组委会展示/公开归档的便利样本，不代表全部获奖论文，也不用于推断“某个标题必然得分”。</p><div class="exemplar-grid"><div><b>观察到的稳定结构</b><ul><li>逐小问覆盖与交付物映射</li><li>问题分析、假设与符号独立呈现</li><li>baseline → 主路线 → 决策的模型链</li><li>算法入口、流程、参数来源可复算</li><li>基线比较、扰动/回测/收敛等验证</li><li>指标、图表、优缺点和推广边界</li></ul></div><div><b>被挑战后的硬门</b><ul><li>结构共现 ≠ 评分因果，标题不计完成</li><li>模型链必须逐边对齐单位、粒度和 provenance</li><li>验证按题型分层，至少两类互补检查</li><li>数字必须带分母、范围、基线、不确定性</li><li>缺件或 image-only 未复核 → BLOCKED</li><li>未 VERIFIED/ACCEPTED 的 claim 不进论文</li></ul></div></div><h3>可复核来源</h3><p class="source-links"><a href="https://dxs.moe.gov.cn/zx/hd/sxjm/sxjmlw/qkt_sxjm_lw_lwzs.shtml" target="_blank" rel="noreferrer">官方 2016—2025 论文展示索引</a><br><a href="https://www.mcm.edu.cn/html_cn/node/b1f48689659f0660e80a2d6279d7b37d.html" target="_blank" rel="noreferrer">全国评阅工作与评审标准说明</a><br><a href="https://dxs.moe.gov.cn/zx/a/hd_sxjm_sxjmlw_2018qgdxssxjmjslwzs_2018btlw/240206/1699831.shtml" target="_blank" rel="noreferrer">2018 B203：模型链与 12 组检验示例</a></p><p><span class="tag violet">observed：结构来自来源页/镜像</span> <span class="tag amber">inferred：设计启发</span> <span class="tag rose">hypothesis：需真实题回放验证</span></p>`);
}

function bindEvents() {
  document.querySelectorAll('.conversation-tab').forEach((tab, index) => {
    const filter = tab.dataset.filter || ['all', 'group', 'private', 'mentions'][index] || 'all';
    tab.dataset.filter = filter;
    tab.setAttribute('role', 'tab');
    tab.setAttribute('aria-selected', String(filter === activeConversationFilter));
    tab.addEventListener('click', () => setActiveConversationFilter(filter));
  });
  document.querySelectorAll('.channel-item').forEach(channel => channel.addEventListener('click', () => setActiveChannel(channel.dataset.channel || '主议事群')));
  const initialChannel = allChannelLabels().includes(activeChannel) ? activeChannel : '主议事群';
  setActiveChannel(initialChannel, { silent: true });
  setActiveConversationFilter(activeConversationFilter);
  document.querySelectorAll('[data-dag-task]').forEach(node => node.addEventListener('click', () => {
    const targetId = node.dataset.dagTask;
    const target = tasks.find(item => item.id === targetId) || tasks.find(item => item.id === 'G6-A');
    taskModal(target);
  }));
  document.getElementById('sendBtn').addEventListener('click', sendMessage);
  document.getElementById('messageInput').addEventListener('keydown', event => {
    if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); sendMessage(); }
  });
  document.getElementById('messageInput').addEventListener('input', event => { event.target.style.height = 'auto'; event.target.style.height = `${Math.min(event.target.scrollHeight, 110)}px`; });
  document.getElementById('memberList').addEventListener('click', event => { const button = event.target.closest('[data-member]'); if (button) memberModal(getMember(button.dataset.member)); });
  const memberStrip = document.getElementById('memberStrip');
  if (memberStrip) memberStrip.addEventListener('click', event => { const button = event.target.closest('[data-member]'); if (button) memberModal(getMember(button.dataset.member)); });
  document.getElementById('taskList').addEventListener('click', event => { const button = event.target.closest('[data-task]'); if (button) taskModal(tasks.find(item => item.id === button.dataset.task)); });
  document.getElementById('evidenceList').addEventListener('click', event => { const row = event.target.closest('[data-evidence]'); if (row) evidenceModal(row.dataset.evidence); });
  document.getElementById('subproblemStrip').addEventListener('click', event => {
    const card = event.target.closest('[data-subproblem]');
    if (!card) return;
    window.selectedSubproblem = card.dataset.subproblem;
    renderModelingOverview();
    showToast(`已聚焦 ${card.dataset.subproblem}；聊天与路线详情保持只读投影`);
  });
  document.getElementById('modelChainStrip').addEventListener('click', event => {
    const node = event.target.closest('[data-chain-node]');
    if (node) chainNodeModal(node.dataset.chainNode);
  });
  document.getElementById('modelTraceBtn').addEventListener('click', modelTraceModal);
  document.getElementById('exemplarBtn').addEventListener('click', exemplarStudyModal);
  document.getElementById('routeCompareBtn').addEventListener('click', routeCompareModal);
  document.getElementById('knowledgeBtn').addEventListener('click', openKnowledgePanel);
  const workspaceBrowseButton = document.getElementById('workspaceBrowseBtn');
  if (workspaceBrowseButton) workspaceBrowseButton.addEventListener('click', openWorkspaceBrowser);
  document.getElementById('assemblyBtn').addEventListener('click', () => {
    // The full-screen puzzle lab is the primary composition surface.  Keep
    // the compact legacy panel available as a graceful fallback for hosts
    // that load an older asset bundle.
    if (typeof window.openPuzzleStudio === 'function') window.openPuzzleStudio();
    else openAssemblyPanel();
  });
  const panelToggle = document.getElementById('panelToggleBtn');
  if (panelToggle) panelToggle.addEventListener('click', () => {
    const willOpen = !document.body.classList.contains('panel-drawer-open');
    if (willOpen) {
      const activePanel = document.querySelector('.right-tab.active')?.dataset.panel || 'modeling';
      selectRightPanel(activePanel);
    } else {
      setPanelDrawerOpen(false);
    }
  });
  const panelClose = document.getElementById('panelCloseBtn');
  if (panelClose) panelClose.addEventListener('click', () => setPanelDrawerOpen(false));
  const panelBackdrop = document.getElementById('panelBackdrop');
  if (panelBackdrop) panelBackdrop.addEventListener('click', () => setPanelDrawerOpen(false));
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape') {
      const modal = document.getElementById('modalBackdrop');
      if (modal && !modal.hidden) { closeModal(); return; }
      if (document.body.classList.contains('panel-drawer-open')) setPanelDrawerOpen(false);
    }
  });
  document.getElementById('decisionList').addEventListener('click', event => {
    const action = event.target.closest('[data-action]'); if (!action) return;
    const card = action.closest('[data-decision]');
    if (!card) return;
    const item = decisions.find(row => row.id === card.dataset.decision);
    if (action.dataset.action === 'approve' || action.dataset.action === 'reject') recordDecision(card.dataset.decision, action.dataset.action);
    else if (item) showModal('审批所需证据', `<p>${escapeHTML(item.body)}</p><pre>scope: ${escapeHTML(decisionScope(item))}\nowner: owner\ncurrent_revision: ${escapeHTML(runtimeContext.controlRevision || 'UNVERIFIED')}\ncritical_findings: ${item.id === 'dec-1' ? 'open' : 'check required'}\nexternal_transfer: ${item.id === 'dec-3' ? 'requires explicit approval' : 'not requested'}\nnext_gate: independent_review</pre>`);
  });
  document.querySelectorAll('.right-tab').forEach(tab => tab.addEventListener('click', () => {
    selectRightPanel(tab.dataset.panel);
    if (tab.dataset.panel === 'knowledge' && !knowledgeState.summary) loadKnowledgeSummary();
    if (tab.dataset.panel === 'assembly' && !capabilityState.catalog) loadCapabilityCatalog();
    // The puzzle studio is the primary workflow surface.  Keep the legacy
    // assembly panel mounted underneath it so older hosts and deep links still
    // have a graceful fallback, but route the visible tab to the new lab.
    if (tab.dataset.panel === 'assembly' && typeof window.openPuzzleStudio === 'function') window.openPuzzleStudio();
  }));
  document.querySelectorAll('.assembly-mode').forEach(button => button.addEventListener('click', () => setAssemblyMode(button.dataset.assemblyMode)));
  document.getElementById('capabilityRefreshBtn').addEventListener('click', async () => { await loadCapabilityCatalog(true); showToast('能力目录已按最新资料快照刷新'); });
  document.getElementById('applyPresetBtn').addEventListener('click', buildPresetAssembly);
  document.getElementById('capabilityPresetSelect').addEventListener('change', () => { capabilityState.assembly.presetId = document.getElementById('capabilityPresetSelect').value || null; });
  document.getElementById('capabilityArchetypeSelect').addEventListener('change', () => { capabilityState.assembly.archetypeId = document.getElementById('capabilityArchetypeSelect').value || null; });
  document.getElementById('blockPalette').addEventListener('click', event => { const button = event.target.closest('[data-assembly-add-type]'); if (button) addAssemblyItem(button.dataset.assemblyAddType, button.dataset.assemblyAddId); });
  document.getElementById('methodPalette').addEventListener('click', event => { const button = event.target.closest('[data-assembly-add-type]'); if (button) addAssemblyItem(button.dataset.assemblyAddType, button.dataset.assemblyAddId); });
  document.getElementById('contentPackPalette').addEventListener('click', event => { const button = event.target.closest('[data-content-pack]'); const pack = capabilityPacks().find(item => item.id === button?.dataset.contentPack); if (pack) { toggleContentPack(pack); openKnowledgePanel(); runKnowledgeSearch(pack.query, true); } });
  document.getElementById('assemblyCanvas').addEventListener('click', event => { const remove = event.target.closest('[data-assembly-node-remove]'); if (remove) { removeAssemblyNode(Number(remove.dataset.assemblyNodeRemove)); return; } const view = event.target.closest('[data-assembly-node-view]'); if (view) capabilityNodeModal(Number(view.dataset.assemblyNodeView)); });
  document.getElementById('clearAssemblyBtn').addEventListener('click', () => { assemblyValidationEpoch += 1; capabilityState.assembly = { nodes: [], edges: [], presetId: null, archetypeId: null, validation: null, revision: null, diff: null, previousNodes: [], previousEdges: [], committedRevision: null, innovationCard: null, previousInnovationCard: null, contentPackIds: [], previousContentPackIds: [], contentPackEvidenceRefs: [], contentPackEvidenceByPack: {}, contentPackIndexRevision: null, contentPackResolutionRevision: null, methodBlockWarnings: [] }; renderAssemblyCanvas(); renderAssemblyGate(); renderAssemblyDiff(null); renderInnovationSummary(); renderCapabilityCatalog(capabilityState.catalog); showToast('已清空自由装配草稿'); });
  document.getElementById('validateAssemblyBtn').addEventListener('click', validateAssembly);
  document.getElementById('innovationBtn').addEventListener('click', innovationModal);
  document.getElementById('sendAssemblyBtn').addEventListener('click', sendAssemblyToChat);
  document.getElementById('draftProblemContractBtn').addEventListener('click', draftProblemContract);
  document.querySelectorAll('.toolbar-button').forEach(button => button.addEventListener('click', () => {
    document.querySelectorAll('.toolbar-button').forEach(item => item.classList.remove('active')); button.classList.add('active');
    if (button.dataset.view === 'events') openEventsModal();
    if (button.dataset.view === 'threads') openThreadsModal();
    if (button.dataset.view === 'chat') { setActiveChannel(activeChannel, { silent: true }); showToast('已回到群聊视图'); }
  }));
  const pauseButton = document.getElementById('pauseBtn');
  const syncPauseButton = () => {
    if (!pauseButton) return;
    pauseButton.classList.toggle('paused', collaborationPaused);
    pauseButton.setAttribute('aria-pressed', String(collaborationPaused));
    pauseButton.title = collaborationPaused ? '本地暂停：恢复后可发送/派发' : '暂停本地出站动作';
    const label = pauseButton.querySelector('span:last-child'); if (label) label.textContent = collaborationPaused ? '继续协作' : '暂停协作';
  };
  syncPauseButton();
  pauseButton?.addEventListener('click', () => { collaborationPaused = !collaborationPaused; localStoreSet('qingjia.collaborationPaused', collaborationPaused); syncPauseButton(); showToast(collaborationPaused ? '已暂停本地出站动作；仍接收事件与快照' : '已恢复本地出站动作'); });
  document.getElementById('newTaskBtn')?.addEventListener('click', openNewTaskModal);
  document.getElementById('approveAllBtn')?.addEventListener('click', openApprovalQueue);
  document.getElementById('protocolBtn').addEventListener('click', () => showModal('agent-collab/v1', '<p>所有 Agent 使用统一 task/result/review/relay envelope；版本、哈希、身份、能力和证据必须可追溯。</p><pre>submit → poll → fetch_output → send_followup → cancel</pre>'));
  document.getElementById('settingsBtn').addEventListener('click', () => showModal('群组设置', '<h3>默认门禁</h3><ul><li>Coordinator：当前 Codex 根任务</li><li>最大 Agent：8 · 最大并行：4 · 深度：1</li><li>敏感数据：默认禁止外传</li><li>P0/P1 未关闭：禁止 ACCEPTED / RELEASED</li></ul>'));
  document.getElementById('inviteBtn')?.addEventListener('click', openInviteModal);
  document.getElementById('notificationBtn')?.addEventListener('click', openNotifications);
  document.getElementById('ownerMenuBtn').addEventListener('click', () => memberModal(getMember('owner')));
  document.getElementById('searchBtn').addEventListener('click', () => openSearch());
  const globalSearch = document.getElementById('globalSearchBtn');
  if (globalSearch) globalSearch.addEventListener('click', () => openSearch());
  document.addEventListener('keydown', event => {
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); openSearch(); }
  });
  document.getElementById('attachBtn').addEventListener('click', openAttachmentPicker);
  document.getElementById('mentionBtn').addEventListener('click', () => { const input = document.getElementById('messageInput'); input.value += '@'; input.focus(); });
  document.getElementById('kbRefreshBtn').addEventListener('click', async () => { await loadKnowledgeSummary(true); await runKnowledgeSearch(document.getElementById('kbSearchInput')?.value || ''); showToast('已刷新本地资料索引快照'); });
  document.getElementById('kbSearchForm').addEventListener('submit', event => { event.preventDefault(); runKnowledgeSearch(); });
  document.querySelectorAll('[data-kb-query]').forEach(button => button.addEventListener('click', () => runKnowledgeSearch(button.dataset.kbQuery || '')));
  ['kbModuleFilter', 'kbKindFilter', 'kbYearFilter'].forEach(id => document.getElementById(id).addEventListener('change', () => runKnowledgeSearch()));
  document.getElementById('kbResults').addEventListener('click', event => {
    const action = event.target.closest('[data-kb-action]');
    const card = event.target.closest('[data-kb-doc]');
    if (!action || !card) return;
    const item = knowledgeState.results.find(row => String(row.doc_id || row.docId || row.id) === card.dataset.kbDoc);
    if (!item) return;
    if (action.dataset.kbAction === 'view') openKnowledgeDocument(card.dataset.kbDoc, item);
    if (action.dataset.kbAction === 'cite') citeKnowledgeItem(item);
  });
  const conversationMore = document.querySelector('.conversation-more');
  conversationMore?.addEventListener('click', openConversationManager);
  document.querySelector('.channel-settings')?.addEventListener('click', openChannelSettings);
  document.getElementById('mobileMoreBtn')?.addEventListener('click', openMobileMoreModal);
  document.getElementById('chatFeed')?.addEventListener('click', event => {
    const action = event.target.closest('[data-message-action]');
    if (action) { handleMessageAction(action.dataset.messageAction, action.closest('[data-message-id]')?.dataset.messageId); return; }
  });
  document.getElementById('modalBody')?.addEventListener('submit', event => {
    event.preventDefault();
    const form = event.target;
    if (form.id === 'globalSearchForm') { renderSearchResults(form.elements.q.value); return; }
    if (form.id === 'newTaskForm') { submitNewTask(form); return; }
    if (form.id === 'threadReplyForm') { submitThreadReply(form); return; }
    if (form.id === 'inviteForm') { submitInvite(form); return; }
    if (form.id === 'newChannelForm') { addLocalChannel(form.elements.channel.value); return; }
  });
  document.getElementById('modalBody')?.addEventListener('click', event => {
    const cancel = event.target.closest('[data-modal-cancel]'); if (cancel) { closeModal(); return; }
    const mobileAction = event.target.closest('[data-mobile-more-action]');
    if (mobileAction) {
      const action = mobileAction.dataset.mobileMoreAction;
      closeModal();
      if (action === 'threads') openThreadsModal();
      if (action === 'events') openEventsModal();
      if (action === 'filter') openConversationManager();
      if (action === 'channels') openChannelSettings();
      return;
    }
    const filterButton = event.target.closest('[data-manage-filter]');
    if (filterButton) { setActiveConversationFilter(filterButton.dataset.manageFilter); return; }
    const selectChannel = event.target.closest('[data-channel-manage-select], [data-channel-settings-select]');
    if (selectChannel) { setActiveChannel(selectChannel.dataset.channelManageSelect || selectChannel.dataset.channelSettingsSelect); closeModal(); return; }
    const approvalAction = event.target.closest('[data-approval-action]');
    if (approvalAction) {
      const row = approvalAction.closest('[data-approval-decision]');
      if (!row) return;
      if (approvalAction.dataset.approvalAction === 'inspect') {
        const item = decisions.find(entry => entry.id === row.dataset.approvalDecision);
        if (item) showModal('审批证据', `<p>${escapeHTML(item.body)}</p><pre>scope: ${escapeHTML(decisionScope(item))}\nrevision: ${escapeHTML(runtimeContext.controlRevision || 'UNVERIFIED')}\nstatus: ${escapeHTML(decisionState(item) || 'PENDING')}</pre>`);
      } else recordDecision(row.dataset.approvalDecision, approvalAction.dataset.approvalAction);
      return;
    }
    const taskNudgeButton = event.target.closest('[data-task-nudge]'); if (taskNudgeButton) { taskNudge(taskNudgeButton.dataset.taskNudge); return; }
    const taskSnapshotButton = event.target.closest('[data-task-snapshot]'); if (taskSnapshotButton) { taskAuditSnapshot(taskSnapshotButton.dataset.taskSnapshot); return; }
    const taskRequeueButton = event.target.closest('[data-task-requeue]'); if (taskRequeueButton) { requeueTask(tasks.find(item => item.id === taskRequeueButton.dataset.taskRequeue)); return; }
    const searchKb = event.target.closest('[data-search-kb]'); if (searchKb) { closeModal(); openKnowledgePanel(); runKnowledgeSearch(searchKb.dataset.searchKb || '', true); return; }
    const searchTarget = event.target.closest('[data-search-message], [data-search-task], [data-search-evidence], [data-search-kb-doc], [data-search-event]');
    if (searchTarget) {
      if (searchTarget.dataset.searchMessage) { closeModal(); focusMessage(searchTarget.dataset.searchMessage); return; }
      if (searchTarget.dataset.searchTask) { taskModal(tasks.find(item => item.id === searchTarget.dataset.searchTask)); return; }
      if (searchTarget.dataset.searchEvidence) { evidenceModal(searchTarget.dataset.searchEvidence); return; }
      if (searchTarget.dataset.searchKbDoc) { const row = knowledgeState.results.find(item => String(item.doc_id || item.docId || item.id) === searchTarget.dataset.searchKbDoc); if (row) openKnowledgeDocument(searchTarget.dataset.searchKbDoc, row); return; }
      if (searchTarget.dataset.searchEvent) { const row = eventRows.find(item => item.event_id === searchTarget.dataset.searchEvent); if (row) showModal(`事件 ${row.event_id}`, `<pre>${escapeHTML(JSON.stringify(row, null, 2))}</pre>`); return; }
    }
    const copyButton = event.target.closest('[data-copy-text]');
    if (copyButton) { navigator.clipboard?.writeText(copyButton.dataset.copyText || '').then(() => showToast('已复制到剪贴板')).catch(() => showToast('当前浏览器未授权剪贴板，请手动复制')); return; }
    const removeAttachment = event.target.closest('[data-remove-attachment]');
    if (removeAttachment) { localAttachments.splice(Number(removeAttachment.dataset.removeAttachment), 1); renderComposerAttachments(); return; }
  });
  document.getElementById('channelMuteToggle')?.addEventListener('change', event => localStoreSet(`qingjia.muted.${activeChannel}`, event.target.checked));
  document.getElementById('modalClose').addEventListener('click', closeModal); document.getElementById('modalBackdrop').addEventListener('click', event => { if (event.target.id === 'modalBackdrop') closeModal(); });

  document.querySelectorAll('.nav-rail-item').forEach(item => item.addEventListener('click', () => {
    document.querySelectorAll('.nav-rail-item').forEach(node => node.classList.remove('active'));
    item.classList.add('active');
    const label = item.querySelector('span:last-child')?.textContent?.trim();
    if (label === '任务') selectRightPanel('tasks');
    else if (label === '资料') openKnowledgePanel();
    else if (label === '工作台') selectRightPanel('modeling');
    else if (label === '设置') showModal('群组设置', '<h3>默认门禁</h3><ul><li>Coordinator：当前 Codex 根任务</li><li>最大 Agent：8 · 最大并行：4 · 深度：1</li><li>敏感数据：默认禁止外传</li><li>P0/P1 未关闭：禁止 ACCEPTED / RELEASED</li></ul>');
    else if (label === '总览') selectRightPanel('tasks');
    else showToast('已回到主议事群');
  }));
}

/*
 * A deliberately small bridge for the full-screen workflow puzzle lab.
 * Keeping this adapter here means the new visual layer can evolve without
 * duplicating the capability catalogue or bypassing the existing compose /
 * commit gates.  It is read/write scoped to the in-memory assembly projection;
 * the server remains authoritative whenever LIVE_API is available.
 */
function notifyPuzzleAssembly() {
  try { window.dispatchEvent(new CustomEvent('qingjia:assembly-updated', { detail: { assembly: capabilityState.assembly } })); } catch (_) { /* older host */ }
}

function invalidatePuzzleAssembly() {
  const assembly = capabilityState.assembly;
  assembly.edges = autoLinkAssembly(assembly.nodes || []);
  assembly.validation = null;
  assembly.revision = null;
  assembly.diff = null;
  assembly.methodBlockWarnings = [];
  assemblyValidationEpoch += 1;
  renderAssemblyCanvas();
  renderAssemblyGate();
  renderAssemblyDiff(null);
  renderInnovationSummary();
  notifyPuzzleAssembly();
}

function puzzleSetSelection(presetId, archetypeId) {
  if (presetId && typeof presetId === 'object') {
    const payload = presetId;
    presetId = payload.preset_id || payload.presetId || null;
    archetypeId = payload.archetype_id || payload.archetypeId || archetypeId || null;
  }
  const presetSelect = document.getElementById('capabilityPresetSelect');
  const archetypeSelect = document.getElementById('capabilityArchetypeSelect');
  if (presetSelect && presetId && [...presetSelect.options].some(option => option.value === presetId)) presetSelect.value = presetId;
  if (archetypeSelect && archetypeId && [...archetypeSelect.options].some(option => option.value === archetypeId)) archetypeSelect.value = archetypeId;
  capabilityState.assembly.presetId = presetId || capabilityState.assembly.presetId || null;
  capabilityState.assembly.archetypeId = archetypeId || capabilityState.assembly.archetypeId || null;
  notifyPuzzleAssembly();
}

function puzzleReplaceMethod(index, methodId) {
  if (index && typeof index === 'object') {
    const payload = index;
    methodId = payload.method_id || payload.methodId || methodId;
    const nodeId = payload.node_id || payload.nodeId;
    index = nodeId ? capabilityState.assembly.nodes.findIndex(item => item.node_id === nodeId) : payload.index;
  }
  const node = capabilityState.assembly.nodes?.[Number(index)];
  const method = capabilityMethod(methodId);
  if (!node || !method) return false;
  node.method_id = method.id;
  // Keep the workflow-block label stable.  The selected method is a replaceable
  // hypothesis inside the block, not a semantic rename of the deliverable.
  node.label = node.label || capabilityBlock(node.block_id)?.title || node.block_id;
  node.config = { ...(node.config || {}), selected_method: method.id };
  invalidatePuzzleAssembly();
  // Return the canonical projection, not a bare acknowledgement.  The
  // puzzle layer can then reconcile server-assigned ids without guessing
  // whether a legacy adapter actually applied the edit.
  return capabilityState.assembly;
}

function puzzleMoveNode(index, delta) {
  if (index && typeof index === 'object') {
    const payload = index;
    const nodeId = payload.node_id || payload.nodeId;
    index = nodeId ? capabilityState.assembly.nodes.findIndex(item => item.node_id === nodeId) : payload.from_index ?? payload.index;
    delta = Number(payload.delta ?? (Number(payload.to_index) - Number(index)));
  }
  const nodes = capabilityState.assembly.nodes || [];
  const from = Number(index);
  const to = from + Number(delta);
  if (!Number.isInteger(from) || !Number.isInteger(to) || from < 0 || to < 0 || from >= nodes.length || to >= nodes.length) return false;
  [nodes[from], nodes[to]] = [nodes[to], nodes[from]];
  // Node IDs intentionally stay stable; only the proposed topological order
  // changes, which keeps event/audit references meaningful across edits.
  invalidatePuzzleAssembly();
  return capabilityState.assembly;
}

function puzzleInsertBlock(index, blockId) {
  if (index && typeof index === 'object') {
    const payload = index;
    blockId = payload.block_id || payload.blockId || blockId;
    index = payload.index;
  }
  const block = capabilityBlock(blockId);
  if (!block) return false;
  const nodes = capabilityState.assembly.nodes || [];
  const requestedIndex = Number(index);
  const safeIndex = Number.isFinite(requestedIndex) ? Math.max(0, Math.min(requestedIndex, nodes.length)) : nodes.length;
  const node = makeAssemblyNode(block.id, safeIndex, null);
  const used = new Set(nodes.map(item => item.node_id));
  let suffix = safeIndex + 1;
  let candidate = node.node_id;
  while (used.has(candidate)) candidate = `${block.id.replace(/[^A-Za-z0-9]+/g, '-')}-${suffix += 1}`;
  node.node_id = candidate;
  nodes.splice(safeIndex, 0, node);
  invalidatePuzzleAssembly();
  return capabilityState.assembly;
}

function puzzleRestoreAssembly(draft) {
  if (draft && draft.assembly && typeof draft.assembly === 'object') draft = draft.assembly;
  if (!draft || !Array.isArray(draft.nodes)) return false;
  // Restoration is an explicit reconciliation boundary.  Never turn an
  // outdated draft into a shorter canonical graph by silently dropping
  // unknown blocks or methods; the puzzle layer will surface a repair path.
  const sourceNodes = draft.nodes;
  const invalidBlock = sourceNodes.some(item => !item || !capabilityBlock(item.block_id));
  const invalidMethod = sourceNodes.some(item => item?.method_id && !capabilityMethod(item.method_id));
  if (invalidBlock || invalidMethod) return false;
  const nodes = sourceNodes.map((item, index) => ({
    node_id: String(item.node_id || `${String(item.block_id).replace(/[^A-Za-z0-9]+/g, '-')}-${index + 1}`),
    block_id: String(item.block_id),
    method_id: item.method_id && capabilityMethod(item.method_id) ? String(item.method_id) : null,
    label: String(item.label || capabilityBlock(item.block_id)?.title || item.block_id),
    config: { ...(item.config || {}) },
  }));
  capabilityState.assembly = {
    nodes,
    edges: autoLinkAssembly(nodes),
    presetId: draft.presetId || null,
    archetypeId: draft.archetypeId || null,
    validation: null,
    revision: null,
    diff: null,
    previousNodes: Array.isArray(draft.previousNodes) ? JSON.parse(JSON.stringify(draft.previousNodes)) : [],
    previousEdges: Array.isArray(draft.previousEdges) ? JSON.parse(JSON.stringify(draft.previousEdges)) : [],
    committedRevision: draft.committedRevision || null,
    innovationCard: draft.innovationCard || null,
    previousInnovationCard: draft.previousInnovationCard || null,
    contentPackIds: Array.isArray(draft.contentPackIds) ? [...draft.contentPackIds] : [],
    previousContentPackIds: Array.isArray(draft.previousContentPackIds) ? [...draft.previousContentPackIds] : [],
    contentPackEvidenceRefs: Array.isArray(draft.contentPackEvidenceRefs) ? [...draft.contentPackEvidenceRefs] : [],
    contentPackEvidenceByPack: draft.contentPackEvidenceByPack || {},
    contentPackIndexRevision: draft.contentPackIndexRevision || null,
    contentPackResolutionRevision: draft.contentPackResolutionRevision || null,
    methodBlockWarnings: [],
  };
  puzzleSetSelection(capabilityState.assembly.presetId, capabilityState.assembly.archetypeId);
  renderAssemblyCanvas();
  renderAssemblyGate();
  renderAssemblyDiff(null);
  renderInnovationSummary();
  notifyPuzzleAssembly();
  return capabilityState.assembly;
}

window.qingjiaCapabilityBridge = {
  getCatalog: () => capabilityState.catalog,
  getAssembly: () => capabilityState.assembly,
  getMode: () => capabilityState.mode,
  getRevision: () => capabilityState.revision,
  loadCatalog: loadCapabilityCatalog,
  setSelection: puzzleSetSelection,
  applyPreset: payload => {
    if (payload && typeof payload === 'object') puzzleSetSelection(payload.preset_id || payload.presetId, payload.archetype_id || payload.archetypeId);
    const options = payload && typeof payload === 'object' && Array.isArray(payload.block_ids) ? { block_ids: payload.block_ids } : {};
    const applied = buildPresetAssembly(options);
    if (!applied) return false;
    notifyPuzzleAssembly(); return applied;
  },
  addBlock: payload => { const id = payload && typeof payload === 'object' ? (payload.block_id || payload.blockId) : payload; addAssemblyItem('block', id); notifyPuzzleAssembly(); return capabilityState.assembly; },
  insertBlock: puzzleInsertBlock,
  replaceMethod: puzzleReplaceMethod,
  moveNode: puzzleMoveNode,
  removeNode: payload => { const index = payload && typeof payload === 'object' ? (payload.index ?? capabilityState.assembly.nodes.findIndex(item => item.node_id === (payload.node_id || payload.nodeId))) : payload; removeAssemblyNode(Number(index)); notifyPuzzleAssembly(); return capabilityState.assembly; },
  validate: validateAssembly,
  send: sendAssemblyToChat,
  restoreAssembly: puzzleRestoreAssembly,
  openLegacyPanel: openAssemblyPanel,
};

window.showToast = showToast; window.closeModal = closeModal;
// Expose the workspace boundary for smoke tests and future host adapters. The
// functions still enforce the same local allowlist; exporting them does not
// grant a caller access to arbitrary paths or external providers.
window.openWorkspaceBrowser = openWorkspaceBrowser;
window.loadWorkspaceCatalog = loadWorkspaceCatalog;
window.runWorkspaceSearch = runWorkspaceSearch;
window.isSafeWorkspaceRef = isSafeWorkspaceRef;
window.selectedSubproblem = 'Q2';
initDragonMotion();
renderRuntimeContext(); renderMembers(); renderTasks(); renderDecisions(); renderEvidence(); renderModelingOverview(); renderMessages(); renderPendingKbCitations(); renderWorkspaceMount(null); renderComposerAttachments(); renderLocalChannels(); bindEvents(); setActiveChannel(activeChannel, { silent: true }); initTemplateShell(); connectLiveTransport();
if (LIVE_API) loadKnowledgeSummary();
if (LIVE_API) loadCapabilityCatalog();
if (LIVE_API) loadWorkspaceCatalog();
if (LIVE_API_BLOCKED) showToast('已阻止未列入 allowlist 的实时 API；当前保持 SIMULATED 演示');
