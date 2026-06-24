# 文档站生成库对比（2025-06）

调研主流文档站生成方案，as of 2025。

## React 系

| 库 | 技术栈 | 最新版 | 特点 |
|---|---|---|---|
| **Docusaurus** | React | 3.10.x | Meta 出品，功能最全，MDX 支持，适合大型项目文档 |
| **Nextra** | Next.js + React | 4.x | Vercel 出品，极简风格，类 Linear/Notion，颜值高 |
| **Fumadocs** | Next.js + React | 16.x | 现代感，颜值高，适合 API 文档 |
| **Mintlify** | React | 4.x | 专注开发者/API 文档，SaaS + 本地两用，颜值极高 |

## 非 React 系

| 库 | 技术栈 | 特点 |
|---|---|---|
| **VitePress** | Vue + Vite | Vue 官方文档在用，启动极快，极简 |
| **Starlight** | Astro | 内容优先，SEO 极好，输出零 JS |
| **MkDocs** | Python | 最容易上手，Material 主题好看，纯 Markdown |
| **GitBook** | SaaS/CLI | 协作文档，UI 精美，有免费层 |

## 推荐选择

- **追求颜值 + React 生态**：Nextra 或 Fumadocs
- **功能最全 + 插件生态最大**：Docusaurus
- **最快上手 / 纯静态**：VitePress 或 MkDocs + Material
- **API 文档 / 开发者产品**：Mintlify
- **内容博客 / SEO 优先**：Starlight（Astro）

## 快速验证版本

```bash
npm show @docusaurus/core version   # 3.x
npm show vitepress version          # 1.x
npm show nextra version             # 4.x
npm show @astrojs/starlight version # 0.x
npm show fumadocs-core version      # 16.x
npm show mintlify version           # 4.x
```
