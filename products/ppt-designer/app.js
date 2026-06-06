// ─── 状态 ─────────────────────────────────────────
let slides = [];
let selectedIndex = 0;
let currentTab = 'edit';

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
  canvasNav: $('canvasNav'),
  prevBtn: $('prevBtn'),
  nextBtn: $('nextBtn'),
  navLabel: $('navLabel'),
  infoPanel: $('infoPanel'),
  taskSection: $('taskSection'),
  topicInput: $('topicInput'),
  audienceInput: $('audienceInput'),
  pageCountInput: $('pageCountInput'),
  styleInput: $('styleInput'),
  notesSection: $('notesSection'),
  notesSectionLabel: $('notesSectionLabel'),
  notesEditor: $('notesEditor'),
  copyNotesBtn: $('copyNotesBtn'),
  outlineSection: $('outlineSection'),
  outlineList: $('outlineList'),
  exportBtn: $('exportBtn'),
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
  els.slideFrame.innerHTML = renderSlideHTML(slides[selectedIndex], selectedIndex);
  els.navLabel.textContent = `${selectedIndex + 1} / ${slides.length}`;
  els.prevBtn.disabled = selectedIndex === 0;
  els.nextBtn.disabled = selectedIndex === slides.length - 1;

  // 左侧列表
  els.slidesList.innerHTML = slides.map((sl, i) => `
    <li>
      <button class="slide-thumb ${i === selectedIndex ? 'active' : ''}" data-index="${i}">
        ${renderThumbHTML(sl, i)}
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
  });
});
els.styleInput.addEventListener('change', syncStyle);

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
  showToast('请在 Chat 中输入"导出 PPTX"，我来帮你生成文件');
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

  /** 获取当前所有幻灯片数据 */
  get() {
    return { title: els.deckTitle.textContent, slides };
  },

  /** 更新单页内容 */
  updateSlide(index, data) {
    if (!slides[index]) return;
    Object.assign(slides[index], data);
    renderAll();
  }
};

// ─── 初始化 ────────────────────────────────────────
// 加载示例内容，方便演示
window.PPT.load('AI 工具在研发团队的落地实践', EXAMPLE_SLIDES);
