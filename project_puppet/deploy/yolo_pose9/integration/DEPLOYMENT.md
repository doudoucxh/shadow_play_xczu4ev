# YOLO9 XCZU4EV 部署候选包

状态：离线集成与测试；未实板验收。模型为项目训练的 YOLOv8n Pose9 ReLU，非 AMD 官方预训练模型。

## 启动文件

`sd_candidate/BOOT.BIN`、`sd_candidate/boot.scr`、`sd_candidate/image.ub` 是本次 SD 测试包。仅这三个文件放入既有 SD 启动分区根目录；无需将该目录的其他封装中间文件复制上板。保持先前已验证的 SD1 启动方式。本文档不表示已写入 SD 卡或完成烧录。

BOOT 使用 Vivado 2022.2 生成的 Video In 软件复位修复 bitstream 和此前已验证的 SD1 FSBL/PMUFW/U-Boot。布线报告 WNS=0.766ns、WHS=0.009ns，所有用户指定时序约束满足。PetaLinux 全项目构建仍有既有 FSBL 缺 xsdps.h 的问题，因此本次基于已可启动镜像重封装根文件系统；不是全量构建通过声明。

## 数据链路与图审查

- 输入：VDMA 原始 1280×720，地址 0x70000000，三个 2764800 字节缓冲。内存低字节 B、G、R 与 RGB888 总线打包和小端 DDR 一致；上板仍需用颜色测试确认。
- 模型预处理：完整画面缩放至 384×216，上下各 84 像素灰边；RGB /255；NHWC INT8，使用模型 fix_point。
- 不读取 0x72000000 的 256×144 模型输入支路。硬件初始化仍启动其 VDMA，避免共享 broadcaster 背压。
- 模型及 Vivado DPU arch 指纹均为 0x101000056010407。启动读取 xdputil query 验证实际设备；目前未连接板子，实际寄存器值尚未复测。
- 九个 CPU 子图实际均是单个 fix2float：一进一出、直连 DPU 输出、相同形状、INT8→FP32、同一 fix_point。graph_contract.py 每次启动重新验证，拒绝仅凭形状推断跳过计算。
- A53 执行反量化、DFL、sigmoid、NMS、坐标还原。三尺度 48/24/12，每尺度 64/1/27 通道。九关键点顺序保持 head、左右肩、左右肘、左右腕、左右髋。
- 当前按人物置信度最高的检测输出姿态；多人情况下不保证持续锁定同一演员，需实测或另行增加人物跟踪。

## 服务与回退

`shadow-yolo-pose.service` 开机先执行 shadow-hw-init，再运行新程序。与 shadow-arm-chain.service 互斥；旧程序、权重和服务仍在镜像中，仅撤销旧服务开机链接。

检查：`systemctl status shadow-yolo-pose`；日志：`journalctl -u shadow-yolo-pose -b`。

板端回退：以 root 执行 `shadow-rollback-arm-chain`，停止新服务并启用旧服务。SD 回退：恢复 `rollback/arm_chain_reset_image.ub` 为 image.ub，使用 rollback/BOOT.BIN 和原 boot.scr。incoming/ 保存交付时全部 22 个文件及原 manifest；不修改原始训练权重。

## 验证范围

- 9 项主机测试：完整 letterbox、RGB/归一化、坐标还原、无人帧、VDMA 停止/错误拒绝、正常帧中断、指纹拒绝/接受和输入格式拒绝。
- Vitis AI 3.0 容器对真实 xmodel 执行严格图校验。
- 新 FIT 回读比较内核、设备树、根文件系统、模型和运行程序。原内核/设备树保留。
- 384×384 实际卷积：1,539,450,144 MAC，按乘/加各计一次 3.078900288 GFLOPs；不含 BN/ReLU/pool/A53 后处理。参数 3,142,166。不能据此承诺 DPU FPS。
- 原发布包的离线 PCK 不等于实板精度。27 帧独立测试集规模很小。

## 尚需实板验收

验证实际指纹和 VART 兼容性；720P 出帧及颜色、缓冲一致性和 HDMI 换帧；双臂下垂、叉腰、平举、上举、交叉、快速升降、多人物抗干扰。检查重复摄像头初始化是否恢复出帧、是否有 VDMA 错误和长期运行异常。

界面显示 YOLO9 DPU。JSON 日志包含 dpu_ms、capture_inference_decode_draw_ms、loop_including_hdmi_ms 和区间 fps。循环耗时包含等待新帧及 HDMI 换帧确认，不是传感器曝光到显示器发光的真实端到端延迟；后者需外部时间标记/高速录像测量。--jsonl 可记录详细日志，文件保存在用户指定路径。
