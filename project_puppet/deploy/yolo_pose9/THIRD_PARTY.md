# 第三方模型与许可

本工程从 Ultralytics YOLOv8n Pose 权重迁移学习：

- 来源：https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8n-pose.pt
- 下载文件 SHA-256：`c6fa93dd1ee4a2c18c900a45c1d864a1c6f7aba75d84f91648a30b7fb641d212`
- 训练代码与模型架构：https://github.com/ultralytics/ultralytics
- 上游许可：AGPL-3.0（另有 Ultralytics 企业许可选项）

Vitis AI 3.0 用于 INT8 量化和 DPUCZDX8G B4096 编译。最终 XModel 是上述 YOLO 派生模型，许可义务不会因转换格式而消失。
