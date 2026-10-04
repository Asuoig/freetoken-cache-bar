# FreeToken Cache Bar

一个常驻桌面右侧的浮动小工具，给 [FreeToken](https://github.com/FlashML-org/FreeToken) 的 cache 配置加上可保存、可一键切换的 **Custom** 预设。

FreeToken Desktop 的 Cache 面板只给了「基础 / Chat / Agent」三个内置预设，自定义只能拖滑块、每次重新调。这个工具补上缺的那块：**把你调好的组合存成预设，下次点一下就切过去**。

它不修改 `freetoken-desktop.exe` 的任何一行代码，只通过 FreeToken 的 REST API 下发配置——所以升级 FreeToken Desktop 后依然可用。

## 长什么样

```
┌─────────────────────────────────┐
│ FreeToken · Cache Bar    —  ⟳ ✕ │
├─────────────────────────────────┤
│ ● 已连接                         │
│ ┌─────────────────────────────┐ │
│ │ 当前配置                     │ │
│ │ KV 缓存   SWA 池   MoE 槽    │ │
│ │ 131,072   25,600   254/768  │ │
│ │ 显存 6.07 / 6.73 GiB        │ │
│ └─────────────────────────────┘ │
│ 预设                             │
│ [基础] [Chat] [Agent] [Custom]   │
│ ─────────────────────────────── │
│ Custom 配置                      │
│ KV 缓存   131072  tokens         │
│ 滑窗池     26214  tokens         │
│ MoE 槽       254  experts        │
│ [保存为 Custom]      [重置][应用] │
└─────────────────────────────────┘
```

## 安装

### 前置条件

- Windows + FreeToken 已安装（自带 Python venv 里有 `tkinter`）
- FreeToken server 在 `127.0.0.1:1919` 运行

### 步骤

1. 把这个仓库 clone 到本地任意目录，例如 `C:\Users\<你>\.freetoken\cache-bar`
2. 编辑 `ft_cache_bar.cmd`，把两行路径改成你本机的实际路径：

   ```bat
   set "FT_PY=C:\Users\<你>\AppData\Local\FreeToken\venv\Scripts\pythonw.exe"
   set "FT_BAR=C:\Users\<你>\.freetoken\cache-bar\ft_cache_bar.pyw"
   ```

3. 双击 `ft_cache_bar.cmd` 启动
4. 想钉到桌面 / 任务栏：右键 `install.ps1` → 用 PowerShell 运行

## 用法

| 操作 | 怎么做 |
|---|---|
| **切预设** | 点顶部 `基础 / Chat / Agent / Custom` 任一按钮 |
| **改参数** | 在下面三个输入框里填数字，点 **应用** |
| **存为新预设** | 填好数字 → **保存为 Custom** → 命名 |
| **删预设** | 右键 Custom 按钮 → 确认删除 |
| **折叠** | 双击标题栏，或点 `—` |
| **移动** | 直接拖窗口 |

预设保存在 `~/.freetoken/cache-presets.json`，可以直接手工编辑。

## 命令行参数

```bat
ft_cache_bar.cmd --pin left      :: 停靠到指定边缘
ft_cache_bar.cmd --port 8080     :: 自定义 FreeToken 端口
ft_cache_bar.cmd --host 0.0.0.0  :: 自定义 host
```

`--pin` 可选 `left` / `right`（默认）/ `top` / `bottom`。

## 工作原理

| 动作 | 对应 API |
|---|---|
| 读取当前配置 | `GET /v1/cache/status` （每 2 秒轮询一次） |
| 下发新配置 | `POST /v1/cache/rebuild`，body 为 `{num_pages, num_swa_pages, moe_cache_size, mode:"if_idle", timeout}` |

与 `ft ctl cache --kv <n> --swa <n> --moe <n>` 完全等价。注意切换会清空前缀缓存，正在跑的请求会等重建完成。

## 内置预设默认值

| 预设 | KV tokens | SWA tokens | MoE slots |
|---|---|---|---|
| 基础 | 8,192 | 1,609 | 32 |
| Chat | 120,000 | 25,000 | 200 |
| Agent | 100,000 | 25,000 | 254 |
| Custom（输入框默认） | 131,072 | 26,214 | 254 |

想加"出厂预设"就编辑 `ft_cache_bar.pyw` 里的 `BUILTIN_PRESETS` 列表。

## License

MIT
