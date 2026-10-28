# 大脑—小脑接口接入指南

## 1. 模块职责

大脑负责把蒸馏出的 skill 转成结构化任务，包括“哪个工件、哪个区域、怎样喷”。小脑不解释任意自然语言，也不执行上传的脚本；它接收 `spray_surface.v1`，负责轨迹、运动验证和仿真反馈。

使用 `examples/task_mock.json` 验证联调流程。`context.brain_skill_id` 记录上游 skill 标识，`task_id` 是任务的唯一幂等键。完整字段约束见 [接口契约](API_CONTRACT.md)。

## 2. 调用示例

```python
from spray_cerebellum.client import SprayClient

client = SprayClient('http://127.0.0.1:8765')
task = {
    'schema_version': '1.0',
    'task_id': 'skill-door-example-001',
    'skill_id': 'spray_surface.v1',
    'target': {'asset_id': 'demo_car_4500', 'units': 'mm'},
    'process': {'standoff_mm': 200, 'speed_mm_s': 400, 'passes': 1},
    'execution': {'backend': 'mock', 'mode': 'simulate'},
    'context': {'brain_skill_id': 'sprayer_skill_v0.1'},
}
client.submit(task)
feedback = client.wait(task['task_id'])
if feedback['state'] == 'succeeded':
    trajectory = client.trajectory(task['task_id'])
    print(feedback['result'])
else:
    print(feedback['error'])
```

HTTP 调用方可以不使用这个客户端，直接 POST JSON、GET 状态，协议完全一致。客户端本身只使用 Python 标准库，不依赖 RoboDK、torch 或 skill 蒸馏框架。

## 3. 任务状态与生命周期

`queued → planning → validating → simulating → succeeded`；失败为 `failed`，取消为 `cancelled`。mock 或 plan_only 会跳过不适用的阶段。

- 提交返回 202 只代表已受理，不代表已经喷涂完成。
- 终态 `succeeded/failed/cancelled` 后停止轮询。
- 同一任务的网络重试继续使用原 ID、原内容；改参数或有意再次执行时换新 ID。不同内容复用 ID 会返回 409。
- 取消：POST `/v1/tasks/<id>/cancel`，然后等终态。仿真运动会检查取消；正在执行的阻塞式运动校验/SDK 调用返回后才可处理取消。它不是实体机器人的急停接口。
- 服务重启不自动恢复运动；未完成任务标记 `SERVER_RESTARTED`，大脑决定是否以新 ID 重试。

## 4. RoboDK 仿真接入

将 `execution.backend` 改为 `robodk`，使用新 `task_id`。保持 `mode: plan_only` 可先拿校验后的轨迹；需要实际仿真时用新 ID 提交 `mode: simulate`。

`show_window: false` 默认尽量不打断电脑操作；需要看界面再设为 true。程序使用独立 API 端口 20721，并给每个任务建独立仿真工作站；小脑任务单工作线程排队。

mock 的 `validation.executable` 为 false，碰撞/可达性为 null；只有真实 RoboDK 后端校验通过才返回 true。不要仅根据 `state: succeeded` 判断已经做过机器人运动验证。

## 5. 点云资产导入

通过 GET `/v1/assets` 查看可用资产。内置演示使用 `demo_car_4500`。导入其他点云时，调用上传接口，明确单位、输入到工件坐标变换、工件到机器人底座变换及待喷区域，成功后获得新的 `asset_id`。样例见 `examples/upload_cloud.py`。

新资产使用 `planning.method: raster`；演示 SAC 的验证范围限于演示资产。其他资产的 SAC 接入需要增加匹配策略与注册配置，任务提交、状态查询和结果获取沿用同一协议。

仓库还提供 `generated_curved_panel.xyz` 和 `generated_panel_metadata.json`，专门用于演示新点云导入；它是明确标注的解析曲面测试件，不是真实扫描数据。安装 geometry extra 后运行：

```bash
python examples/upload_cloud.py examples/generated_curved_panel.xyz examples/generated_panel_metadata.json
python examples/brain_client.py --task examples/task_uploaded_panel.json
```

第二条会调用真实 RoboDK 做新工件的规划和验证，仍需在仿真电脑准备机器人模型和 robodk extra。只做上传接口联调不需要 RoboDK。

## 6. 联调验收清单

1. 大脑下发 mock 任务，得到任务 ID 和最终状态。
2. 大脑能够读取轨迹，每段可区分喷涂/关枪移动。
3. 错误参数返回 422；同 ID 不同内容返回 409；取消能到 cancelled。
4. 在 RoboDK 电脑切到真实后端，得到可达/采样碰撞结果，并实际播放 E12 喷涂。
5. 大脑读取结果里的 `backend / validation / execution / quality`，区分协议成功、机器人校验和相对覆盖评价。
