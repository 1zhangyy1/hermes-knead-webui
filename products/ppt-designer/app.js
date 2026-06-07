// ─── 状态 ─────────────────────────────────────────
let slides = [];
let selectedIndex = 0;
let currentTab = 'edit';
let workflowStage = 'brief';
let viewMode = 'html'; // 'html' | 'img'
let falKeyOk = false;

// ─── 示例数据（从 Chat 生成后替换） ────────────────
const EXAMPLE_SLIDES = [
  {
    type: 'cover',
    title: 'AI 工具在研发团队的落地实践',
    subtitle: '从试点到规模化 — Q2 成果与 Q3 计划',
    tag: '季度汇报 · 研发团队',
    notes: '开场简洁，30 秒内建立背景：这个 PPT 汇报 Q2 期间 AI 工具落地的核心进展，并提出 Q3 方向。'
  },
  {
    type: 'section',
    label: 'Part 1',
    title: 'Q2 背景与目标',
    body: '团队在 Q2 初提出一个假设：将 AI 辅助工具引入日常代码审查和测试生成流程，可在不增加人力的情况下提升交付效率 20%。',
    notes: '这一页快速过，30 秒。目的是对齐背景，让听众知道 Q2 的目标是什么。'
  },
  {
    type: 'bullets',
    title: '落地了哪些工具',
    bullets: ['Copilot：代码补全，覆盖 12 名工程师', 'Codex：Bug 修复与测试生成自动化', 'Claude：需求文档生成与 API 注释', '内部 Prompt 规范库：统一提示词模板'],
    notes: '列举工具时，重点不是工具名，而是覆盖了哪些工作流节点。'
  },
  {
    type: 'section',
    label: 'Part 2',
    title: '数据与结果',
    body: 'Q2 试点 8 周后，我们在三个关键指标上观察到可量化的变化：代码审查时间、测试覆盖率、工程师主观满意度。',
    notes: '数据页要克制——只展示 3 个核心指标，每个配一句解释，不要堆太多数字。'
  },
  {
    type: 'bullets',
    title: '核心指标',
    bullets: ['Code Review 平均时长：–28%（从 2.1h 降至 1.5h）', '单元测试覆盖率：从 61% 提升至 79%', 'AI 辅助接受率：Copilot 建议采纳率 43%', '工程师净推荐值（eNPS）：+18 分'],
    notes: '建议在演讲时先给结论，再补充背景。比如："最直接的变化是 Code Review 时间缩短了近三成。"'
  },
  {
    type: 'section',
    label: 'Part 3',
    title: '遇到的挑战',
    body: '工具落地并不顺利。我们在权限治理、提示词质量和团队习惯三个维度上遇到了阻力，需要坦诚汇报。',
    notes: '这一页要实事求是，赢得听众信任。不要把挑战轻描淡写成"小问题"。'
  },
  {
    type: 'bullets',
    title: '主要挑战与应对',
    bullets: ['代码安全审计要求 → 已对接安全团队，建立审查流程', '提示词质量参差不齐 → 沉淀 Prompt 规范库（v1.2）', '工程师接受度分化 → 建立自愿试点机制，消除强制感', '幻觉风险 → 强制保留人工验收环节'],
    notes: '每个挑战配应对措施，显示团队已经在解决，而不只是抱怨。'
  },
  {
    type: 'cover',
    title: 'Q3 计划：从试点走向标准',
    subtitle: '目标：AI 辅助工具覆盖率提升至 80% 工程师，建立可复制的引入框架',
    tag: '下一步',
    notes: '结尾用一个方向性的标题收束，配合下一页的行动计划。简短有力，不要写太多字。'
  }
];

// ─── DOM 引用 ──────────────────────────────────────
const $ = id => document.getElementById(id);
const els = {
  app: $('app'),
  deckTitle: $('deckTitle'),
  deckMeta: $('deckMeta'),
  tabEdit: $('tabEdit'),
  tabOutline: $('tabOutline'),
  tabNotes: $('tabNotes'),
  slidesPanel: $('slidesPanel'),
  slidesList: $('slidesList'),
  addSlideBtn: $('addSlideBtn'),
  emptyState: $('emptyState'),
  slideCanvas: $('slideCanvas'),
  slideFrame: $('slideFrame'),
  slideFrameImg: $('slideFrameImg'),
  slideImg: $('slideImg'),
  slideImgBadge: $('slideImgBadge'),
  canvasNav: $('canvasNav'),
  prevBtn: $('prevBtn'),
  nextBtn: $('nextBtn'),
  navLabel: $('navLabel'),
  viewModeBtn: $('viewModeBtn'),
  infoPanel: $('infoPanel'),
  taskSection: $('taskSection'),
  topicInput: $('topicInput'),
  audienceInput: $('audienceInput'),
  pageCountInput: $('pageCountInput'),
  styleInput: $('styleInput'),
  skillSection: $('skillSection'),
  workflowStagePill: $('workflowStagePill'),
  workflowSteps: $('workflowSteps'),
  deckNameInput: $('deckNameInput'),
  deckSizeInput: $('deckSizeInput'),
  qualityInput: $('qualityInput'),
  deckSpecInput: $('deckSpecInput'),
  requestSpecBtn: $('requestSpecBtn'),
  confirmSpecBtn: $('confirmSpecBtn'),
  packDeckBtn: $('packDeckBtn'),
  workflowHint: $('workflowHint'),
  notesSection: $('notesSection'),
  notesSectionLabel: $('notesSectionLabel'),
  notesEditor: $('notesEditor'),
  copyNotesBtn: $('copyNotesBtn'),
  outlineSection: $('outlineSection'),
  outlineList: $('outlineList'),
  exportBtn: $('exportBtn'),
  falStatusDot: $('falStatusDot'),
  falStatusText: $('falStatusText'),
  falConfigBtn: $('falConfigBtn'),
  toast: $('toast'),
};

// ─── Toast ─────────────────────────────────────────
let toastTimer;
function showToast(msg) {
  els.toast.textContent = msg;
  els.toast.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => els.toast.classList.remove('show'), 2000);
}

// ─── FAL KEY 状态 ──────────────────────────────────
const FAL_KEY_STORE = 'ppt-fal-key';

function getFalKey() {
  try {
    return localStorage.getItem(FAL_KEY_STORE) || '';
  } catch (_) { return ''; }
}

function setFalKey(key) {
  try { localStorage.setItem(FAL_KEY_STORE, key); } catch (_) {}
}

function updateFalStatus() {
  const key = getFalKey();
  falKeyOk = !!(key && key.length > 10);
  if (els.falStatusDot) els.falStatusDot.className = 'fal-status-dot ' + (falKeyOk ? 'ok' : '');
  if (els.falStatusText) els.falStatusText.textContent = falKeyOk ? '图片服务已配置' : '图片服务未配置';
  if (els.falConfigBtn) els.falConfigBtn.textContent = falKeyOk ? '修改' : '配置';
}

if (els.falConfigBtn) {
  els.falConfigBtn.addEventListener('click', () => {
    const cur = getFalKey();
    const val = prompt('请输入 fal.ai API Key（格式：xxxx:xxxx）：', cur || '');
    if (val === null) return;
    if (val.trim()) { setFalKey(val.trim()); showToast('FAL_KEY 已保存'); }
    else { localStorage.removeItem(FAL_KEY_STORE); showToast('FAL_KEY 已清除'); }
    updateFalStatus();
  });
}

// ─── 图片幻灯片模式 ────────────────────────────────
// slides 数组里，每个 slide 可以有 .imgPath（本地绝对路径或 /api/... URL）

function setViewMode(mode) {
  viewMode = mode;
  const isImg = mode === 'img';
  if (els.viewModeBtn) els.viewModeBtn.textContent = isImg ? '📝' : '🖼';
  if (els.viewModeBtn) els.viewModeBtn.title = isImg ? '切换为文字预览' : '切换为图片预览';
  renderCanvasFrame();
}

function renderCanvasFrame() {
  const slide = slides[selectedIndex];
  if (!slide) return;

  const hasImg = !!(slide.imgPath);
  const showImg = viewMode === 'img' && hasImg;

  if (els.slideFrame) els.slideFrame.style.display = showImg ? 'none' : 'flex';
  if (els.slideFrameImg) els.slideFrameImg.style.display = showImg ? 'flex' : 'none';

  if (showImg) {
    els.slideImg.src = slide.imgPath;
    els.slideImg.alt = `Slide ${selectedIndex + 1}`;
    if (els.slideImgBadge) els.slideImgBadge.textContent = `${selectedIndex + 1} / ${slides.length}`;
  } else {
    els.slideFrame.innerHTML = renderSlideHTML(slide, selectedIndex);
  }
}

function renderThumbMode(slide, index) {
  if (slide.imgPath) {
    return `<div class="thumb-preview thumb-img" style="background:#111">
      <img src="${slide.imgPath}" alt="Slide ${index+1}" loading="lazy">
    </div>
    <div class="thumb-label">${slide.title || `第 ${index+1} 页`}</div>`;
  }
  return renderThumbHTML(slide, index);
}

// ─── Skill 工作流 ──────────────────────────────────
const STAGE_LABELS = {
  brief: '补齐信息',
  spec: '确认方案',
  prompts: '细化画面',
  generate: '生成图片',
  pack: '导出文件'
};

const STAGE_HINTS = {
  brief: '先补齐主题、受众、页数和风格，然后让 AI 生成页面方案。',
  spec: '检查页面方案：每一页都应该有画面设计和正文内容。',
  prompts: '确认后让 AI 细化每页画面，再进入图片生成。',
  generate: 'AI 会按页面方案生成图片页；缺少图片服务密钥时会提示配置。',
  pack: '图片页完成后导出 PPTX 文件。'
};

function slugifyDeckName(value) {
  const text = String(value || '').trim().toLowerCase();
  const ascii = text
    .replace(/[^a-z0-9\u4e00-\u9fa5]+/gi, '-')
    .replace(/^-+|-+$/g, '');
  if (/^[a-z0-9][a-z0-9-]*$/i.test(ascii)) return ascii.slice(0, 48);
  return `deck-${Date.now().toString(36)}`;
}

function ensureDeckName() {
  if (els.deckNameInput.value.trim()) return els.deckNameInput.value.trim();
  const source = els.topicInput.value.trim() || els.deckTitle.textContent.trim() || 'ppt-deck';
  const name = slugifyDeckName(source);
  els.deckNameInput.value = name;
  return name;
}

function collectBrief() {
  return {
    title: els.deckTitle.textContent.trim(),
    topic: els.topicInput.value.trim(),
    audience: els.audienceInput.value.trim(),
    pageCount: els.pageCountInput.value,
    style: els.styleInput.value,
    deckName: ensureDeckName(),
    size: els.deckSizeInput.value,
    quality: els.qualityInput.value,
    deckSpec: els.deckSpecInput.value.trim(),
    slides: slides.map(slide => ({
      type: slide.type || '',
      title: slide.title || '',
      body: slide.body || '',
      bullets: Array.isArray(slide.bullets) ? slide.bullets : [],
      notes: slide.notes || ''
    }))
  };
}

function setWorkflowStage(stage, options = {}) {
  workflowStage = STAGE_LABELS[stage] ? stage : 'brief';
  if (els.workflowStagePill) els.workflowStagePill.textContent = STAGE_LABELS[workflowStage];
  if (els.workflowSteps) {
    els.workflowSteps.querySelectorAll('.workflow-step').forEach(step => {
      step.classList.toggle('active', step.dataset.stage === workflowStage);
    });
  }
  if (els.workflowHint) els.workflowHint.textContent = STAGE_HINTS[workflowStage] || STAGE_HINTS.brief;
  if (options.persist !== false) persistWorkflowState();
}

async function persistWorkflowState() {
  const state = {
    stage: workflowStage,
    brief: collectBrief()
  };
  try {
    if (window.NextAI && window.NextAI.state) {
      await window.NextAI.state.set('ppt-workflow', state, {scope: 'session'});
    } else {
      localStorage.setItem('ppt-workflow', JSON.stringify(state));
    }
  } catch (_err) {}
}

async function restoreWorkflowState() {
  try {
    let state = null;
    if (window.NextAI && window.NextAI.state) {
      state = await window.NextAI.state.get('ppt-workflow', null, {scope: 'session'});
    } else {
      state = JSON.parse(localStorage.getItem('ppt-workflow') || 'null');
    }
    const brief = state && state.brief ? state.brief : null;
    if (brief) {
      if (brief.title) els.deckTitle.textContent = brief.title;
      if (brief.topic) els.topicInput.value = brief.topic;
      if (brief.audience) els.audienceInput.value = brief.audience;
      if (brief.pageCount) els.pageCountInput.value = brief.pageCount;
      if (brief.style) els.styleInput.value = brief.style;
      if (brief.deckName) els.deckNameInput.value = brief.deckName;
      if (brief.size) els.deckSizeInput.value = brief.size;
      if (brief.quality) els.qualityInput.value = brief.quality;
      if (brief.deckSpec) els.deckSpecInput.value = brief.deckSpec;
    }
    syncStyle();
    setWorkflowStage(state && state.stage || 'brief', {persist: false});
  } catch (_err) {
    setWorkflowStage('brief', {persist: false});
  }
}

function agentInstruction(kind) {
  const brief = collectBrief();
  const skillPath = 'maxgpt_ppt_skill-main/maxgpt_ppt_skill-main/SKILL.md';
  if (kind === 'spec') {
    return [
      `请按当前 PPT 产品画布里的 brief 生成完整 deck_spec。`,
      `优先参考产品工作区里的 ${skillPath} 和 rules/workflow.md。`,
      `只做 Phase 1-2：收集输入、输出完整 deck_spec，暂时不要调用 API、不要生成图片。`,
      `deck_spec 必须包含 Style Decisions，以及每一页的 Visual design 和 Text content；不要写占位符。`,
      `主题：${brief.topic || brief.title || '未填写'}`,
      `受众：${brief.audience || 'general'}`,
      `页数：${brief.pageCount}`,
      `Deck 名称：${brief.deckName}`,
      `尺寸：${brief.size}`,
      `质量：${brief.quality}`,
      brief.deckSpec ? `已有 deck_spec 备忘：\n${brief.deckSpec}` : ''
    ].filter(Boolean).join('\n');
  }
  if (kind === 'generate') {
    return [
      `我确认当前 deck_spec，请继续按 gpt-image-2-ppt skill 生成这份 PPT。`,
      `先构建每页完整 prompt，再按 workflow 的两阶段流程生成图片：第 1 页先串行，其余页带 --slot 并发。`,
      `如果缺少图片服务密钥或依赖，请明确告诉我需要配置什么，不要假装已生成。`,
      `Deck 名称：${brief.deckName}`,
      `尺寸：${brief.size}`,
      `质量：${brief.quality}`,
      brief.deckSpec ? `确认版 deck_spec：\n${brief.deckSpec}` : '确认版 deck_spec 在上一轮对话里，请沿用。',
      ``,
      `生成完成后，请在回复末尾附上如下代码块（替换实际值），让画布自动显示图片：`,
      `\`\`\`js`,
      `window.PPT.loadImages("${brief.title || brief.deckName}", "${brief.deckName}", [`,
      `  {slot:1, imgUrl:"/api/products/ppt-designer/preview/maxgpt_ppt_skill-main/maxgpt_ppt_skill-main/outputs/${brief.deckName}/slide-01.png", title:"第1页标题"},`,
      `  // ...其余页...`,
      `]);`,
      `\`\`\``,
    ].join('\n');
  }
  return [
    `请使用 gpt-image-2-ppt skill 打包当前 deck，并告诉我 deck.pptx 和 index.html 的路径。`,
    `Deck 名称：${brief.deckName}`,
    `如果 outputs/${brief.deckName}/ 里还没有可打包的 slide-NN.png，请先说明当前缺少什么。`
  ].join('\n');
}

async function sendWorkflowToAgent(kind, button) {
  const stageByKind = {spec: 'spec', generate: 'generate', pack: 'pack'};
  setWorkflowStage(stageByKind[kind] || 'brief');
  const text = agentInstruction(kind);
  const canUseHostBridge = window.parent !== window &&
    window.NextAI &&
    window.NextAI.chat &&
    window.NextAI.chat.send;
  if (!canUseHostBridge) {
    try { await navigator.clipboard.writeText(text); } catch (_err) {}
    showToast('已复制指令，请粘贴到 Chat');
    return;
  }
  const oldText = button ? button.textContent : '';
  if (button) {
    button.disabled = true;
    button.textContent = '已发送...';
  }
  try {
    const response = await window.NextAI.chat.send({
      text,
      action: `ppt:${kind}`,
      context: {ppt: collectBrief()}
    });
    applyAgentWorkflowReply(kind, response && response.content || '');
    showToast('已发送给 Agent');
  } catch (err) {
    showToast(err && err.message ? err.message : '发送失败');
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = oldText;
    }
  }
}

function extractDeckSpec(content) {
  const text = String(content || '').trim();
  if (!text) return '';
  const styleIndex = text.search(/(^|\n)#{1,3}\s*Style Decisions\b/i);
  if (styleIndex >= 0) return text.slice(styleIndex).trim();
  if (/Style Decisions/i.test(text) && /Slide\s+\d+/i.test(text)) return text;
  if (/deck[_\s-]*spec/i.test(text)) return text;
  if (/(Visual design|Text content|Layout|HEADLINE|SLIDE\s+\d+)/i.test(text)) return text;
  if (/(视觉设计|文本内容|页面\s*\d+|幻灯片\s*\d+|版式|标题)/.test(text)) return text;
  return '';
}

async function applyAgentWorkflowReply(kind, content) {
  if (kind !== 'spec') return;
  const deckSpec = extractDeckSpec(content);
  if (!deckSpec) return;
  if (els.deckSpecInput) els.deckSpecInput.value = deckSpec;
  setWorkflowStage('spec');
  await persistWorkflowState();
  showToast('页面方案已同步到工作区');
}

// ─── 幻灯片渲染 ────────────────────────────────────
function renderSlideHTML(slide, index) {
  const num = `<span class="sf-page-num">${String(index + 1).padStart(2, '0')}</span>`;

  if (slide.type === 'cover') {
    return `<div class="sf-cover">
      ${slide.tag ? `<div class="sf-tag">${slide.tag}</div>` : ''}
      <div class="sf-h1">${slide.title}</div>
      <div class="sf-divider"></div>
      ${slide.subtitle ? `<div class="sf-sub">${slide.subtitle}</div>` : ''}
    </div>${num}`;
  }

  if (slide.type === 'section') {
    return `<div class="sf-section">
      ${slide.label ? `<div class="sf-label">${slide.label}</div>` : ''}
      <div class="sf-h2">${slide.title}</div>
      <div class="sf-divider"></div>
      ${slide.body ? `<div class="sf-body">${slide.body}</div>` : ''}
    </div>${num}`;
  }

  if (slide.type === 'bullets') {
    const items = (slide.bullets || []).map(b => `<li>${b}</li>`).join('');
    return `<div class="sf-bullets">
      <div class="sf-h2">${slide.title}</div>
      <ul>${items}</ul>
    </div>${num}`;
  }

  // 通用 fallback
  return `<div class="sf-section">
    <div class="sf-h2">${slide.title || '未命名'}</div>
    ${slide.body ? `<div class="sf-divider"></div><div class="sf-body">${slide.body}</div>` : ''}
  </div>${num}`;
}

function renderThumbHTML(slide, index) {
  const preview = `<div class="thumb-preview" style="background:var(--slide-bg)">
    <span class="thumb-num">${String(index + 1).padStart(2, '0')}</span>
    <span class="thumb-title">${slide.title}</span>
  </div>`;
  const label = `<div class="thumb-label">${slide.title}</div>`;
  return preview + label;
}

// ─── 渲染整个 UI ───────────────────────────────────
function renderAll() {
  const hasSl = slides.length > 0;

  // 空状态
  els.emptyState.style.display = hasSl ? 'none' : 'flex';
  els.slideCanvas.style.display = hasSl ? 'block' : 'none';
  els.canvasNav.style.display = hasSl ? 'flex' : 'none';

  // 顶部元信息
  els.deckMeta.textContent = hasSl ? `${slides.length} 页` : '0 页';

  if (!hasSl) {
    els.slidesList.innerHTML = '';
    return;
  }

  // 当前幻灯片画布
  renderCanvasFrame();
  els.navLabel.textContent = `${selectedIndex + 1} / ${slides.length}`;
  els.prevBtn.disabled = selectedIndex === 0;
  els.nextBtn.disabled = selectedIndex === slides.length - 1;

  // 左侧列表
  els.slidesList.innerHTML = slides.map((sl, i) => `
    <li>
      <button class="slide-thumb ${i === selectedIndex ? 'active' : ''}" data-index="${i}">
        ${renderThumbMode(sl, i)}
      </button>
    </li>
  `).join('');

  // 讲稿
  const slide = slides[selectedIndex];
  els.notesSectionLabel.textContent = `讲稿 — 第 ${selectedIndex + 1} 页`;
  els.notesEditor.value = slide.notes || '';

  // 大纲
  els.outlineList.innerHTML = slides.map((sl, i) => `
    <li class="outline-item ${i === selectedIndex ? 'active' : ''}" data-index="${i}">
      <span class="outline-num">${i + 1}</span>
      <span class="outline-title">${sl.title}</span>
    </li>
  `).join('');

  // 右栏面板切换
  updatePanelVisibility();
}

function updatePanelVisibility() {
  const hasSl = slides.length > 0;
  els.notesSection.style.display = (currentTab === 'edit' || currentTab === 'notes') && hasSl ? 'flex' : 'none';
  els.outlineSection.style.display = currentTab === 'outline' && hasSl ? 'block' : 'none';
  els.taskSection.style.display = currentTab === 'edit' ? 'block' : 'none';
}

// ─── 风格同步 ──────────────────────────────────────
function syncStyle() {
  const style = els.styleInput.value;
  els.app.dataset.style = style;
  document.querySelectorAll('.thumb-preview').forEach(el => { el.style.background = ''; });
  renderAll();
}

// ─── Tab ───────────────────────────────────────────
function setTab(tab) {
  currentTab = tab;
  [els.tabEdit, els.tabOutline, els.tabNotes].forEach(btn => btn.classList.remove('active'));
  $(`tab${tab.charAt(0).toUpperCase() + tab.slice(1)}`).classList.add('active');
  updatePanelVisibility();
}

// ─── 选页 ──────────────────────────────────────────
function selectSlide(index) {
  if (index < 0 || index >= slides.length) return;
  // 保存当前讲稿
  if (slides[selectedIndex]) slides[selectedIndex].notes = els.notesEditor.value;
  selectedIndex = index;
  renderAll();
}

// ─── 事件绑定 ──────────────────────────────────────
els.tabEdit.addEventListener('click', () => setTab('edit'));
els.tabOutline.addEventListener('click', () => setTab('outline'));
els.tabNotes.addEventListener('click', () => setTab('notes'));

els.slidesList.addEventListener('click', e => {
  const btn = e.target.closest('.slide-thumb');
  if (btn) selectSlide(Number(btn.dataset.index));
});

els.outlineList.addEventListener('click', e => {
  const item = e.target.closest('.outline-item');
  if (item) selectSlide(Number(item.dataset.index));
});

els.prevBtn.addEventListener('click', () => selectSlide(selectedIndex - 1));
els.nextBtn.addEventListener('click', () => selectSlide(selectedIndex + 1));

// 切换图片/文字预览模式
if (els.viewModeBtn) {
  els.viewModeBtn.addEventListener('click', () => {
    setViewMode(viewMode === 'img' ? 'html' : 'img');
  });
}

document.addEventListener('keydown', e => {
  if (slides.length === 0) return;
  if (e.target.matches('input, textarea, select, [contenteditable]')) return;
  if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') selectSlide(selectedIndex - 1);
  if (e.key === 'ArrowRight' || e.key === 'ArrowDown') selectSlide(selectedIndex + 1);
});

els.notesEditor.addEventListener('input', () => {
  if (slides[selectedIndex]) slides[selectedIndex].notes = els.notesEditor.value;
});

// 顶部标题点击可编辑
els.deckTitle.addEventListener('click', () => {
  const t = prompt('修改演示文稿标题：', els.deckTitle.textContent.trim());
  if (t !== null && t.trim()) els.deckTitle.textContent = t.trim();
});

// 参数变更时同步
[els.topicInput, els.audienceInput].forEach(input => {
  input.addEventListener('change', () => {
    if (els.topicInput.value.trim()) els.deckTitle.textContent = els.topicInput.value.trim();
    if (!els.deckNameInput.value.trim() && els.topicInput.value.trim()) ensureDeckName();
    persistWorkflowState();
  });
});
els.styleInput.addEventListener('change', () => {
  syncStyle();
  persistWorkflowState();
});
[els.pageCountInput, els.deckNameInput, els.deckSizeInput, els.qualityInput, els.deckSpecInput].forEach(input => {
  input.addEventListener('change', persistWorkflowState);
  input.addEventListener('input', persistWorkflowState);
});

els.requestSpecBtn.addEventListener('click', () => sendWorkflowToAgent('spec', els.requestSpecBtn));
els.confirmSpecBtn.addEventListener('click', () => sendWorkflowToAgent('generate', els.confirmSpecBtn));
els.packDeckBtn.addEventListener('click', () => sendWorkflowToAgent('pack', els.packDeckBtn));

// 新增空白页
els.addSlideBtn.addEventListener('click', () => {
  slides.splice(selectedIndex + 1, 0, {
    type: 'section',
    title: '新页面',
    body: '',
    notes: ''
  });
  selectSlide(selectedIndex + 1);
  showToast('已新增一页');
});

// 复制讲稿
els.copyNotesBtn.addEventListener('click', () => {
  const text = els.notesEditor.value.trim();
  if (!text) { showToast('讲稿为空'); return; }
  navigator.clipboard.writeText(text).then(() => showToast('讲稿已复制'));
});

// 导出（占位）
els.exportBtn.addEventListener('click', () => {
  sendWorkflowToAgent('pack', els.exportBtn);
});

// ─── 公共 API（供 Chat 调用）─────────────────────────
window.PPT = {
  /**
   * 从 Chat 设置幻灯片数据
   * @param {string} title 演示文稿标题
   * @param {Array}  slideData 幻灯片数组
   */
  load(title, slideData) {
    els.deckTitle.textContent = title || '未命名演示文稿';
    slides = slideData || [];
    selectedIndex = 0;
    renderAll();
    showToast('已更新 PPT 内容');
  },

  /**
   * 加载已生成的图片幻灯片
   * @param {string} title        演示文稿标题
   * @param {string} deckName     deck 名称（用于 outputs/ 路径）
   * @param {Array}  imageEntries [{slot, imgUrl, title?, notes?}, ...]
   *   imgUrl: 可以是 /api/products/ppt-designer/... 或绝对路径
   */
  loadImages(title, deckName, imageEntries) {
    els.deckTitle.textContent = title || deckName || '未命名演示文稿';
    if (deckName && els.deckNameInput) els.deckNameInput.value = deckName;
    slides = (imageEntries || []).map((entry, i) => ({
      type: 'cover',
      title: entry.title || `第 ${i + 1} 页`,
      notes: entry.notes || '',
      imgPath: entry.imgUrl || entry.imgPath || '',
    }));
    selectedIndex = 0;
    // 有图片时自动切到图片模式
    if (slides.some(s => s.imgPath)) setViewMode('img');
    renderAll();
    showToast(`已加载 ${slides.length} 张幻灯片`);
  },

  /** 获取当前所有幻灯片数据 */
  get() {
    return { title: els.deckTitle.textContent, slides, workflowStage, brief: collectBrief() };
  },

  /** 更新单页内容 */
  updateSlide(index, data) {
    if (!slides[index]) return;
    Object.assign(slides[index], data);
    renderAll();
  },

  /** 更新 skill 工作流状态 */
  setWorkflow(stage, patch = {}) {
    if (patch.deckSpec != null) els.deckSpecInput.value = String(patch.deckSpec);
    if (patch.deckName != null) els.deckNameInput.value = String(patch.deckName);
    if (patch.size != null) els.deckSizeInput.value = String(patch.size);
    if (patch.quality != null) els.qualityInput.value = String(patch.quality);
    setWorkflowStage(stage || workflowStage);
    persistWorkflowState();
  },

  /** 设置 FAL_KEY（Agent 生成成功后可回调通知状态）*/
  setFalKey(key) {
    if (key) { setFalKey(key); updateFalStatus(); }
  }
};

// ─── 初始化 ────────────────────────────────────────
// 加载示例内容，方便演示
window.PPT.load('AI 工具在研发团队的落地实践', EXAMPLE_SLIDES);
restoreWorkflowState();
updateFalStatus();

// 如果有已生成的测试图片，自动加载展示
(function tryLoadTestDeck() {
  const testImg = new Image();
  const testUrl = '/api/products/ppt-designer/preview/maxgpt_ppt_skill-main/maxgpt_ppt_skill-main/outputs/test-demo/slide-01.png';
  testImg.onload = function() {
    // 测试图存在 — 不自动覆盖（保留示例数据）
    // 用户可以通过 Chat 调用 PPT.loadImages() 来加载真实幻灯片
  };
  testImg.src = testUrl;
})();
