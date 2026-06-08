# GPT Image 2 PPT Skill

基于 fal.ai 上的 **GPT Image 2** 生成 PPT 图片，主打字体排版质量。Deck 驱动的 CLI，干净优雅。

## 设计哲学

**给原子命令，AI 自己决定怎么组合。**

- `gen` / `edit` — 调 fal.ai 生成 / 编辑图片
- `pack` — 本地把图片合成 `.pptx` 和 `index.html`

没有 "mode A / B / C" 这种写死的流程，Claude 根据上下文自己判断每一页用哪个。

## 核心概念：deck

**一个 deck = `outputs/` 下的一个目录**。
- slides 按 `slide-01.png`, `slide-02.png` 自动编号
- `deck.json` 记录 size / quality / style 默认值 + 操作历史
- `pack` 命令产出可分享的 `.pptx` 和 `index.html`

## 快速开始

```bash
# 1. 装依赖
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 2. 配置 key（复制 .env.example 到 .env，填入 FAL_KEY）
cp .env.example .env

# 3. 生成第一页（设好 deck 默认值）
#    风格不是 CLI 参数——AI 根据内容自己判断，直接写进 prompt
.venv/bin/python ppt.py gen q1-demo \
  "Editorial magazine cover, huge serif title '产品复盘 Q1', off-white bg, thin hairline divider, small sans-serif subtitle '2026 · 产品团队'. Crisp exact typography." \
  --size 2048x1152 --quality high

# 4. 后续页引用第 1 页做母版（size/quality 自动继承）
.venv/bin/python ppt.py edit q1-demo \
  "Keep layout identical. REPLACE title WITH: '核心成果'. REPLACE subtitle WITH: '用户 +32% · 留存 78% · NPS 62'." \
  --ref 1

.venv/bin/python ppt.py edit q1-demo \
  "Keep layout identical. REPLACE title WITH: 'Thank you'. REPLACE subtitle WITH: 'Q2 再见'." \
  --ref 1

# 5. 看一眼状态
.venv/bin/python ppt.py info q1-demo

# 6. 一键打包
.venv/bin/python ppt.py pack q1-demo
# → outputs/q1-demo/deck.pptx     （可在 Keynote/PowerPoint 打开）
# → outputs/q1-demo/index.html    （键盘 ← → 导航的播放器）
open outputs/q1-demo/index.html
```

## 四个命令

| 命令 | 作用 | 示例 |
|------|------|------|
| `gen <deck> <prompt>` | 文生图，自动编号 | `ppt gen my "..."` |
| `edit <deck> <prompt> --ref N` | 图生图，引用 slot N | `ppt edit my "..." --ref 1` |
| `pack <deck>` | 打包成 .pptx + .html | `ppt pack my` |
| `info <deck>` | 查看 deck 状态 | `ppt info my` |

### edit 的 --ref

支持三种格式：
- `--ref 1` — 引用同 deck 的 slot 1
- `--ref /path/to/brand.png` — 本地文件
- `--ref https://...png` — URL
- 可传多个：`--ref 1 --ref brand.png`

### 精修某一页

```bash
ppt edit mydeck "Change title to 'XX'." --ref 3 --slot 3   # 覆盖第 3 页
ppt pack mydeck                                             # 重新打包
```

## 作为 Claude Code Skill 使用

```bash
ln -s "$(pwd)/GPTImage2-PPT-Skills" ~/.claude/skills/gpt-image-2-ppt
```

然后让 Claude 按 `SKILL.md` 规划并调 CLI 生成。

## 项目结构

```
GPTImage2-PPT-Skills/
├── ppt.py                    # CLI 入口
├── ppt_skill/                # 核心包
│   ├── env.py                #   加载 .env
│   ├── deck.py               #   Deck 类
│   ├── api.py                #   gen_image / edit_image
│   └── pack.py               #   to_pptx / to_html
├── templates/viewer.html     # HTML 播放器
├── style_refs/               # 风格参考样本（仅供借鉴，非必选菜单）
├── .env.example
├── requirements.txt
└── outputs/<deck>/           # 每个 deck 一个目录
```

## 关于尺寸

GPT Image 2 要求：**两边都是 16 的倍数**、最大边 ≤ 3840、总像素 655,360–8,294,400。

- 标清：`1280x720`
- **高清（默认）：`2048x1152`** ⭐
- 4K：`3840x2160`

⚠️ `1920x1080` 不行（1080 不是 16 的倍数）。

## 计费参考

按 token 算：图片 $8/M input · $30/M output。`quality=high` 是默认（也最贵），可改 `medium`/`low` 省钱。
