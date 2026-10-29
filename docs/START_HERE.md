# 汽车喷漆大脑模块接入

大脑负责喷漆skill蒸馏与任务下达；小脑负责车身曲面轨迹、华沿E12运动检查和仿真反馈。软件0.3.1，HTTP/JSON v1。

## 协议联调

```bash
python -m pip install -e ".[test]"
python -m spray_cerebellum
# 另开终端：
python examples/brain_client.py --task examples/task_mock.json
```

mock验证消息与状态，不代表机器人已执行。API为`http://127.0.0.1:8765`，文档`/docs`。

## 汽车场景

按[复现说明](PRECISE_DEMO.md)安装依赖、运行`python tools/setup_automotive_demo.py`并准备RoboDK和E12模型，然后用`examples/task_precise_door.json`调用同一HTTP接口。

- `target.asset_id`: `sacgen_e350_v2`，完整E350显示，实际前车门局部喷涂。
- `planning.policy_id`: `sac_multisurface_gpu_v2`，保留既有策略标识与70维观测。
- `process`: 喷距、名义速度、喷幅、搭接率、遍数，mm及mm/s。
- `target.region_uv_mm`与坐标变换按工件坐标系；区域不得超出注册有效范围。
- `execution`: mock/robodk，plan_only/simulate，是否显示窗口。

POST `/v1/tasks`后轮询状态，终态后读取result和trajectory。同ID同参数是幂等重试，重新执行或改参数必须换task_id。`succeeded`只代表流程成功；看`validation`判断机器人检查，看`execution.executed_in_simulator`判断是否实际播放。

输出包括TCP位姿、速度、喷涂开关、E12关节角、坐标系及相对覆盖。任意自然语言先由大脑转为任务JSON；气压等未建模字段会报错。新增车身点云需明确单位和变换，默认raster规划；绑定SAC前另做适配与运动检查。

接口契约见[API_CONTRACT](API_CONTRACT.md)，跨电脑、token和生命周期见[HANDOFF](HANDOFF.md)。[汽车实验记录](EXPERIMENT_20261029.md)和[整车视野视频](media/E12_E350_WholeCar_View.mp4)供交接查看。GitHub是代码和材料，不是运行中的服务地址。
