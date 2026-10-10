# Ubuntu 双击启动采集界面

v0.4 的桌面入口默认 `--reference-view front`（观众视角）。本入口仍使用演示指令单位；正式实物采集请按 [机械队友使用说明](mechanical_handoff.md) 使用真实配置启动。

安装依赖和编译只需首次进行；修改 C++ 源码后再重新编译。以后可从 Ubuntu 桌面或应用菜单启动，不用重复长命令。本入口适合准备相机和坐标取点流程。

## 给已安装 v0.2 的电脑添加入口

将 `shadow-capture-launcher.zip` 复制到 Ubuntu 主文件夹，在 Ubuntu 终端依次执行：

```bash
unzip -o ~/shadow-capture-launcher.zip -d ~/shadow-capture-v0.2
cd ~/shadow-capture-v0.2/shadow_play
python3 integrations/calibration/capture_launcher.py --install-shortcuts
```

补丁只包含启动脚本和本说明。已有 v0.2 可执行程序可以直接使用，不需要重新编译；如果尚未编译，请先按 `capture_setup.md` 完成安装与编译。如果工程解压在其他目录，相应替换上述路径。

安装器会在当前 Ubuntu 用户的应用菜单，以及检测到的桌面目录中创建两个入口：

- **皮影坐标采集（摄像头练习）**：真实相机、手录模式、演示指令单位。
- **皮影坐标采集（演示）**：合成画面，不需要摄像头。

安装使用普通用户，不需要 `sudo`。桌面图标若提示不可信，右键选择“允许启动”；也可以按 Ubuntu 的 Super 键，搜索“皮影坐标采集”。未检测到桌面目录时，应用菜单入口仍可使用。

## 第一次和以后怎样启动

双击摄像头入口，首次在随之打开的终端中输入：

1. 摄像头编号，如 `/dev/video0` 对应 `0`。
2. 实测有效幕布宽度，单位 mm。
3. 实测有效幕布高度，单位 mm。

程序保存到工程内 `runtime/capture-launcher.json`。以后直接使用这些设置打开界面；终端仅显示状态和报错。每次启动会生成唯一的新会话目录，位置为工程内 `capture-sessions/camera-practice-日期时间-随机编号/`；演示则使用 `demo-日期时间-随机编号/`。保存按钮按原有流程使用，关闭界面后启动终端显示该轮保存位置，按回车关闭终端。

每轮仍需设置幕布四个参考点。入口记住相机编号和幕布尺寸；四点参考在当前采集会话中设置，摄像头移动后重新设置。

本摄像头入口固定使用 `manual_unconfirmed` 和 `capture.demo.json`，**输入数字只登记，不发真实电机命令**；尺寸是实测值时，指令仍然是 `demo` 单位。真正电机采集需要真实配置和已验证的驱动接口，不能把这些练习数据拿去拟合。

## 修改设置和排查问题

相机编号或幕布尺寸改变时，在工程根目录执行一次：

```bash
python3 integrations/calibration/capture_launcher.py --configure
```

相机打不开时，先检查 VirtualBox 已把目标 USB 摄像头转交 Ubuntu，再检查实际 `/dev/videoN`、其他程序占用和上方报错。工程目录移动后，在新的根目录重新运行 `--install-shortcuts`，更新入口中的路径。

需要只核对启动参数而不打开界面时：

```bash
python3 integrations/calibration/capture_launcher.py --mode camera --print-command
```

## JSON、JSONL 和 CSV 的区别

扩展名代表存储格式，文件用途由内容决定：

| 文件 | 用途 |
| --- | --- |
| `samples.jsonl` | 每行一条 JSON 采样记录：完整控制状态、所选杆的 XY、照片路径等 |
| `samples.csv` | 同批样本的表格形式，便于查看 |
| `config.snapshot.json` | 本轮实际采用的轴、单位、限位、幕布尺寸等配置 |
| `calibration_*.json` | 相机像素到幕布毫米坐标的转换参数 |
| `runtime/capture-launcher.json` | 双击入口记住的相机编号和幕布尺寸 |

这些采集文件用于后续拟合和检查。剧本文件用于描述按时间执行的动作；采集记录不会因为采用 JSON 格式就成为剧本或可直接运行的映射参数。

JSONL 中的电机指令是登记或驱动采用值，实际反馈单独保存，没有反馈时为 `null`。后续交接仍打包整个采集会话目录，保留 CSV、JSONL、照片和坐标转换配置。
