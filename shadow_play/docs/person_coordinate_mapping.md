# 人物三杆与六路指令：补齐数据链路

2026-10-15：已整理历史候选样本并实现离线标注转换、六轴联合拟合。**尚未得到实物坐标控制模型，没有部署或驱动电机。**

BL、BM、BN、BO 四份记录共 30 个候选采样点，全部找到 Sony/Camo 对应图片；人物六轴有 15 组不同指令，中心化指令矩阵秩为 6。这说明指令有六维数值变化，不证明杆端空间覆盖、帧与指令同步或当前装配适用性。三个杆端坐标仍缺测，不能自动填写。

本地候选文件在 `.review_work/person_coordinate_mapping_20261015/candidates.json`，原始图片继续留在忽略目录，不进入 Git。历史最大最小指令只用于覆盖统计，不能作为带杆限位。

## 数据顺序

1. `prepare_person_coordinate_samples.py` 从明确指定的历史结果文件建立索引，保留十路原指令、双视角证据和来源。输出中 `context_verified`、`annotation_verified`、`command_frame_pair_verified` 默认均为 false。
2. 在原始前视帧标注四个幕布内角和三个真实杆端连接中心。不能以头顶、肩膀、木杆影子的末端替代连接中心；遮挡点留 null。四角顺序：左下、右下、右上、左上。每帧独立计算平面变换，不直接套用旧机位矩阵。
3. `annotate_person_coordinates.py` 将像素点转为幕面归一化坐标（右为 x 正，上为 y 正，范围 0～1）。保留原像素标注和对应文件。该转换不自动确认时间配对或装配上下文；离幕点仍只是平面投影。
4. 单独检查采样时机。移动途中记录的最新 PWM 不等于画面中的已到达位置，不能因帧文件存在就将 `command_frame_pair_verified` 设为 true。机位、杆长、连接条件不同的记录需分开核准上下文，不能强行混合。
5. 只有完成上述核准的数据才能送入 `fit_person_coordinates.py`。输入六维坐标为左手 x/y、头杆 x/y、右手 x/y；输出轴顺序为 1～6。正向也联合拟合六轴对三个杆端的影响，保留身体联动，而非三组独立二维控制。

至少需要 14 组不同的完整指令，且全数据和每个交叉验证训练折都必须满秩。样本重复不会扩大独立覆盖；验证时同一六轴指令的所有重复样本一起留出。报告每个点的预测误差、每轴反算误差与重复散布。线性模型仅描述局部关系，交叉验证通过也不等于冷启动恢复或碰撞检查通过。

## 标注输入示例

以下只是字段格式，数值不是实物测量，不得作为训练样本。`front_file` 必须与候选记录的绝对路径完全相同。

```json
[
  {
    "sample_id": "原候选sample_id",
    "front_file": "原候选evidence.front_file",
    "corners_px": [[0,100],[100,100],[100,0],[0,0]],
    "points_px": {"wusong_left": null,"wusong_neck": null,"wusong_right": null},
    "annotation_verified": false
  }
]
```

从仓库根目录运行（输出文件必须尚不存在）：

```powershell
python shadow_play/integrations/calibration/annotate_person_coordinates.py .review_work/person_coordinate_mapping_20261015/candidates.json annotations.json --output annotated.json
python shadow_play/integrations/calibration/fit_person_coordinates.py verified-context.json --output candidate-model.json
```

`verified-context.json` 是按相同装配与机位筛选、完成标注和时间配对核准后的数据，不是简单改名或批量修改布尔字段。输出始终 `deployment_ready=false`；拟合程序不读取串口、不开 PWM、不解除动作锁，也不向已有控制器注入参数。

下一项实质工作是逐帧补上可辨认的三个连接点，并检查静态保持阶段的指令配对。若剩下的可信历史数据不足以保持六维覆盖，就需要补采缺失方向；不能用拟合自身生成的数据替代实测。未知起点恢复仍是独立未解决项。
