# 大脑模块接入入口

本仓库是喷涂机器人的小脑模块。大脑负责喷涂 skill 蒸馏、任务选择和指令下发；小脑接收结构化任务，生成末端轨迹，进行华沿 E12 运动验证，并返回仿真结果。软件版本为 0.2.0，接口版本为 1.0。

## 先完成接口联调

使用 Python 3.11，克隆仓库后运行：

```bash
python -m pip install -e ".[test]"
python -m spray_cerebellum
```

在另一个终端运行：

```bash
python examples/brain_client.py --task examples/task_mock.json
```

这条路径不依赖 RoboDK、PyTorch 或机械臂，验证任务提交、状态查询、轨迹获取、错误处理和取消。mock 结果不代表完成了机器人可达性或喷涂质量验证。

## 大脑需要提供的内容

| 输入 | 含义 |
|---|---|
| task_id | 唯一任务编号；网络重试沿用，重新执行或改参数时更换 |
| target.asset_id | 已注册工件；精细演示为 artec_e350_door_v2 |
| target.region_uv_mm | 可选，工件局部坐标系中的待喷区域，单位 mm |
| process | 喷距、名义速度、喷幅、搭接率、遍数 |
| planning | sac 或 raster；SAC 策略必须与工件匹配 |
| execution | mock/robodk、plan_only/simulate，以及是否显示窗口 |
| context | skill 版本、上游任务编号等追踪信息 |

大脑调用 `POST /v1/tasks`，再轮询 `GET /v1/tasks/{id}`。任务完成后从 result 和 trajectory 接口读取结果。`succeeded` 表示任务流程成功；是否实际执行仿真，应检查 `execution.executed_in_simulator`，运动验证看 `validation`。

输出包括：每段 TCP 位姿、速度、喷涂开关、E12 关节角、坐标系、运动检查结果和未标定的相对覆盖评价。任意自然语言指令需由大脑先转换成任务 JSON。

## 运行精细演示

完成 [精细演示复现说明](PRECISE_DEMO.md) 的依赖安装和资产注册，然后：

```bash
python examples/brain_client.py --task examples/task_precise_door.json
```

该样例经同一个 HTTP 接口调用真实 SAC、E12 逆解、碰撞检查和 RoboDK 动画。首次查看演示可直接运行仓库根目录的 `Run_Precise_Demo.bat`；模型和策略已包含在仓库中，不需要重新训练。

## 对接参考

- [完整接入指南](HANDOFF.md)：Python 调用、任务生命周期、跨电脑接入和验收步骤。
- [接口契约](API_CONTRACT.md)：字段、单位、坐标系、错误码和边界。
- [OpenAPI](../contracts/openapi.json) / [任务输入 Schema](../contracts/task_request.schema.json)：机器可读定义。
- [精细任务样例](../examples/task_precise_door.json) / [大脑客户端](../examples/brain_client.py)。

跨电脑调用需要使用运行小脑服务的电脑地址，并配置共享 token；GitHub 链接本身不是运行中的服务地址。仓库为私有项目，接收者需要 GitHub 仓库访问权限。

## 验证范围

已验证：结构化接口、点云导入、规则/SAC 规划、E12 采样运动与碰撞检查，以及 RoboDK 动画。当前演示是单车门局部区域；车门轮廓和把手遮罩由人工指定。SAC 是开源通用算法在自定义环境中的短训原型，未进行充分训练或跨零件泛化验证。实体机械臂通信、自动整车分割、真实膜厚、气压与雾化物理模型不在现有实现中。
