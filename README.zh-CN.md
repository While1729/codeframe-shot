# Codeframe Shot

把源码的指定行段渲染成带行号的代码图片。工具生成独立 HTML，再调用本机 Chrome、Edge 或 Chromium 的无头模式输出 PNG；不操作桌面窗口，也不会上传源码。

## 功能

- 按包含首尾的行号范围截取源码，并保留原始行号。
- 提供 VS Code 深色主题和简洁浅色主题。
- 长行默认扩展图片宽度，或换行以固定图片宽度。
- 按所选行数估算图片高度，并核对 PNG 实际尺寸。
- 将 HTML 预览与 PNG 放在一起，便于复查和重做。
- 可选使用 Pygments 着色；基础渲染只需要 Python 标准库和 Chromium 浏览器。
- 在不可见的 HTML 注释中记录源文件名、行号范围和完整文件 SHA-256。

## 需要什么

- Python 3.9 或更新版本
- Chrome、Edge 或 Chromium
- 可选：Pygments 语法着色（`python -m pip install Pygments`）

## Windows 快速开始

```powershell
python .\codeframe_shot.py .\examples\demo.js --range 1-18
```

默认生成 `codeframe-output\demo-lines-1-18.html` 和 `.png`。工具会搜索常见的 Chrome、Edge 安装位置。如果浏览器安装在其他地方，可指定完整路径：

```powershell
python .\codeframe_shot.py .\path\to\source.js --range 454-466 `
  --browser "C:\Program Files\Google\Chrome\Application\chrome.exe" `
  --output-dir .\out
```

`--long-lines expand`（默认）会扩宽图片，保证长行保持在一行内。`--long-lines wrap` 会在默认 1700 CSS 像素宽度内换行。PNG 的像素宽高等于 CSS 视口尺寸乘以 `--scale`（默认 2）。

## 常用选项

```text
--range START-END       包含首尾的行号范围；省略时渲染整个文件
--output-dir PATH       输出目录（默认 ./codeframe-output）
--browser PATH          Chrome/Edge/Chromium 程序路径；默认自动查找
--theme NAME            vscode-dark 或 paper
--language NAME         Pygments 语言名；默认按文件扩展名识别
--encoding NAME         源码编码（默认 utf-8-sig）
--font-size N           字号（CSS px，默认 14）
--line-height N         行高倍数（默认 1.5）
--padding N             外边距（CSS px，默认 12）
--width N               最小视口宽度（CSS px，默认 1700）
--scale N               设备缩放倍数（默认 2）
--long-lines MODE       expand 或 wrap（默认 expand）
--no-line-numbers       隐藏行号栏
--no-highlight          关闭可选的 Pygments 着色
--force                 覆盖已有的 HTML/PNG
```

## 隐私与准确性

渲染在本机完成。浏览器只打开生成的 `file:///` HTML；工具关闭浏览器扩展和后台联网，并使用临时浏览器配置目录。项目不包含遥测。

HTML 只记录源文件名、行号范围和 SHA-256，不嵌入绝对路径。源码会先进行 HTML 转义。发布图片前仍应检查源码和图片，尤其注意源码里是否包含密钥、个人信息，或极长的代码行。

本工具生成的是**源码展示图**，不会执行程序，因此图片不能证明代码实际运行过。

## 许可证

MIT，详见 [LICENSE](LICENSE)。
