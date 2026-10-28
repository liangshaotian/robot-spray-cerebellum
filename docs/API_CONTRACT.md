# 小脑接口契约 v1.0

机器可读入口：`GET /openapi.json`；仓库中的 `contracts/` 保存生成的 OpenAPI 和 JSON Schema。URL 前缀为 `/v1`，正文 `schema_version` 固定为 `1.0`。未知字段一律拒绝，不依赖字段顺序。

## 请求

完整可运行 JSON 见 `examples/task_robodk.json`。所有参数变化都进入任务指纹，避免同一 ID 被静默改成另一条任务。

| 字段 | 语义及约束 |
|---|---|
| task_id | 1–64 位字母、数字、下划线或连字符；唯一幂等键 |
| skill_id | `spray_surface.v1` |
| target.asset_id | 服务端注册的点云/曲面资产标识，不接受任意文件路径 |
| target.units | 固定 `mm`；`m` 会报错，不自动猜测 |
| target.region_uv_mm | 可选区域 `{u_min_mm,u_max_mm,v_min_mm,v_max_mm}`，必须位于资产可用范围 |
| target.T_robot_base_workpiece | 可选 4×4 刚体变换，覆盖资产默认工位；平移为 mm，旋转正交且行列式 +1 |
| robot.model_id | 当前仅注册 `huayan_e12` |
| robot.tool_id | `spray_tcp_200`，法兰 +Z 方向 200 mm 的 TCP |
| process.standoff_mm | 100–350，喷涂 TCP 到实测表面的名义距离 |
| process.speed_mm_s | 50–700，名义速度；raster 使用该值，SAC 可在其 0.75–1.25 倍间输出局部速度 |
| process.spray_width_mm | 60–400，在相对高斯模型中定义为 4σ 的横向喷幅，不是标定后的真实雾化宽度 |
| process.overlap_ratio | 0–0.9；行距 = 喷幅 × (1−搭接率)，至少 10 mm |
| process.passes | 1–3，重复生成对应遍数的喷涂行，覆盖剂量累计 |
| planning.method | `sac` 或 `raster`；新上传资产没有匹配 SAC 时必须先用 raster |
| planning.policy_id | 当前 `sac_car_side_v1`；该策略只对 demo 资产注册 |
| planning.sample_step_mm | 10–80，沿喷涂行离散间距；任务最多 3000 个表面采样点 |
| execution.backend | `mock` 或 `robodk`；默认 mock |
| execution.mode | `plan_only` 或 `simulate`；默认 plan_only |
| execution.show_window | 默认 false；true 请求显示 RoboDK 窗口 |
| execution.simulation_speed | 0.1–20，仿真播放倍率，不改变导出的 mm/s |
| execution.timeout_s | 5–900，从任务出队开始计时；阻塞 SDK 调用返回后检查超时 |
| context | 至多 16 个字符串键值，记录 skill 版本/关联 ID；仅用于追踪 |

气压、流量、真实膜厚、任意 Python 命令等字段不在协议中，提交时返回 `INVALID_REQUEST`。当前姿态按局部表面法向生成，TCP 的 +Z 指向工件，未开放任意喷射倾角字段。

## 坐标与输出轨迹

`T_robot_base_workpiece` 左乘工件齐次坐标，得到机器人底座坐标。矩阵按 JSON 行排列。机器人保持原尺寸，不随工件缩放。

轨迹端点：`GET /v1/tasks/{task_id}/trajectory`。每段包含：

| 字段 | 说明 |
|---|---|
| nozzle_xyz_mm | 工件坐标系中的 TCP 出口位置 |
| rotation_matrix | 工件坐标系中的 3×3 工具朝向，各列为 TCP 的 X/Y/Z 轴 |
| surface_xyz_mm / surface_normal | 对应实测表面位置及朝外单位法向 |
| speed_mm_s | 该运动段实际下发的速度 |
| spray_on | 到该端点的运动是否喷涂；接近、换行和撤离为 false |
| motion | `MoveJ` 或 `MoveL` |
| joints_deg | 真实后端求得的 E12 关节角，单位 deg；mock 不提供 |
| nozzle_xyz_robot_base_mm / rotation_matrix_robot_base | 真实后端输出的底座坐标系 TCP 位姿 |
| source_policy_step / segment | 对应上游规划步和连续喷涂行 |

真实执行前，全部目标先求逆解、检查关节范围及线性段分支连续性，并对完整路径做 5 mm / 1° 采样运动及碰撞检查。碰撞范围见结果的 `validation.scope`；新上传资产只包含观测曲面，未知实体体积不被自动补全。

## 结果与状态

POST `/v1/tasks`：新任务返回 202；同 ID 同内容返回 200；同 ID 不同内容返回 409。

GET `/v1/tasks/{id}` 返回状态、0–1 进度、事件、result 或 error。结果包含 `backend`、`mode`、`simulation_only`、`validation`、`execution`、`quality`、轨迹链接和坐标变换。

- `validation.executable` 只有真实 RoboDK 全路径检查通过才为 true。
- `execution.executed_in_simulator` 和 `waypoints_executed` 表示是否真的执行了仿真运动；plan_only 为 false / 0。
- `quality.coverage_fraction`、`relative_dose_mean`、`relative_dose_cv` 仅针对指定可靠区域。`physical_thickness_um` 固定为 null。
- mock 的 `planner` 为 `mock_fixture`、quality 为 null、碰撞和可达性为 null，不声称使用了 RL 或机器人。

## 点云上传

POST `/v1/assets/upload`，multipart 两个部分：`metadata` 为 AssetImport JSON 字符串，`point_cloud` 为文件。metadata Schema 见 GET `/v1/schemas/asset-import`。

- 支持 PLY、PCD ASCII/binary（按实际字段解析 XYZ）、无表头 XYZ/TXT、无表头数字 CSV。
- 不支持 PCD binary_compressed、NaN/Inf、少于 16 或多于 200 万点、超过 64 MiB 文件。
- 先按 `input_units` 将原始点转为 mm，再应用 `T_workpiece_input`，其平移始终为 mm。
- 工件局部 X/Y 作为 u/v，局部 +Z 为朝外深度。调用方提供正确的变换和可见曲面；当前不是任意全车点云的自动分割器。
- 资产标识不可覆盖；换数据时使用新的 asset_id。上传资产默认没有已训练 SAC 策略。

## 失败与取消

错误结构为 `{error:{code,message,details}}`。常见 code：

`INVALID_REQUEST`、`ASSET_NOT_FOUND`、`ROBOT_NOT_SUPPORTED`、`REGION_OUT_OF_BOUNDS`、`POLICY_ASSET_MISMATCH`、`TASK_ID_CONFLICT`、`NO_USABLE_SURFACE`、`NO_USABLE_PATH`、`REGION_DISCONTINUITY`、`ROBODK_UNAVAILABLE`、`ROBOT_ASSET_MISSING`、`UNREACHABLE`、`JOINT_LIMIT`、`IK_BRANCH_DISCONTINUITY`、`PATH_VALIDATION_FAILED`、`TRACKING_ERROR`、`CANCELLED`、`TASK_TIMEOUT`、`SERVER_RESTARTED`。

POST `/v1/tasks/{id}/cancel` 请求取消，继续轮询到终态；运动期间约每 40 ms 检查一次取消，但阻塞校验/通信调用必须先返回。服务重启不自动恢复运动。它不替代实体机器人的安全控制器。

任务目录和调试日志在服务端 `.local/`；HTTP 只暴露轨迹、校验结果、结果 JSON 与截图这几个允许的产物，不提供任意文件下载。
