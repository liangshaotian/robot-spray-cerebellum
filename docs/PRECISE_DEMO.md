# 汽车喷漆演示与复现

汽车喷涂场景由Artec E350车身、华沿E12及喷枪组成。车身长约4.88m，包含106万个顶点、211万个三角面；喷涂选区为前车门约0.58m²区域。

## 汽车喷涂过程

[观看39.1秒整车视野视频](media/E12_E350_WholeCar_View.mp4)

![整车视野](media/E12_E350_WholeCar_View.png)

视频时长39.1秒，展示车身、机械臂、TCP轨迹及喷涂覆盖过程。训练参数与定量评价见[汽车实验记录](EXPERIMENT_20261029.md)。

## 运行仿真

使用现有Python3.11/3.12环境安装项目依赖，推理不需要GPU：

```bash
python -m pip install -e ".[test,geometry,rl,robodk,demo]"
python tools/setup_automotive_demo.py
python tools/fetch_robot.py
python tools/replay_demo.py --asset-id sacgen_e350_v2
```

RoboDK安装和许可自行准备，设置实际`ROBODK_EXE`和`ROBODK_PORT`。Windows一键入口`Run_Precise_Demo.bat`会注册汽车资产并播放；`Show_Demo.bat`只显示已完成场景。更新代码后应重启API服务。

安装脚本校验SHA256，将车身曲面和SAC策略注册为`sacgen_e350_v2`。重复安装相同内容会复用，被修改的本地资产会明确报错。通过`--state-dir`可安装到独立状态目录。

## 大脑接口与验证

启动API后，运行`python examples/brain_client.py --task examples/task_precise_door.json`。工件为`sacgen_e350_v2`，策略为`sac_multisurface_gpu_v2`，采用70维观测及HTTP v1接口。每次重新执行或改参数应使用不同的task_id。

SAC采用24万步通用曲面预训练参数；E350选区参与过训练，汽车结果属于回归检查，跨车型泛化尚未验证。喷涂参数：喷距200mm、名义速度400mm/s、喷幅240mm、搭接率约58.3%、一遍。已完成159段E12仿真及5mm/1°采样检查。

```bash
python tools/evaluate_automotive.py --verify-recorded --output .local/car_check_01
```

CPU复现同一车门3工况×3方法共9次检查，输出到指定新目录。相对沉积非实测膜厚；高覆盖率不等于均匀合格。车门与把手遮罩人工指定，独立车型迁移、整车喷涂、真实喷枪物理和实体机器人通信尚未验证。
