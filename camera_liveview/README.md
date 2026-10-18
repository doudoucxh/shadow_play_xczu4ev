# Sony A7M4 无界面操作实时取景

本工具通过 Sony Camera Remote SDK 直接读取 A7M4 的 Wi-Fi 预览帧，不截取桌面或 Imaging Edge 窗口。预览程序连续更新图片，助手通过读取最新图片判断场景；这不代表助手会逐帧、持续自动分析整个视频。

## 当前验证状态

2026 年 10 月 8 日已使用 Sony 官方 SDK 2.02.00 和本机 MSVC 编译成功，并通过用户在本地输入的访问认证登录 `192.168.31.250`。实际读取到 640×360 的 JPEG 预览，画面为显示器和键盘。

连续六次间隔约一秒的采样中，帧计数从 446、451、456、461、466 增至 471，六张图片的 SHA-256 均不同；读取时最近一次更新时间距离当前约 122～142 毫秒。由此确认当次取景持续更新，采集速率约 5 帧每秒。该时间只表示本地文件更新的新鲜度，不是实测的相机到助手的总延迟。

## 启动

2026-10-11 已重新编译，将默认时长改为 8 小时，上限 24 小时。28,800 和 86,400 秒参数通过无连接检查，0 和 86,401 秒被拒绝；PowerShell 语法解析通过。实际启动 8 小时会话后，连续取得 Sony/Camo 各 19 张可解码新 JPEG，全部帧号不同，最大帧龄分别为 188/204 ms；已查看两路画面。该验证是启动和短时连续采样，没有声称已完成 8 小时耐久测试。

本次受限执行环境曾拒绝网络套接字（WinError 10013），表现为 SDK 指纹读取失败。在获准访问局域网的执行环境中，SDK probe 成功并恢复取景。因此重连失败时先检查本机网络执行权限，再判断是否需要用户唤醒相机，不把 SDK 错误直接等同于相机离线。

先关闭 Imaging Edge 的 Remote 窗口，让这个程序接管取景，保持相机 Wi-Fi 连接。在 Windows PowerShell 执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "D:\Desktop\piying\camera_liveview\start_liveview.ps1"
```

本地提示输入的是相机访问认证用户名和密码，不是 Sony 账户或电脑密码。位置为相机 MENU → 网络 → 网络选项 → 访问身份验证信息，见 [Sony A7M4 帮助指南](https://helpguide.sony.net/ilc/2110/v1/zh-cn/contents/TP1001106195.html)。无需修改认证开关或生成新密码。

密码输入隐藏，经子进程标准输入传递，不放在命令行参数、脚本或应用日志中。上述执行策略仅作用于这次 PowerShell 进程。

出现 `LIVE VIEW READY` 才表示已检查到帧计数三次前进且最新状态不超过 2 秒。保持终端开启，默认以最高约 5 帧每秒更新，**运行 8 小时后结束**；时长上限已由 1 小时提高到 **24 小时**。实际帧率受 Wi-Fi 和相机状态影响。需要 24 小时可添加 `-Seconds 86400`；改变帧率可添加 `-FramesPerSecond 10`，相机 IP 改变时添加 `-CameraIP 新地址`。旧命令显式写了 `-Seconds 3600` 的，仍只运行一小时，应去掉此参数以采用新默认值。

延长的是电脑程序的主动退出时间，不会修改相机休眠或供电设置。SDK 连续 15 秒无新帧仍报错退出；不能用进程仍在或旧图片存在来判断取景正常。助手每次使用画面前自行检查帧计数、时间戳、JPEG 解码及可见内容；相机无法通过 SDK 连接时才需要现场唤醒。自动恢复取景不会自动解除舵机动作锁或重放运动。

每次启动新建 `output/session-*`，只覆盖其中的 `latest.jpg`，不逐帧归档。`status.json` 记录帧计数和更新时间，`output/current.json` 指向当前会话并记录请求时长与帧率。程序只调用连接和读取预览相关 API，没有拍照、录像、改曝光或删除相机内容的命令。

## 读取与停止

需要本机密码遮挡窗口时，可运行 `powershell -NoProfile -STA -ExecutionPolicy Bypass -File "D:\Desktop\piying\camera_liveview\start_with_prompt.ps1"`。窗口读取相机访问认证，通过内存中的PSCredential交给原启动器，仍由stdin传给SDK，不存储凭据。默认8小时，不会操作舵机。脚本使用UTF-8 BOM以兼容Windows PowerShell 5.1的中文；窗口出现和网络probe成功均不代表已有新画面，仍按下述新鲜度检查核验。

需要在浏览器中连续观看时，在 SDK 取景已经启动的前提下，使用装有 Pillow 的 Python 运行 `python camera_liveview/preview_server.py`，然后打开 <http://127.0.0.1:8766/>。页面约每秒刷新五次，可以暂停显示或全屏。它读取已有会话文件，普通预览不额外归档画面；下面的点选模式只在用户确认保存后写入参考图。不重复连接相机，也不控制舵机；关闭该预览服务不会停止 SDK 取景。服务固定监听本机回环地址，不对局域网开放。

预览沿用网关的 JPEG 解码及 1.5 秒新鲜度检查；浏览器还检查连续帧号，画面过期或请求失败时隐藏旧图并提示。页面放大只便于观看，不能增加 SDK 原图分辨率。按 Ctrl+C 可停止预览服务。

助手与现场观察对连接点位置有分歧时，可点击“点选五个连接点”，冻结一张新的 Sony 图片，然后按 **1 人物左手、2 人物头、3 人物右手、4 虎头、5 虎脚控制杆** 的顺序点击实际连接点。可撤销上一点；核对编号后点击“保存五点”。浏览器按原图像素换算点击位置，自动排除图像周围的留黑区域。此模式显示的是明确冻结的参考图，返回实时画面后才继续刷新。

冻结记录最多保留 8 份、30 分钟内有效。保存时在忽略的 `output/annotations/<编号>/` 中写入同一张 `frame.jpg` 及 `points.json`，记录原始帧号、时间戳、哈希和点选位置。除了用户确认保存的这一帧，不额外归档实时画面。该记录尚未换算为毫米，也不代表实际舵机角度或运动许可；没有串口或电机后端，禁止将点选直接用于自动试转。保存成功后告诉助手“已点好”，再由助手复核四角基准、连接点对应和两路可见性。

已有静态坐标结果时，可给预览服务添加 `--coordinates-dir 本地结果目录`。目录包含 `geometry.json`、`numbered_reference.png` 和 `numbered_stage.png`，页面“查看五点坐标”显示记录时间、编号图及近似毫米坐标。此页是静态记录，不随实时画面更新；数值为幕布平面投影，不是舵机角度。相机画面继续保留在忽略目录中。2026-10-11 的结果和误差说明见 [五点坐标记录](../shadow_play/docs/point_coordinates_20261011.md)。

`snapshot_latest.py` 使用 Python 和 Pillow 检查状态、图片新鲜度及 JPEG 解码，再将最新 JPEG 复制到固定的 `output/snapshot.jpg`，供图像读取工具使用；预览超过 5 秒未更新时拒绝把它当成当前画面。已适配 Sony 在 JPEG 结束标志之后附加的缓冲区填充字节。

在另一个 PowerShell 终端执行下列命令停止取景：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "D:\Desktop\piying\camera_liveview\stop_liveview.ps1"
```

断开后可重新打开 Imaging Edge Remote。程序不修改其配置。如果出现认证错误，检查相机上的用户名、密码；若连接超时，确认 Remote 已退出、IP 未变化、电脑与相机仍在同一网络。终端退出时会请求停止辅助进程。

## 构建与来源

运行 `build.ps1` 重新编译。SDK 位于 `vendor/sdk/simple`，官方原始压缩包保留于 `vendor`；不应将 SDK 文件随源代码提交或另行分发。软件许可和兼容说明以 [Sony Camera Remote SDK 官网](https://support.d-imaging.sony.co.jp/app/sdk/en/) 及下载包内文件为准。
