const starterSlides = [
  {
    title: "Codex 是什么",
    intent: "用一句话建立定位：Codex 是能理解任务、读写代码、调用工具并协助交付的软件工程 AI 代理。",
    notes: "开场先把 Codex 从“聊天机器人”中区分出来：它不仅回答问题，还能在代码库里执行任务。适合强调它面向开发工作流，而不是单次问答。"
  },
  {
    title: "为什么现在需要它",
    intent: "说明研发团队面临的上下文切换、重复修改、测试回归和知识传递成本。",
    notes: "这一页从团队痛点切入：需求变更频繁、代码库复杂、文档不完整、review 压力大。Codex 的价值是把部分可描述、可验证的开发任务自动化。"
  },
  {
    title: "核心能力",
    intent: "展示理解需求、检索上下文、生成代码、运行命令、修复问题、总结结果六类能力。",
    notes: "不要只讲“会写代码”。重点讲完整闭环：理解目标，查找相关文件，提出修改，运行测试，根据错误继续迭代，最后把变更解释清楚。"
  },
  {
    title: "典型使用场景",
    intent: "覆盖 bug 修复、重构、测试补全、代码审查、文档生成和原型搭建。",
    notes: "建议用 2×3 卡片呈现场景。每个场景说明输入是什么、Codex 做什么、人类如何验收。这样听众更容易判断能否落到自己的团队。"
  },
  {
    title: "团队工作流嵌入",
    intent: "描述从聊天任务到代码修改、测试验证、PR/审查的协作路径。",
    notes: "强调 Codex 不应绕过工程流程，而应进入现有流程：任务描述、权限边界、分支管理、测试、review、合并。人类仍负责目标、风险和最终判断。"
  },
  {
    title: "收益与边界",
    intent: "平衡说明效率提升、知识沉淀与潜在风险：幻觉、权限、隐私、质量控制。",
    notes: "这一页要克制。收益包括减少重复劳动、加快探索、提升测试覆盖；边界包括不能替代架构责任、不能无审核上线、敏感代码和凭据需要治理。"
  },
  {
    title: "落地路线图",
    intent: "给出试点任务、规范提示词、建立验收标准、扩展到团队的四步方案。",
    notes: "建议把路线图拆成 30 天：第 1 周选低风险任务，第 2 周沉淀提示与检查清单，第 3 周接入 CI/PR，第 4 周复盘指标并扩展。"
  },
  {
    title: "结论：把 AI 变成工程协作者",
    intent: "收束观点：Codex 的关键不是替代开发者，而是让开发者用更高层的意图驱动交付。",
    notes: "结尾回到一句话：Codex 让团队从“逐行操作代码”逐步转向“描述目标、验证结果、管理风险”。邀请听众选择一个小任务开始试点。"
  }
];

let slides = structuredClone(starterSlides);
let selectedIndex = 0;

const els = {
  shell: document.querySelector('.app-shell'),
  topicInput: document.getElementById('topicInput'),
  audienceInput: document.getElementById('audienceInput'),
  pageCountInput: document.getElementById('pageCountInput'),
  styleInput: document.getElementById('styleInput'),
  goalInput: document.getElementById('goalInput'),
  deckTitle: document.getElementById('deckTitle'),
  audiencePreview: document.getElementById('audiencePreview'),
  pagePreview: document.getElementById('pagePreview'),
  stylePreview: document.getElementById('stylePreview'),
  outlineList: document.getElementById('outlineList'),
  slideThumbs: document.getElementById('slideThumbs'),
  selectedSlidePill: document.getElementById('selectedSlidePill'),
  selectedSlideCard: document.getElementById('selectedSlideCard'),
  notesEditor: document.getElementById('notesEditor'),
  toast: document.getElementById('toast'),
  compactButton: document.getElementById('compactButton'),
  generateButton: document.getElementById('generateButton'),
  resetButton: document.getElementById('resetButton'),
  addAssetButton: document.getElementById('addAssetButton'),
  assetList: document.getElementById('assetList'),
  polishButton: document.getElementById('polishButton'),
  splitButton: document.getElementById('splitButton')
};

function showToast(message) {
  els.toast.textContent = message;
  els.toast.classList.add('show');
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => els.toast.classList.remove('show'), 1900);
}

function syncBrief() {
  els.deckTitle.textContent = els.topicInput.value.trim() || '未命名 PPT 主题';
  els.audiencePreview.textContent = els.audienceInput.value.trim() || '待补充';
  els.pagePreview.textContent = els.pageCountInput.value;
  els.stylePreview.textContent = els.styleInput.value;
}

function renderOutline() {
  els.outlineList.innerHTML = slides.map((slide, index) => `
    <li class="outline-item">
      <span class="outline-num">${index + 1}</span>
      <div>
        <h4 contenteditable="true" data-field="title" data-index="${index}">${slide.title}</h4>
        <p contenteditable="true" data-field="intent" data-index="${index}">${slide.intent}</p>
      </div>
    </li>
  `).join('');
}

function renderThumbs() {
  els.slideThumbs.innerHTML = slides.map((slide, index) => `
    <button class="thumb ${index === selectedIndex ? 'active' : ''}" data-index="${index}">
      <small>${String(index + 1).padStart(2, '0')}</small>
      <strong>${slide.title}</strong>
      <span>${slide.intent}</span>
    </button>
  `).join('');
}

function renderSelectedSlide() {
  const slide = slides[selectedIndex];
  els.selectedSlidePill.textContent = `第 ${selectedIndex + 1} 页`;
  els.selectedSlideCard.innerHTML = `
    <small>Slide ${selectedIndex + 1}</small>
    <h4>${slide.title}</h4>
    <p>${slide.intent}</p>
  `;
  els.notesEditor.value = slide.notes;
}

function renderAll() {
  syncBrief();
  renderOutline();
  renderThumbs();
  renderSelectedSlide();
}

function regenerateOutline() {
  const topic = els.topicInput.value.trim() || 'Codex';
  const pageCount = Number.parseInt(els.pageCountInput.value, 10) || 8;
  const base = [
    [`${topic}：一句话定位`, '明确它是什么，以及它和普通 AI 聊天、IDE 插件的区别。'],
    ['问题背景', '解释团队为什么需要 AI 编程代理：复杂代码库、重复劳动和交付压力。'],
    ['能力地图', '梳理读代码、改代码、运行工具、测试修复、总结交付等核心能力。'],
    ['高价值场景', '选择最容易落地的 4–6 个场景，用输入、动作、验收来说明。'],
    ['工作流与权限', '说明如何嵌入分支、CI、PR、review 和安全边界。'],
    ['收益指标', '定义效率、质量、学习曲线、测试覆盖等可观测指标。'],
    ['风险与治理', '覆盖幻觉、误改、隐私、权限、依赖外部服务等问题。'],
    ['落地路线图', '给出试点、规范、扩展、复盘的阶段性计划。'],
    ['案例页', '用一个具体 bug 修复或测试补全任务展示前后对比。'],
    ['结论与行动', '用一句话收束，并给出下一步试点建议。']
  ];
  slides = base.slice(0, pageCount).map(([title, intent], index) => ({
    title,
    intent,
    notes: `第 ${index + 1} 页讲稿建议：围绕“${title}”展开。先给结论，再补充 1–2 个例子，最后说明听众需要记住的决策点。`
  }));
  selectedIndex = 0;
  renderAll();
  showToast('已生成一版可继续让 Chat 调整的大纲');
}

els.slideThumbs.addEventListener('click', (event) => {
  const button = event.target.closest('.thumb');
  if (!button) return;
  slides[selectedIndex].notes = els.notesEditor.value;
  selectedIndex = Number(button.dataset.index);
  renderThumbs();
  renderSelectedSlide();
});

els.outlineList.addEventListener('input', (event) => {
  const node = event.target.closest('[data-field]');
  if (!node) return;
  const index = Number(node.dataset.index);
  const field = node.dataset.field;
  slides[index][field] = node.textContent.trim();
  renderThumbs();
  if (index === selectedIndex) renderSelectedSlide();
});

els.notesEditor.addEventListener('input', () => {
  slides[selectedIndex].notes = els.notesEditor.value;
});

[els.topicInput, els.audienceInput, els.pageCountInput, els.styleInput].forEach((input) => {
  input.addEventListener('input', syncBrief);
  input.addEventListener('change', syncBrief);
});

els.generateButton.addEventListener('click', regenerateOutline);
els.compactButton.addEventListener('click', () => {
  els.shell.classList.toggle('compact');
  const isCompact = els.shell.classList.contains('compact');
  els.compactButton.textContent = isCompact ? '显示参数' : '隐藏参数';
  showToast(isCompact ? '已隐藏任务参数区' : '已显示任务参数区');
});
els.resetButton.addEventListener('click', () => {
  slides = structuredClone(starterSlides);
  selectedIndex = 0;
  els.topicInput.value = 'Codex：面向开发者的 AI 编程代理';
  els.audienceInput.value = '产品经理、研发团队、技术决策者';
  els.pageCountInput.value = '8 页';
  els.styleInput.value = '科技感 / 简洁 / 深色';
  els.goalInput.value = '让听众快速理解 Codex 是什么、适合解决什么开发问题、如何嵌入团队工作流，以及采用前需要注意的边界。';
  renderAll();
  showToast('已恢复 Codex 示例稿');
});
els.addAssetButton.addEventListener('click', () => {
  const item = document.createElement('li');
  item.contentEditable = 'true';
  item.textContent = '新增素材：点击这里改写要求或粘贴资料';
  els.assetList.appendChild(item);
  item.focus();
});
els.polishButton.addEventListener('click', () => {
  const current = els.notesEditor.value.trim();
  els.notesEditor.value = `讲稿润色版：${current}\n\n表达建议：先用一句结论开场，再补充业务价值，最后提醒这页和下一页的衔接。`;
  slides[selectedIndex].notes = els.notesEditor.value;
  showToast('已加入润色提示');
});
els.splitButton.addEventListener('click', () => {
  const slide = slides[selectedIndex];
  els.notesEditor.value = `演讲提示：\n1. 先讲结论：${slide.title}\n2. 解释重点：${slide.intent}\n3. 给一个团队落地例子。\n4. 收束到下一页：为什么这件事值得现在开始试点。`;
  slides[selectedIndex].notes = els.notesEditor.value;
  showToast('已拆成演讲提示');
});

renderAll();
