# 笔记本模块重构开发计划 (Notebook Migration Plan)

该开发计划旨在将 `open-notebook` 项目的智能笔记本界面（三列可折叠布局、现代化的编辑体验）集成到您的 `writingbot` 项目中，替换原本的笔记本模块。由于 `open-notebook` 源代码已移动到 `writingbot/open-notebook` 目录下，该移植过程将更加直接。

## 1. 依赖项与基础配置迁移 (Dependencies & Config)
`open-notebook` 基于基于 Shadcn UI 构建，我们需要对现有项目进行包和配置对齐。
- **添加依赖**: 
  在 `writingbot/web/package.json` 中添加缺失的组件库和状态管理包：包括 `@radix-ui/react-*` 系列 (dialog, dropdown-menu, tabs, tooltip, scroll-area 等), `zustand` (用于侧边栏折叠状态管理), `sonner` (Toast 提示), 以及 `clsx`, `tailwind-merge` 等。
- **样式基础与 Tailwind**: 
  将 `writingbot/open-notebook/frontend/src/app/globals.css` 中的 CSS 变量（例如 `--primary`, `--muted`, `--background` 等）以及 `tailwind.config` 的相关配置同步到 `writingbot/web` 中，以保证 UI 组件的表现和颜色百分百还原。
- **工具函数**: 
  复制 `cn` (Tailwind 类合并) 工具类到 `writingbot/web/src/lib/utils.ts`。

## 2. 通用 UI 组件移植 (Common UI Components)
考虑到跨包引用可能会导致 Next.js 或 Tailwind CSS 在编译时增加复杂性（如路径解析或样式扫描遗漏），最佳实践是将基础组件直接平移：
- 复制 `writingbot/open-notebook/frontend/src/components/ui/` 下的全部基础组件（Button, Dialog, ScrollArea, Tabs, Tooltip 等）进入 `writingbot/web/src/components/ui/`，使其可以被 `writingbot` 的应用原生无缝使用。

## 3. 面板与布局组件移植 (Layout & Module Components)
引入 `open-notebook` 的核心亮点 —— 三列响应式可折叠工作台布局：
- **状态管理**: 移植 `useNotebookColumnsStore` (Zustand) 以控制左右侧边栏组件的展示与隐藏交互。
- **业务组件平移**: 将以下布局级组件集成到 `writingbot/web/src/components/notebook/`：
  - `CollapsibleColumn.tsx` (提供平滑拖拽/点击折叠动效)。
  - `NotebookHeader.tsx` (顶部栏)。
  - `SourcesColumn.tsx` (左侧资料面板)。
  - `NotesColumn.tsx` (中间笔记列表/卡片列表面板)。
  - 编辑器面板组件等。

## 4. API 数据接入层适配 (Data Integration Adapters)
`writingbot` 目前 `page.tsx` 高度耦合，需要基于移植过来的模块化组件进行重构和数据绑定：
- **数据解耦**: 不改变 `writingbot` 目前的后端接口和数据结构，而在渲染 UI 组件时将现有的 state 转为 `open-notebook` 组件期待的 `props` (例如 `notes`, `sources`, `onContextModeChange` 等)。
- **交互对接**:
  - `NotesColumn` 的列表项点击时，依旧触发当前加载卡片详情的 fetch 行动。
  - 右侧的核心编辑组件区域将接入现有的 AI 润色、扩写、生成标签等功能 (`writingbot` 的 AI Edit 模块)。

## 5. 页面入口重构 (Page Overhaul)
重写 `writingbot/web/src/app/notebook/page.tsx`。
- 保留最外层的全局导航侧边栏，将右侧工作区替换为 `open-notebook` 采用的 `AppShell` 结构和三列展示 (`SourcesColumn`、`NotesColumn`、编辑区)。
- 通过此重构大幅提升右侧编辑器的视野大小，并且提供折叠辅助面板的“专注模式”。

## 验证与测试计划 (Verification Plan)
- **编译打包测试**: 使用 `npm run build` 确保没有产生路径未找到或者 TypeScript 类型不匹配的报错。
- **视觉验收**: 运行本地服务并在浏览器检查折叠动画流畅度，确保界面没有发生样式丢失 (Tailwind 未扫到等情况)。
- **功能联机验收**: 
  - 新增、保存、删除卡片。
  - 展开与折叠“阅读区/素材区”验证“编辑感”是否达标。
  - 执行一遍 AI 修改功能确保工作流不中断。
