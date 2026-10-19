# Folio · 随手记浏览器扩展

适用于 Microsoft Edge / Google Chrome。扩展连接本机 `http://127.0.0.1:8771`，需先启动项目服务。Codex 内置浏览器不提供加载此类扩展的入口。

## 加载到 Edge

1. 打开 `edge://extensions`，启用“开发人员模式”。
2. 点击“加载解压缩的扩展”，选择本目录 `extension`（包含 manifest.json）。
3. 将“Folio · 随手记”固定到工具栏。
4. 在普通网页选中文字或右键图片，选择“收集到 Folio”；未选内容时保存页面标题和链接。
5. 在弹窗中可补一句说明，再点击“保存到Folio”。主页“收集箱”可以查看原文、原图、分类与待办。

Chrome 使用 `chrome://extensions`，其余相同。扩展尚未发布到商店；本项目提供可审阅的源码和解压加载包。

## 快捷键与其他软件

默认全局快捷键为 `Ctrl+Shift+9`，唤出空白记录小窗。可从微信、PDF 或办公软件复制文字或图片后，在小窗中粘贴。扩展不会自动读取剪贴板或历史。

如果快捷键被占用，可在 Edge 的 `edge://extensions/shortcuts` 或 Chrome 对应页面修改，并确认范围为“全局”。浏览器必须运行。主页内也可使用 `Alt+Shift+M` 打开随手记。

## 图片与草稿

支持 4 MB 以内的 PNG、JPEG、WebP。右键图片时优先从用户操作的页面读取已显示原图；跨域等页面限制可能阻止读取，此时明确显示“仅保留图片链接”，可通过粘贴、选择图片文件补充。扩展不会向来源服务器主动请求图片。

服务未启动或断网时，未提交的草稿保留在浏览器本地存储，下次打开小窗可恢复。草稿和原图可能占用磁盘，因此扩展申请本地不设配额的存储权限，不使用浏览器云同步。保存成功后清理对应扩展草稿。

## 整理方式

收集记录总是保存到“我的本机记录”。保存先完成，图片识别和分类随后进行。Windows 图片识别使用系统本机 OCR，结果可能有误，可在详情中修改。

若服务配置了 Ollama 本机模型（`MEMORY_LOCAL_MODEL`），分类使用本机 AI；未配置或失败时使用本机规则初步分类，并显示实际方式。当前收集内容不会发送到 DeepSeek 或其他外部接口。

自动识别的任务进入待确认，用户负责确认和完成。网页里别人的“我负责……”不会仅凭规则直接当作你的任务；填写自己的说明可以表达行动意图。分类与日期都可修改；已关联待办有独立修改历史，收集箱修改不覆盖已有待办。

## 权限与实现依据

只有用户点击右键、工具栏或快捷键时收集内容。权限为 contextMenus、activeTab、scripting、本地 storage / unlimitedStorage，以及固定的本机服务地址。没有所有网站访问权限、剪贴板读取权限、浏览历史权限或远程上传功能。

接口依据：[右键菜单 API](https://developer.chrome.com/docs/extensions/reference/api/contextMenus)、[临时页面访问权限](https://developer.chrome.com/docs/extensions/develop/concepts/activeTab)、[快捷键 API](https://developer.chrome.com/docs/extensions/reference/api/commands)。
