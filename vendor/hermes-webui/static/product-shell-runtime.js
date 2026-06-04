let _activeProductPreview = null;
let _lastTaskAssistantKind = 'ppt';
window._currentAiAssistantTitle = window._currentAiAssistantTitle || 'PPT 设计师';
const NEXT_AI_TASK_ASSIGNMENTS_KEY = 'next-ai-session-assistant-assignments';
const NEXT_AI_TASK_TITLES_KEY = 'next-ai-session-task-titles';
let _backendProductAssistants = [];

const AI_OBJECTS = {
  general: {
    title: '通用 AI',
    avatar: 'G',
    desc: '适合临时问题、写作、分析和文件处理。先从一条消息开始，需要时再展开产品界面。',
    placeholder: '向通用 AI 描述你想完成的事...',
    productType: 'general',
    uiMode: 'chat_only',
    suggestions: [
      ['帮我整理今天的工作计划，拆成可执行步骤。', '整理工作计划'],
      ['帮我改写这段文案，让它更清晰专业。', '润色一段文案'],
      ['帮我分析这个问题，先给我几个可能方案。', '分析一个问题']
    ]
  },
  ppt: {
    title: 'PPT 设计师',
    avatar: 'P',
    desc: '把想法、资料和要求变成清晰好看的演示文稿。先描述你要做什么，后面产品界面会按 PPT 任务展开。',
    homeDesc: '把主题、资料和要求交给我，我会先帮你理清 PPT 的方向、受众和结构。',
    placeholder: '描述你想做的 PPT，或上传资料...',
    productType: 'ppt',
    suggestions: [
      ['帮我做一个产品介绍 PPT，先确认主题、受众和大纲。', '做一份产品介绍 PPT'],
      ['我有一份文档，帮我整理成汇报 PPT 的结构。', '把文档变成汇报 PPT'],
      ['帮我优化已有 PPT 结构，先告诉我应该怎么调整。', '优化已有 PPT 结构']
    ]
  },
  create: {
    title: '新建 AI 产品',
    desc: '说一句你想要的 AI 产品。确认后会创建产品，并自动开始生成第一版界面。',
    placeholder: '例如：我想创建一个帮我做融资路演 PPT 的 AI 产品...',
    suggestions: [
      ['我想创建一个帮我做融资路演 PPT 的 AI 产品。', '新建融资路演产品'],
      ['我想创建一个帮我做行业研究报告的 AI 产品。', '新建行业研究产品'],
      ['我想创建一个帮我分析运营数据的 AI 产品。', '新建运营数据产品']
    ]
  }
};

function _syncProductPreviewMode(activeProductPreview) {
  const title = $('productModeTitle');
  if (title && !syncAssistantTaskUi()) title.textContent = activeProductPreview ? (activeProductPreview.name || '产品界面') : (window._currentAiAssistantTitle || window._currentAiProductTitle || 'PPT 设计师');
}

function _setActiveProductPreviewMenuOpen(open) {
  const menu = $('activeProductMoreMenu');
  const btn = $('activeProductMoreBtn');
  if (!menu) return;
  menu.hidden = !open;
  if (btn) btn.setAttribute('aria-expanded', open ? 'true' : 'false');
}

function toggleActiveProductPreviewMenu(event) {
  if (event && typeof event.stopPropagation === 'function') event.stopPropagation();
  const menu = $('activeProductMoreMenu');
  _setActiveProductPreviewMenuOpen(!!menu && menu.hidden);
}

window.toggleActiveProductPreviewMenu = toggleActiveProductPreviewMenu;

document.addEventListener('click', (event) => {
  const menu = $('activeProductMoreMenu');
  const menuButton = event.target && event.target.closest ? event.target.closest('.active-product-menu button') : null;
  if (menu && !menu.hidden && menuButton) {
    setTimeout(() => _setActiveProductPreviewMenuOpen(false), 0);
    return;
  }
  const more = event.target && event.target.closest ? event.target.closest('.active-product-more') : null;
  if (menu && !menu.hidden && !more) _setActiveProductPreviewMenuOpen(false);
});

document.addEventListener('keydown', (event) => {
  if (event && event.key === 'Escape') _setActiveProductPreviewMenuOpen(false);
  if (event && event.key === 'Escape') closeCurrentProductCapabilities();
});

function _assistantAssignmentsRead() {
  try {
    const raw = localStorage.getItem(NEXT_AI_TASK_ASSIGNMENTS_KEY);
    const data = raw ? JSON.parse(raw) : {};
    return data && typeof data === 'object' ? data : {};
  } catch (_err) {
    return {};
  }
}

function _assistantAssignmentsWrite(data) {
  try {
    localStorage.setItem(NEXT_AI_TASK_ASSIGNMENTS_KEY, JSON.stringify(data || {}));
  } catch (_err) {}
}

function _assistantTaskTitlesRead() {
  try {
    const raw = localStorage.getItem(NEXT_AI_TASK_TITLES_KEY);
    const parsed = raw ? JSON.parse(raw) : {};
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch (_err) {
    return {};
  }
}

function _assistantTaskTitlesWrite(data) {
  try {
    localStorage.setItem(NEXT_AI_TASK_TITLES_KEY, JSON.stringify(data || {}));
  } catch (_err) {}
}

function _customAssistantsRead() {
  return _backendProductAssistants.filter(item => item && item.kind && item.title && _customAssistantIsProductBacked(item));
}

function _customAssistantsWrite(items) {
  _backendProductAssistants = Array.isArray(items)
    ? items.filter(item => item && item.kind && item.title && _customAssistantIsProductBacked(item))
    : [];
}

function _customAssistantIsProductBacked(item) {
  return !!(item && (item.backendProduct || item.productId || item.product_id));
}

function _assistantSlug(value) {
  const base = String(value || 'assistant')
    .toLowerCase()
    .replace(/[^a-z0-9\u4e00-\u9fa5]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 32);
  return base || 'assistant';
}

function _assistantTitleKey(value) {
  return String(value || '').replace(/\s+/g, '').toLowerCase();
}

function _assistantRolePhraseFromPrompt(prompt) {
  let text = String(prompt || '').replace(/\s+/g, ' ').trim();
  if (!text) return '';
  text = text
    .replace(/[。.!！?？]+$/g, '')
    .replace(/[，,；;:：].*$/g, '')
    .replace(/^(我想要?|我希望|我需要|请|麻烦)?\s*(可以|能不能|可不可以|帮我|帮忙|帮|给我|为我|替我)?\s*/g, '')
    .replace(/^(创建一个|创建|新建一个|新建|做一个|做个|做|生成一个|生成|设计一个|设计|开发一个|开发)\s*/g, '')
    .replace(/^(一个|一款|一套|一种)\s*/g, '')
    .replace(/^(可以|能够|能|专门|主要)?\s*(帮我|帮助我|帮忙|帮|给我|为我|替我)?\s*/g, '')
    .replace(/^(用来|用于|可以用来|能够用来)\s*/g, '')
    .replace(/\s*(的)?\s*(AI\s*产品|AI产品|产品|助手|智能体|工具|应用|app)\s*$/i, '')
    .replace(/\s*(的)?\s*(页面|界面|工作台|预览区|任务区).*/g, '')
    .replace(/\s*(吧|好吗|可以吗)$/i, '')
    .trim();
  return text.slice(0, 24);
}

function _assistantNaturalTitleFromRolePhrase(phrase, sourcePrompt = '') {
  const text = String(phrase || '').trim();
  if (!text || text.length < 2) return '';
  const seed = `${text} ${sourcePrompt || ''}`;
  const directRules = [
    [/logo|Logo|标志|品牌视觉|品牌设计/, 'Logo 设计师'],
    [/旅行|旅游|行程|出游|攻略/, '旅行规划师'],
    [/简历|求职|面试/, '简历优化师'],
    [/小红书|公众号|朋友圈|短视频脚本|文案|营销内容/, '内容文案师'],
    [/播客|访谈|会议纪要|逐字稿/, '内容整理师'],
    [/论文|文献|学术/, '学术研究师'],
    [/代码|编程|开发|bug|程序/, '代码开发助手'],
    [/客服|售后|工单/, '客服处理师'],
    [/招聘|候选人|JD|岗位/, '招聘助手'],
    [/财务|报销|预算|账单/, '财务分析师']
  ];
  for (const [pattern, title] of directRules) {
    if (pattern.test(seed)) return title;
  }
  let core = text
    .replace(/^(自动|智能|AI|ai)\s*/g, '')
    .replace(/\s*(系统|平台|能力)\s*$/g, '')
    .trim();
  if (!core) return '';
  if (/(师|专家|顾问|生成器|分析师|设计师|助手)$/i.test(core)) return core.slice(0, 18);
  if (/生成|出图|绘图|画图|生图|图片|图像/.test(seed)) return `${core.replace(/(生成|制作|设计)$/g, '')}生成器`.slice(0, 18);
  if (/设计|视觉|海报|封面|装修|排版/.test(seed)) return `${core.replace(/设计$/g, '')}设计师`.slice(0, 18);
  if (/分析|数据|指标|报表|看板|复盘/.test(seed)) return `${core.replace(/分析$/g, '')}分析师`.slice(0, 18);
  if (/研究|调研|报告|竞品|行业/.test(seed)) return `${core.replace(/研究$/g, '')}研究师`.slice(0, 18);
  if (/规划|计划|路线|流程|项目/.test(seed)) return `${core.replace(/规划$/g, '')}规划师`.slice(0, 18);
  if (/写|写作|改写|润色|编辑|整理|总结/.test(seed)) return `${core.replace(/写作?$/g, '')}写作师`.slice(0, 18);
  return `${core} AI 产品`.slice(0, 22);
}

function _registerCustomAssistant(assistant) {
  if (!assistant || !assistant.kind) return;
  if (_isBuiltinAssistantKind(assistant.kind)) return;
  if (!_customAssistantIsProductBacked(assistant)) return;
  const title = assistant.title || '自定义 AI 产品';
  const starterKit = _assistantStarterKit(title, assistant.sourcePrompt || assistant.desc || '');
  const imageLike = /图片|图像|生图|绘图|文生图|画图|生成图|海报|封面|插画|头像|视觉|image/i.test(`${title} ${assistant.desc || ''} ${assistant.sourcePrompt || ''}`);
  const productType = assistant.productType || (imageLike ? 'image' : '');
  const tools = typeof _assistantNormalizeToolsets === 'function'
    ? _assistantNormalizeToolsets(assistant.tools)
    : (Array.isArray(assistant.tools) ? assistant.tools : []);
  AI_OBJECTS[assistant.kind] = {
    title,
    avatar: assistant.avatar || '',
    desc: assistant.desc || '按照你描述的职责处理任务，需要时生成自己的产品界面。',
    placeholder: assistant.placeholder || starterKit.placeholder,
    suggestions: Array.isArray(assistant.suggestions) && assistant.suggestions.length
      ? assistant.suggestions
      : starterKit.suggestions,
    custom: true,
    sourcePrompt: assistant.sourcePrompt || '',
    createdAt: assistant.createdAt || 0,
    titleSource: assistant.titleSource || '',
    productId: assistant.productId || assistant.product_id || '',
    workspacePath: assistant.workspacePath || assistant.workspace_path || '',
    previewUrl: assistant.previewUrl || assistant.preview_url || '',
    uiStatus: assistant.uiStatus || assistant.ui_status || 'empty',
    skills: Array.isArray(assistant.skills) ? assistant.skills : [],
    tools,
    backendProduct: !!assistant.backendProduct,
    productType,
    uiMode: assistant.uiMode || assistant.ui_mode || 'workspace',
    toolHints: Array.isArray(assistant.toolHints) && assistant.toolHints.length
      ? assistant.toolHints
      : tools.length
        ? tools
      : imageLike ? ['image generation', 'image editing', 'visual prompt writing'] : []
  };
}

function _customAssistantByKind(kind) {
  return _customAssistantsRead().find(item => item && item.kind === kind && _customAssistantIsProductBacked(item)) || null;
}

function _customAssistantTitleExists(title, exceptKind = '') {
  const key = _assistantTitleKey(title);
  if (!key) return false;
  if (_customAssistantsRead().some(item => item && _customAssistantIsProductBacked(item) && item.kind !== exceptKind && _assistantTitleKey(item.title) === key)) return true;
  return Object.entries(AI_OBJECTS).some(([kind, object]) => kind !== exceptKind && object && !object.custom && _assistantTitleKey(object.title) === key);
}

function _customAssistantByTitle(title) {
  const key = _assistantTitleKey(title);
  if (!key) return null;
  return _customAssistantsRead().find(item => item && _customAssistantIsProductBacked(item) && _assistantTitleKey(item.title) === key) || null;
}

function _assistantUniqueCustomTitle(title, fallback = '自定义 AI 产品') {
  const base = String(title || fallback || '自定义 AI 产品').replace(/\s+/g, ' ').trim() || '自定义 AI 产品';
  if (!_customAssistantTitleExists(base)) return base;
  const personal = `${base} 专属版`;
  if (!_customAssistantTitleExists(personal)) return personal;
  for (let index = 2; index < 100; index += 1) {
    const candidate = `${personal} ${index}`;
    if (!_customAssistantTitleExists(candidate)) return candidate;
  }
  return `${personal} ${Date.now().toString(36)}`;
}

function _assistantNeedsInitialProductUi(assistant) {
  if (!assistant || !assistant.productId) return false;
  const status = String(assistant.uiStatus || assistant.ui_status || '').toLowerCase();
  return !status || status === 'empty' || status === 'failed';
}

function _maybeStartInitialProductUiForExistingAssistant(assistant, sourcePrompt = '') {
  if (!assistant || !_assistantNeedsInitialProductUi(assistant)) return false;
  const object = assistant.kind && AI_OBJECTS[assistant.kind] ? AI_OBJECTS[assistant.kind] : assistant;
  if (!object || !object.productId || !object.workspacePath) return false;
  const prompt = String(sourcePrompt || object.sourcePrompt || object.desc || object.title || '').trim();
  setTimeout(() => {
    if (typeof _startProductInitializationTask === 'function') {
      _startProductInitializationTask(object, prompt);
    }
  }, 80);
  return true;
}

function _deleteCustomAssistantKind(kind) {
  if (!kind) return false;
  const before = _customAssistantsRead();
  const next = before.filter(item => item && item.kind !== kind);
  if (next.length === before.length) return false;
  _customAssistantsWrite(next);
  if (AI_OBJECTS[kind] && AI_OBJECTS[kind].custom) delete AI_OBJECTS[kind];

  const assignments = _assistantAssignmentsRead();
  let changed = false;
  Object.keys(assignments).forEach(sessionId => {
    if (assignments[sessionId] === kind) {
      delete assignments[sessionId];
      changed = true;
    }
  });
  if (changed) _assistantAssignmentsWrite(assignments);

  if (typeof S !== 'undefined' && S.session && S.session.next_ai_assistant_kind === kind) {
    delete S.session.next_ai_assistant_kind;
  }
  return true;
}

function _assistantShortMeta(object) {
  const title = object && object.title ? object.title : '';
  if (/图片|图像|生图|绘图|海报|插画|头像|视觉|image/i.test(title)) return '自定义图片产品';
  if (/PPT|演示|路演|幻灯/.test(title)) return '自定义 PPT 产品';
  if (/研究|调研|资料|报告/.test(title)) return '自定义研究产品';
  if (/数据|运营|指标|表格/.test(title)) return '自定义数据产品';
  return '自定义 AI 产品';
}

function _assistantBaseMeta(kind, object) {
  if (kind === 'general') return '从消息开始';
  if (object && object.custom) return _assistantShortMeta(object);
  if (kind === 'ppt') return '演示文稿任务';
  return _assistantShortMeta(object);
}

function _assistantIsChatOnlyProduct(object) {
  return !!(object && String(object.uiMode || object.ui_mode || '') === 'chat_only');
}

function _assistantListMeta(kind, object) {
  if (!kind || kind === 'create') return '';
  if (object && (object.productId || object.backendProduct)) {
    if (_assistantIsChatOnlyProduct(object)) return _assistantBaseMeta(kind, object);
    const status = String(object.uiStatus || object.ui_status || '').toLowerCase();
    if (status === 'generating') return '界面生成中';
    if (status === 'failed') return '可重新生成';
    if (status === 'ready') return '已有产品界面';
    return '待生成界面';
  }
  return _assistantBaseMeta(kind, object);
}

function syncAssistantListMeta() {
  document.querySelectorAll('.ai-object-item[data-ai-object]').forEach(btn => {
    const kind = btn.dataset.aiObject;
    if (!kind || kind === 'create') return;
    const object = AI_OBJECTS[kind] || null;
    const avatar = btn.querySelector('.ai-object-avatar');
    if (avatar) avatar.textContent = _assistantAvatarLabel(kind, object);
    const small = btn.querySelector('small');
    const meta = _assistantListMeta(kind, object);
    if (small && meta) {
      small.textContent = meta;
      small.title = meta;
    }
  });
}

function renderAssistantList() {
  const list = document.querySelector('.ai-object-list');
  if (!list) return;
  const createItem = list.querySelector('[data-ai-object="create"]');
  list.querySelectorAll('.ai-object-item.custom-assistant').forEach(item => item.remove());
  const customAssistants = _customAssistantsRead().filter(_customAssistantIsProductBacked);
  for (const assistant of customAssistants) {
    if (!AI_OBJECTS[assistant.kind]) AI_OBJECTS[assistant.kind] = assistant;
    const object = AI_OBJECTS[assistant.kind];
    const btn = document.createElement('button');
    btn.className = 'ai-object-item custom-assistant';
    btn.dataset.aiObject = assistant.kind;
    btn.type = 'button';
    btn.onclick = () => openAssistantHome(assistant.kind);
    const avatar = document.createElement('span');
    avatar.className = 'ai-object-avatar';
    avatar.textContent = _assistantAvatarLabel(assistant.kind, object);
    const copy = document.createElement('span');
    const strong = document.createElement('strong');
    strong.textContent = object.title;
    const small = document.createElement('small');
    small.textContent = _assistantListMeta(assistant.kind, object);
    small.title = small.textContent;
    copy.appendChild(strong);
    copy.appendChild(small);
    btn.appendChild(avatar);
    btn.appendChild(copy);
    if (createItem) list.insertBefore(btn, createItem);
    else list.appendChild(btn);
  }
  syncAssistantListMeta();
}

function _assistantTitleFromPrompt(prompt) {
  const text = String(prompt || '').replace(/\s+/g, ' ').trim();
  if (/头像|个人形象/.test(text) && /图片|图像|生图|画|生成|设计/.test(text)) return '头像图片生成器';
  if (/海报|封面|主视觉|KV|banner/i.test(text)) return '海报图片生成器';
  if (/插画|绘本|漫画|角色|人物设定/.test(text)) return '插画图片生成器';
  if (/图片|图像|生图|绘图|文生图|画图|生成图|视觉设计|image/i.test(text)) return '图片生成器';
  if (/融资|路演|BP|投资人/.test(text)) return '融资路演 PPT 设计师';
  if (/(销售|提案|客户|方案)/.test(text) && /PPT|幻灯|演示|汇报/.test(text)) return '销售提案 PPT 设计师';
  if (/行业.*研究|研究.*报告|行业.*报告/.test(text)) return '行业研究产品';
  if (/竞品/.test(text)) return '竞品研究产品';
  if (/运营.*数据|数据.*运营/.test(text)) return '运营数据分析师';
  if (/PPT|幻灯|演示|汇报/.test(text)) return 'PPT 设计师';
  if (/行业|竞品|研究|调研|报告/.test(text)) return '研究分析师';
  if (/数据|运营|指标|表格|看板/.test(text)) return '数据分析师';
  const roleTitle = _assistantNaturalTitleFromRolePhrase(_assistantRolePhraseFromPrompt(text), text);
  if (roleTitle) return roleTitle;
  const cleaned = text
    .replace(/[。.!！?？]+$/g, '')
    .replace(/^(我想要?|我希望|我需要|请|麻烦)?\s*(可以)?\s*(帮我|帮忙|帮)?\s*(创建一个|创建|新建一个|新建|做一个|做个|一个)?\s*(帮我|帮忙|帮)?\s*/g, '')
    .replace(/[，,；;:：].*$/g, '')
    .replace(/(右侧|左侧|页面|界面|工作台|预览区|任务区).*/g, '')
    .replace(/\s*(的)?\s*(AI\s*产品|产品|助手)\s*$/i, '')
    .trim();
  return (cleaned ? `${cleaned.slice(0, 18)} AI 产品` : '自定义 AI 产品');
}

function _assistantStarterKit(title, text = '') {
  const seed = `${title || ''} ${text || ''}`;
  const isPpt = /PPT|幻灯|演示|路演|BP|汇报/.test(seed);
  const isPitch = /融资|路演|BP|投资人/.test(seed);
  const isSales = /销售|提案|客户|方案/.test(seed);
  const isResearch = /研究|调研|资料|报告|竞品|行业/.test(seed);
  const isData = /数据|运营|指标|表格|看板/.test(seed);
  const isImage = /图片|图像|生图|绘图|文生图|画图|生成图|海报|封面|插画|头像|视觉|image/i.test(seed);
  if (isImage) {
    return {
      placeholder: '描述你想生成的图片内容、风格、尺寸或上传参考...',
      suggestions: [
        ['帮我生成一张产品发布会海报，先确认主题、风格和尺寸。', '生成一张海报'],
        ['帮我画一个适合作为头像的 AI 形象。', '生成头像'],
        ['帮我把这段文字变成一张插画提示词并生成图片。', '文字转插画']
      ]
    };
  }
  if (isPpt && isSales) {
    return {
      placeholder: '描述这次销售提案 PPT 的客户、目标或上传资料...',
      suggestions: [
        ['帮我做一份销售提案 PPT，先确认客户背景、痛点和方案亮点。', '做销售提案 PPT'],
        ['帮我把客户资料整理成提案大纲。', '资料转提案大纲'],
        ['帮我优化销售方案的叙事和页面结构。', '优化方案结构']
      ]
    };
  }
  if (isPpt && isPitch) {
    return {
      placeholder: '描述这次路演 PPT 的目标、受众或上传资料...',
      suggestions: [
        ['帮我做一份融资路演 PPT，先确认投资人、轮次和核心叙事。', '做一份路演 PPT'],
        ['帮我把融资材料整理成路演大纲。', '资料转路演大纲'],
        ['帮我优化路演 PPT 的结构和讲稿。', '优化结构和讲稿']
      ]
    };
  }
  if (isPpt) {
    return {
      placeholder: '描述这次要做的 PPT 或上传资料...',
      suggestions: [
        ['帮我做一份 PPT，先确认主题、受众、页数和核心叙事。', '做一份 PPT'],
        ['帮我把现有资料整理成汇报大纲。', '资料转汇报大纲'],
        ['帮我优化这份 PPT 的结构和讲稿。', '优化结构和讲稿']
      ]
    };
  }
  if (isResearch) {
    return {
      placeholder: '输入这次要研究的问题...',
      suggestions: [
        ['帮我调研这个方向，先列出问题框架和资料来源。', '调研一个方向'],
        ['帮我整理竞品差异和定位。', '整理竞品差异'],
        ['帮我输出一版研究结论。', '输出研究结论']
      ]
    };
  }
  if (isData) {
    return {
      placeholder: '描述要分析的数据或上传表格...',
      suggestions: [
        ['帮我分析这份数据，先告诉我应该看哪些指标。', '分析关键指标'],
        ['帮我把这些指标整理成看板结构。', '整理看板结构'],
        ['帮我解释最近的数据变化。', '解释数据变化']
      ]
    };
  }
  return {
    placeholder: title ? `向「${title}」描述这次要完成的任务...` : '向这个 AI 产品描述你要完成的任务...',
    suggestions: [
      ['帮我把这个任务拆成可执行步骤。', '拆解任务'],
      ['帮我先问几个关键问题。', '澄清需求'],
      ['帮我输出一个初稿。', '生成初稿']
    ]
  };
}

function _assistantDraftFromPrompt(prompt) {
  const sourcePrompt = String(prompt || '').trim();
  const title = _assistantTitleFromPrompt(sourcePrompt);
  const isPpt = /PPT|幻灯|演示|路演|BP|汇报/.test(title + sourcePrompt);
  const isImage = /图片|图像|生图|绘图|文生图|画图|生成图|海报|封面|插画|头像|视觉|image/i.test(title + sourcePrompt);
  const isResearch = /研究|调研|资料|报告|竞品|行业/.test(title + sourcePrompt);
  const isData = /数据|运营|指标|表格|看板/.test(title + sourcePrompt);
  const kind = `custom-${_assistantSlug(title)}-${Date.now().toString(36)}`;
  const starterKit = _assistantStarterKit(title, sourcePrompt);
  const desc = isPpt
    ? '把资料、想法和目标受众整理成清晰的演示文稿，并在任务需要时长出合适的产品界面。'
    : isImage
      ? '把一句话、参考图和风格要求转成可执行的图片生成任务，并优先调用可用的图片生成能力产出结果。'
      : isResearch
      ? '帮你拆解问题、收集资料、整理证据和结论，输出可以继续加工的研究结果。'
      : isData
        ? '帮你理解指标、整理表格、发现趋势，并把数据转成结论和报告。'
        : '按照你描述的职责处理任务，需要时生成自己的产品界面。';
  const placeholder = starterKit.placeholder;
  const suggestions = starterKit.suggestions;
  const productType = isImage ? 'image' : isPpt ? 'ppt' : isResearch ? 'research' : isData ? 'data' : 'general';
  const capabilities = _assistantDefaultCapabilities(productType, title + sourcePrompt);
  const draft = {
    kind,
    title,
    desc,
    placeholder,
    suggestions,
    sourcePrompt,
    titleSource: 'generated',
    createdAt: Date.now(),
    productType,
    skills: capabilities.skills,
    tools: capabilities.tools,
    toolHints: capabilities.tools.length ? capabilities.tools : (isImage ? ['image generation', 'image editing', 'visual prompt writing'] : [])
  };
  return draft;
}

async function confirmAssistantCreatePreview(draft) {
  const overlay = $('assistantCreateOverlay');
  const applyBtn = $('assistantCreateApply');
  const cancelBtn = $('assistantCreateCancel');
  const closeBtn = $('assistantCreateClose');
  const taskLabels = Array.isArray(draft && draft.suggestions)
    ? draft.suggestions.map(item => item && item[1]).filter(Boolean)
    : [];
  const interfaceName = '创建后自动生成';
  if (overlay && applyBtn && cancelBtn && draft) {
    const setText = (id, value) => {
      const el = $(id);
      if (el) el.textContent = value || '';
    };
    const isPersonalVersion = !!draft.baseAssistantTitle;
    setText('assistantCreateTitle', isPersonalVersion ? '创建专属 AI 产品？' : '创建这个 AI 产品？');
    setText(
      'assistantCreateDesc',
      isPersonalVersion
        ? `基于「${draft.baseAssistantTitle}」创建，确认后会自动开始第一次任务。`
        : '确认名称；创建后会自动开始第一次任务并生成产品界面。'
    );
    setText('assistantCreateName', draft.title);
    setText('assistantCreateSource', draft.sourcePrompt || '我想创建一个新的 AI 产品。');
    setText('assistantCreatePreviewAvatar', _assistantAvatarLabel(draft.kind, draft));
    setText('assistantCreateDuty', draft.desc);
    setText('assistantCreateInput', draft.placeholder);
    setText('assistantCreateProductUiLabel', '产品界面');
    setText('assistantCreateProductUi', interfaceName);
    setText('assistantCreateFlowProductUiTitle', '自动生成产品界面');
    setText('assistantCreateFlowProductUi', '创建后会自动生成第一版产品界面');
    const tasks = $('assistantCreateTasks');
    if (tasks) {
      tasks.innerHTML = '';
      const labels = taskLabels.length ? taskLabels : ['继续这个方向'];
      labels.forEach(label => {
        const chip = document.createElement('span');
        chip.textContent = label;
        tasks.appendChild(chip);
      });
    }
    overlay.hidden = false;
    overlay.setAttribute('aria-hidden', 'false');
    return new Promise(resolve => {
      let settled = false;
      const settle = value => {
        if (settled) return;
        settled = true;
        overlay.hidden = true;
        overlay.setAttribute('aria-hidden', 'true');
        applyBtn.removeEventListener('click', onApply);
        cancelBtn.removeEventListener('click', onCancel);
        if (closeBtn) closeBtn.removeEventListener('click', onCancel);
        overlay.removeEventListener('click', onBackdrop);
        document.removeEventListener('keydown', onKeyDown);
        if (!value) {
          const input = $('msg');
          if (input) setTimeout(() => input.focus(), 0);
        }
        resolve(value);
      };
      const onApply = () => settle(true);
      const onCancel = () => settle(false);
      const onBackdrop = event => {
        if (event.target === overlay) settle(false);
      };
      const onKeyDown = event => {
        if (event.key === 'Escape') settle(false);
      };
      applyBtn.addEventListener('click', onApply);
      cancelBtn.addEventListener('click', onCancel);
      if (closeBtn) closeBtn.addEventListener('click', onCancel);
      overlay.addEventListener('click', onBackdrop);
      document.addEventListener('keydown', onKeyDown);
      const dialog = overlay.querySelector('.product-dialog-panel');
      if (dialog) dialog.scrollTop = 0;
      const initialFocus = closeBtn || applyBtn;
      if (initialFocus) {
        try {
          initialFocus.focus({ preventScroll: true });
        } catch (_err) {
          initialFocus.focus();
        }
      }
      requestAnimationFrame(() => {
        if (dialog) dialog.scrollTop = 0;
      });
    });
  }
  const message = [
    `名称：${draft.title}`,
    `产品说明：${draft.desc}`,
    `新任务怎么开始：${draft.placeholder}`,
    `推荐任务：${taskLabels.join(' / ') || '继续这个方向'}`,
    `产品界面：${interfaceName}`,
    '',
    '确认后，它会加入 AI 产品库，并自动开始第一次任务来生成产品界面。'
  ].join('\n');
  if (typeof showConfirmDialog === 'function') {
    return showConfirmDialog({
      title: '新建 AI 产品',
      message,
      confirmLabel: '创建 AI 产品',
      focusCancel: true
    });
  }
  return window.confirm(message);
}

function _assistantProductPayloadFromDraft(draft) {
  const tools = typeof _assistantNormalizeToolsets === 'function'
    ? _assistantNormalizeToolsets(draft && draft.tools)
    : (Array.isArray(draft && draft.tools) ? draft.tools : []);
  return {
    kind: draft && draft.kind,
    title: draft && draft.title,
    avatar: draft && draft.avatar || '',
    desc: draft && draft.desc || '',
    placeholder: draft && draft.placeholder || '',
    suggestions: Array.isArray(draft && draft.suggestions) ? draft.suggestions : [],
    source_prompt: draft && (draft.sourcePrompt || draft.source_prompt) || '',
    product_type: draft && (draft.productType || draft.product_type) || 'custom',
    ui_mode: draft && (draft.uiMode || draft.ui_mode) || 'workspace',
    skills: Array.isArray(draft && draft.skills) ? draft.skills : [],
    tools
  };
}

async function _createProductFromAssistantDraft(draft) {
  if (!draft || !draft.title) throw new Error('缺少 AI 产品信息');
  const created = await api('/api/products/create', {
    method: 'POST',
    body: JSON.stringify(_assistantProductPayloadFromDraft(draft))
  });
  const product = created && created.product ? created.product : null;
  const saved = typeof _productToCustomAssistant === 'function' ? _productToCustomAssistant(product) : null;
  if (!saved || !saved.productId) throw new Error('AI 产品创建后没有生成 productId');
  _customAssistantsWrite(_mergeCustomAssistants(_customAssistantsRead(), [saved]));
  _registerCustomAssistant(saved);
  return saved;
}

async function _saveProductBackedAssistant(nextAssistant) {
  const productId = String(nextAssistant && (nextAssistant.productId || nextAssistant.product_id) || '').trim();
  if (!productId) throw new Error('这个 AI 产品缺少 productId');
  const data = await api('/api/products/update', {
    method: 'POST',
    body: JSON.stringify({
      product_id: productId,
      ..._assistantProductPayloadFromDraft(nextAssistant)
    })
  });
  const persisted = data && data.product && typeof _productToCustomAssistant === 'function'
    ? _productToCustomAssistant(data.product)
    : null;
  const saved = {
    ...(persisted || nextAssistant),
    titleSource: nextAssistant.titleSource || (persisted && persisted.titleSource) || ''
  };
  _customAssistantsWrite(_mergeCustomAssistants(_customAssistantsRead(), [saved]));
  _registerCustomAssistant(saved);
  return saved;
}

async function createProductFromPrompt(prompt) {
  const text = String(prompt || '').trim();
  if (!text) {
    if (typeof showToast === 'function') showToast('先描述你想创建什么 AI 产品');
    return null;
  }
  const draft = _assistantDraftFromPrompt(text);
  await hydrateProductsFromBackend();
  const existing = _customAssistantByTitle(draft.title);
  if (existing) {
    if (!AI_OBJECTS[existing.kind]) _registerCustomAssistant(existing);
    renderAssistantList();
    openAssistantHome(existing.kind);
    const started = _maybeStartInitialProductUiForExistingAssistant(existing, text);
    if (typeof showToast === 'function') {
      showToast(started ? `已打开已有 AI 产品，正在生成界面：${existing.title}` : `已打开已有 AI 产品：${existing.title}`);
    }
    return existing;
  }
  const ok = await confirmAssistantCreatePreview(draft);
  if (!ok) return null;
  let savedDraft = null;
  try {
    savedDraft = await _createProductFromAssistantDraft(draft);
  } catch (err) {
    if (typeof showToast === 'function') showToast(`创建 AI 产品失败：${err && err.message || err}`, 3200, 'error');
    return null;
  }
  renderAssistantList();
  openAssistantHome(savedDraft.kind);
  if (typeof showToast === 'function') showToast(`已创建 AI 产品：${savedDraft.title}`);
  setTimeout(() => _startProductInitializationTask(savedDraft, text), 80);
  return savedDraft;
}

async function createAssistantFromPrompt(prompt) {
  return createProductFromPrompt(prompt);
}

async function renameCurrentCustomAssistant() {
  const kind = _assistantKey();
  const assistant = _customAssistantByKind(kind);
  if (!assistant) {
    if (typeof showToast === 'function') showToast('只有你创建的 AI 产品可以重命名');
    return null;
  }
  const nextTitleRaw = typeof showPromptDialog === 'function'
    ? await showPromptDialog({
        title: '重命名 AI 产品',
        message: '这个名称会显示在 AI 产品库和产品主页。',
        value: assistant.title,
        confirmLabel: '保存'
      })
    : window.prompt('重命名 AI 产品', assistant.title);
  const nextTitle = String(nextTitleRaw || '').replace(/\s+/g, ' ').trim();
  if (!nextTitle || nextTitle === assistant.title) return assistant;
  if (_customAssistantTitleExists(nextTitle, kind)) {
    if (typeof showToast === 'function') showToast('已经有同名 AI 产品');
    return assistant;
  }
  let updated = null;
  try {
    updated = await _saveProductBackedAssistant({ ...assistant, title: nextTitle, titleSource: 'manual' });
  } catch (err) {
    if (typeof showToast === 'function') showToast(`重命名失败：${err && err.message || err}`, 3200, 'error');
    return assistant;
  }
  renderAssistantList();
  openAssistantHome(updated.kind || kind);
  if (typeof showToast === 'function') showToast(`已重命名为：${nextTitle}`);
  return updated;
}

async function deleteCurrentCustomAssistant() {
  const kind = _assistantKey();
  const assistant = _customAssistantByKind(kind);
  if (!assistant) {
    if (typeof showToast === 'function') showToast('内置 AI 产品不能删除');
    return false;
  }
  const ok = typeof showConfirmDialog === 'function'
    ? await showConfirmDialog({
        title: `删除「${assistant.title}」？`,
        message: '只会删除这个 AI 产品对象，不会删除它处理过的历史任务。历史任务会回到最匹配的内置 AI 产品；无法识别时回到通用 AI。',
        confirmLabel: '删除',
        danger: true,
        focusCancel: true
      })
    : window.confirm(`删除「${assistant.title}」？`);
  if (!ok) return false;
  if ((assistant.backendProduct || assistant.productId) && assistant.productId) {
    try {
      await api('/api/products/delete', {
        method: 'POST',
        body: JSON.stringify({ product_id: assistant.productId })
      });
    } catch (err) {
      if (typeof showToast === 'function') showToast(`删除 AI 产品失败：${err && err.message || err}`, 3200, 'error');
      return false;
    }
  }
  const deleted = _deleteCustomAssistantKind(kind);
  if (!deleted) return false;
  renderAssistantList();
  openAssistantHome('general');
  if (typeof renderSessionListFromCache === 'function') renderSessionListFromCache();
  if (typeof showToast === 'function') showToast(`已删除 AI 产品：${assistant.title}`);
  return true;
}

function _assistantKey() {
  return window._currentAiAssistantKind || 'ppt';
}

function _assistantObject(kind = _assistantKey()) {
  return AI_OBJECTS[kind] || AI_OBJECTS.ppt;
}

function assistantKindForSession(sessionId) {
  if (!sessionId) return '';
  const assignments = _assistantAssignmentsRead();
  return assignments[sessionId] || '';
}

function _assistantKindFromLegacySession(session) {
  if (!session) return '';
  const messageSource = Array.isArray(session.messages) && session.messages.length
    ? session.messages
    : ((typeof S !== 'undefined' && Array.isArray(S.messages)) ? S.messages : []);
  const messageText = messageSource
    .filter(message => message && message.role !== 'tool')
    .slice(0, 8)
    .map(message => {
      if (typeof msgContent === 'function') return msgContent(message);
      const content = message.content || '';
      if (Array.isArray(content)) {
        return content
          .filter(part => part && part.type === 'text')
          .map(part => part.text || part.content || '')
          .join(' ');
      }
      return String(content || '');
    })
    .filter(Boolean)
    .join(' ');
  const text = [
    session.title,
    session.pending_user_message,
    session.last_message,
    session.preview,
    session.summary,
    messageText
  ].filter(Boolean).join(' ');
  if (!text) return '';
  if (/(PPT|ppt|PowerPoint|幻灯|演示|路演)/.test(text) || /\b(BP|deck|slide|slides)\b/i.test(text)) return 'ppt';
  if (/(数据|表格|指标|运营|Excel|excel|CSV|csv|图表|看板|分析报表)/.test(text)) return 'data';
  if (/(研究|调研|竞品|资料|文献|论文|引用|市场分析|行业分析)/.test(text)) return 'research';
  return '';
}

function _assistantKindExists(kind) {
  return !!(kind && AI_OBJECTS[kind]);
}

function _clearAssistantAssignment(sessionId) {
  if (!sessionId) return;
  const assignments = _assistantAssignmentsRead();
  if (!Object.prototype.hasOwnProperty.call(assignments, sessionId)) return;
  delete assignments[sessionId];
  _assistantAssignmentsWrite(assignments);
}

function assistantKindForLoadedSession(session) {
  if (!session || !session.session_id) return 'general';
  const productId = String(session.product_id || session.productId || '').trim();
  if (productId) {
    const productKind = _assistantKindForProductId(productId);
    if (productKind && _assistantKindExists(productKind)) return productKind;
    return 'general';
  }
  const assignedKind = session.next_ai_assistant_kind || assistantKindForSession(session.session_id);
  const inferredKind = _assistantKindFromLegacySession(session);
  const validInferredKind = _assistantKindExists(inferredKind) ? inferredKind : '';
  if (!assignedKind) return validInferredKind || 'general';
  if (_assistantKindExists(assignedKind)) {
    return assignedKind === 'general' && validInferredKind ? validInferredKind : assignedKind;
  }
  _clearAssistantAssignment(session.session_id);
  return validInferredKind || 'general';
}

function syncAssistantForLoadedSession(session) {
  const productId = String(session && (session.product_id || session.productId) || '').trim();
  const kind = assistantKindForLoadedSession(session);
  if (session && kind) session.next_ai_assistant_kind = kind;
  if (kind && kind !== _assistantKey() && AI_OBJECTS[kind]) {
    selectAiObject(kind);
  } else {
    syncAssistantTaskUi();
  }
  if (productId && !_assistantKindForProductId(productId) && typeof hydrateProductsFromBackend === 'function') {
    void hydrateProductsFromBackend().then(() => {
      const hydratedKind = _assistantKindForProductId(productId);
      if (!hydratedKind || !AI_OBJECTS[hydratedKind]) return;
      if (typeof S !== 'undefined' && S.session && String(S.session.product_id || S.session.productId || '') !== productId) return;
      selectAiObject(hydratedKind);
      if (typeof refreshCurrentProductPreview === 'function') refreshCurrentProductPreview({silent:true, reason:'session-product-hydrate'});
    }).catch(err => console.debug('Failed to hydrate product for loaded session', err));
  }
  return kind;
}

function rememberAssistantTaskTitle(sessionId, title) {
  const sid = sessionId || (typeof S !== 'undefined' && S.session && (S.session.session_id || S.session.id));
  const nextTitle = _assistantTaskCompactDisplayTitle(title);
  if (!sid || !nextTitle) return;
  if (_assistantTaskLooksGenericTitle(nextTitle)) return;
  const titles = _assistantTaskTitlesRead();
  if (_assistantTaskLooksProductUiCommand(nextTitle)) {
    const firstUserTitle = _assistantTaskCompactDisplayTitle(_assistantTaskFirstUserMessage());
    if (firstUserTitle && !_assistantTaskLooksGenericTitle(firstUserTitle) && !_assistantTaskLooksProductUiCommand(firstUserTitle)) {
      titles[sid] = firstUserTitle;
      _assistantTaskTitlesWrite(titles);
    }
    return;
  }
  const currentTitle = _assistantTaskNormalizeTitle(titles[sid]);
  if (currentTitle && !_assistantTaskLooksGenericTitle(currentTitle) && !_assistantTaskLooksProductUiCommand(currentTitle)) return;
  if (titles[sid] === nextTitle) return;
  titles[sid] = nextTitle;
  _assistantTaskTitlesWrite(titles);
}

function markSessionForCurrentAssistant(sessionId, taskTitle = '') {
  const sid = sessionId || (typeof S !== 'undefined' && S.session && (S.session.session_id || S.session.id));
  if (!sid) return;
  const kind = _assistantKey();
  const assignments = _assistantAssignmentsRead();
  assignments[sid] = kind;
  _assistantAssignmentsWrite(assignments);
  if (taskTitle) rememberAssistantTaskTitle(sid, taskTitle);
  if (typeof S !== 'undefined' && S.session && (S.session.session_id || S.session.id) === sid) {
    S.session.next_ai_assistant_kind = kind;
  }
}

function assistantTaskBelongsToCurrentAssistant(session) {
  if (!session || !session.session_id) return false;
  const assignedKind = session.next_ai_assistant_kind || assistantKindForSession(session.session_id);
  if (!assignedKind) {
    const inferredKind = _assistantKindFromLegacySession(session);
    const validInferredKind = _assistantKindExists(inferredKind) ? inferredKind : '';
    return validInferredKind ? validInferredKind === _assistantKey() : _assistantKey() === 'general';
  }
  if (!_assistantKindExists(assignedKind)) {
    _clearAssistantAssignment(session.session_id);
    const inferredKind = _assistantKindFromLegacySession(session);
    const validInferredKind = _assistantKindExists(inferredKind) ? inferredKind : '';
    return validInferredKind ? validInferredKind === _assistantKey() : _assistantKey() === 'general';
  }
  return assignedKind === _assistantKey();
}

function filterSessionsForCurrentAssistant(sessions) {
  if (!Array.isArray(sessions)) return [];
  return sessions.filter(assistantTaskBelongsToCurrentAssistant);
}

function _assistantAvatarLabel(kind = _assistantKey(), object) {
  if (kind === 'create') return '+';
  const title = object && object.title ? object.title : (window._currentAiAssistantTitle || 'AI 产品');
  const avatar = object && object.avatar ? String(object.avatar).trim() : '';
  if (avatar) return avatar.slice(0, 2).toUpperCase();
  if (/ppt/i.test(kind) || /PPT/.test(title)) return 'P';
  if (kind === 'research') return 'R';
  if (kind === 'data') return 'D';
  if (kind === 'general') return 'G';
  return String(title).trim().slice(0, 1).toUpperCase() || 'A';
}

function _renderAssistantHomeDefaultHint(hint, text, actionLabel = '', actionHandler = null) {
  if (!hint) return;
  hint.hidden = false;
  hint.innerHTML = '';
  const copy = document.createElement('span');
  copy.textContent = text;
  hint.appendChild(copy);
  if (actionLabel && typeof actionHandler === 'function') {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'assistant-home-default-action';
    btn.textContent = actionLabel;
    btn.title = `${actionLabel}：${text}`;
    btn.setAttribute('aria-label', btn.title);
    btn.onclick = actionHandler;
    hint.appendChild(btn);
  }
}

function _renderAssistantHomeActionBar(el, text, actionLabel = '', actionHandler = null) {
  if (!el) return;
  el.hidden = false;
  el.innerHTML = '';
  const copy = document.createElement('span');
  copy.textContent = text;
  el.appendChild(copy);
  if (actionLabel && typeof actionHandler === 'function') {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'assistant-home-inline-action';
    btn.textContent = actionLabel;
    btn.title = actionLabel;
    btn.setAttribute('aria-label', actionLabel);
    btn.onclick = actionHandler;
    el.appendChild(btn);
  }
}

function focusAssistantComposerForFirstTask() {
  const input = $('msg');
  if (!input) return;
  try {
    input.scrollIntoView({ block: 'center', behavior: 'smooth' });
  } catch (_err) {}
  setTimeout(() => input.focus(), 80);
}

window.focusAssistantComposerForFirstTask = focusAssistantComposerForFirstTask;

function _syncAssistantHome(object = AI_OBJECTS[_assistantKey()] || AI_OBJECTS.ppt) {
  const kind = _assistantKey();
  const isCreate = kind === 'create';
  const assistantTitle = object.title || 'AI 产品';
  const home = $('assistantHome');
  const title = $('assistantHomeTitle');
  const desc = $('assistantHomeDesc');
  const avatar = $('assistantHomeAvatar');
  const eyebrow = $('assistantHomeEyebrow');
  const guide = $('assistantHomeGuide');
  const origin = $('assistantHomeOrigin');
  const nextStep = $('assistantHomeNextStep');
  const manage = $('assistantHomeManage');
  const hint = $('assistantHomeDefaultHint');
  const newTaskLabel = $('newTaskPrimaryLabel');
  const newTaskBtn = $('newTaskPrimaryBtn');
  const newTaskIcon = $('newTaskPrimaryIcon');
  const relationKickerA = $('assistantHomeRelationKickerA');
  const relationTitleA = $('assistantHomeRelationTitleA');
  const relationDescA = $('assistantHomeRelationDescA');
  const relationKickerB = $('assistantHomeRelationKickerB');
  const relationTitleB = $('assistantHomeRelationTitleB');
  const relationDescB = $('assistantHomeRelationDescB');
  const relationKickerC = $('assistantHomeRelationKickerC');
  const relationTitleC = $('assistantHomeRelationTitleC');
  const relationDescC = $('assistantHomeRelationDescC');
  const isChatOnlyProduct = _assistantIsChatOnlyProduct(object);
  if (home) home.classList.toggle('is-create', isCreate);
  if (title) title.textContent = assistantTitle;
  if (desc) {
    desc.textContent = isCreate
      ? (object.desc || '描述你想创建的 AI 产品。')
      : (object.homeDesc || object.desc || '直接说你想完成什么。需要更具体的界面时，会在任务里展开。');
  }
  if (avatar) avatar.textContent = _assistantAvatarLabel(kind, object);
  if (eyebrow) eyebrow.textContent = isCreate ? '新建 AI 产品' : object.custom ? '你创建的 AI 产品' : 'AI 产品';
  if (guide) {
    guide.textContent = isCreate
      ? '说一句它要帮你完成什么，确认后会自动开始第一次任务。'
      : '从一句话开始，也可以上传资料。';
  }
  if (origin) {
    if (isCreate) {
      origin.hidden = false;
      origin.textContent = '创建后，它会出现在 AI 产品库。';
      origin.removeAttribute('title');
    } else {
      origin.hidden = true;
      origin.textContent = '';
      origin.removeAttribute('title');
    }
  }
  if (nextStep) {
    if (isCreate) {
      _renderAssistantHomeActionBar(nextStep, '发送后确认名称，然后自动进入新产品并生成界面。');
    } else if (isChatOnlyProduct) {
      nextStep.hidden = true;
      nextStep.innerHTML = '';
    } else if (object.productId && String(object.uiStatus || 'empty') === 'failed') {
      const failureReason = String(object.uiErrorMessage || '').trim();
      _renderAssistantHomeActionBar(
        nextStep,
        failureReason
          ? `${failureReason} 可以继续说需求，或先重新生成一版。`
          : '产品界面生成失败，可以继续说需求，或先重新生成一版。',
        '重新生成界面',
        () => requestCurrentProductUiGeneration()
      );
    } else if (object.productId && String(object.uiStatus || 'empty') === 'empty') {
      _renderAssistantHomeActionBar(
        nextStep,
        '这个 AI 产品还没有自己的界面，可以先让它生成第一版。',
        '生成产品界面',
        () => requestCurrentProductUiGeneration()
      );
    } else if (object.productId && String(object.uiStatus || 'empty') === 'generating') {
      _renderAssistantHomeActionBar(nextStep, '正在生成这个 AI 产品的界面，完成后会自动刷新。');
    } else {
      nextStep.hidden = true;
      nextStep.innerHTML = '';
    }
  }
  if (manage) manage.hidden = true;
  if (newTaskLabel) newTaskLabel.textContent = isCreate ? '返回当前产品' : '新任务';
  if (newTaskBtn) {
    const lastObject = AI_OBJECTS[_lastTaskAssistantKind] || AI_OBJECTS.general || AI_OBJECTS.ppt;
    const lastTitle = lastObject && lastObject.title ? lastObject.title : '当前 AI 产品';
    newTaskBtn.title = isCreate ? `回到「${lastTitle}」的新任务` : `开始「${assistantTitle}」的新任务`;
    newTaskBtn.setAttribute('aria-label', newTaskBtn.title);
    newTaskBtn.classList.toggle('is-return', isCreate);
  }
  if (newTaskIcon) {
    newTaskIcon.innerHTML = isCreate
      ? '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M19 12H5"/><path d="m12 19-7-7 7-7"/></svg>'
      : '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5v14"/><path d="M5 12h14"/></svg>';
  }
  const relation = $('assistantHomeRelation');
  if (relation) relation.hidden = true;
  if (relationKickerA) relationKickerA.textContent = isCreate ? '想法' : '开始';
  if (relationTitleA) relationTitleA.textContent = isCreate ? '说想做什么' : '说一句任务';
  if (relationDescA) {
    relationDescA.textContent = isCreate
      ? '例如：帮我做融资路演 PPT。'
      : `下方第一句话就是「${assistantTitle}」的新任务。`;
  }
  if (relationKickerB) relationKickerB.textContent = isCreate ? '预览' : '任务资料';
  if (relationTitleB) {
    relationTitleB.textContent = isCreate
      ? '确认后创建'
      : '从对话开始';
  }
  if (relationDescB) {
    relationDescB.textContent = isCreate
      ? '系统会生成名称、开始方式和默认能力。'
      : '需要时再让产品界面长出来。';
  }
  if (relationKickerC) relationKickerC.textContent = isCreate ? '加入' : '复用';
  if (relationTitleC) relationTitleC.textContent = isCreate ? '放进 AI 产品库' : '继续改进';
  if (relationDescC) {
    relationDescC.textContent = isCreate
      ? '以后可以继续通过聊天让它改界面。'
      : '聊天里提出要求，界面和流程可以继续改。';
  }
  if (hint) {
    hint.hidden = true;
    hint.innerHTML = '';
  }
}

function selectAiObject(kind = 'ppt') {
  const object = AI_OBJECTS[kind] || AI_OBJECTS.ppt;
  window._currentAiAssistantKind = kind;
  window._currentAiAssistantTitle = object.title;
  window._currentAiProductTitle = object.title;
  if (kind !== 'create') _lastTaskAssistantKind = kind;
  document.querySelectorAll('.ai-object-item[data-ai-object]').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.aiObject === kind);
  });
  const title = $('aiObjectEmptyTitle');
  const desc = $('aiObjectEmptyDesc');
  const topTitle = $('productModeTitle');
  const input = $('msg');
  if (title) title.textContent = object.title;
  if (desc) desc.textContent = object.desc;
  if (topTitle) topTitle.textContent = object.title;
  if (input) input.placeholder = object.placeholder;
  _syncAssistantHome(object);
  const buttons = Array.from(document.querySelectorAll('[data-ai-suggestion]'));
  object.suggestions.forEach((item, index) => {
    const btn = buttons[index];
    if (!btn) return;
    btn.dataset.msg = item[0];
    const label = btn.querySelector('span:last-child');
    if (label) label.textContent = item[1];
  });
  syncAssistantTaskUi();
  syncAssistantListMeta();
  const previewUrl = typeof currentAssistantPreviewUrl === 'function'
    ? currentAssistantPreviewUrl(kind)
    : (object.previewUrl || '');
  if (previewUrl && typeof refreshCurrentProductPreview === 'function') refreshCurrentProductPreview({silent:true});
  else _hideProductPreviewIfActive();
  if (typeof renderSessionListFromCache === 'function') renderSessionListFromCache();
}

function startAssistantNewTask() {
  const kind = _assistantKey() === 'create' ? (_lastTaskAssistantKind || 'general') : _assistantKey();
  openAssistantHome(kind);
}

function openAssistantLanding(options = {}) {
  const kind = _assistantKey() === 'create' ? (_lastTaskAssistantKind || 'general') : _assistantKey();
  openAssistantHome(kind, options);
}

function _setAssistantHomeUrl() {
  if (typeof window === 'undefined' || !window.history) return;
  try {
    const current = new URL(window.location.href);
    const base = new URL(document.baseURI || '/', window.location.origin);
    current.searchParams.delete('session');
    const path = base.pathname || '/';
    const next = path + current.search + current.hash;
    const currentPath = window.location.pathname + window.location.search + window.location.hash;
    if (next && next !== currentPath) window.history.replaceState({}, '', next);
  } catch (_err) {}
}

function openAssistantHome(kind, options = {}) {
  if (typeof S !== 'undefined' && (S.busy || S.activeStreamId)) {
    if (typeof showToast === 'function') showToast('当前任务还在运行，完成后再开始新任务');
    return;
  }
  if (kind) selectAiObject(kind);
  if (typeof S !== 'undefined') {
    S.session = null;
    S.messages = [];
    S.entries = [];
    S.toolCalls = [];
    S.activeStreamId = null;
    S.busy = false;
  }
  try { localStorage.removeItem('hermes-webui-session'); } catch (_err) {}
  if (options.replaceUrl !== false) _setAssistantHomeUrl();
  const inner = $('msgInner');
  const empty = $('emptyState');
  if (inner) inner.innerHTML = '';
  if (empty) empty.style.display = 'none';
  syncAssistantTaskUi();
  if (currentAssistantPreviewUrl()) refreshCurrentProductPreview({silent:true});
  const input = $('msg');
  if (input) {
    const object = AI_OBJECTS[_assistantKey()] || AI_OBJECTS.ppt;
    input.placeholder = object.placeholder || input.placeholder;
    setTimeout(() => input.focus(), 0);
  }
  if (typeof syncTopbar === 'function') syncTopbar();
  if (typeof updateSendBtn === 'function') updateSendBtn();
}

function _assistantTaskNormalizeTitle(value) {
  return String(value == null ? '' : value).replace(/\s+/g, ' ').trim();
}

function _assistantTaskClampTitle(value, max = 36) {
  const title = _assistantTaskNormalizeTitle(value);
  if (!title) return '';
  return title.length > max ? `${title.slice(0, Math.max(1, max - 3))}...` : title;
}

function _assistantTaskCollapseRepeatedPrefix(value) {
  let title = _assistantTaskNormalizeTitle(value);
  for (let i = 0; i < 3; i += 1) {
    const next = title.replace(/^(.{1,12}版)\1+/, '$1');
    if (next === title) break;
    title = next;
  }
  return title;
}

function _assistantTaskCompactDisplayTitle(value) {
  const title = _assistantTaskCollapseRepeatedPrefix(value);
  if (!title) return '';

  const topicMatch = title.match(/主题\s*[：:]?\s*[「“"']([^」”"']{2,48})[」”"']/);
  if (topicMatch && topicMatch[1]) {
    const topic = _assistantTaskNormalizeTitle(topicMatch[1]);
    const audienceMatch = title.match(/受众\s*[：:]?\s*[「“"']([^」”"']{2,24})[」”"']/);
    const audience = audienceMatch ? _assistantTaskNormalizeTitle(audienceMatch[1]) : '';
    if (audience && !/^(客户|用户|大众|普通用户|所有人)$/i.test(audience)) {
      return _assistantTaskClampTitle(`${audience}版${topic}`);
    }
    return _assistantTaskClampTitle(topic);
  }

  const firstClause = title.split(/[，,。；;]/)[0] || title;
  let cleaned = firstClause
    .replace(/^(请|麻烦)?\s*(你)?\s*(帮我|给我|为我)?\s*(做|制作|生成|创建|设计|写|整理|优化|继续优化)\s*(一份|一个|一套|一下)?\s*/i, '')
    .replace(/^(把|将)\s*/, '')
    .replace(/\s*(吧|好吗|可以吗)$/i, '')
    .trim();
  if (/^这份\s*PPT/i.test(cleaned)) cleaned = '优化 PPT';
  return _assistantTaskClampTitle(cleaned || title);
}

function _assistantTaskLooksDefaultTitle(value) {
  const title = _assistantTaskNormalizeTitle(value);
  return !title || title === 'Untitled' || title === 'New Chat' || title === 'Session' || title === '未命名任务' || title === '刚开始的任务';
}

function _assistantTaskLooksGenericTitle(value) {
  const title = _assistantTaskNormalizeTitle(value);
  if (_assistantTaskLooksDefaultTitle(title)) return true;
  if (/^(AI productivity discussion|PowerPoint assistance|Presentation task|PPT task|Slide deck task)$/i.test(title)) return true;
  return /^(ppt|PPT|幻灯片|演示文稿|presentation|deck|slide deck)$/i.test(title);
}

function _assistantTaskLooksProductUiCommand(value) {
  const title = _assistantTaskNormalizeTitle(value);
  if (!title) return false;
  if (/^(请)?基于.*(产品界面|工作界面|PPT 工作界面|继续优化)/.test(title)) return true;
  if (/^(请)?同步更新右侧/.test(title)) return true;
  if (/^(请)?(继续)?优化当前 PPT/.test(title)) return true;
  if (/^(生成页面|重排|收敛成|写\s*\d+\s*分钟讲稿|投资人审阅)/.test(title)) return true;
  return false;
}

function _assistantTaskFirstUserTitle() {
  const messages = (typeof S !== 'undefined' && Array.isArray(S.messages)) ? S.messages : [];
  const first = messages.find(message => message && message.role === 'user' && message.content);
  const title = first ? _assistantTaskCompactDisplayTitle(first.content) : '';
  if (title && typeof S !== 'undefined' && S.session && S.session.session_id) {
    rememberAssistantTaskTitle(S.session.session_id, title);
  }
  return title;
}

function _assistantTaskFirstUserMessage() {
  const messages = (typeof S !== 'undefined' && Array.isArray(S.messages)) ? S.messages : [];
  const first = messages.find(message => message && message.role === 'user' && message.content);
  if (!first) return '';
  const raw = typeof msgContent === 'function' ? msgContent(first) : first.content;
  return _assistantTaskNormalizeTitle(raw).slice(0, 160);
}

function _assistantTaskTitle() {
  const session = (typeof S !== 'undefined') ? S.session : null;
  const sessionTitle = session ? _assistantTaskNormalizeTitle(session.title) : '';
  const storedTitle = session && session.session_id ? _assistantTaskNormalizeTitle(_assistantTaskTitlesRead()[session.session_id]) : '';
  if (!_assistantTaskLooksGenericTitle(sessionTitle) && !_assistantTaskLooksProductUiCommand(sessionTitle)) return _assistantTaskCompactDisplayTitle(sessionTitle) || sessionTitle.slice(0, 48);
  const stableStoredTitle = !_assistantTaskLooksProductUiCommand(storedTitle) ? storedTitle : '';
  return (_assistantTaskCompactDisplayTitle(stableStoredTitle) || _assistantTaskFirstUserTitle() || '当前任务').slice(0, 48);
}

function assistantChromeTitleState() {
  const assistantTitle = window._currentAiAssistantTitle || window._currentAiProductTitle || 'PPT 设计师';
  const hasTask = _assistantTaskHasActiveTask();
  const taskTitle = hasTask ? _assistantTaskTitle() : '';
  const main = hasTask ? taskTitle : assistantTitle;
  const sub = hasTask ? assistantTitle : 'AI 产品';
  return {
    main,
    sub,
    documentTitle: hasTask ? `${taskTitle} — ${assistantTitle} — Next AI` : `${assistantTitle} — Next AI`,
  };
}

function assistantDisplayTitleForSession(session) {
  const rawTitle = session ? _assistantTaskNormalizeTitle(session.display_title || session._state_db_title || session.title) : '';
  if (!_assistantTaskLooksGenericTitle(rawTitle) && !_assistantTaskLooksProductUiCommand(rawTitle)) return _assistantTaskCompactDisplayTitle(rawTitle) || rawTitle || 'Untitled';
  const storedTitle = session && session.session_id ? _assistantTaskNormalizeTitle(_assistantTaskTitlesRead()[session.session_id]) : '';
  if (storedTitle && !_assistantTaskLooksGenericTitle(storedTitle) && !_assistantTaskLooksProductUiCommand(storedTitle)) return _assistantTaskCompactDisplayTitle(storedTitle) || storedTitle;
  const hintedTitle = _assistantTaskTitleFromSessionHints(session);
  if (hintedTitle) return hintedTitle;
  return rawTitle && !_assistantTaskLooksGenericTitle(rawTitle) && !_assistantTaskLooksProductUiCommand(rawTitle) ? rawTitle : '刚开始的任务';
}

function _assistantTaskTitleFromSessionHints(session) {
  if (!session) return '';
  const candidates = [
    session.pending_user_message,
    session.first_user_message,
    session.last_user_message,
    session.user_message,
    session.initial_message,
    session.preview,
    session.last_message,
    session.summary
  ];
  for (const value of candidates) {
    const title = _assistantTaskCompactDisplayTitle(value);
    if (!title) continue;
    if (_assistantTaskLooksGenericTitle(title) || _assistantTaskLooksProductUiCommand(title)) continue;
    if (/^(好的|可以|当然|收到|明白|我先|我会|我可以|已|已经|下面|这里|这是)/.test(title)) continue;
    return title;
  }
  return '';
}

const _assistantTitleHydrationDone = new Set();
const _assistantTitleHydrationInFlight = new Set();

function _assistantMessageTextForTitle(message) {
  if (!message || message.role !== 'user') return '';
  if (typeof msgContent === 'function') {
    const text = _assistantTaskNormalizeTitle(msgContent(message));
    if (text) return text;
  }
  const content = message.content || message.text || '';
  if (Array.isArray(content)) {
    return _assistantTaskNormalizeTitle(content
      .filter(part => part && part.type === 'text')
      .map(part => part.text || part.content || '')
      .join(' '));
  }
  return _assistantTaskNormalizeTitle(content);
}

async function _hydrateAssistantDisplayTitle(session) {
  const sid = session && session.session_id;
  if (!sid || _assistantTitleHydrationDone.has(sid) || _assistantTitleHydrationInFlight.has(sid)) return false;
  const rawTitle = _assistantTaskNormalizeTitle(session.display_title || session._state_db_title || session.title);
  const storedTitle = _assistantTaskNormalizeTitle(_assistantTaskTitlesRead()[sid]);
  if (storedTitle && !_assistantTaskLooksGenericTitle(storedTitle) && !_assistantTaskLooksProductUiCommand(storedTitle)) {
    _assistantTitleHydrationDone.add(sid);
    return false;
  }
  if (!_assistantTaskLooksGenericTitle(rawTitle) && !_assistantTaskLooksProductUiCommand(rawTitle)) {
    _assistantTitleHydrationDone.add(sid);
    return false;
  }
  _assistantTitleHydrationInFlight.add(sid);
  try {
    const data = await api(`/api/session?session_id=${encodeURIComponent(sid)}&messages=1&resolve_model=0&msg_limit=6`);
    const messages = data && data.session && Array.isArray(data.session.messages) ? data.session.messages : [];
    const title = messages
      .filter(message => message && message.role === 'user')
      .map(message => _assistantTaskCompactDisplayTitle(_assistantMessageTextForTitle(message)))
      .find(candidate => candidate && !_assistantTaskLooksGenericTitle(candidate) && !_assistantTaskLooksProductUiCommand(candidate));
    if (title) {
      rememberAssistantTaskTitle(sid, title);
      _assistantTitleHydrationDone.add(sid);
      return true;
    }
    _assistantTitleHydrationDone.add(sid);
  } catch (_err) {
    _assistantTitleHydrationDone.add(sid);
  } finally {
    _assistantTitleHydrationInFlight.delete(sid);
  }
  return false;
}

function hydrateAssistantDisplayTitlesForSessions(sessions) {
  if (!Array.isArray(sessions) || typeof api !== 'function') return;
  const candidates = sessions
    .filter(session => session && session.session_id)
    .filter(session => !_assistantTitleHydrationDone.has(session.session_id))
    .filter(session => {
      const rawTitle = _assistantTaskNormalizeTitle(session.display_title || session._state_db_title || session.title);
      const storedTitle = _assistantTaskNormalizeTitle(_assistantTaskTitlesRead()[session.session_id]);
      if (storedTitle && !_assistantTaskLooksGenericTitle(storedTitle) && !_assistantTaskLooksProductUiCommand(storedTitle)) return false;
      return _assistantTaskLooksGenericTitle(rawTitle) || _assistantTaskLooksProductUiCommand(rawTitle);
    })
    .slice(0, 6);
  if (!candidates.length) return;
  Promise.all(candidates.map(session => _hydrateAssistantDisplayTitle(session)))
    .then(results => {
      if (results.some(Boolean) && typeof renderSessionListFromCache === 'function') renderSessionListFromCache();
    })
    .catch(() => {});
}

function _assistantTaskHasActiveTask() {
  if (typeof S === 'undefined' || !S.session) return false;
  const messages = Array.isArray(S.messages) ? S.messages : [];
  if (messages.some(message => message && message.role && message.role !== 'tool')) return true;
  return Number(S.session.message_count || 0) > 0 || !!S.session.pending_user_message || !!S.session.active_stream_id;
}

function _syncAssistantTaskContextStrip(hasTask = _assistantTaskHasActiveTask()) {
  const strip = $('assistantTaskContextStrip');
  if (!strip) return;
  const kicker = $('assistantTaskContextKicker');
  const title = $('assistantTaskContextTitle');
  const desc = $('assistantTaskContextDesc');
  const assistantTitle = window._currentAiAssistantTitle || window._currentAiProductTitle || '当前 AI 产品';
  const taskTitle = _assistantTaskTitle();
  if (!hasTask) {
    strip.hidden = true;
    if (kicker) kicker.textContent = '当前任务';
    if (title) title.textContent = '';
    if (desc) desc.textContent = '';
    return;
  }
  strip.hidden = false;
  if (kicker) kicker.textContent = '当前任务';
  if (title) title.textContent = taskTitle;
  if (desc) {
    if (_activeProductPreview && _activeProductPreview.product_preview) {
      desc.textContent = `「${_activeProductPreview.name || '产品界面'}」已打开。继续补充要求即可。`;
    } else {
      desc.textContent = `继续补充要求即可。`;
    }
  }
}

function _syncAssistantTaskProgress(hasTask = _assistantTaskHasActiveTask()) {
  const progress = $('assistantTaskProgress');
  if (!progress) return;
  const title = $('assistantTaskProgressTitle');
  const desc = $('assistantTaskProgressDesc');
  const dot = $('assistantTaskProgressDot');
  const productUi = $('assistantTaskProgressProduct');
  const productUiKicker = $('assistantTaskProgressProductKicker');
  const isRunning = !!(typeof S !== 'undefined' && (S.busy || S.activeStreamId || (S.session && S.session.active_stream_id)));
  if (!hasTask || !isRunning) {
    progress.hidden = true;
    progress.classList.remove('is-running', 'is-idle');
    return;
  }
  progress.hidden = false;
  const hasProductPreview = !!(_activeProductPreview && _activeProductPreview.product_preview);
  const productScope = String((S.session && S.session.product_scope) || '').trim();
  const isInit = productScope === 'product_init';
  const assistantTitle = window._currentAiAssistantTitle || window._currentAiProductTitle || '当前 AI 产品';
  progress.classList.toggle('is-running', isRunning);
  progress.classList.remove('is-idle');
  if (dot) dot.setAttribute('aria-label', '任务运行中');
  if (title) title.textContent = isInit ? '正在生成第一版产品界面' : '正在处理这次任务';
  if (desc) {
    desc.textContent = isInit
      ? `「${assistantTitle}」正在先做一个简单可用的界面；你可以继续补充要求。`
      : `由「${assistantTitle}」执行；你可以继续补充要求。`;
  }
  if (productUiKicker) productUiKicker.textContent = '产品界面';
  if (productUi) {
    if (hasProductPreview) {
      productUi.textContent = (_activeProductPreview && _activeProductPreview.name) || '当前产品界面';
    } else if (isInit) {
      productUi.textContent = '正在生成第一版';
    } else {
      productUi.textContent = '按需生成';
    }
  }
}

function _syncProductPreviewCopy() {
  const kicker = $('activeProductKicker');
  const nameEl = $('activeProductPreviewName');
  const versionEl = $('activeProductVersion');
  const note = $('activeProductNote');
  const regenerateBtn = $('regenerateProductUiBtn');
  const rollbackBtn = $('rollbackActiveProductBtn');
  const productCapabilitiesBtn = $('productCapabilitiesBtn');
  const collapseBtn = $('collapseActiveProductBtn');
  const moreBtn = $('activeProductMoreBtn');
  const moreWrap = document.querySelector('.active-product-more');
  const assistantTitle = window._currentAiAssistantTitle || window._currentAiProductTitle || '当前 AI 产品';
  const taskTitle = _assistantTaskTitle();
  const isProductPreview = !!(_activeProductPreview && _activeProductPreview.product_preview);
  const productPreviewName = _activeProductPreview
    ? (_activeProductPreview.name || _activeProductPreview.id)
    : '产品界面';
  const previousVersion = _activeProductPreview && _activeProductPreview.previous_version ? _activeProductPreview.previous_version : '';
  const canRollback = !!(_activeProductPreview && _activeProductPreview.can_rollback && previousVersion);
  if (kicker) kicker.textContent = isProductPreview ? '产品界面' : assistantTitle;
  if (nameEl) nameEl.textContent = productPreviewName;
  if (versionEl) {
    versionEl.textContent = isProductPreview && canRollback ? ' · 可恢复上一版' : '';
    versionEl.title = isProductPreview && canRollback ? `产品界面可以恢复到上一版 ${previousVersion}` : '';
  }
  if (note) {
    if (isProductPreview) {
      const uiStatus = String(_activeProductPreview && _activeProductPreview.ui_status || '');
      note.textContent = uiStatus === 'generating'
        ? '正在生成这个 AI 产品的界面'
        : uiStatus === 'failed'
          ? (_activeProductPreview.ui_error_message || '产品界面需要重新生成')
          : !_activeProductPreview.entry_generated
            ? '还没有生成界面，可以从聊天里让它长出来'
            : canRollback
              ? '已生成，可继续对话调整，也可以恢复上一版'
              : '已生成，可继续对话要求它调整';
    } else {
      note.textContent = _assistantTaskHasActiveTask()
        ? `当前任务：${taskTitle}`
        : '当前任务';
    }
  }
  if (regenerateBtn) {
    regenerateBtn.hidden = !isProductPreview;
    regenerateBtn.textContent = _activeProductPreview && _activeProductPreview.entry_generated ? '重新生成界面' : '生成产品界面';
    regenerateBtn.title = `让「${productPreviewName}」根据当前对话生成产品界面`;
    regenerateBtn.setAttribute('aria-label', regenerateBtn.title);
  }
  if (rollbackBtn) {
    rollbackBtn.hidden = !isProductPreview || !canRollback;
    rollbackBtn.disabled = !canRollback;
    rollbackBtn.textContent = '恢复上一版界面';
    rollbackBtn.title = canRollback
      ? `把「${productPreviewName}」的产品界面恢复到上一版 ${previousVersion}`
      : `「${productPreviewName}」还没有上一版可恢复`;
    rollbackBtn.setAttribute('aria-label', rollbackBtn.title);
  }
  if (productCapabilitiesBtn) {
    productCapabilitiesBtn.hidden = !isProductPreview;
    productCapabilitiesBtn.textContent = '产品能力';
    productCapabilitiesBtn.title = `配置「${productPreviewName}」的技能和工具`;
    productCapabilitiesBtn.setAttribute('aria-label', productCapabilitiesBtn.title);
  }
  if (collapseBtn) {
    collapseBtn.textContent = '收起';
    collapseBtn.title = `收起「${assistantTitle}」的产品界面，继续保留聊天`;
    collapseBtn.setAttribute('aria-label', collapseBtn.title);
  }
  if (moreBtn) {
    moreBtn.textContent = '更多';
    moreBtn.title = '产品界面操作';
    moreBtn.disabled = false;
    moreBtn.setAttribute('aria-label', moreBtn.title);
    moreBtn.onclick = toggleActiveProductPreviewMenu;
  }
  if (moreWrap) {
    moreWrap.hidden = !isProductPreview;
  }
}

function _focusActiveProductPreviewSurface() {
  const surface = $('activeProductSurface');
  if (!surface || surface.hidden) return false;
  surface.scrollIntoView({ behavior: 'smooth', block: 'start' });
  try { surface.focus({ preventScroll: true }); } catch (_err) {}
  return true;
}

async function openOrFocusTaskProductPreviewFromHeader() {
  if (_activeProductPreview && _focusActiveProductPreviewSurface()) return;
  if (typeof showToast === 'function') showToast('当前任务还没有生成产品界面');
}

function _syncTaskHeaderProductPreviewChipAction({ isCreate, hasTask, canOpenProductPreview, label }) {
  const productPreviewStatus = $('taskHeaderProductStatus');
  if (!productPreviewStatus) return;
  const actionable = !isCreate && hasTask && canOpenProductPreview;
  productPreviewStatus.classList.toggle('is-actionable', actionable);
  if (actionable) {
    productPreviewStatus.setAttribute('role', 'button');
    productPreviewStatus.setAttribute('tabindex', '0');
    productPreviewStatus.setAttribute('aria-label', _activeProductPreview ? `跳到当前产品界面：${label}` : `打开产品界面：${label}`);
    productPreviewStatus.onclick = () => openOrFocusTaskProductPreviewFromHeader();
    productPreviewStatus.onkeydown = event => {
      if (event.key !== 'Enter' && event.key !== ' ') return;
      event.preventDefault();
      openOrFocusTaskProductPreviewFromHeader();
    };
  } else {
    productPreviewStatus.removeAttribute('role');
    productPreviewStatus.removeAttribute('tabindex');
    productPreviewStatus.removeAttribute('aria-label');
    productPreviewStatus.onclick = null;
    productPreviewStatus.onkeydown = null;
  }
}

function _syncTaskHeaderStatus(hasTask = _assistantTaskHasActiveTask()) {
  const chatStatus = $('taskHeaderChatStatus');
  const productPreviewStatus = $('taskHeaderProductStatus');
  const chatText = chatStatus ? chatStatus.querySelector('span:last-child') : null;
  const productPreviewText = productPreviewStatus ? productPreviewStatus.querySelector('span:last-child') : null;
  const assistantTitle = window._currentAiAssistantTitle || window._currentAiProductTitle || '当前 AI 产品';
  const isCreate = _assistantKey() === 'create';
  const activeProductPreviewName = _activeProductPreview
    ? (_activeProductPreview.name || _activeProductPreview.id || '产品界面')
    : '';
  const isProductPreview = !!(_activeProductPreview && _activeProductPreview.product_preview);
  if (chatText) {
    chatText.textContent = isCreate
      ? '新建 AI 产品'
      : hasTask
        ? '当前任务'
        : '新任务';
  }
  if (productPreviewText) {
    if (isCreate) {
      productPreviewText.textContent = '生成预览';
    } else if (_activeProductPreview) {
      productPreviewText.textContent = isProductPreview ? '产品界面' : activeProductPreviewName;
    } else {
      productPreviewText.textContent = hasTask ? '按需生成界面' : '从消息开始';
    }
  }
  if (productPreviewStatus) {
    productPreviewStatus.classList.toggle('is-active-product', !isCreate && !!_activeProductPreview);
    const label = productPreviewText ? productPreviewText.textContent : '';
    const canOpenProductPreview = !!_activeProductPreview;
    productPreviewStatus.title = !isCreate && hasTask && canOpenProductPreview
      ? `跳到当前产品界面：${label}`
      : label;
    _syncTaskHeaderProductPreviewChipAction({ isCreate, hasTask, canOpenProductPreview, label });
  }
  if (chatStatus) {
    chatStatus.title = isCreate
      ? '描述要创建的 AI 产品'
      : hasTask
        ? `当前任务由「${assistantTitle}」处理`
        : `从这里开始「${assistantTitle}」的新任务`;
  }
}

function _syncAssistantSidebarIntro(hasTask = _assistantTaskHasActiveTask()) {
  const sub = $('assistantPanelSub');
  if (!sub) return;
  const assistantTitle = window._currentAiAssistantTitle || window._currentAiProductTitle || '当前 AI 产品';
  const isCreate = _assistantKey() === 'create';
  if (isCreate) {
    sub.textContent = '描述新产品。';
  } else if (hasTask) {
    sub.textContent = `${assistantTitle} 的任务`;
  } else {
    sub.textContent = '选择产品，开始任务。';
  }
}

function syncAssistantTaskUi() {
  const assistantTitle = window._currentAiAssistantTitle || window._currentAiProductTitle || 'PPT 设计师';
  const root = $('productCrumbRoot');
  const title = $('productModeTitle');
  const listTitle = $('assistantTaskListTitle');
  const search = $('sessionSearch');
  const input = $('msg');
  const home = $('assistantHome');
  const messagesShell = document.querySelector('.messages-shell');
  const body = $('productChatBody');
  const hasTask = _assistantTaskHasActiveTask();
  const taskTitle = _assistantTaskTitle();
  document.body.dataset.nextAiView = hasTask ? 'task' : 'assistant';
  if (body) body.dataset.nextAiView = hasTask ? 'task' : 'assistant';
  if (title) title.textContent = assistantTitle;
  if (root) {
    root.hidden = !hasTask;
    root.textContent = hasTask ? taskTitle : '';
    root.title = hasTask ? taskTitle : '';
  }
  if (listTitle) listTitle.textContent = _assistantKey() === 'create' ? '新产品' : '最近任务';
  if (search) search.placeholder = _assistantKey() === 'create'
    ? '创建后可搜索任务...'
    : '搜索当前产品任务...';
  if (input) {
    const object = AI_OBJECTS[_assistantKey()] || AI_OBJECTS.ppt;
    input.placeholder = hasTask
      ? `继续补充「${taskTitle}」这次任务...`
      : (object.placeholder || input.placeholder);
  }
  if (home) home.hidden = hasTask;
  if (messagesShell) messagesShell.hidden = !hasTask;
  if (!hasTask) {
    const empty = $('emptyState');
    if (empty) empty.style.display = 'none';
    _syncAssistantHome(AI_OBJECTS[_assistantKey()] || AI_OBJECTS.ppt);
  }
  _syncAssistantTaskContextStrip(hasTask);
  _syncAssistantTaskProgress(hasTask);
  if (_activeProductPreview) _syncProductPreviewCopy();
  _syncAssistantSidebarIntro(hasTask);
  _syncTaskHeaderStatus(hasTask);
  return true;
}

function deactivateProductPreviewInChat() {
  const activeProductPreviewName = _activeProductPreview ? (_activeProductPreview.name || _activeProductPreview.id) : '';
  const surface = $('activeProductSurface');
  const frame = $('activeProductFrame');
  const body = $('productChatBody');
  if (surface) surface.hidden = true;
  if (frame) frame.removeAttribute('src');
  if (body) body.classList.remove('has-active-product');
  _activeProductPreview = null;
  _syncProductPreviewMode(null);
  _syncAssistantTaskContextStrip();
  _syncAssistantTaskProgress();
  if (typeof showToast === 'function' && activeProductPreviewName) {
    showToast(`已收起「${activeProductPreviewName}」`);
  }
}

function openActiveProductPreviewWindow() {
  if (_activeProductPreview && _activeProductPreview.preview_url) {
    window.open(_activeProductPreview.preview_url, '_blank');
  }
}

function initNextAiAssistants() {
  try { localStorage.removeItem('next-ai-custom-assistants'); } catch (_err) {}
  renderAssistantList();
  hydrateProductsFromBackend();
  syncAssistantListMeta();
  syncAssistantTaskUi();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => initNextAiAssistants(), { once: true });
} else {
  initNextAiAssistants();
}
