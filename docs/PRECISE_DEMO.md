# 汽车喷漆演示与复现

场景保留完整Artec E350车身和项目指定华沿E12。整车模型约4.88m长、106万个顶点、211万个三角面；当前实际喷涂区域是前车门约0.58m²，而不是整车全覆盖。

## 恢复的汽车视频

[观看39.1秒整车视野视频](media/E12_E350_WholeCar_View.mp4)

![整车视野](media/E12_E350_WholeCar_View.png)

这是原汽车流程录屏，显示完整车身、机械臂、黄色轨迹和逐步覆盖；不是新权重的定量对照视频。当前新权重结果另见[汽车实验记录](EXPERIMENT_20261029.md)。

## 当前模型启动

使用现有Python3.11/3.12环境安装项目依赖，推理不需要GPU：

```bash
python -m pip install -e ".[test,geometry,rl,robodk,demo]"
python tools/setup_automotive_demo.py
python tools/fetch_robot.py
python tools/replay_demo.py --asset-id sacgen_e350_v2
```

RoboDK安装和许可自行准备，设置实际`ROBODK_EXE`和`ROBODK_PORT`。Windows一键入口`Run_Precise_Demo.bat`会注册汽车资产并播放；`Show_Demo.bat`只显示已完成场景。更新代码后应重启旧API进程。

安装校验SHA256，复用完整E350几何；新曲面和策略以`sacgen_e350_v2`注册，不覆盖旧资产。相同内容可复用，被修改的本地资产会明确报错。通过`--state-dir`可安装到独立状态目录。

## 大脑接口与验证

启动API后，运行`python examples/brain_client.py --task examples/task_precise_door.json`。工件为`sacgen_e350_v2`，策略为`sac_multisurface_gpu_v2`（保持已有策略标识），HTTP字段仍为v1。每次重新执行或改参数应使用新的task_id。

新模型来自24万步通用曲面预训练，汽车专用数据训练尚未完成；E350选区见于预训练，因此汽车结果属于回归检查。喷涂参数：喷距200mm、名义速度400mm/s、喷幅240mm、搭接率约58.3%、一遍。已完成159段E12仿真及5mm/1°采样检查。

```bash
python tools/evaluate_automotive.py --verify-recorded --output .local/car_check_01
```

CPU复现同一车门3工况×3方法共9次检查，输出到指定新目录。相对沉积非实测膜厚；高覆盖率不等于均匀合格。车门与把手遮罩人工指定，独立车型迁移、整车喷涂、真实喷枪物理和实体机器人通信尚未验证。
