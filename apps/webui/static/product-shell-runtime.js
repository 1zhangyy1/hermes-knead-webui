let _activeProductPreview = null;
let _lastTaskAssistantKind = 'ppt';
window._currentAiAssistantTitle = window._currentAiAssistantTitle || 'PPT Designer';
const NEXT_AI_TASK_ASSIGNMENTS_KEY = 'next-ai-session-assistant-assignments';
const NEXT_AI_TASK_TITLES_KEY = 'next-ai-session-task-titles';
let _backendProductAssistants = [];

const AI_OBJECTS = {
  general: {
    title: 'General AI',
    avatar: 'G',
    iconName: 'message-square',
    desc: 'Open-ended chat for quick questions, writing, analysis, and files.',
    homeDesc: 'Start with anything. Repeated work can be kneaded into its own AI.',
    placeholder: 'Say what you want to do...',
    productType: 'general',
    uiMode: 'chat_only',
    productLayout: 'chat_only',
    canvasLabel: '',
    suggestions: [
      ['Help me organize today’s work into clear next steps.', 'Plan my day'],
      ['Rewrite this copy so it is clearer and more professional.', 'Polish copy'],
      ['Analyze this problem and give me a few possible paths.', 'Analyze a problem']
    ]
  },
  ppt: {
    title: 'PPT Designer',
    avatar: 'P',
    iconName: 'presentation',
    desc: 'Make decks through chat, with outline, slides, and speaker notes when structure helps.',
    homeDesc: 'Tell me the topic, audience, and goal. I will shape the outline, slides, and speaker notes.',
    placeholder: 'Describe this deck, or upload materials...',
    productType: 'ppt',
    uiMode: 'workspace',
    productLayout: 'chat_left_canvas_right',
    canvasLabel: 'PPT workspace',
    suggestions: [
      ['Help me make a product intro deck. First confirm topic, audience, and outline.', 'Start from topic'],
      ['I have a document. Turn it into a presentation structure.', 'Use materials'],
      ['Help me improve an existing deck structure. Tell me what to change first.', 'Improve structure']
    ]
  },
  create: {
    title: 'Knead one',
    iconName: 'plus',
    desc: 'Describe a recurring job. It becomes an AI you can keep using and shaping.',
    placeholder: 'Describe the work you want this AI to handle...',
    suggestions: [
      ['I want an AI that keeps helping me make fundraising decks.', 'Fundraising decks'],
      ['I want an AI that keeps helping me write industry research reports.', 'Industry research'],
      ['I want an AI that keeps helping me analyze operations data.', 'Ops data']
    ]
  }
};

function _syncProductPreviewMode(activeProductPreview) {
  const title = $('productModeTitle');
  if (title && !syncAssistantTaskUi()) title.textContent = activeProductPreview ? (activeProductPreview.name || 'Workspace') : (window._currentAiAssistantTitle || window._currentAiProductTitle || 'PPT Designer');
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
    [/代码|编程|开发|bug|程序/, '代码工作台'],
    [/客服|售后|工单/, '客服处理师'],
    [/招聘|候选人|JD|岗位/, '招聘工作台'],
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
  if (/(师|专家|顾问|生成器|分析师|设计师|工作台)$/i.test(core)) return core.slice(0, 18);
  if (/生成|出图|绘图|画图|生图|图片|图像/.test(seed)) return `${core.replace(/(生成|制作|设计)$/g, '')}生成器`.slice(0, 18);
  if (/设计|视觉|海报|封面|装修|排版/.test(seed)) return `${core.replace(/设计$/g, '')}设计师`.slice(0, 18);
  if (/分析|数据|指标|报表|看板|复盘/.test(seed)) return `${core.replace(/分析$/g, '')}分析师`.slice(0, 18);
  if (/研究|调研|报告|竞品|行业/.test(seed)) return `${core.replace(/研究$/g, '')}研究师`.slice(0, 18);
  if (/规划|计划|路线|流程|项目/.test(seed)) return `${core.replace(/规划$/g, '')}规划师`.slice(0, 18);
  if (/写|写作|改写|润色|编辑|整理|总结/.test(seed)) return `${core.replace(/写作?$/g, '')}写作师`.slice(0, 18);
  return `${core} AI`.slice(0, 22);
}

function _registerCustomAssistant(assistant) {
  if (!assistant || !assistant.kind) return;
  if (_isBuiltinAssistantKind(assistant.kind)) return;
  if (!_customAssistantIsProductBacked(assistant)) return;
  const title = assistant.title || 'Custom AI';
  const starterKit = _assistantStarterKit(title, assistant.sourcePrompt || assistant.desc || '');
  const imageLike = /图片|图像|生图|绘图|文生图|画图|生成图|海报|封面|插画|头像|视觉|image/i.test(`${title} ${assistant.desc || ''} ${assistant.sourcePrompt || ''}`);
  const productType = assistant.productType || (imageLike ? 'image' : '');
  const tools = typeof _assistantNormalizeToolsets === 'function'
    ? _assistantNormalizeToolsets(assistant.tools)
    : (Array.isArray(assistant.tools) ? assistant.tools : []);
  AI_OBJECTS[assistant.kind] = {
    title,
    avatar: assistant.avatar || '',
    desc: assistant.desc || 'Owns the kind of work you describe. A workspace appears when structure helps.',
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
    productLayout: assistant.productLayout || assistant.product_layout || assistant.layout || '',
    canvasLabel: assistant.canvasLabel || assistant.canvas_label || '',
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

function _assistantUniqueCustomTitle(title, fallback = 'Custom AI') {
  const base = String(title || fallback || 'Custom AI').replace(/\s+/g, ' ').trim() || 'Custom AI';
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
  if (typeof _assistantUsesProductCanvas === 'function' && !_assistantUsesProductCanvas(assistant)) return false;
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
  if (/图片|图像|生图|绘图|海报|插画|头像|视觉|image/i.test(title)) return '图片';
  if (/PPT|演示|路演|幻灯/.test(title)) return 'PPT';
  if (/研究|调研|资料|报告/.test(title)) return '研究';
  if (/数据|运营|指标|表格/.test(title)) return '数据';
  return '自定义';
}

function _assistantBaseMeta(kind, object) {
  if (kind === 'general') return '聊天';
  if (object && object.custom) return _assistantShortMeta(object);
  if (kind === 'ppt') return '演示文稿';
  return _assistantShortMeta(object);
}

function _assistantIsChatOnlyProduct(object) {
  if (!object) return false;
  if (typeof _assistantProductLayout === 'function') return _assistantProductLayout(object) === 'chat_only';
  return String(object.uiMode || object.ui_mode || '') === 'chat_only';
}

function _assistantListMeta(kind, object) {
  if (!kind || kind === 'create') return '';
  if (object && (object.productId || object.backendProduct)) {
    const usesProductCanvas = typeof _assistantCanShowProductCanvas === 'function'
      ? _assistantCanShowProductCanvas(object)
      : typeof _assistantUsesProductCanvas === 'function'
      ? _assistantUsesProductCanvas(object)
      : !_assistantIsChatOnlyProduct(object);
    if (!usesProductCanvas) return _assistantBaseMeta(kind, object);
    const status = String(object.uiStatus || object.ui_status || '').toLowerCase();
    if (status === 'generating') return '生成中';
    if (status === 'failed') return '可重试';
    if (status === 'ready') return '界面';
    return '待生成';
  }
  return _assistantBaseMeta(kind, object);
}

function syncAssistantListMeta() {
  document.querySelectorAll('.ai-object-item[data-ai-object]').forEach(btn => {
    const kind = btn.dataset.aiObject;
    if (!kind) return;
    const object = AI_OBJECTS[kind] || null;
    const avatar = btn.querySelector('.ai-object-avatar');
    _renderAssistantAvatar(avatar, kind, object, 16);
    if (kind === 'create') return;
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
    _renderAssistantAvatar(avatar, assistant.kind, object, 16);
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
  if (/融资|路演|BP|投资人|fundrais|investor|pitch/i.test(text)) return 'Fundraising Deck AI';
  if (/(销售|提案|客户|方案|sales|proposal|client)/i.test(text) && /PPT|幻灯|演示|汇报|deck|slides|presentation/i.test(text)) return 'Sales Deck AI';
  if (/行业.*研究|研究.*报告|行业.*报告/.test(text)) return '行业研究产品';
  if (/竞品/.test(text)) return '竞品研究产品';
  if (/运营.*数据|数据.*运营/.test(text)) return '运营数据分析师';
  if (/PPT|幻灯|演示|汇报|deck|slides|presentation/i.test(text)) return 'PPT Designer';
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
  return (cleaned ? `${cleaned.slice(0, 18)} AI` : 'Custom AI');
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
      placeholder: 'Describe the image content, style, size, or upload a reference...',
      suggestions: [
        ['Create a product launch poster. First confirm the theme, style, and size.', 'Create a poster'],
        ['Create an AI avatar image for me.', 'Create an avatar'],
        ['Turn this text into an illustration prompt and generate the image.', 'Text to illustration']
      ]
    };
  }
  if (isPpt && isSales) {
    return {
      placeholder: 'Describe this sales proposal deck, client, goal, or upload material...',
      suggestions: [
        ['Create a sales proposal deck. First confirm the client, pain points, and solution highlights.', 'Create sales proposal'],
        ['Turn client material into a proposal outline.', 'Material to outline'],
        ['Improve the story and slide structure of this proposal.', 'Improve structure']
      ]
    };
  }
  if (isPpt && isPitch) {
    return {
      placeholder: 'Describe this pitch deck, goal, audience, or upload material...',
      suggestions: [
        ['Create a fundraising deck. First confirm investors, round, and core story.', 'Create pitch deck'],
        ['Turn fundraising material into a pitch outline.', 'Material to pitch outline'],
        ['Improve the deck structure and speaker notes.', 'Improve structure and notes']
      ]
    };
  }
  if (isPpt) {
    return {
      placeholder: 'Describe this deck, or upload material...',
      suggestions: [
        ['Create a deck. First confirm topic, audience, slide count, and core story.', 'Create a deck'],
        ['Turn existing material into a presentation outline.', 'Material to outline'],
        ['Improve this deck structure and speaker notes.', 'Improve structure and notes']
      ]
    };
  }
  if (isResearch) {
    return {
      placeholder: 'Enter the question you want to research...',
      suggestions: [
        ['Research this direction. First list the question frame and sources.', 'Research a direction'],
        ['Organize competitor differences and positioning.', 'Compare competitors'],
        ['Draft research conclusions.', 'Draft conclusions']
      ]
    };
  }
  if (isData) {
    return {
      placeholder: 'Describe the data to analyze, or upload a spreadsheet...',
      suggestions: [
        ['Analyze this data. First tell me which metrics matter.', 'Analyze metrics'],
        ['Organize these metrics into a dashboard structure.', 'Create dashboard structure'],
        ['Explain recent data changes.', 'Explain changes']
      ]
    };
  }
  return {
    placeholder: title ? `Tell "${title}" what you want to finish...` : 'Describe what you want to finish...',
    suggestions: [
      ['Break this task into executable steps.', 'Break down task'],
      ['Ask me a few key questions first.', 'Clarify requirements'],
      ['Draft the first version.', 'Draft first version']
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
  const isInteractive = /c\.?ai|character|角色|人物|游戏|剧情|npc|rpg|虚拟人|陪伴|互动/.test(title + sourcePrompt);
  const kind = `custom-${_assistantSlug(title)}-${Date.now().toString(36)}`;
  const starterKit = _assistantStarterKit(title, sourcePrompt);
  const desc = isPpt
    ? 'Turns material, ideas, and audience goals into a clear presentation. Opens a workspace when structure helps.'
    : isImage
      ? '把一句话、参考图和风格要求转成可执行的图片生成任务，并优先调用可用的图片生成能力产出结果。'
      : isResearch
        ? 'Breaks down questions, gathers sources, organizes evidence, and drafts research conclusions.'
        : isData
          ? 'Helps you understand metrics, organize sheets, spot trends, and turn data into conclusions.'
          : isInteractive
            ? 'Uses its own workspace for interactive experiences, so characters, story, and play can be selected and shaped directly.'
            : 'Owns the kind of work you describe. A workspace appears when the task needs structure.';
  const placeholder = starterKit.placeholder;
  const suggestions = starterKit.suggestions;
  const productType = isImage ? 'image' : isPpt ? 'ppt' : isResearch ? 'research' : isData ? 'data' : isInteractive ? 'interactive' : 'general';
  const productLayout = isInteractive ? 'canvas_full' : (isImage || isPpt || isResearch || isData) ? 'chat_left_canvas_right' : 'chat_center';
  const canvasLabel = isPpt ? 'PPT workspace' : isImage ? 'Image workspace' : isResearch ? 'Research workspace' : isData ? 'Data workspace' : isInteractive ? 'Interactive workspace' : 'Workspace';
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
    productLayout,
    canvasLabel,
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
  const interfaceName = '自动生成';
  if (overlay && applyBtn && cancelBtn && draft) {
    const setText = (id, value) => {
      const el = $(id);
      if (el) el.textContent = value || '';
    };
    const isPersonalVersion = !!draft.baseAssistantTitle;
    setText('assistantCreateTitle', isPersonalVersion ? 'Create a personal version?' : 'Create this AI?');
    setText(
      'assistantCreateDesc',
      isPersonalVersion
        ? `Create a personal version based on "${draft.baseAssistantTitle}". Open it, keep chatting, and a workspace will appear when structure helps.`
        : 'It will appear in the AI shelf. Open it, keep chatting, and a workspace will appear when structure helps.'
    );
    setText('assistantCreateName', draft.title);
    setText('assistantCreateSource', draft.sourcePrompt || 'I want to create a new AI.');
    setText('assistantCreatePreviewAvatar', _assistantAvatarLabel(draft.kind, draft));
    setText('assistantCreateDuty', draft.desc);
    const tasks = $('assistantCreateTasks');
    if (tasks) {
      tasks.innerHTML = '';
      const labels = taskLabels.length ? taskLabels : ['Keep going'];
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
      if (dialog) {
        dialog.scrollTop = 0;
        dialog.setAttribute('tabindex', '-1');
      }
      const initialFocus = dialog || applyBtn;
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
    `Name: ${draft.title}`,
    `Role: ${draft.desc}`,
    `Starting prompt: ${draft.placeholder}`,
    `Suggested tasks: ${taskLabels.join(' / ') || 'Keep going'}`,
    `Workspace: ${interfaceName}`,
    '',
    'It will appear in the AI shelf. Open it, keep chatting, and a workspace will appear when structure helps.'
  ].join('\n');
  if (typeof showConfirmDialog === 'function') {
    return showConfirmDialog({
      title: 'Knead one',
      message,
      confirmLabel: 'Create and open',
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
    product_layout: draft && (draft.productLayout || draft.product_layout || draft.layout) || '',
    canvas_label: draft && (draft.canvasLabel || draft.canvas_label) || '',
    skills: Array.isArray(draft && draft.skills) ? draft.skills : [],
    tools
  };
}

async function _createProductFromAssistantDraft(draft) {
  if (!draft || !draft.title) throw new Error('缺少产品信息');
  const created = await api('/api/products/create', {
    method: 'POST',
    body: JSON.stringify(_assistantProductPayloadFromDraft(draft))
  });
  const product = created && created.product ? created.product : null;
  const saved = typeof _productToCustomAssistant === 'function' ? _productToCustomAssistant(product) : null;
  if (!saved || !saved.productId) throw new Error('No productId was returned after creating this AI.');
  _customAssistantsWrite(_mergeCustomAssistants(_customAssistantsRead(), [saved]));
  _registerCustomAssistant(saved);
  return saved;
}

async function _saveProductBackedAssistant(nextAssistant) {
  const productId = String(nextAssistant && (nextAssistant.productId || nextAssistant.product_id) || '').trim();
  if (!productId) throw new Error('这个产品缺少 productId');
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
    if (typeof showToast === 'function') showToast('Describe the AI you want to create first.');
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
      showToast(started ? `Opened existing AI and started its workspace: ${existing.title}` : `Opened existing AI: ${existing.title}`);
    }
    return existing;
  }
  const ok = await confirmAssistantCreatePreview(draft);
  if (!ok) return null;
  let savedDraft = null;
  try {
    savedDraft = await _createProductFromAssistantDraft(draft);
  } catch (err) {
    if (typeof showToast === 'function') showToast(`Create failed: ${err && err.message || err}`, 3200, 'error');
    return null;
  }
  renderAssistantList();
  openAssistantHome(savedDraft.kind);
  if (typeof showToast === 'function') showToast(`Created AI: ${savedDraft.title}`);
  _maybeStartInitialProductUiForExistingAssistant(savedDraft, text);
  return savedDraft;
}

async function createAssistantFromPrompt(prompt) {
  return createProductFromPrompt(prompt);
}

async function renameCurrentCustomAssistant() {
  const kind = _assistantKey();
  const assistant = _customAssistantByKind(kind);
  if (!assistant) {
    if (typeof showToast === 'function') showToast('Only AIs you created can be renamed.');
    return null;
  }
  const nextTitleRaw = typeof showPromptDialog === 'function'
    ? await showPromptDialog({
      title: '重命名产品',
      message: '这个名称会显示在左侧产品列表和产品主页。',
        value: assistant.title,
        confirmLabel: 'Save'
      })
    : window.prompt('重命名产品', assistant.title);
  const nextTitle = String(nextTitleRaw || '').replace(/\s+/g, ' ').trim();
  if (!nextTitle || nextTitle === assistant.title) return assistant;
  if (_customAssistantTitleExists(nextTitle, kind)) {
    if (typeof showToast === 'function') showToast('已经有同名产品');
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
    if (typeof showToast === 'function') showToast('Built-in AIs cannot be deleted.');
    return false;
  }
  const ok = typeof showConfirmDialog === 'function'
    ? await showConfirmDialog({
        title: `Delete "${assistant.title}"?`,
        message: 'This only deletes the AI object. Past tasks stay in history and move back to the closest built-in AI.',
        confirmLabel: 'Delete',
        danger: true,
        focusCancel: true
      })
    : window.confirm(`Delete "${assistant.title}"?`);
  if (!ok) return false;
  if ((assistant.backendProduct || assistant.productId) && assistant.productId) {
    try {
      await api('/api/products/delete', {
        method: 'POST',
        body: JSON.stringify({ product_id: assistant.productId })
      });
    } catch (err) {
      if (typeof showToast === 'function') showToast(`Delete failed: ${err && err.message || err}`, 3200, 'error');
      return false;
    }
  }
  const deleted = _deleteCustomAssistantKind(kind);
  if (!deleted) return false;
  renderAssistantList();
  openAssistantHome('general');
  if (typeof renderSessionListFromCache === 'function') renderSessionListFromCache();
  if (typeof showToast === 'function') showToast(`Deleted AI: ${assistant.title}`);
  return true;
}

function _assistantKey() {
  return window._currentAiAssistantKind || 'ppt';
}

function _assistantObject(kind = _assistantKey()) {
  return AI_OBJECTS[kind] || AI_OBJECTS.ppt;
}

function _assistantDirectoryMode(hasTask = _assistantTaskHasActiveTask()) {
  const raw = document.body && document.body.dataset ? document.body.dataset.nextAiDirectory : '';
  if (raw === 'library' || raw === 'product') return raw;
  if (window._nextAiDirectory === 'library' || window._nextAiDirectory === 'product') return window._nextAiDirectory;
  return hasTask ? 'product' : 'library';
}

function _setAssistantDirectoryMode(mode) {
  const next = mode === 'library' ? 'library' : 'product';
  window._nextAiDirectory = next;
  if (document.body && document.body.dataset) document.body.dataset.nextAiDirectory = next;
  return next;
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
  _setAssistantDirectoryMode('product');
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

function assistantProductLabelForSession(session) {
  const kind = assistantKindForLoadedSession(session);
  const object = AI_OBJECTS[kind] || AI_OBJECTS.general || AI_OBJECTS.ppt;
  return object && object.title ? object.title : 'General AI';
}

function _assistantAvatarLabel(kind = _assistantKey(), object) {
  if (kind === 'create') return '+';
  const title = object && object.title ? object.title : (window._currentAiAssistantTitle || 'AI product');
  const avatar = object && object.avatar ? String(object.avatar).trim() : '';
  if (avatar) return avatar.slice(0, 2).toUpperCase();
  if (/ppt/i.test(kind) || /PPT/.test(title)) return 'P';
  if (kind === 'research') return 'R';
  if (kind === 'data') return 'D';
  if (kind === 'general') return 'G';
  return String(title).trim().slice(0, 1).toUpperCase() || 'A';
}

function _assistantIconName(kind = _assistantKey(), object) {
  const title = String(object && object.title || '').toLowerCase();
  const type = String(object && (object.productType || object.product_type) || '').toLowerCase();
  const label = `${kind || ''} ${title} ${type}`;
  if (object && object.iconName) return object.iconName;
  if (kind === 'create') return 'plus';
  if (kind === 'general' || type === 'general') return 'message-square';
  if (/ppt|deck|slide|presentation|演示|幻灯|汇报/.test(label)) return 'presentation';
  if (/game|角色|character|role|c\\.ai|chatbot|interactive/.test(label)) return 'gamepad-2';
  if (/image|avatar|poster|illustration|海报|头像|图片|图像|生图|插画/.test(label)) return 'image';
  if (/research|report|search|研究|调研|报告|竞品/.test(label)) return 'search';
  if (/data|analytics|table|chart|运营|数据|指标|表格/.test(label)) return 'chart-column';
  if (/timer|time|pomodoro|番茄|计时/.test(label)) return 'clock';
  return '';
}

function _renderAssistantAvatar(el, kind = _assistantKey(), object, size = 16) {
  if (!el) return;
  const iconName = _assistantIconName(kind, object);
  el.classList.toggle('has-product-icon', !!iconName);
  el.classList.toggle('has-avatar-label', !iconName);
  if (iconName) el.dataset.productIcon = iconName;
  else delete el.dataset.productIcon;
  if (iconName && typeof li === 'function') {
    el.innerHTML = li(iconName, size);
    return;
  }
  el.textContent = _assistantAvatarLabel(kind, object);
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
  const assistantTitle = object.title || 'AI product';
  const home = $('assistantHome');
  const title = $('assistantHomeTitle');
  const desc = $('assistantHomeDesc');
  const avatar = $('assistantHomeAvatar');
  const eyebrow = $('assistantHomeEyebrow');
  const guide = $('assistantHomeGuide');
  const origin = $('assistantHomeOrigin');
  const nextStep = $('assistantHomeNextStep');
  const manage = $('assistantHomeManage');
  const newTaskLabel = $('newTaskPrimaryLabel');
  const newTaskBtn = $('newTaskPrimaryBtn');
  const newTaskIcon = $('newTaskPrimaryIcon');
  const isChatOnlyProduct = _assistantIsChatOnlyProduct(object);
  const usesProductCanvas = typeof _assistantCanShowProductCanvas === 'function'
    ? _assistantCanShowProductCanvas(object)
    : typeof _assistantUsesProductCanvas === 'function'
    ? _assistantUsesProductCanvas(object)
    : !isChatOnlyProduct;
  if (home) home.classList.toggle('is-create', isCreate);
  if (title) title.textContent = assistantTitle;
  if (desc) {
    desc.textContent = isCreate
      ? (object.desc || 'Describe a repeatable job.')
      : (object.homeDesc || object.desc || 'Say what you want to finish. A workspace appears when the task needs structure.');
  }
  _renderAssistantAvatar(avatar, kind, object, 22);
  if (eyebrow) eyebrow.textContent = isCreate ? 'Knead one' : object.custom ? 'Your AI' : 'Selected';
  if (guide) {
    guide.textContent = isCreate
      ? 'Say what it should own over time.'
      : 'Start with one sentence.';
  }
  if (origin) {
    if (isCreate) {
      origin.hidden = false;
      origin.textContent = 'After creation, it appears in the AI shelf and keeps its own skills, tasks, and workspace.';
      origin.removeAttribute('title');
    } else {
      origin.hidden = true;
      origin.textContent = '';
      origin.removeAttribute('title');
    }
  }
  if (nextStep) {
    if (isCreate) {
      _renderAssistantHomeActionBar(nextStep, 'Confirm to open this AI. If structure helps, it will create the first workspace.');
    } else if (!usesProductCanvas) {
      nextStep.hidden = true;
      nextStep.innerHTML = '';
    } else if (object.productId && String(object.uiStatus || 'empty') === 'failed') {
      const failureReason = String(object.uiErrorMessage || '').trim();
      _renderAssistantHomeActionBar(
        nextStep,
        failureReason
          ? `${failureReason} Keep chatting, or rebuild the workspace first.`
          : 'Workspace generation failed. Keep chatting, or rebuild it first.',
        'Rebuild workspace',
        () => requestCurrentProductUiGeneration()
      );
    } else if (object.productId && String(object.uiStatus || 'empty') === 'empty') {
      _renderAssistantHomeActionBar(
        nextStep,
        'This AI does not have a fixed workspace yet. Chat first, or create the first version.',
        'Create workspace',
        () => requestCurrentProductUiGeneration()
      );
    } else if (object.productId && String(object.uiStatus || 'empty') === 'generating') {
      _renderAssistantHomeActionBar(nextStep, 'Creating this AI workspace. It will refresh when ready.');
    } else {
      nextStep.hidden = true;
      nextStep.innerHTML = '';
    }
  }
  if (manage) manage.hidden = true;
  if (newTaskLabel) newTaskLabel.textContent = isCreate ? 'Back to current AI' : 'New task';
  if (newTaskBtn) {
    const lastObject = AI_OBJECTS[_lastTaskAssistantKind] || AI_OBJECTS.general || AI_OBJECTS.ppt;
    const lastTitle = lastObject && lastObject.title ? lastObject.title : 'Current AI';
    newTaskBtn.title = isCreate ? `Back to a new task with ${lastTitle}` : `Start a new task with ${assistantTitle}`;
    newTaskBtn.setAttribute('aria-label', newTaskBtn.title);
    newTaskBtn.classList.toggle('is-return', isCreate);
  }
  if (newTaskIcon) {
    newTaskIcon.innerHTML = isCreate
      ? '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M19 12H5"/><path d="m12 19-7-7 7-7"/></svg>'
      : '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5v14"/><path d="M5 12h14"/></svg>';
  }
}

function selectAiObject(kind = 'ppt') {
  const object = AI_OBJECTS[kind] || AI_OBJECTS.ppt;
  const previousKind = window._currentAiAssistantKind || '';
  window._currentAiAssistantKind = kind;
  window._currentAiAssistantTitle = object.title;
  window._currentAiProductTitle = object.title;
  if (previousKind && previousKind !== kind && document.body && document.body.dataset) {
    document.body.dataset.nextAiProductAdjust = 'closed';
    document.body.dataset.nextAiChatPanel = 'closed';
    delete document.body.dataset.nextAiChatPanelManual;
  }
  document.body.dataset.nextAiProductLayout = typeof _assistantProductLayout === 'function'
    ? _assistantProductLayout(object)
    : (_assistantIsChatOnlyProduct(object) ? 'chat_only' : 'chat_center');
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
  if (previewUrl && _assistantTaskHasActiveTask() && typeof refreshCurrentProductPreview === 'function') refreshCurrentProductPreview({silent:true});
  else _hideProductPreviewIfActive();
  if (typeof renderSessionListFromCache === 'function') renderSessionListFromCache();
}

function startAssistantNewTask() {
  const kind = _assistantKey() === 'create' ? (_lastTaskAssistantKind || 'general') : _assistantKey();
  openAssistantHome(kind);
}

function openAssistantLanding(options = {}) {
  const kind = _assistantKey() === 'create' ? (_lastTaskAssistantKind || 'general') : _assistantKey();
  openAssistantHome(kind, { ...options, directory: 'library' });
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
    if (typeof showToast === 'function') showToast('This task is still running. Start a new one when it finishes.');
    return;
  }
  _setAssistantDirectoryMode(options.directory === 'library' ? 'library' : 'product');
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
  _hideProductPreviewIfActive();
  syncAssistantTaskUi();
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
  if (/^(请)?基于.*(产品画布|产品界面|工作界面|PPT 工作界面|继续优化)/.test(title)) return true;
  if (/^生成.*产品(画布|界面)$/.test(title)) return true;
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
  return (_assistantTaskCompactDisplayTitle(stableStoredTitle) || _assistantTaskFirstUserTitle() || 'Current task').slice(0, 48);
}

function assistantChromeTitleState() {
  const assistantTitle = window._currentAiAssistantTitle || window._currentAiProductTitle || 'PPT Designer';
  const hasTask = _assistantTaskHasActiveTask();
  const taskTitle = hasTask ? _assistantTaskTitle() : '';
  const main = hasTask ? taskTitle : assistantTitle;
  const sub = hasTask ? assistantTitle : 'AI product';
  return {
    main,
    sub,
    documentTitle: hasTask ? `${taskTitle} — ${assistantTitle} — Knead` : `${assistantTitle} — Knead`,
  };
}

function assistantDisplayTitleForSession(session) {
  const rawTitle = session ? _assistantTaskNormalizeTitle(session.display_title || session._state_db_title || session.title) : '';
  if (!_assistantTaskLooksGenericTitle(rawTitle) && !_assistantTaskLooksProductUiCommand(rawTitle)) return _assistantTaskCompactDisplayTitle(rawTitle) || rawTitle || 'Untitled';
  const storedTitle = session && session.session_id ? _assistantTaskNormalizeTitle(_assistantTaskTitlesRead()[session.session_id]) : '';
  if (storedTitle && !_assistantTaskLooksGenericTitle(storedTitle) && !_assistantTaskLooksProductUiCommand(storedTitle)) return _assistantTaskCompactDisplayTitle(storedTitle) || storedTitle;
  const hintedTitle = _assistantTaskTitleFromSessionHints(session);
  if (hintedTitle) return hintedTitle;
  return rawTitle && !_assistantTaskLooksGenericTitle(rawTitle) && !_assistantTaskLooksProductUiCommand(rawTitle) ? rawTitle : 'New task';
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
  const hasProductPreview = !!(_activeProductPreview && _activeProductPreview.product_preview);
  if (!hasTask || !hasProductPreview) {
    strip.hidden = true;
    if (kicker) kicker.textContent = 'Workspace';
    if (title) title.textContent = '';
    if (desc) desc.textContent = '';
    return;
  }
  strip.hidden = false;
  if (kicker) kicker.textContent = 'Workspace';
  if (title) title.textContent = (_activeProductPreview && (_activeProductPreview.name || _activeProductPreview.id)) || 'Current workspace';
  if (desc) {
    desc.textContent = 'The workspace is open. Keep chatting to refine the task.';
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
  const productUiItem = document.querySelector('.assistant-task-progress-product-ui');
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
  const assistantTitle = window._currentAiAssistantTitle || window._currentAiProductTitle || 'current AI';
  const object = _assistantObject();
  const usesProductCanvas = typeof _assistantCanShowProductCanvas === 'function'
    ? _assistantCanShowProductCanvas(object)
    : typeof _assistantUsesProductCanvas === 'function'
    ? _assistantUsesProductCanvas(object)
    : !_assistantIsChatOnlyProduct(object);
  progress.classList.toggle('is-running', isRunning);
  progress.classList.remove('is-idle');
  if (dot) dot.setAttribute('aria-label', '任务运行中');
  if (title) title.textContent = isInit ? 'Creating the first workspace' : 'Working on this task';
  if (desc) {
    desc.textContent = isInit
      ? 'Keep adding topic, style, and output requirements.'
      : `"${assistantTitle}" is working. You can keep adding requirements.`;
  }
  if (productUiItem) productUiItem.hidden = !usesProductCanvas;
  if (productUiKicker) productUiKicker.textContent = 'Workspace';
  if (usesProductCanvas && productUi) {
    if (hasProductPreview) {
      productUi.textContent = (_activeProductPreview && _activeProductPreview.name) || 'Current workspace';
    } else if (isInit) {
      productUi.textContent = 'Creating first version';
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
  const assistantTitle = window._currentAiAssistantTitle || window._currentAiProductTitle || 'Current AI';
  const taskTitle = _assistantTaskTitle();
  const isProductPreview = !!(_activeProductPreview && _activeProductPreview.product_preview);
  const productPreviewName = _activeProductPreview
    ? (_activeProductPreview.name || _activeProductPreview.id)
    : 'Workspace';
  const previousVersion = _activeProductPreview && _activeProductPreview.previous_version ? _activeProductPreview.previous_version : '';
  const canRollback = !!(_activeProductPreview && _activeProductPreview.can_rollback && previousVersion);
  if (kicker) kicker.textContent = isProductPreview ? 'Workspace' : assistantTitle;
  if (nameEl) nameEl.textContent = productPreviewName;
  if (versionEl) {
    versionEl.textContent = isProductPreview && canRollback ? ' · previous version available' : '';
    versionEl.title = isProductPreview && canRollback ? `可以恢复到上一版 ${previousVersion}` : '';
  }
  if (note) {
    if (isProductPreview) {
      const uiStatus = String(_activeProductPreview && _activeProductPreview.ui_status || '');
      note.textContent = uiStatus === 'generating'
        ? 'Creating workspace'
        : uiStatus === 'failed'
          ? (_activeProductPreview.ui_error_message || 'Workspace needs to be rebuilt')
          : !_activeProductPreview.entry_generated
            ? 'No workspace yet. Keep chatting, or create the first version.'
            : canRollback
              ? 'Ready. Keep chatting to shape it, or restore the previous version.'
              : 'Ready. Keep chatting to shape it.';
    } else {
      note.textContent = _assistantTaskHasActiveTask()
        ? `Current task: ${taskTitle}`
        : 'Workspace appears when needed';
    }
  }
  if (regenerateBtn) {
    regenerateBtn.hidden = !isProductPreview;
    regenerateBtn.textContent = _activeProductPreview && _activeProductPreview.entry_generated ? 'Rebuild workspace' : 'Create first version';
    regenerateBtn.title = `Create a workspace for "${productPreviewName}" from the current chat`;
    regenerateBtn.setAttribute('aria-label', regenerateBtn.title);
  }
  if (rollbackBtn) {
    rollbackBtn.hidden = !isProductPreview || !canRollback;
    rollbackBtn.disabled = !canRollback;
    rollbackBtn.textContent = 'Restore previous';
    rollbackBtn.title = canRollback
      ? `把「${productPreviewName}」恢复到上一版 ${previousVersion}`
      : `「${productPreviewName}」还没有上一版可恢复`;
    rollbackBtn.setAttribute('aria-label', rollbackBtn.title);
  }
  if (productCapabilitiesBtn) {
    productCapabilitiesBtn.hidden = !isProductPreview;
    productCapabilitiesBtn.textContent = 'Skills and tools';
    productCapabilitiesBtn.title = `调整「${productPreviewName}」的长期能力和可用工具`;
    productCapabilitiesBtn.setAttribute('aria-label', productCapabilitiesBtn.title);
  }
  if (collapseBtn) {
    collapseBtn.textContent = 'Hide';
    collapseBtn.title = `Hide "${assistantTitle}" workspace. Chat stays available.`;
    collapseBtn.setAttribute('aria-label', collapseBtn.title);
  }
  if (moreBtn) {
    moreBtn.textContent = 'More';
    moreBtn.title = 'Workspace actions';
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
  if (typeof refreshCurrentProductPreview === 'function') {
    const opened = await refreshCurrentProductPreview({ focus: true, reason: 'header-open-product-preview' });
    if (opened) return;
  }
  if (typeof showToast === 'function') showToast('This task does not have a workspace yet.');
}

async function toggleTaskProductPreviewFromHeader() {
  if (_activeProductPreview) {
    if (typeof _hideProductPreviewIfActive === 'function') {
      _hideProductPreviewIfActive();
    } else {
      deactivateProductPreviewInChat();
    }
    return;
  }
  await openOrFocusTaskProductPreviewFromHeader();
}

function _currentProductLayoutForTaskHeader(object = _assistantObject()) {
  if (typeof _assistantEffectiveProductLayout === 'function') return _assistantEffectiveProductLayout(object);
  if (typeof _assistantProductLayout === 'function') return _assistantProductLayout(object);
  return _assistantIsChatOnlyProduct(object) ? 'chat_only' : 'chat_center';
}

function _isCanvasFullProductUseMode(object = _assistantObject()) {
  return _assistantTaskHasActiveTask() && _currentProductLayoutForTaskHeader(object) === 'canvas_full' && !!_activeProductPreview;
}

function setCurrentProductAdjustMode(open, options = {}) {
  const next = !!open;
  document.body.dataset.nextAiProductAdjust = next ? 'open' : 'closed';
  if (next) document.body.dataset.nextAiChatPanel = 'closed';
  const adjustHeader = $('productAdjustPanelHeader');
  if (adjustHeader) adjustHeader.hidden = !next;
  // 走完整同步,让侧画布(PPT)的 composer 文案、开关按钮标签随用/调切换刷新。
  if (typeof syncAssistantTaskUi === 'function') syncAssistantTaskUi();
  else _syncTaskHeaderStatus();
  if (next && options.focus !== false) {
    const input = $('msg');
    if (input) {
      setTimeout(() => {
        try { input.focus(); } catch (_err) {}
      }, 0);
    }
  }
}

function toggleCurrentProductAdjustMode() {
  setCurrentProductAdjustMode(document.body.dataset.nextAiProductAdjust !== 'open');
}

function setCurrentProductChatPanelMode(open, options = {}) {
  const next = !!open;
  document.body.dataset.nextAiChatPanel = next ? 'open' : 'closed';
  if (!(options && options.auto)) {
    document.body.dataset.nextAiChatPanelManual = next ? 'open' : 'closed';
  }
  if (next) {
    document.body.dataset.nextAiProductAdjust = 'closed';
    const adjustHeader = $('productAdjustPanelHeader');
    if (adjustHeader) adjustHeader.hidden = true;
  }
  if (typeof syncAssistantTaskUi === 'function') syncAssistantTaskUi();
  else _syncTaskHeaderStatus();
  if (next && options.focus !== false) {
    const input = $('msg');
    if (input) {
      setTimeout(() => {
        try { input.focus(); } catch (_err) {}
      }, 0);
    }
  }
}

function toggleCurrentProductChatPanelMode() {
  setCurrentProductChatPanelMode(document.body.dataset.nextAiChatPanel !== 'open');
}

window.setCurrentProductAdjustMode = setCurrentProductAdjustMode;
window.toggleCurrentProductAdjustMode = toggleCurrentProductAdjustMode;
window.setCurrentProductChatPanelMode = setCurrentProductChatPanelMode;
window.toggleCurrentProductChatPanelMode = toggleCurrentProductChatPanelMode;

function _syncTaskHeaderProductPreviewChipAction({ isCreate, hasTask, canOpenProductPreview, label }) {
  const productPreviewStatus = $('taskHeaderProductStatus');
  if (!productPreviewStatus) return;
  const actionable = !isCreate && hasTask && canOpenProductPreview;
  productPreviewStatus.classList.toggle('is-actionable', actionable);
  if (actionable) {
    productPreviewStatus.setAttribute('role', 'button');
    productPreviewStatus.setAttribute('tabindex', '0');
    productPreviewStatus.setAttribute('aria-label', _activeProductPreview ? `Hide workspace: ${label}` : `Show workspace: ${label}`);
    productPreviewStatus.onclick = () => toggleTaskProductPreviewFromHeader();
    productPreviewStatus.onkeydown = event => {
      if (event.key !== 'Enter' && event.key !== ' ') return;
      event.preventDefault();
      toggleTaskProductPreviewFromHeader();
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
  const assistantTitle = window._currentAiAssistantTitle || window._currentAiProductTitle || 'Current AI';
  const isCreate = _assistantKey() === 'create';
  const object = _assistantObject();
  const canAdjustProduct = !isCreate && !!(object && object.productId);
  const usesProductCanvas = isCreate || (
    typeof _assistantCanShowProductCanvas === 'function'
      ? _assistantCanShowProductCanvas(object)
      : typeof _assistantUsesProductCanvas === 'function'
      ? _assistantUsesProductCanvas(object)
      : !_assistantIsChatOnlyProduct(object)
  );
  const activeProductPreviewName = _activeProductPreview
    ? (_activeProductPreview.name || _activeProductPreview.id || 'Workspace')
    : '';
  const isProductPreview = !!(_activeProductPreview && _activeProductPreview.product_preview);
  const adjustOpen = document.body.dataset.nextAiProductAdjust === 'open';
  const chatPanelOpen = document.body.dataset.nextAiChatPanel === 'open';
  const canvasOpen = usesProductCanvas && !!_activeProductPreview;
  const canToggleChatPanel = !isCreate && hasTask && canvasOpen && _currentProductLayoutForTaskHeader(object) === 'chat_left_canvas_right';
  const canOpenProductPreview = usesProductCanvas && !!(
    _activeProductPreview ||
    typeof _assistantHasGeneratedProductCanvas === 'function' && _assistantHasGeneratedProductCanvas(object)
  );
  // 用/调是产品级入口:不依赖是否已经长出画布。
  const adjustToggle = $('taskHeaderAdjustToggle');
  if (adjustToggle) {
    adjustToggle.hidden = !canAdjustProduct;
    if (canAdjustProduct) {
      adjustToggle.classList.toggle('is-adjust-product', adjustOpen);
      adjustToggle.classList.toggle('is-actionable', true);
      adjustToggle.setAttribute('aria-pressed', adjustOpen ? 'true' : 'false');
      adjustToggle.setAttribute('aria-label', adjustOpen ? `Stop shaping ${assistantTitle}` : `Shape ${assistantTitle}`);
      const adjustLabel = adjustToggle.querySelector('span:last-child');
      if (adjustLabel) adjustLabel.textContent = adjustOpen ? 'Done shaping' : 'Shape it';
      adjustToggle.title = adjustOpen ? 'Go back to using this AI' : 'Tell the AI how this product should work better';
    }
  }
  if (productPreviewStatus) productPreviewStatus.classList.remove('is-adjust-product');
  if (chatStatus) chatStatus.hidden = false;
  if (chatText) {
    chatText.textContent = isCreate
      ? 'Kneading'
      : adjustOpen
        ? 'Shaping'
        : chatPanelOpen
          ? 'Chatting'
        : 'Using';
  }
  if (productPreviewStatus) {
    productPreviewStatus.hidden = !usesProductCanvas;
  }
  if (!usesProductCanvas) {
    _syncTaskHeaderProductPreviewChipAction({ isCreate, hasTask, canOpenProductPreview: false, label: '' });
  } else if (productPreviewText) {
    if (isCreate) {
      productPreviewText.textContent = 'Make workspace';
    } else if (_activeProductPreview) {
      productPreviewText.textContent = isProductPreview ? 'Hide workspace' : activeProductPreviewName;
    } else {
      productPreviewText.textContent = canOpenProductPreview ? 'Show workspace' : 'Workspace on demand';
    }
  }
  if (productPreviewStatus) {
    productPreviewStatus.classList.toggle('is-active-product', !isCreate && !!_activeProductPreview);
    const label = productPreviewText ? productPreviewText.textContent : '';
    const workspaceName = activeProductPreviewName || (typeof _assistantCanvasLabel === 'function' ? _assistantCanvasLabel(object) : '') || 'workspace';
    productPreviewStatus.title = usesProductCanvas && !isCreate && hasTask && canOpenProductPreview
      ? (_activeProductPreview ? `Hide ${workspaceName}` : `Show ${workspaceName}`)
      : label;
    _syncTaskHeaderProductPreviewChipAction({ isCreate, hasTask, canOpenProductPreview, label: workspaceName });
  }
  if (chatStatus) {
    chatStatus.classList.toggle('is-actionable', canToggleChatPanel);
    chatStatus.title = isCreate
      ? 'Describe the AI you want to knead'
      : canToggleChatPanel
        ? (chatPanelOpen ? 'Collapse chat' : 'Open chat')
        : adjustOpen
          ? `Shaping ${assistantTitle}`
          : hasTask
          ? `Current task handled by "${assistantTitle}"`
          : `从这里开始使用「${assistantTitle}」`;
    if (canToggleChatPanel) {
      chatStatus.setAttribute('role', 'button');
      chatStatus.setAttribute('tabindex', '0');
      chatStatus.setAttribute('aria-label', chatPanelOpen ? 'Hide chat' : 'Open chat');
      chatStatus.onclick = () => toggleCurrentProductChatPanelMode();
      chatStatus.onkeydown = event => {
        if (event.key !== 'Enter' && event.key !== ' ') return;
        event.preventDefault();
        toggleCurrentProductChatPanelMode();
      };
    } else {
      chatStatus.removeAttribute('role');
      chatStatus.removeAttribute('tabindex');
      chatStatus.removeAttribute('aria-label');
      chatStatus.onclick = null;
      chatStatus.onkeydown = null;
    }
  }
}

function _syncAssistantSidebarIntro(hasTask = _assistantTaskHasActiveTask()) {
  const sub = $('assistantPanelSub');
  if (!sub) return;
  const assistantTitle = window._currentAiAssistantTitle || window._currentAiProductTitle || 'Current AI';
  const isCreate = _assistantKey() === 'create';
  const directoryMode = _assistantDirectoryMode(hasTask);
  if (directoryMode === 'library' && !hasTask) {
    sub.textContent = '选择产品，进入它的任务目录。';
  } else if (isCreate) {
    sub.textContent = '描述新产品。';
  } else if (hasTask) {
    sub.textContent = `${assistantTitle} 的任务`;
  } else {
    sub.textContent = 'Start a new task, or open a previous one.';
  }
}

function _syncAssistantSidebarDirectory(hasTask = _assistantTaskHasActiveTask()) {
  const mode = hasTask ? 'product' : _assistantDirectoryMode(hasTask);
  _setAssistantDirectoryMode(mode);
  const isLibrary = mode === 'library';
  const isCreate = _assistantKey() === 'create';
  const object = _assistantObject();
  const assistantTitle = (object && object.title) || window._currentAiAssistantTitle || 'Current AI';
  const panelTitle = $('assistantPanelTitle');
  const back = $('assistantProductBackBtn');
  const listTitle = $('assistantTaskListTitle');
  const search = $('sessionSearch');
  const newTaskBtn = $('newTaskPrimaryBtn');
  if (panelTitle) panelTitle.textContent = isLibrary ? 'AI shelf' : assistantTitle;
  if (back) back.hidden = isLibrary;
  if (listTitle) {
    listTitle.textContent = isLibrary
      ? 'Recent activity'
      : isCreate
        ? 'Create'
        : 'Tasks';
  }
  if (search) {
    search.placeholder = isLibrary
      ? 'Search recent activity'
      : isCreate
      ? 'Search tasks after creating it...'
      : `Search ${assistantTitle} tasks`;
  }
  if (newTaskBtn) {
    newTaskBtn.hidden = isLibrary;
  }
}

function syncAssistantTaskUi() {
  const assistantTitle = window._currentAiAssistantTitle || window._currentAiProductTitle || 'PPT Designer';
  const currentObject = _assistantObject();
  const productLayout = _currentProductLayoutForTaskHeader(currentObject);
  const canAdjustProduct = _assistantKey() !== 'create' && !!(currentObject && currentObject.productId);
  const usesProductCanvas = typeof _assistantCanShowProductCanvas === 'function'
    ? _assistantCanShowProductCanvas(currentObject)
    : typeof _assistantUsesProductCanvas === 'function'
    ? _assistantUsesProductCanvas(currentObject)
    : productLayout !== 'chat_only';
  const root = $('productCrumbRoot');
  const title = $('productModeTitle');
  const listTitle = $('assistantTaskListTitle');
  const search = $('sessionSearch');
  const input = $('msg');
  const home = $('assistantHome');
  const messagesShell = document.querySelector('.messages-shell');
  const adjustHeader = $('productAdjustPanelHeader');
  const activeProductSurface = $('activeProductSurface');
  const body = $('productChatBody');
  const hasTask = _assistantTaskHasActiveTask();
  const taskTitle = _assistantTaskTitle();
  if (!usesProductCanvas && _activeProductPreview && _activeProductPreview.product_preview) {
    if (typeof _hideProductPreviewIfActive === 'function') {
      _hideProductPreviewIfActive({sync:false});
    } else {
      const frame = $('activeProductFrame');
      const previewState = $('productPreviewState');
      if (activeProductSurface) activeProductSurface.hidden = true;
      if (frame) frame.removeAttribute('src');
      if (previewState) previewState.hidden = true;
      if (body) body.classList.remove('has-active-product');
      _activeProductPreview = null;
      _syncProductPreviewMode(null);
    }
  }
  document.body.dataset.nextAiView = hasTask ? 'task' : 'assistant';
  document.body.dataset.nextAiProductLayout = productLayout;
  document.body.dataset.nextAiCanvas = usesProductCanvas && _activeProductPreview ? 'open' : 'closed';
  const canvasFullUseMode = hasTask && productLayout === 'canvas_full' && usesProductCanvas && !!_activeProductPreview;
  const canvasOpen = usesProductCanvas && !!_activeProductPreview;
  const sideCanvasUseMode = hasTask && productLayout === 'chat_left_canvas_right' && canvasOpen;
  const adjustableUseMode = canAdjustProduct;
  if (!adjustableUseMode) document.body.dataset.nextAiProductAdjust = 'closed';
  else if (!document.body.dataset.nextAiProductAdjust) document.body.dataset.nextAiProductAdjust = 'closed';
  const adjustOpen = adjustableUseMode && document.body.dataset.nextAiProductAdjust === 'open';
  if (!hasTask || !canvasOpen || canvasFullUseMode) {
    document.body.dataset.nextAiChatPanel = 'closed';
    delete document.body.dataset.nextAiChatPanelManual;
  } else if (adjustOpen) {
    document.body.dataset.nextAiChatPanel = 'closed';
  } else if (sideCanvasUseMode) {
    const manualChatPanel = document.body.dataset.nextAiChatPanelManual;
    document.body.dataset.nextAiChatPanel = manualChatPanel === 'closed' ? 'closed' : 'open';
  } else if (!document.body.dataset.nextAiChatPanel) {
    document.body.dataset.nextAiChatPanel = 'closed';
  }
  if (adjustHeader) adjustHeader.hidden = !adjustOpen;
  if (body) body.dataset.nextAiView = hasTask ? 'task' : 'assistant';
  if (title) title.textContent = assistantTitle;
  if (root) {
    root.hidden = !hasTask || canvasFullUseMode;
    root.textContent = hasTask ? taskTitle : '';
    root.title = hasTask ? taskTitle : '';
  }
  if (listTitle) listTitle.textContent = _assistantKey() === 'create' ? '新产品' : '最近任务';
  if (search) search.placeholder = _assistantKey() === 'create'
    ? 'Search tasks after creating it...'
    : '搜索任务';
  if (input) {
    const object = AI_OBJECTS[_assistantKey()] || AI_OBJECTS.ppt;
    input.placeholder = adjustOpen
      ? `告诉「${assistantTitle}」你想怎么调整这个产品...`
      : hasTask
        ? `Continue "${taskTitle}"...`
        : (object.placeholder || input.placeholder);
  }
  if (home) home.hidden = hasTask || adjustOpen;
  if (messagesShell) messagesShell.hidden = !hasTask && !adjustOpen;
  if (!hasTask && !adjustOpen) {
    if (activeProductSurface) activeProductSurface.hidden = true;
    if (body) body.classList.remove('has-active-product');
  }
  if (!hasTask) {
    const empty = $('emptyState');
    if (empty) empty.style.display = 'none';
    _syncAssistantHome(AI_OBJECTS[_assistantKey()] || AI_OBJECTS.ppt);
  }
  _syncAssistantTaskContextStrip(hasTask);
  _syncAssistantTaskProgress(hasTask);
  if (_activeProductPreview) _syncProductPreviewCopy();
  _syncAssistantSidebarDirectory(hasTask);
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
  if (document.body && document.body.dataset) {
    document.body.dataset.nextAiChatPanel = 'closed';
    delete document.body.dataset.nextAiChatPanelManual;
  }
  _activeProductPreview = null;
  _syncProductPreviewMode(null);
  _syncAssistantTaskContextStrip();
  _syncAssistantTaskProgress();
  if (typeof showToast === 'function' && activeProductPreviewName) {
    showToast(`Hidden "${activeProductPreviewName}"`);
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

// ── Draggable chat/canvas splitter (two-pane chat_left_canvas_right) ──
(function wirePaneResizer() {
  function init() {
    const r = document.getElementById('paneResizer');
    const body = document.getElementById('productChatBody');
    if (!r || !body) return;
    try { const w = localStorage.getItem('nextai-chat-pane-w'); if (w) body.style.setProperty('--chat-pane-w', w); } catch (_) {}
    let dragging = false;
    const onMove = (e) => {
      if (!dragging) return;
      const rect = body.getBoundingClientRect();
      const min = 300, max = Math.max(min, rect.width - 360);
      let w = Math.max(min, Math.min(max, e.clientX - rect.left));
      body.style.setProperty('--chat-pane-w', w + 'px');
    };
    const stop = () => {
      if (!dragging) return;
      dragging = false; r.classList.remove('is-dragging');
      document.body.style.userSelect = ''; document.body.style.cursor = '';
      try { localStorage.setItem('nextai-chat-pane-w', body.style.getPropertyValue('--chat-pane-w')); } catch (_) {}
    };
    r.addEventListener('mousedown', (e) => {
      dragging = true; r.classList.add('is-dragging');
      document.body.style.userSelect = 'none'; document.body.style.cursor = 'col-resize';
      e.preventDefault();
    });
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', stop);
    // Double-click resets to the default ratio.
    r.addEventListener('dblclick', () => { body.style.removeProperty('--chat-pane-w'); try { localStorage.removeItem('nextai-chat-pane-w'); } catch (_) {} });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, { once: true });
  else init();
})();
