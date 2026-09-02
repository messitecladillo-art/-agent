/*
 * 青甲 Agent · 拼图式数学建模工作流
 *
 * This file intentionally has no framework dependency.  The host page may
 * provide the #puzzleStudio overlay and its slots; when a slot is absent the
 * module creates a minimal one so the feature remains usable in fixture mode.
 * All text coming from a catalog or a user draft is inserted with textContent
 * (never interpolated into HTML).
 */
(function workflowPuzzleModule(window, document) {
  'use strict';

  const STORAGE_KEY = 'qingjia.workflowPuzzle.v1';
  const GUIDE_IMAGE = 'assets/workflow/qinglong-puzzle-guide-v1.png';
  const ATLAS_IMAGE = 'assets/workflow/qinglong-puzzle-atlas-v1.png';
  const UPDATE_EVENTS = ['qingjia:capability-catalog', 'qingjia:assembly-updated'];
  const REQUIRED_BLOCKS = new Set(['problem-decomposition', 'baseline-model', 'validation', 'writing']);

  const FALLBACK_CATALOG = {
    catalog_version: 'capability-catalog/v1-fixture',
    capability_revision: 'fixture:puzzle-v1',
    workflow_blocks: [
      { id: 'problem-decomposition', title: '题面拆解', kind: 'problem', required: true, input_ports: { problem_contract: 'problem' }, output_ports: { subproblems: 'subproblems' } },
      { id: 'data-audit', title: '数据审计', kind: 'data', input_ports: { subproblems: 'subproblems' }, output_ports: { data_contract: 'data_contract' } },
      { id: 'parameter-contract', title: '参数与约束', kind: 'contract', input_ports: { subproblems: 'subproblems' }, output_ports: { model_contract: 'model_contract', constraints: 'constraints' } },
      { id: 'scenario-contract', title: '情景与边界', kind: 'contract', input_ports: { subproblems: 'subproblems' }, output_ports: { scenario: 'scenario', boundary_conditions: 'boundary_conditions' } },
      { id: 'baseline-model', title: '透明基线', kind: 'baseline', required: true, input_ports: { data_contract: 'data_contract' }, output_ports: { model: 'model', result: 'result' } },
      { id: 'mechanism-model', title: '机制模型', kind: 'mechanism', input_ports: { mechanism_spec: 'mechanism_spec' }, output_ports: { model: 'model', result: 'result' } },
      { id: 'optimization', title: '优化求解', kind: 'optimization', input_ports: { model: 'model', constraints: 'constraints' }, output_ports: { solution: 'result' } },
      { id: 'simulation', title: '情景仿真', kind: 'simulation', input_ports: { model: 'model', scenario: 'scenario' }, output_ports: { result: 'result' } },
      { id: 'validation', title: '题型验证', kind: 'validation', required: true, input_ports: { model: 'model', result: 'result' }, output_ports: { validation_report: 'validation_report' } },
      { id: 'sensitivity', title: '敏感性分析', kind: 'validation', input_ports: { model: 'model', result: 'result' }, output_ports: { sensitivity_report: 'sensitivity_report' } },
      { id: 'critic-challenger', title: '独立质疑', kind: 'review', input_ports: { model: 'model', result: 'result' }, output_ports: { critique_report: 'critique_report' } },
      { id: 'writing', title: '论文写作', kind: 'writing', required: true, input_ports: { result: 'result', validation_report: 'validation_report' }, output_ports: { paper_draft: 'paper_draft' } },
      { id: 'defense', title: '答辩准备', kind: 'defense', input_ports: { paper_draft: 'paper_draft' }, output_ports: { defense_pack: 'defense_pack' } },
    ],
    methods: [
      { id: 'scope-mapping', title: '目标—小问覆盖表', family: 'problem', applicability: ['题干含多小问', '交付物可追踪'], prohibitions: ['跳过单位与评分对象'], assumptions: ['题面版本已锁定'], inputs: ['problem_contract'], outputs: ['subproblems', 'scope_table'], validation: ['小问覆盖检查', '单位核对'], fallback: ['人工范围复核'] },
      { id: 'causal-loop-map', title: '因果 / 机制关系图', family: 'problem', applicability: ['变量关系可解释', '需要机制链'], prohibitions: ['把相关性写成因果'], assumptions: ['变量定义和方向可核验'], inputs: ['problem_contract'], outputs: ['subproblems', 'causal_map'], validation: ['方向审查', '反例检查'], fallback: ['范围表 + 透明基线'] },
      { id: 'schema-leakage-audit', title: '模式—泄漏审计', family: 'data', applicability: ['表格或多源数据', '目标列可识别'], prohibitions: ['未经记录直接删样本'], assumptions: ['字段字典和时间切分可获取'], inputs: ['dataset', 'subproblems'], outputs: ['data_contract', 'leakage_report'], validation: ['键唯一性', '时间泄漏检查'], fallback: ['人工抽样审计'] },
      { id: 'missingness-audit', title: '缺失机制与稳健性审计', family: 'data', applicability: ['缺失或异常值存在', '可比较处理方案'], prohibitions: ['把缺失当随机却无证据'], assumptions: ['缺失模式可分层统计'], inputs: ['dataset'], outputs: ['data_contract', 'missingness_report'], validation: ['分层缺失率', '处理敏感性'], fallback: ['保守完整案例'] },
      { id: 'dimensional-analysis', title: '量纲—单位契约', family: 'contract', applicability: ['物理量或成本指标', '单位容易混淆'], prohibitions: ['无量纲依据强行相加'], assumptions: ['单位表和换算关系可核验'], inputs: ['subproblems', 'data_contract'], outputs: ['model_contract', 'unit_table'], validation: ['量纲平衡', '数量级检查'], fallback: ['显式保留单位并阻断'] },
      { id: 'identifiability-check', title: '可识别性与边界契约', family: 'contract', applicability: ['参数需要估计', '约束或边界不完整'], prohibitions: ['不可识别参数直接拟合'], assumptions: ['观测量与参数映射可列出'], inputs: ['subproblems', 'data_contract'], outputs: ['model_contract', 'parameter_ranges'], validation: ['秩 / 灵敏度检查', '边界回放'], fallback: ['固定可解释先验'] },
      { id: 'linear-regression', title: '线性 / 岭回归', family: 'statistical', applicability: ['连续响应', '可解释系数'], prohibitions: ['明显非线性且无变换'], validation: ['留出集', '残差诊断'] },
      { id: 'random-forest', title: '随机森林', family: 'ensemble', applicability: ['非线性表格数据', '混合特征'], prohibitions: ['把特征重要性当因果'], validation: ['留出集', '置换检验'] },
      { id: 'gradient-boosting', title: '梯度提升树', family: 'ensemble', applicability: ['非线性预测', '中小型表格'], prohibitions: ['外推到训练域外'], validation: ['交叉验证', '留出集'] },
      { id: 'linear-programming', title: '线性规划', family: 'optimization', applicability: ['线性目标与约束', '资源分配'], prohibitions: ['无误差界的线性化'], validation: ['可行性', '最优性间隙'] },
      { id: 'integer-programming', title: '整数 / 混合整数规划', family: 'optimization', applicability: ['离散决策', '排程与指派'], prohibitions: ['规模超界仍声称最优'], validation: ['可行性', '最优性间隙'] },
      { id: 'nsga2-multiobjective', title: 'NSGA-II 多目标', family: 'optimization', applicability: ['冲突目标', 'Pareto 前沿'], prohibitions: ['只报一个无解释权重解'], validation: ['可行性', '敏感性'] },
      { id: 'finite-difference-pde', title: '有限差分 PDE', family: 'mechanism', applicability: ['扩散 / 传热 / 输运', '网格可定义'], prohibitions: ['边界初值不明或不守恒'], validation: ['守恒', '网格收敛'] },
      { id: 'runge-kutta-ode', title: 'Runge–Kutta ODE', family: 'mechanism', applicability: ['状态随时间演化', '右端可计算'], prohibitions: ['刚性系统无步长策略'], validation: ['步长收敛', '不变量检查'] },
      { id: 'monte-carlo', title: '蒙特卡洛模拟', family: 'simulation', applicability: ['不确定性传播', '随机场景'], prohibitions: ['重复次数不足却报稳定概率'], validation: ['重复种子', '置信区间'] },
      { id: 'discrete-event-simulation', title: '离散事件仿真', family: 'simulation', applicability: ['排队 / 流程 / 资源竞争', '事件规则明确'], prohibitions: ['把单次轨迹当结论'], validation: ['暖机敏感性', '重复种子'] },
      { id: 'lhs-sensitivity', title: '拉丁超立方敏感性', family: 'validation', applicability: ['参数扰动筛查', '模型可重复运行'], prohibitions: ['参数范围无依据'], validation: ['范围扰动', '重复种子'] },
      { id: 'bootstrap-uncertainty', title: 'Bootstrap 不确定性', family: 'validation', applicability: ['有限样本估计不确定性'], prohibitions: ['时间依赖数据直接独立重采样'], validation: ['重采样重复', '稳定性'] },
      { id: 'counterexample-review', title: '反例压力测试', family: 'review', applicability: ['假设边界可构造', '需要独立质疑'], prohibitions: ['没有对照却下结论'], validation: ['反例清单', '边界回归'] },
      { id: 'assumption-stress-review', title: '假设压力测试', family: 'review', applicability: ['关键假设可扰动', '需要独立复核'], prohibitions: ['只挑有利情景'], assumptions: ['扰动范围有来源'], inputs: ['model', 'result', 'validation_report'], outputs: ['critique_report'], validation: ['最坏情景', '替代假设'], fallback: ['保守结论 + 禁用条件'] },
      { id: 'claim-evidence-map', title: '主张—证据映射', family: 'writing', applicability: ['论文 claim 可追溯'], prohibitions: ['把候选资料当事实'], validation: ['引用覆盖', '人工核验'] },
      { id: 'derivation-narrative', title: '公式推导叙事', family: 'writing', applicability: ['需要展示数学语言和逻辑链'], prohibitions: ['跳步或隐藏定义'], assumptions: ['符号表和前置条件已锁定'], inputs: ['result', 'validation_report', 'critique_report'], outputs: ['paper_draft', 'derivation_map'], validation: ['符号一致性', '逐式回代'], fallback: ['先写透明基线推导'] },
      { id: 'defense-qa-matrix', title: '答辩问题矩阵', family: 'defense', applicability: ['需要解释假设、参数和结果'], prohibitions: ['用未验证数字应答'], assumptions: ['论文 claim 已分级'], inputs: ['paper_draft', 'validation_report'], outputs: ['defense_pack'], validation: ['逐问证据链接', '反例追问'], fallback: ['只回答 VERIFIED 内容'] },
      { id: 'reproducible-defense-rehearsal', title: '复现演练脚本', family: 'defense', applicability: ['代码和图表可运行', '需要现场演示'], prohibitions: ['把演示快照冒充实跑'], assumptions: ['命令、种子和结果 hash 齐全'], inputs: ['paper_draft', 'validation_report'], outputs: ['defense_pack'], validation: ['clean-run', '结果 hash'], fallback: ['静态证据包 + 明示限制'] },
    ],
    workflow_presets: [
      { id: 'standard-cumcm', title: '标准国赛链', description: '从题面锁定到论文与答辩，保留透明基线、独立质疑和验证门。', block_ids: ['problem-decomposition', 'data-audit', 'parameter-contract', 'baseline-model', 'validation', 'critic-challenger', 'sensitivity', 'writing', 'defense'] },
      { id: 'data-to-paper', title: '数据驱动快线', description: '适合预测或表格决策题，先审计数据，再建立可解释基线。', block_ids: ['problem-decomposition', 'data-audit', 'parameter-contract', 'baseline-model', 'validation', 'critic-challenger', 'writing'] },
      { id: 'mechanism-simulation', title: '机制仿真线', description: '先锁定参数、边界与情景，再用机制模型和仿真回答动态问题。', block_ids: ['problem-decomposition', 'data-audit', 'parameter-contract', 'scenario-contract', 'baseline-model', 'mechanism-model', 'simulation', 'validation', 'writing'] },
    ],
    problem_archetypes: [
      { id: 'prediction', title: '预测 / 统计' },
      { id: 'optimization', title: '优化 / 运筹' },
      { id: 'mechanism', title: '机制 / 物理' },
      { id: 'simulation', title: '仿真 / 随机过程' },
      { id: 'policy-decision', title: '政策 / 决策' },
    ],
  };

  const state = {
    catalog: null,
    catalogRevision: null,
    mode: 'preset',
    selectedPresetId: null,
    selectedArchetypeId: '',
    selectedNodeId: null,
    showAllMethods: false,
    assembly: { nodes: [], edges: [], presetId: null, archetypeId: null },
    draft: null,
    stale: false,
    lastValidation: null,
    mounted: false,
    listenersBound: false,
    pollTimer: null,
    pollStartedAt: 0,
    loadingCatalog: false,
    catalogUnavailable: false,
    localAssemblyDirty: false,
    hydratingHost: false,
    mutationInFlight: 0,
  };

  const root = () => document.getElementById('puzzleStudio');
  const q = id => document.getElementById(id);
  const text = value => value == null ? '' : String(value);
  const safeText = value => text(value).slice(0, 4000);

  function node(tag, options, children) {
    const element = document.createElement(tag);
    const opts = options || {};
    Object.entries(opts).forEach(([key, value]) => {
      if (value == null || value === false) return;
      if (key === 'className') element.className = value;
      else if (key === 'text') element.textContent = safeText(value);
      else if (key === 'dataset') Object.entries(value).forEach(([dataKey, dataValue]) => { element.dataset[dataKey] = safeText(dataValue); });
      else if (key === 'on') Object.entries(value).forEach(([event, handler]) => element.addEventListener(event, handler));
      else if (key === 'style') Object.entries(value || {}).forEach(([styleKey, styleValue]) => {
        // CSS custom properties cannot be assigned reliably through
        // Object.assign(CSSStyleDeclaration).  setProperty keeps the atlas
        // slice and any future design tokens visible in real browsers.
        if (styleKey.startsWith('--')) element.style.setProperty(styleKey, text(styleValue));
        else element.style[styleKey] = styleValue;
      });
      else if (key in element) element[key] = value;
      else element.setAttribute(key, safeText(value));
    });
    (Array.isArray(children) ? children : [children]).flat(Infinity).forEach(child => {
      if (child == null) return;
      element.appendChild(typeof child === 'string' ? document.createTextNode(child) : child);
    });
    return element;
  }

  function normalizeCatalog(raw) {
    const source = raw && typeof raw === 'object' ? raw : FALLBACK_CATALOG;
    return {
      ...FALLBACK_CATALOG,
      ...source,
      workflow_blocks: Array.isArray(source.workflow_blocks || source.blocks) && (source.workflow_blocks || source.blocks).length ? (source.workflow_blocks || source.blocks) : FALLBACK_CATALOG.workflow_blocks,
      methods: Array.isArray(source.methods) && source.methods.length ? source.methods : FALLBACK_CATALOG.methods,
      workflow_presets: Array.isArray(source.workflow_presets || source.presets) && (source.workflow_presets || source.presets).length ? (source.workflow_presets || source.presets) : FALLBACK_CATALOG.workflow_presets,
      problem_archetypes: Array.isArray(source.problem_archetypes || source.archetypes) && (source.problem_archetypes || source.archetypes).length ? (source.problem_archetypes || source.archetypes) : FALLBACK_CATALOG.problem_archetypes,
    };
  }

  function revisionOf(catalog) {
    return text(catalog?.capability_revision || catalog?.catalog_revision || catalog?.source?.index_revision || catalog?.catalog_version || 'unknown');
  }

  function blockById(id) { return state.catalog?.workflow_blocks?.find(item => item.id === id) || null; }
  function methodById(id) { return state.catalog?.methods?.find(item => item.id === id) || null; }
  function presetById(id) { return state.catalog?.workflow_presets?.find(item => item.id === id) || null; }
  function selectedNode() { return state.assembly.nodes.find(item => item.node_id === state.selectedNodeId) || null; }

  // The generated atlas is a visual index, not a source of meaning.  Keep the
  // mapping semantic so a reordered route still shows the same visual cue.
  function pieceIndexForBlock(block) {
    const kind = text(block?.kind).toLowerCase();
    if (kind === 'problem') return 0;
    if (kind === 'data') return 1;
    if (kind === 'contract') return 2;
    if (['baseline', 'mechanism', 'optimization', 'simulation'].includes(kind)) return 3;
    if (['validation', 'review'].includes(kind)) return 4;
    if (['writing', 'defense'].includes(kind)) return 5;
    return 2;
  }

  function atlasStyle(index, extra) {
    const safeIndex = Math.max(0, Math.min(5, Number(index) || 0));
    return { ...(extra || {}), '--piece-index': safeIndex, '--piece-position': `${safeIndex * 20}%` };
  }

  function bridge() { return window.qingjiaCapabilityBridge && typeof window.qingjiaCapabilityBridge === 'object' ? window.qingjiaCapabilityBridge : null; }
  // The legacy shell always exposes a bridge, even before its live catalogue
  // has loaded.  In that interval its mutators can legitimately return an
  // empty projection; using that projection as the source of truth would
  // erase a locally assembled draft.  Keep edits deterministic in fallback
  // mode and hand them to the bridge only once a non-empty catalogue is
  // authoritative.
  const FALLBACK_LOCAL_MUTATIONS = new Set([
    'applyPreset', 'addBlock', 'insertBlock', 'replaceMethod', 'moveNode',
    'removeNode', 'restoreAssembly', 'validate', 'send',
  ]);
  const STRICT_LIVE_MUTATIONS = new Set(FALLBACK_LOCAL_MUTATIONS);
  const bridgeFailure = (operation, reason) => ({
    __puzzleBridgeFailure: true,
    operation,
    reason: safeText(reason || 'bridge did not apply'),
  });
  const isBridgeFailure = value => Boolean(value && value.__puzzleBridgeFailure === true);
  function liveRequested() {
    try {
      const params = new URLSearchParams(window.location.search || '');
      return params.has('live') || params.has('api');
    } catch (_) { return false; }
  }
  async function bridgeCall(name, payload, fallback) {
    const api = bridge();
    const mutating = FALLBACK_LOCAL_MUTATIONS.has(name);
    // A live URL without the host bridge is a broken integration, not a
    // permission to report a local demo as a successful server write.  The
    // fixture-only URL remains intentionally editable without a host.
    if (!api || typeof api[name] !== 'function') {
      return mutating && liveRequested() ? bridgeFailure(name, 'bridge_unavailable') : fallback;
    }
    // During the normal fixture→live handoff the bridge exists but its
    // catalogue is still empty.  Preserve the deterministic local preview;
    // once a live catalogue is authoritative, the bridge response is required
    // and null/false is handled below as a failed mutation.
    if (state.catalogUnavailable && mutating) return fallback;
    if (mutating) state.mutationInFlight += 1;
    try {
      const value = await api[name](payload);
      // Once a live catalogue is authoritative, a missing/false response is
      // a failed write—not permission to invent a successful local result.
      // Fixture mode is the only place where the deterministic fallback is
      // allowed to stand in for a missing bridge response.
      if (value == null || value === false) {
        return STRICT_LIVE_MUTATIONS.has(name) ? bridgeFailure(name, value === false ? 'not_applied' : 'empty_response') : fallback;
      }
      return value;
    } catch (error) {
      emit('bridge-error', { operation: name, message: text(error?.message || 'unknown') });
      return STRICT_LIVE_MUTATIONS.has(name) ? bridgeFailure(name, error?.message || 'request_failed') : fallback;
    } finally {
      if (mutating) state.mutationInFlight = Math.max(0, state.mutationInFlight - 1);
    }
  }

  function reportBridgeFailure(result, label) {
    if (!isBridgeFailure(result)) return false;
    const suffix = result.reason ? `（${result.reason}）` : '';
    emit('bridge-failed', result);
    if (typeof window.showToast === 'function') window.showToast(`${label || '操作'}未同步，请检查连接后重试${suffix}`);
    return true;
  }

  function emit(type, detail) { window.dispatchEvent(new CustomEvent(`qingjia:puzzle-${type}`, { detail })); }

  function loadLocalDraft() {
    try {
      const parsed = JSON.parse(window.localStorage.getItem(STORAGE_KEY) || 'null');
      if (parsed && typeof parsed === 'object') state.draft = parsed;
    } catch (_) { state.draft = null; }
  }

  function persistDraft() {
    const payload = { schema: 'workflow-puzzle/v1', catalogRevision: state.catalogRevision, mode: state.mode, selectedPresetId: state.selectedPresetId, selectedArchetypeId: state.selectedArchetypeId, assembly: state.assembly, savedAt: new Date().toISOString() };
    state.draft = payload;
    try { window.localStorage.setItem(STORAGE_KEY, JSON.stringify(payload)); } catch (_) { /* storage is optional */ }
    const restore = q('puzzleRestoreDraft');
    if (restore) restore.disabled = false;
  }

  function makeNodes(blockIds, presetId, archetypeId) {
    return blockIds.map((blockId, index) => {
      const block = blockById(blockId) || { id: blockId, title: blockId, kind: 'custom' };
      return { node_id: `${blockId}-${index + 1}`, block_id: blockId, method_id: null, label: block.title, config: {} };
    });
  }

  function fallbackAssemblyFromPreset(preset) {
    const nodes = makeNodes(preset?.block_ids || [], preset?.id || null, state.selectedArchetypeId || null);
    return { nodes, edges: [], presetId: preset?.id || null, archetypeId: state.selectedArchetypeId || null };
  }

  function normalizeAssembly(raw) {
    const source = raw?.assembly && typeof raw.assembly === 'object' ? raw.assembly : raw;
    if (!source || typeof source !== 'object') return state.assembly;
    const nodes = Array.isArray(source.nodes) ? source.nodes.map((item, index) => ({ node_id: text(item.node_id || item.id || `${item.block_id || 'block'}-${index + 1}`), block_id: text(item.block_id || item.blockId || ''), method_id: item.method_id || item.methodId || null, label: text(item.label || blockById(item.block_id)?.title || item.block_id || '未命名块'), config: item.config && typeof item.config === 'object' ? item.config : {} })).filter(item => item.block_id) : [];
    return { ...state.assembly, ...source, nodes, edges: Array.isArray(source.edges) ? source.edges : [], presetId: source.presetId || source.preset_id || null, archetypeId: source.archetypeId || source.archetype_id || null };
  }

  function ensureSlots() {
    const host = root();
    if (!host) return null;
    const slots = ['puzzleModePreset', 'puzzleModeDiy', 'puzzlePresetView', 'puzzleDiyView', 'puzzlePresetCards', 'puzzlePresetPreview', 'puzzleArchetypeSelect', 'puzzleApplyPreset', 'puzzleBlockPalette', 'puzzleRail', 'puzzleMethodDrawer', 'puzzleGate', 'puzzleStaleNotice', 'puzzleRestoreDraft', 'puzzleRefreshCatalog'];
    const find = id => q(id);
    const make = (id, tag, className) => {
      if (find(id)) return find(id);
      const el = node(tag, { id, className });
      host.appendChild(el);
      return el;
    };
    make('puzzlePresetView', 'section', 'puzzle-view');
    make('puzzleDiyView', 'section', 'puzzle-view');
    make('puzzlePresetCards', 'div', 'puzzle-preset-cards');
    make('puzzlePresetPreview', 'div', 'puzzle-preset-preview');
    make('puzzleArchetypeSelect', 'select', 'puzzle-archetype-select');
    make('puzzleApplyPreset', 'button', 'puzzle-apply-button');
    make('puzzleBlockPalette', 'div', 'puzzle-block-palette');
    make('puzzleRail', 'div', 'puzzle-rail');
    make('puzzleMethodDrawer', 'div', 'puzzle-method-drawer');
    make('puzzleGate', 'div', 'puzzle-gate');
    make('puzzleStaleNotice', 'div', 'puzzle-stale-notice');
    make('puzzleRestoreDraft', 'button', 'puzzle-restore-draft');
    make('puzzleRefreshCatalog', 'button', 'puzzle-refresh-catalog');
    return host;
  }

  function setMode(mode) {
    state.mode = mode === 'diy' ? 'diy' : 'preset';
    const presetButton = q('puzzleModePreset');
    const diyButton = q('puzzleModeDiy');
    [presetButton, diyButton].forEach(item => { if (item) { item.setAttribute('role', 'tab'); item.setAttribute('aria-selected', String(item === (state.mode === 'diy' ? diyButton : presetButton))); item.classList.toggle('active', item === (state.mode === 'diy' ? diyButton : presetButton)); } });
    const presetView = q('puzzlePresetView');
    const diyView = q('puzzleDiyView');
    if (presetView) presetView.hidden = state.mode !== 'preset';
    if (diyView) diyView.hidden = state.mode !== 'diy';
    renderAll();
  }

  function renderArchetypes() {
    const select = q('puzzleArchetypeSelect');
    if (!select) return;
    const previous = state.selectedArchetypeId;
    select.replaceChildren();
    select.appendChild(node('option', { value: '', text: '自动识别题型' }));
    (state.catalog?.problem_archetypes || []).forEach(item => select.appendChild(node('option', { value: item.id, text: item.title })));
    select.value = previous;
    select.onchange = () => { state.selectedArchetypeId = select.value; persistDraft(); renderAll(); };
  }

  function renderPresetCards() {
    const host = q('puzzlePresetCards');
    const preview = q('puzzlePresetPreview');
    if (!host) return;
    host.replaceChildren();
    const presets = state.catalog?.workflow_presets || [];
    if (!state.selectedPresetId && presets[0]) state.selectedPresetId = presets[0].id;
    presets.forEach(preset => {
      const selected = preset.id === state.selectedPresetId;
      const button = node('button', { type: 'button', className: `puzzle-preset-card${selected ? ' selected' : ''}`, dataset: { presetId: preset.id }, 'aria-pressed': String(selected) });
      const index = node('span', { className: 'puzzle-card-index', text: String(presets.indexOf(preset) + 1).padStart(2, '0') });
      const previewBlock = (preset.block_ids || []).map(id => blockById(id)).find(Boolean);
      const art = node('span', { className: 'puzzle-preset-art', style: atlasStyle(pieceIndexForBlock(previewBlock)) });
      const copy = node('span', { className: 'puzzle-preset-copy' }, [node('strong', { text: preset.title }), node('small', { text: preset.description })]);
      const tags = node('span', { className: 'puzzle-preset-tags' });
      const archetypes = (preset.archetype_ids || []).map(id => state.catalog?.problem_archetypes?.find(item => item.id === id)?.title || id).slice(0, 3);
      (archetypes.length ? archetypes : ['通用题型']).forEach(label => tags.appendChild(node('span', { text: label })));
      button.append(index, art, copy, tags);
      button.addEventListener('click', () => { state.selectedPresetId = preset.id; renderAll(); });
      host.appendChild(button);
    });
    if (preview) {
      preview.replaceChildren();
      const preset = presetById(state.selectedPresetId);
      if (!preset) { preview.appendChild(node('p', { text: '暂无可选工作流，请刷新能力目录。' })); return; }
      const blocks = (preset.block_ids || []).map(id => blockById(id)).filter(Boolean);
      preview.append(node('div', { className: 'puzzle-preview-heading' }, [node('strong', { text: preset.title }), node('span', { text: `${blocks.length} 个拼图块 · 点击应用后可逐块替换` })]), node('p', { className: 'puzzle-preview-description', text: preset.description }));
      const strip = node('div', { className: 'puzzle-preview-strip' });
      blocks.forEach((block, index) => {
        const pieceIndex = pieceIndexForBlock(block);
        const piece = node('span', { className: 'puzzle-preview-piece', style: atlasStyle(pieceIndex) });
        piece.append(node('span', { className: 'puzzle-piece-art', style: atlasStyle(pieceIndex) }), node('strong', { text: block.title }), node('small', { text: block.required ? '必选硬门' : block.kind }));
        strip.appendChild(piece);
      });
      preview.appendChild(strip);
      const title = q('puzzlePresetPreviewTitle');
      const meta = q('puzzlePresetPreviewMeta');
      if (title) title.textContent = preset.title;
      if (meta) meta.textContent = `${blocks.length} 个拼图块 · ${(preset.archetype_ids || []).length || '通用'} 类题型`;
    }
  }

  function blockFamily(block) {
    const kind = text(block?.kind).toLowerCase();
    if (kind === 'optimization') return 'optimization';
    if (kind === 'mechanism') return 'mechanism';
    if (kind === 'simulation') return 'simulation';
    if (kind === 'validation') return 'validation';
    if (kind === 'review') return 'review';
    if (kind === 'writing') return 'writing';
    if (kind === 'data') return 'data';
    return kind || 'statistical';
  }

  function recommendedMethods(block) {
    const family = blockFamily(block);
    const methods = state.catalog?.methods || [];
    // Prefer the typed port contract.  This keeps newer families such as
    // evaluation, graph and metaheuristic visible in the correct puzzle slot
    // without maintaining a second hand-written family allowlist here.
    const compatible = methods.filter(method => methodMatches(method, block));
    if (compatible.length) return compatible;
    const direct = methods.filter(method => text(method.family).toLowerCase() === family);
    if (direct.length) return direct;
    const fallbackFamilies = { problem: ['statistical'], baseline: ['statistical', 'ensemble'], contract: ['validation'], defense: ['writing'] };
    const candidates = fallbackFamilies[family] || [];
    return methods.filter(method => candidates.includes(text(method.family).toLowerCase()));
  }

  function methodMatches(method, block) {
    if (!method || !block) return false;
    const family = text(method.family).toLowerCase();
    const blockKind = blockFamily(block);
    // Live catalog cards declare their typed input boundary.  Prefer that
    // contract over family-name heuristics, while retaining the heuristic for
    // older snapshots and hand-authored fixture cards.
    const typedKinds = method.compatible_block_kinds;
    if (Array.isArray(typedKinds) && typedKinds.length) {
      return typedKinds.map(item => text(item).toLowerCase()).includes(blockKind)
        || typedKinds.map(item => text(item).toLowerCase()).includes(text(block.kind).toLowerCase());
    }
    return family === blockKind || (blockKind === 'baseline' && ['statistical', 'ensemble', 'classification', 'time-series', 'survival'].includes(family)) || (blockKind === 'contract' && family === 'validation');
  }

  function renderBlockPalette() {
    const host = q('puzzleBlockPalette');
    if (!host) return;
    host.replaceChildren();
    (state.catalog?.workflow_blocks || []).forEach(block => {
      const button = node('button', { type: 'button', className: `puzzle-palette-item${block.required ? ' required' : ''}`, dataset: { blockId: block.id }, title: `${block.required ? '必选 · ' : ''}${block.title}` });
      const art = node('span', { className: 'puzzle-palette-glyph puzzle-mini-art', style: atlasStyle(pieceIndexForBlock(block), { backgroundImage: `url("${ATLAS_IMAGE}")` }), 'aria-hidden': 'true' });
      button.classList.add('puzzle-block-button');
      button.append(art, node('span', { className: 'puzzle-palette-copy' }, [node('strong', { text: block.title }), node('small', { text: `${block.kind}${block.evidence_output ? ' · 有证据输出' : ''}` })]), node('em', { text: block.required ? '必选' : '插入' }));
      button.addEventListener('click', () => addBlock(block.id));
      host.appendChild(button);
    });
  }

  function renderRail() {
    const host = q('puzzleRail');
    if (!host) return;
    host.replaceChildren();
    if (!state.assembly.nodes.length) {
      host.append(node('div', { className: 'puzzle-rail-empty' }, [node('img', { src: GUIDE_IMAGE, alt: '小青龙拼装提示', className: 'puzzle-guide-image' }), node('strong', { text: '还没有拼图块' }), node('span', { text: '从左侧添加一个步骤，或先应用固定方案。' })]));
      return;
    }
    state.assembly.nodes.forEach((item, index) => {
      const block = blockById(item.block_id) || { title: item.label || item.block_id, kind: 'custom' };
      const method = methodById(item.method_id);
      const required = Boolean(block.required);
      const validationError = Boolean(state.lastValidation?.errors?.some(error => text(error).includes(item.node_id)));
      const mismatch = Boolean(method && !methodMatches(method, block));
      const blocked = validationError || mismatch;
      const pending = !method && !blocked;
      const piece = node('div', { className: `puzzle-rail-piece${item.node_id === state.selectedNodeId ? ' selected' : ''}${required ? ' required' : ''}${blocked ? ' blocked' : ''}${pending ? ' pending' : ''}`, dataset: { nodeId: item.node_id }, role: 'button', tabIndex: 0, 'aria-current': item.node_id === state.selectedNodeId ? 'step' : 'false', 'aria-label': `${index + 1}. ${block.title}${method ? `，${method.title}` : ''}` });
      const pieceArt = node('span', { className: 'puzzle-rail-piece-art puzzle-piece-art', style: atlasStyle(pieceIndexForBlock(block), { backgroundImage: `url("${ATLAS_IMAGE}")` }), 'aria-hidden': 'true' });
      piece.append(node('span', { className: 'puzzle-rail-piece-index puzzle-piece-number', text: String(index + 1).padStart(2, '0') }), pieceArt, node('strong', { text: block.title }), node('small', { text: method ? method.title : required ? '必选 · 选择方法卡' : '选择方法卡' }));
      const status = node('span', { className: 'puzzle-rail-piece-status puzzle-piece-status' });
      status.append(node('i', { 'aria-hidden': 'true' }), node('span', { text: blocked ? (mismatch ? '接口不匹配' : '链路待修复') : method ? '已选方法' : required ? '必选 · 待选方法' : '待选方法' }));
      piece.appendChild(status);
      const controls = node('span', { className: 'puzzle-rail-piece-actions puzzle-piece-controls', 'aria-label': '拼图块操作' });
      controls.append(node('button', { type: 'button', className: 'puzzle-piece-control', text: '↑', title: '上移', 'aria-label': '上移', 'data-puzzle-action': 'move-up', disabled: index <= 0 }), node('button', { type: 'button', className: 'puzzle-piece-control', text: '↓', title: '下移', 'aria-label': '下移', 'data-puzzle-action': 'move-down', disabled: index >= state.assembly.nodes.length - 1 }), node('button', { type: 'button', className: 'puzzle-piece-control danger', text: '×', title: '移除', 'aria-label': '移除', 'data-puzzle-action': 'remove' }));
      piece.appendChild(controls);
      const selectPiece = () => { state.selectedNodeId = item.node_id; callSetSelection(); renderAll(); };
      piece.addEventListener('click', event => { if (!event.target.closest('[data-puzzle-action]')) selectPiece(); });
      piece.addEventListener('keydown', event => { if ((event.key === 'Enter' || event.key === ' ') && !event.target.closest('button')) { event.preventDefault(); selectPiece(); } });
      host.appendChild(piece);
      const nextBlock = state.assembly.nodes[index + 1]?.block_id || 'data-audit';
      host.appendChild(node('button', { type: 'button', className: 'puzzle-insert-slot', text: '+ 插入拼图', title: '在此处插入一个拼图块', dataset: { puzzleAction: 'insert', index: index + 1, blockId: nextBlock }, style: { alignSelf: 'center', flex: '0 0 auto', margin: '0 8px 0 0', padding: '7px 8px', border: '1px dashed #b9d2c0', borderRadius: '9px', background: 'rgba(255,255,255,.5)', color: '#6f9581', fontSize: '8px', cursor: 'pointer', whiteSpace: 'nowrap' } }));
      if (index < state.assembly.nodes.length - 1) host.appendChild(node('span', { className: 'puzzle-rail-link', text: '→', 'aria-hidden': 'true' }));
    });
  }

  function renderMethodDrawer() {
    const host = q('puzzleMethodDrawer');
    if (!host) return;
    host.replaceChildren();
    const target = selectedNode();
    if (!target) { host.appendChild(node('p', { className: 'puzzle-method-empty', text: '点击上方拼图块，在这里选择方法。' })); return; }
    const block = blockById(target.block_id) || { title: target.label || target.block_id, kind: 'custom' };
    const recommended = recommendedMethods(block);
    const all = (state.catalog?.methods || []).filter(method => state.showAllMethods || methodMatches(method, block));
    const methods = state.showAllMethods ? all : recommended;
    const head = node('div', { className: 'puzzle-method-head' }, [node('div', {}, [node('span', { className: 'puzzle-kicker', text: 'METHOD SLOT' }), node('strong', { text: `${block.title} · 方法选择` })]), node('button', { type: 'button', className: 'puzzle-all-toggle', text: state.showAllMethods ? '仅看推荐' : '全部候选', 'aria-pressed': String(state.showAllMethods) })]);
    head.querySelector('button').addEventListener('click', () => { state.showAllMethods = !state.showAllMethods; renderMethodDrawer(); });
    host.appendChild(head);
    const index = state.assembly.nodes.findIndex(item => item.node_id === target.node_id);
    const actions = node('div', { className: 'puzzle-node-actions', 'aria-label': '拼图块操作' });
    actions.append(
      node('button', { type: 'button', className: 'puzzle-node-action', text: '↑ 上移', 'data-puzzle-action': 'move-up', disabled: index <= 0 }),
      node('button', { type: 'button', className: 'puzzle-node-action', text: '↓ 下移', 'data-puzzle-action': 'move-down', disabled: index < 0 || index >= state.assembly.nodes.length - 1 }),
      node('button', { type: 'button', className: 'puzzle-node-action danger', text: '移除', 'data-puzzle-action': 'remove' }),
    );
    const insertSelect = node('select', { className: 'puzzle-insert-select', 'aria-label': '选择要插入的拼图块' });
    (state.catalog?.workflow_blocks || []).forEach(item => insertSelect.appendChild(node('option', { value: item.id, text: item.title })));
    const insertButton = node('button', { type: 'button', className: 'puzzle-node-action puzzle-insert-action', text: '+ 插入拼图块' });
    insertButton.addEventListener('click', () => addBlock(insertSelect.value, index + 1));
    actions.append(insertSelect, insertButton);
    host.appendChild(actions);
    const note = node('p', { className: 'puzzle-method-note', text: state.showAllMethods ? '全部候选仍按接口匹配标记；灰色卡片不可直接替换。' : `按「${blockFamily(block)}」步骤优先展示 ${recommended.length} 张推荐卡。` });
    host.appendChild(note);
    const list = node('div', { className: 'puzzle-method-list' });
    if (!methods.length) list.appendChild(node('p', { className: 'puzzle-method-empty', text: '目录中暂时没有匹配方法，可先保留透明基线。' }));
    methods.forEach(method => {
      const compatible = methodMatches(method, block);
      const selected = target.method_id === method.id;
      const card = node('button', { type: 'button', className: `puzzle-method-card${selected ? ' selected' : ''}${compatible ? '' : ' incompatible'}`, disabled: !compatible, dataset: { methodId: method.id }, 'aria-pressed': String(selected), title: compatible ? '点击替换当前节点的方法' : `接口不匹配：${block.kind || '步骤'} 需要 ${blockFamily(block)} 方法` });
      const methodNote = compatible ? (method.applicability || ['适用条件待补']).slice(0, 2).join(' · ') : `接口不匹配：${blockFamily(block)} 步骤暂不接收 ${text(method.family) || '该'} 方法`;
      card.append(node('span', { className: 'puzzle-method-family', text: text(method.family).toUpperCase() }), node('strong', { text: method.title }), node('small', { text: methodNote }), node('em', { text: compatible ? (selected ? '当前采用' : '可替换') : '不匹配' }));
      if (compatible) card.addEventListener('click', () => replaceMethod(target.node_id, method.id));
      list.appendChild(card);
    });
    host.appendChild(list);
    const detail = methodById(target.method_id);
    if (detail) {
      const detailBox = node('div', { className: 'puzzle-method-detail' }, [
        node('strong', { text: '方法边界 · 当前候选' }),
        node('span', { text: `适用：${(detail.applicability || []).join('；') || '待核验'}` }),
        node('span', { text: `禁用：${(detail.prohibitions || []).join('；') || '待核验'}` }),
        node('span', { text: `假设：${(detail.assumptions || []).join('；') || '待补'}` }),
        node('span', { text: `验证：${(detail.validation || []).join('；') || '结构检查 + clean-run'}` }),
        node('span', { text: `回退：${(detail.fallback || []).join('；') || '透明 baseline / BLOCKED' }` }),
        node('span', { text: `绑定技能：${(detail.skill_refs || []).join('、') || '未绑定'} · ${detail.skill_binding_status || '未核验'}` }),
      ]);
      host.appendChild(detailBox);
    }
  }

  function renderGate() {
    const host = q('puzzleGate');
    if (!host) return;
    host.replaceChildren();
    const ids = new Set(state.assembly.nodes.map(item => item.block_id));
    const missing = [...REQUIRED_BLOCKS].filter(id => !ids.has(id));
    const unselected = state.assembly.nodes.filter(item => !item.method_id).length;
    const validation = state.lastValidation;
    const checked = Boolean(validation);
    // A report is authoritative only when it explicitly says valid=true.
    // Truthy-but-malformed responses (or a legacy payload that omits `valid`)
    // must stay blocked until the current graph is checked again.
    const structureValid = checked && validation.valid === true;
    // A complete-looking route is still a draft until the current graph has
    // gone through an explicit structural check.  This prevents an old green
    // state—or a merely present set of required blocks—from enabling send.
    const ready = checked && !missing.length && structureValid;
    const warning = ready && unselected > 0;
    host.className = `puzzle-gate ${ready ? (warning ? 'warn review' : 'pass ready') : 'blocked'}`;
    const title = !checked ? (missing.length ? `还缺 ${missing.length} 个必需拼图块` : '等待检查当前链路') : !ready ? (missing.length ? `还缺 ${missing.length} 个必需拼图块` : '链路需要修复') : warning ? `结构可审 · ${unselected} 个方法待选` : '可以进入独立审查';
    const detail = missing.length ? `缺少：${missing.map(id => blockById(id)?.title || id).join('、')}` : !checked ? '拼图顺序或方法刚发生变化；点击“检查链路”后才能发送。' : validation?.errors?.length ? validation.errors.slice(0, 2).join('；') : warning ? '方法卡是候选假设，不影响拼图结构；选定后仍需核对适用条件与验证。' : '结构检查通过；这不等于数值结果或论文结论已经验证。';
    host.append(node('span', { className: 'puzzle-gate-mark', text: ready ? '✓' : '!' }), node('div', {}, [node('strong', { text: title }), node('small', { text: detail })]), node('button', { type: 'button', className: 'puzzle-validate-button', text: '检查链路' }));
    const send = q('puzzleSend');
    if (send) { send.disabled = !ready; send.setAttribute('aria-disabled', String(!ready)); send.title = ready ? '提交结构审查并同步到群聊' : '先补齐必选拼图块并通过结构检查'; }
    host.querySelector('button').addEventListener('click', validateAssembly);
  }

  function renderStale() {
    const notice = q('puzzleStaleNotice');
    if (!notice) return;
    notice.replaceChildren();
    const hasDraft = Boolean(state.draft?.assembly?.nodes?.length);
    // A current draft is normal and should not leave an empty warning strip
    // in the studio.  Only stale data, or a draft waiting to be restored into
    // an otherwise empty canvas, deserves a visible notice.
    notice.hidden = !(state.stale || (hasDraft && !state.assembly.nodes.length));
    if (state.stale) {
      const restore = node('button', { type: 'button', id: 'puzzleRestoreDraft', className: 'puzzle-stale-refresh', text: '按当前目录恢复草稿' });
      notice.append(node('span', { className: 'puzzle-stale-mark', text: '!' }), node('strong', { text: '能力目录已更新' }), node('small', { text: '当前草稿沿用旧 revision；请人工选择恢复或重新应用方案，不会静默覆盖。' }), restore);
      restore.addEventListener('click', restoreDraft);
    } else if (hasDraft && !state.assembly.nodes.length) {
      const restore = node('button', { type: 'button', id: 'puzzleRestoreDraft', className: 'puzzle-stale-refresh', text: '恢复草稿' });
      notice.append(node('span', { className: 'puzzle-stale-mark', text: '↺' }), node('strong', { text: '发现本地拼图草稿' }), node('small', { text: '恢复上次的拼图顺序与方法选择。' }), restore);
      restore.addEventListener('click', restoreDraft);
    }
  }

  function renderAll() {
    const studio = root();
    if (studio) {
      studio.dataset.puzzleMode = state.mode;
      studio.dataset.puzzleNodeCount = String(state.assembly.nodes.length);
      studio.dataset.puzzleCatalog = state.catalogUnavailable ? 'fallback' : 'live';
    }
    renderArchetypes();
    renderPresetCards();
    renderBlockPalette();
    renderRail();
    renderMethodDrawer();
    renderGate();
    renderStale();
    const restore = q('puzzleRestoreDraft');
    if (restore) { restore.textContent = '恢复本地草稿'; restore.disabled = !state.draft; restore.setAttribute('aria-disabled', String(restore.disabled)); }
    const revision = q('puzzleRevision');
    if (revision) revision.textContent = `能力目录 · ${state.catalogRevision || 'fixture:puzzle-v1'}`;
    const railCount = q('puzzleRailCount');
    if (railCount) railCount.textContent = `${state.assembly.nodes.length} 块`;
  }

  async function callSetSelection() {
    await bridgeCall('setSelection', { node_id: state.selectedNodeId, mode: state.mode, preset_id: state.selectedPresetId }, null);
  }

  async function applyPreset() {
    const preset = presetById(state.selectedPresetId);
    if (!preset) return;
    const fallback = fallbackAssemblyFromPreset(preset);
    const result = await bridgeCall('applyPreset', { preset_id: preset.id, archetype_id: state.selectedArchetypeId || null, block_ids: preset.block_ids }, fallback);
    if (reportBridgeFailure(result, '固定方案')) return false;
    const candidate = result?.assembly || result;
    // A live bridge can be present while its catalogue is still empty.  Do
    // not let that transient empty projection erase the deterministic preview.
    state.assembly = normalizeAssembly(candidate?.nodes?.length ? candidate : fallback);
    markLocalMutation();
    state.selectedNodeId = state.assembly.nodes[0]?.node_id || null;
    state.mode = 'diy';
    persistDraft();
    setMode('diy');
    emit('assembly-changed', state.assembly);
    return true;
  }

  async function replaceMethod(nodeId, methodId) {
    const targetIndex = state.assembly.nodes.findIndex(item => item.node_id === nodeId);
    const target = targetIndex >= 0 ? state.assembly.nodes[targetIndex] : null;
    if (!target || !methodById(methodId)) return;
    const fallback = { ...state.assembly, nodes: state.assembly.nodes.map(item => item.node_id === nodeId ? { ...item, method_id: methodId } : item) };
    const result = await bridgeCall('replaceMethod', { node_id: nodeId, index: targetIndex, method_id: methodId, assembly: state.assembly }, fallback);
    if (reportBridgeFailure(result, '方法替换')) return false;
    const next = result?.assembly || result;
    const applied = next && Array.isArray(next.nodes)
      && ((next.nodes.some(item => item.node_id === nodeId && (item.method_id || item.methodId) === methodId))
        || (next.nodes[targetIndex] && (next.nodes[targetIndex].method_id || next.nodes[targetIndex].methodId) === methodId));
    if (!applied && !state.catalogUnavailable) {
      reportBridgeFailure(bridgeFailure('replaceMethod', 'canonical_response_did_not_apply'), '方法替换');
      return false;
    }
    state.assembly = normalizeAssembly(applied ? next : fallback);
    markLocalMutation();
    state.selectedNodeId = nodeId;
    state.lastValidation = null;
    persistDraft();
    renderAll();
    emit('assembly-changed', state.assembly);
    return true;
  }

  async function addBlock(blockId, index) {
    if (!blockById(blockId)) return;
    const beforeCount = state.assembly.nodes.length;
    const newNode = { node_id: `${blockId}-${Date.now().toString(36)}`, block_id: blockId, method_id: null, label: blockById(blockId).title, config: {} };
    const requestedIndex = Number.isInteger(index) ? index : state.assembly.nodes.length;
    const payload = { block_id: blockId, index: requestedIndex, node: newNode, assembly: state.assembly };
    const operation = Number.isInteger(index) ? 'insertBlock' : 'addBlock';
    const fallbackAssembly = { ...state.assembly, nodes: [...state.assembly.nodes] };
    const at = Math.max(0, Math.min(requestedIndex, fallbackAssembly.nodes.length));
    fallbackAssembly.nodes.splice(at, 0, newNode);
    const result = await bridgeCall(operation, payload, fallbackAssembly);
    if (reportBridgeFailure(result, '插入拼图块')) return false;
    const next = result?.assembly || result;
    const applied = next && Array.isArray(next.nodes) && (next.nodes.some(item => item.node_id === newNode.node_id) || next.nodes.length > beforeCount);
    if (!applied && !state.catalogUnavailable) {
      reportBridgeFailure(bridgeFailure(operation, 'canonical_response_did_not_apply'), '插入拼图块');
      return false;
    }
    state.assembly = normalizeAssembly(applied ? next : fallbackAssembly);
    markLocalMutation();
    // A live adapter may allocate its own node id.  Re-select the actual
    // inserted node instead of leaving the method drawer pointed at a stale
    // client-generated id.
    const sameBlockAtInsertion = state.assembly.nodes.filter(item => item.block_id === blockId);
    state.selectedNodeId = state.assembly.nodes.find(item => item.node_id === newNode.node_id)?.node_id
      || state.assembly.nodes[at]?.node_id
      || sameBlockAtInsertion[sameBlockAtInsertion.length - 1]?.node_id
      || state.assembly.nodes[0]?.node_id
      || null;
    state.mode = 'diy';
    persistDraft();
    renderAll();
    emit('assembly-changed', state.assembly);
    return true;
  }

  async function moveNode(delta) {
    const index = state.assembly.nodes.findIndex(item => item.node_id === state.selectedNodeId);
    if (index < 0) return;
    const to = Math.max(0, Math.min(state.assembly.nodes.length - 1, index + delta));
    if (to === index) return;
    const payload = { node_id: state.selectedNodeId, from_index: index, to_index: to, index, delta, assembly: state.assembly };
    const fallbackAssembly = { ...state.assembly, nodes: [...state.assembly.nodes] };
    const [moved] = fallbackAssembly.nodes.splice(index, 1); fallbackAssembly.nodes.splice(to, 0, moved);
    const result = await bridgeCall('moveNode', payload, fallbackAssembly);
    if (reportBridgeFailure(result, '移动拼图块')) return false;
    const next = result?.assembly || result;
    const applied = next && Array.isArray(next.nodes) && next.nodes.length === state.assembly.nodes.length
      && (next.nodes[to]?.node_id === state.selectedNodeId || next.nodes[to]?.block_id === fallbackAssembly.nodes[to]?.block_id);
    if (!applied && !state.catalogUnavailable) {
      reportBridgeFailure(bridgeFailure('moveNode', 'canonical_response_did_not_apply'), '移动拼图块');
      return false;
    }
    state.assembly = normalizeAssembly(applied ? next : fallbackAssembly);
    markLocalMutation();
    persistDraft();
    renderAll();
    emit('assembly-changed', state.assembly);
    return true;
  }

  async function removeNode() {
    const index = state.assembly.nodes.findIndex(item => item.node_id === state.selectedNodeId);
    if (index < 0) return;
    const nodeId = state.selectedNodeId;
    const fallbackAssembly = { ...state.assembly, nodes: state.assembly.nodes.filter(item => item.node_id !== nodeId) };
    const result = await bridgeCall('removeNode', { node_id: nodeId, index, block_id: state.assembly.nodes[index]?.block_id, assembly: state.assembly }, fallbackAssembly);
    if (reportBridgeFailure(result, '移除拼图块')) return false;
    const next = result?.assembly || result;
    // A legacy adapter can return the unchanged graph when it cannot resolve
    // a client-generated node id.  A shorter graph is the only unambiguous
    // success signal; ``node_id not found`` alone is also true for that no-op.
    const applied = next && Array.isArray(next.nodes) && next.nodes.length === fallbackAssembly.nodes.length;
    if (!applied && !state.catalogUnavailable) {
      reportBridgeFailure(bridgeFailure('removeNode', 'canonical_response_did_not_apply'), '移除拼图块');
      return false;
    }
    state.assembly = normalizeAssembly(applied ? next : fallbackAssembly);
    markLocalMutation();
    state.selectedNodeId = state.assembly.nodes[Math.max(0, index - 1)]?.node_id || state.assembly.nodes[0]?.node_id || null;
    persistDraft();
    renderAll();
    emit('assembly-changed', state.assembly);
    return true;
  }

  async function validateAssembly() {
    const fallback = localValidate();
    const result = await bridgeCall('validate', { assembly: state.assembly, catalog_revision: state.catalogRevision }, fallback);
    if (result?.superseded) {
      // A validation request started before a topology edit is no longer a
      // report about the current graph.  Drop it quietly and leave the gate
      // neutral so the next explicit check is the one that speaks for the UI.
      state.lastValidation = null;
      renderGate();
      return null;
    }
    if (reportBridgeFailure(result, '链路检查')) {
      state.lastValidation = { valid: false, errors: [`bridge:${result.reason || 'request_failed'}`], bridge_error: result.reason || 'request_failed', node_count: state.assembly.nodes.length };
      renderGate();
      persistDraft();
      return state.lastValidation;
    }
    state.lastValidation = result?.validation || result || fallback;
    renderGate();
    persistDraft();
    return state.lastValidation;
  }

  function localValidate() {
    const ids = new Set(state.assembly.nodes.map(item => item.block_id));
    const missing = [...REQUIRED_BLOCKS].filter(id => !ids.has(id));
    const unselected = state.assembly.nodes.filter(item => !item.method_id).map(item => item.node_id);
    // Selecting a method is a deliberate hypothesis, not a structural hard
    // gate.  Keep it as an explicit warning so a fixed route can be applied
    // first and refined block-by-block in DIY mode.
    return { valid: missing.length === 0, errors: missing.map(id => `required_block_missing:${id}`), missing_required_blocks: missing, unselected_nodes: unselected, warnings: unselected.length ? [`${unselected.length} 个拼图块待选择方法`] : [], node_count: state.assembly.nodes.length };
  }

  async function sendAssembly() {
    const validation = await validateAssembly();
    // Sending is a write.  Require a current, explicit positive validation;
    // null, superseded, or malformed reports must never be interpreted as a
    // successful local demo.
    if (!validation || validation.valid !== true) { emit('send-blocked', validation || { valid: false, errors: ['validation_unavailable'] }); return false; }
    const fallback = { sent: true, assembly: state.assembly, assembly_revision: `fixture:${Date.now()}` };
    const result = await bridgeCall('send', { assembly: state.assembly, catalog_revision: state.catalogRevision }, fallback);
    if (reportBridgeFailure(result, '群聊同步')) { emit('send-blocked', result); return false; }
    if (result && result.sent === false) { emit('send-blocked', result); return false; }
    emit('sent', result);
    if (result === fallback && typeof window.showToast === 'function') {
      window.showToast('拼图结构已生成；当前为本地演示模式，尚未写入群聊事实源');
    }
    return result?.sent !== false;
  }

  async function restoreDraft() {
    if (!state.draft?.assembly) return;
    const restored = await bridgeCall('restoreAssembly', { assembly: state.draft.assembly, catalog_revision: state.draft.catalogRevision }, state.draft.assembly);
    if (reportBridgeFailure(restored, '草稿恢复')) return false;
    const expectedCount = Array.isArray(state.draft.assembly.nodes) ? state.draft.assembly.nodes.length : 0;
    const candidate = restored?.assembly || restored;
    const normalizedCandidate = normalizeAssembly(candidate);
    // In live mode the canonical adapter is authoritative.  If it silently
    // filters an old/unknown block, accepting the shortened graph would erase
    // the user's draft and make the restore button look successful.  Keep the
    // local draft intact and require an explicit repair instead.
    if (!state.catalogUnavailable && (!candidate || !Array.isArray(candidate.nodes) || normalizedCandidate.nodes.length < expectedCount)) {
      const failure = bridgeFailure('restoreAssembly', 'canonical_response_incomplete');
      reportBridgeFailure(failure, '草稿恢复');
      return false;
    }
    state.assembly = !state.catalogUnavailable ? normalizedCandidate : normalizeAssembly(state.draft.assembly);
    markLocalMutation();
    state.mode = state.draft.mode === 'preset' ? 'preset' : 'diy';
    state.selectedPresetId = state.draft.selectedPresetId || state.selectedPresetId;
    state.selectedArchetypeId = state.draft.selectedArchetypeId || '';
    state.selectedNodeId = state.assembly.nodes[0]?.node_id || null;
    state.stale = false;
    persistDraft();
    renderAll();
    return true;
  }

  function cloneAssembly(assembly) {
    try { return JSON.parse(JSON.stringify(assembly)); } catch (_) { return assembly; }
  }

  function markLocalMutation() {
    // Any topology/method edit invalidates the previous review report.  A
    // stale green gate is more dangerous than a short-lived neutral one.
    state.lastValidation = null;
    if (state.catalogUnavailable) state.localAssemblyDirty = true;
  }

  function selectedHint(assembly, nodeId) {
    const nodes = assembly?.nodes || [];
    const index = nodes.findIndex(item => item.node_id === nodeId);
    if (index < 0) return { index: -1, blockId: null, ordinal: -1 };
    const blockId = nodes[index].block_id;
    return { index, blockId, ordinal: nodes.slice(0, index + 1).filter(item => item.block_id === blockId).length - 1 };
  }

  function selectedIdFromHint(assembly, previousId, hint) {
    const nodes = assembly?.nodes || [];
    if (nodes.some(item => item.node_id === previousId)) return previousId;
    const sameBlock = hint?.blockId ? nodes.filter(item => item.block_id === hint.blockId) : [];
    return sameBlock[Math.max(0, Math.min(Number(hint?.ordinal ?? 0), sameBlock.length - 1))]?.node_id
      || nodes[Number(hint?.index)]?.node_id
      || nodes[0]?.node_id
      || null;
  }

  async function hydrateHostAssembly() {
    if (!state.localAssemblyDirty || !state.assembly.nodes.length || !bridge()) return;
    const local = cloneAssembly(state.assembly);
    const previousId = state.selectedNodeId;
    const hint = selectedHint(local, previousId);
    state.hydratingHost = true;
    const result = await bridgeCall('restoreAssembly', { assembly: local, catalog_revision: state.catalogRevision }, local);
    if (reportBridgeFailure(result, '草稿同步')) {
      state.hydratingHost = false;
      renderAll();
      return false;
    }
    const candidate = result?.assembly || result;
    let hydrated = false;
    if (candidate && Array.isArray(candidate.nodes) && candidate.nodes.length >= local.nodes.length) {
      state.assembly = normalizeAssembly(candidate);
      state.selectedNodeId = selectedIdFromHint(state.assembly, previousId, hint);
      hydrated = true;
    }
    state.localAssemblyDirty = !hydrated;
    state.hydratingHost = false;
    persistDraft();
    renderAll();
    emit('assembly-changed', state.assembly);
  }

  async function adoptCatalog(raw) {
    if (!raw) return false;
    const revision = revisionOf(raw);
    const wasUnavailable = state.catalogUnavailable;
    if (state.catalogRevision && revision !== state.catalogRevision && state.assembly.nodes.length) {
      state.stale = true;
      // Validation, assembly revisions, and diffs are scoped to the catalogue
      // that produced them.  Clear every green/committable projection before
      // exposing the new catalogue to the editor.
      state.lastValidation = null;
      state.assembly.validation = null;
      state.assembly.revision = null;
      state.assembly.diff = null;
      state.assembly.methodBlockWarnings = [];
    }
    state.catalog = normalizeCatalog(raw);
    state.catalogRevision = revision;
    state.catalogUnavailable = false;
    renderAll();
    emit('catalog-updated', state.catalog);
    if (wasUnavailable) await hydrateHostAssembly();
    return true;
  }

  async function refreshCatalog(force = false) {
    if (state.loadingCatalog) return state.catalog;
    state.loadingCatalog = true;
    try {
      const result = await bridgeCall('loadCatalog', { force: Boolean(force) }, null);
      if (result) await adoptCatalog(result);
      else {
        const catalog = normalizeCatalog(FALLBACK_CATALOG);
        state.catalogUnavailable = true;
        if (state.catalogRevision && revisionOf(catalog) !== state.catalogRevision && state.assembly.nodes.length) {
          state.stale = true;
          state.lastValidation = null;
          state.assembly.validation = null;
          state.assembly.revision = null;
          state.assembly.diff = null;
          state.assembly.methodBlockWarnings = [];
        }
        state.catalog = catalog;
        state.catalogRevision = revisionOf(catalog);
        renderAll();
        emit('catalog-updated', catalog);
      }
      return state.catalog;
    } catch (error) {
      emit('bridge-error', { operation: 'loadCatalog', message: text(error?.message || 'unknown') });
      return state.catalog;
    } finally {
      state.loadingCatalog = false;
    }
  }

  async function boot() {
    if (state.mounted) return;
    if (!root()) return;
    state.mounted = true;
    loadLocalDraft();
    ensureSlots();
    // The host starts its live catalogue fetch at the end of app.js.  The
    // puzzle module is loaded immediately afterwards, so an initial get can
    // observe the intentional ``null while loading`` state.  Render the
    // deterministic fixture immediately, then promote it to the authoritative
    // catalogue in the background; the editor never has to wait on indexing.
    const fromBridge = await bridgeCall('getCatalog', {}, null);
    state.catalogUnavailable = !fromBridge;
    state.catalog = normalizeCatalog(fromBridge || FALLBACK_CATALOG);
    state.catalogRevision = revisionOf(state.catalog);
    const assembly = await bridgeCall('getAssembly', {}, null);
    const bridgeAssembly = assembly?.assembly || assembly;
    if (bridgeAssembly?.nodes?.length) state.assembly = normalizeAssembly(bridgeAssembly);
    else if (state.draft && state.draft.catalogRevision === state.catalogRevision) state.assembly = normalizeAssembly(state.draft.assembly);
    else if (state.draft && state.draft.catalogRevision && state.draft.catalogRevision !== state.catalogRevision) state.stale = true;
    state.localAssemblyDirty = Boolean(state.catalogUnavailable && state.assembly.nodes.length);
    state.selectedPresetId = state.draft?.selectedPresetId || state.catalog.workflow_presets?.[0]?.id || null;
    state.selectedArchetypeId = state.draft?.selectedArchetypeId || '';
    state.selectedNodeId = state.assembly.nodes[0]?.node_id || null;
    bindEvents();
    renderAll();
    if (!fromBridge && bridge()) {
      // A host fetch can be in flight when the bridge is first inspected.  A
      // bounded retry handles that race (and a transient 503) without keeping
      // the editor blocked or replacing a local draft.
      const retryUntil = Date.now() + 30000;
      const retry = async () => {
        if (!state.mounted || !state.catalogUnavailable || Date.now() > retryUntil) { state.pollTimer = null; return; }
        await refreshCatalog();
        if (state.catalogUnavailable) state.pollTimer = window.setTimeout(retry, 900);
        else state.pollTimer = null;
      };
      state.pollTimer = window.setTimeout(retry, 650);
    }
    if (!bridge()) beginPolling();
  }

  function beginPolling() {
    state.pollStartedAt = Date.now();
    const tick = async () => {
      if (bridge() || Date.now() - state.pollStartedAt > 8000) { state.pollTimer = null; return; }
      await refreshCatalog();
      state.pollTimer = window.setTimeout(tick, 800);
    };
    state.pollTimer = window.setTimeout(tick, 800);
  }

  function bindEvents() {
    if (state.listenersBound) return;
    state.listenersBound = true;
    q('puzzleModePreset')?.addEventListener('click', () => setMode('preset'));
    q('puzzleModeDiy')?.addEventListener('click', () => setMode('diy'));
    q('puzzleApplyPreset')?.addEventListener('click', applyPreset);
    q('puzzleRestoreDraft')?.addEventListener('click', restoreDraft);
    q('puzzleRefreshCatalog')?.addEventListener('click', () => refreshCatalog(true));
    q('puzzleValidate')?.addEventListener('click', validateAssembly);
    q('puzzleSend')?.addEventListener('click', sendAssembly);
    q('puzzleStudioClose')?.addEventListener('click', close);
    const host = root();
    host?.addEventListener('click', event => {
      const actionNode = event.target.closest('[data-puzzle-action]');
      const action = actionNode?.dataset.puzzleAction;
      const piece = event.target.closest('[data-node-id]');
      if (piece && action && action !== 'insert') state.selectedNodeId = piece.dataset.nodeId;
      if (action === 'move-up') moveNode(-1);
      if (action === 'move-down') moveNode(1);
      if (action === 'remove') removeNode();
      if (action === 'insert') addBlock(event.target.closest('[data-block-id]')?.dataset.blockId || 'problem-decomposition', Number(event.target.closest('[data-index]')?.dataset.index || state.assembly.nodes.length));
      if (action === 'send') sendAssembly();
      if (action === 'legacy') bridgeCall('openLegacyPanel', {}, null);
    });
    UPDATE_EVENTS.forEach(type => window.addEventListener(type, event => {
      const detail = event.detail || {};
      if (type === 'qingjia:capability-catalog') {
        const rawCatalog = detail.catalog || (detail.workflow_blocks || detail.methods || detail.workflow_presets ? detail : null);
        // A fixture host may deliberately dispatch {catalog: null} while its
        // legacy panel is empty.  That is not an authoritative catalogue and
        // must not disable the local fallback/stale protection.
        if (rawCatalog && (Array.isArray(rawCatalog.methods) || Array.isArray(rawCatalog.workflow_blocks) || Array.isArray(rawCatalog.workflow_presets))) {
          adoptCatalog(rawCatalog);
        } else {
          renderAll();
        }
      } else if (detail.assembly || detail.nodes) {
        const previousNodeId = state.selectedNodeId;
        const previousNodes = state.assembly.nodes || [];
        const previousIndex = previousNodes.findIndex(item => item.node_id === previousNodeId);
        const previousBlockId = previousIndex >= 0 ? previousNodes[previousIndex].block_id : null;
        const previousOrdinal = previousBlockId
          ? previousNodes.slice(0, previousIndex + 1).filter(item => item.block_id === previousBlockId).length - 1
          : -1;
        const incoming = normalizeAssembly(detail.assembly || detail);
        // In fixture mode the legacy bridge has no catalogue and therefore
        // emits an empty projection for every attempted write.  Do not let
        // that placeholder erase a valid local fallback assembly; a genuine
        // live clear is accepted once the authoritative catalogue is present.
        if (!incoming.nodes.length && state.assembly.nodes.length && (state.catalogUnavailable || state.hydratingHost || state.localAssemblyDirty)) return;
        // A live host may re-emit the same graph with canonical node IDs after
        // a legacy mutation.  Keep the user's focus on the corresponding
        // block (and occurrence when a block is repeated), rather than
        // jumping to the first card.  Also reject a shorter, ID-less snapshot
        // while a local edit is still being reconciled.
        if (previousNodeId && !incoming.nodes.some(item => item.node_id === previousNodeId)
          && previousNodes.length > incoming.nodes.length
          && (state.mutationInFlight > 0 || state.hydratingHost || state.localAssemblyDirty || previousIndex >= incoming.nodes.length)) return;
        state.assembly = incoming;
        state.lastValidation = incoming.validation || null;
        state.selectedNodeId = selectedIdFromHint(state.assembly, previousNodeId, { index: previousIndex, blockId: previousBlockId, ordinal: previousOrdinal });
        renderAll();
      }
    }));
    document.addEventListener('keydown', event => { if (event.key === 'Escape' && root() && !root().hidden) close(); });
  }

  function open() {
    const host = root();
    if (!host) return;
    host.hidden = false;
    host.setAttribute('aria-hidden', 'false');
    if ((!state.catalog || state.catalogUnavailable) && !state.loadingCatalog) refreshCatalog();
    q('puzzleStudioClose')?.focus();
  }

  function close() {
    const host = root();
    if (!host) return;
    host.hidden = true;
    host.setAttribute('aria-hidden', 'true');
  }

  window.qingjiaPuzzleStudio = { boot, open, close, refreshCatalog, applyPreset, validate: validateAssembly, getState: () => JSON.parse(JSON.stringify(state)) };
  window.openPuzzleStudio = open;
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, { once: true }); else boot();
})(window, document);
