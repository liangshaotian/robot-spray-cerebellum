# 第三方数据与软件边界

## Artec E350 精细车身

署名：**Car body by Artec Group Inc. / Artec 3D**。来源：[官方模型页面](https://www.artec3d.com/3d-models/car-body)。使用的 PLY 归档直链为 `https://cdn.artec3d.com/content-hub-3dmodels/car-body-ply.zip?VersionId=MyziyBFLx7kp34s.SlRWGjKrUC2EfOnA`，原始 ZIP SHA256 为 `e9f76b1293c627b7a46e81abc8697bc74b73c393405a606395081ce7777992c5`。

下载归档随附的 `license.txt` 明确标注 **Creative Commons Attribution 3.0 Unported**，原文保存在 [LICENSE.source.txt](../demo/artec_e350_door_v2/LICENSE.source.txt)。本仓库按该归档自带许可记录来源。

仓库保留完整 1,056,181 个顶点、2,110,072 个三角形，以及原始约 4.88 m 车长，没有缩放。修改包括刚体坐标变换、增加显示用平滑顶点法向，以及提取规划曲面、人工指定车门轮廓和把手遮罩。压缩网格可由安装脚本无损解压；SHA256 见 `checksums.json`。这是扫描重建网格及其派生曲面，不是原始相机传感器点记录，模型不含车轮。

演示图片和派生曲面来源同上。训练所得策略及项目集成代码的说明不代表 Artec 对喷涂算法或其效果的认可。

## 点云和派生演示资产

来源：[Real3D-AD 作者仓库](https://github.com/M-3LAB/Real3D-AD)，[论文](https://arxiv.org/abs/2309.13226)。原始成员 `Real3D-AD-PCD/car/train/153_template.pcd`，1,296,285 个 XYZ 点；原始 SHA256 为 `242207171941cd8d16f08a67fc972d41905d4c7f3ea697c15de8ed2066011301`。

本仓库包含用于研究演示和接口联调的处理后曲面数组、网格、6 万点子采样和短训模型，不包含公司扫描数据。扫描对象是小型汽车外形实物；演示进行了显式仿射尺度映射，不能称为真实生产整车扫描。

这些第三方派生资产保持原来源的使用条件，本仓库不替来源方授予额外的数据许可。第三方资产的使用和再分发应遵守原来源条款。

## 机器人模型和软件

机器人为项目华沿 E12，采用 RoboDK 库中的旧品牌 [Han's E12](https://robodk.com/robot/Han-s/E12) 模型。`tools/fetch_robot.py` 从官方 CDN 下载并验证 SHA256；机器人数据文件不提交版本库。

RoboDK 应用本体及许可由使用者另行准备。本仓库不包含应用 EXE/DLL、补丁、注册工具、注册信息或 Python 运行环境。

## 算法依赖

策略采用 Stable-Baselines3 2.4.1 的 SAC 和 CPU PyTorch。FastAPI/Pydantic 用于任务协议和文档，NumPy/SciPy 用于几何计算，trimesh 用于点云/网格读写。各依赖保持各自许可证；运动仿真验收不构成喷涂质量或跨零件泛化能力验证。
