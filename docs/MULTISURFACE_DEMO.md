# 多曲面SAC复现与大小脑接入

当前默认演示使用第180,000步验证集选中权重`sac_multisurface_gpu_v2`。训练运行240,000步后停止，耗时67.0分钟；最终240,000步权重未被选为部署模型。结果见[10.29报告](EXPERIMENT_20261029.md)。

## 环境与播放

训练实测为现有conda base、Python3.12.3、PyTorch2.7.1+cu128、RTX3070Ti Laptop 8GB。推理已转为Python3.11、PyTorch2.5.1 CPU可用的相同张量权重，32个观测的GPU/CPU动作最大差为9.54×10⁻⁷。无需重训即可播放。

可使用已有Python3.11/3.12环境；已有CUDA PyTorch正常工作时直接复用，不必再次下载CUDA环境。安装项目依赖：

```bash
python -m pip install -e ".[test,geometry,rl,robodk,demo]"
python tools/setup_multisurface_demo.py
python tools/fetch_robot.py
```

设置实际`ROBODK_EXE`和`ROBODK_PORT`后运行：

```bash
python tools/replay_demo.py --asset-id sacgen_e350_v2
python tools/replay_demo.py --asset-id sacgen_saddle_v2
```

分别演示E350车门和未参与训练的合成鞍形曲面。Windows入口为`Run_Precise_Demo.bat`和`Run_Unseen_Saddle_Demo.bat`。每次运行新建任务，先完成运动/碰撞预检，再播放；显示黄色TCP轨迹和逐步出现的蓝色阈值覆盖。`Show_Demo.bat`只显示已完成的新版车门任务。

安装工具校验SHA256后注册新资产ID。E350完整网格从既有压缩几何包解压复用，新策略与曲面单独注册；同版本复用，遇到被改动的本地资产会报错，请改用独立`--state-dir`。

## 接口示例

启动`python -m spray_cerebellum`后：

```bash
python examples/brain_client.py --task examples/task_precise_door.json
python examples/brain_client.py --task examples/task_unseen_saddle.json
```

新模型显式传入`planning.policy_id: sac_multisurface_gpu_v2`，工件分别为`sacgen_e350_v2`和`sacgen_saddle_v2`。任务保留HTTP/JSON v1字段；喷距200mm、名义速度400mm/s、喷幅240mm、一遍，以及各工件规定的搭接率。重新运行或改参数需换task_id。

软件升级后，旧API服务不会自动重载Python模块，应在原启动终端停止并重启。仓库默认RoboDK端口20721，本次本机检查使用20719，请使用自己的实际配置。

## 独立数值测试

```bash
python tools/evaluate_multisurface.py --verify-recorded --output .local/evaluation_run_01
```

在CPU完成90次当前策略对照，核对公布的全部平均数，不调用RoboDK、不训练。数据在`experiments/multisurface_20261029/`：47个训练/验证/测试几何的曲面、来源与划分、训练报告、权重、逐项CSV、图表及机器人检查结果。原始PCD不重复分发，`sources.json`给出成员和SHA256；`dataset_provenance.json`记录绝对路径改为相对路径，曲面字节不变。

## 可选重新训练

查看演示和接入接口不需要训练。准备可用CUDA PyTorch后，在现有GPU环境运行：

```bash
python tools/train_multisurface.py --steps 240000 --budget-seconds 5400 --run-name study_run_01
```

输出至`.local/multisurface_training/study_run_01`。使用相同45组训练、6组验证配置、随机增益、两层256网络及动作约束。脚本检查真实CUDA运算，不会静默回退CPU；预算最多110分钟，默认90分钟，达到步数或验证平台期可提前停止。一次新训练不保证复现完全相同的权重或耗时。

跨Python3.12训练、3.11推理时，在目标推理环境运行：

```bash
python tools/convert_multisurface_policy.py --run-dir .local/multisurface_training/study_run_01
```

转换严格加载可信张量并检查32个观测，生成`best_inference.zip`。新训练不覆盖发布的固定权重。

## 已知执行限制

E350车门159点、未见鞍形138点已完成RoboDK播放。E350参与训练，仅作回归；鞍形是合成件。`--cases shell starfish`可注册两个真实扫描失败复现资产：贝壳第57点IK跳变，海星第78点MoveL检查返回-1。它们不能用作成功演示，不应绕过预检。

训练没有嵌入机械臂运动学；数值沉积结果不保证E12可执行。新扫描只建模选定可见曲面，未知体积不在碰撞保证范围内。蓝色覆盖不是热力图，也不表示达到真实膜厚；定量热力图在报告中单独展示。
