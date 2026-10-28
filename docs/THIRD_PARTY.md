# 第三方数据与软件边界

## 点云和派生演示资产

来源：[Real3D-AD 作者仓库](https://github.com/M-3LAB/Real3D-AD)，[论文](https://arxiv.org/abs/2309.13226)。原始成员 `Real3D-AD-PCD/car/train/153_template.pcd`，1,296,285 个 XYZ 点；原始 SHA256 为 `242207171941cd8d16f08a67fc972d41905d4c7f3ea697c15de8ed2066011301`。

本仓库包含用于私有项目联调的处理后曲面数组、网格、6 万点子采样和短训模型，不包含公司扫描数据。扫描对象是小型汽车外形实物；演示进行了显式仿射尺度映射，不能称为真实生产整车扫描。

这些第三方派生资产保持原来源的使用条件，本仓库不替来源方授予额外的数据许可。对外发布或用于商业交付前需核对原数据集条款。本仓库用于私有项目协作。

## 机器人模型和软件

机器人为项目华沿 E12，采用 RoboDK 库中的旧品牌 [Han's E12](https://robodk.com/robot/Han-s/E12) 模型。`tools/fetch_robot.py` 从官方 CDN 下载并验证 SHA256；机器人数据文件不提交版本库。

RoboDK 应用本体及许可由使用者另行准备。本仓库不包含应用 EXE/DLL、补丁、注册工具、注册信息或 Python 运行环境。

## 算法依赖

策略采用 Stable-Baselines3 2.4.1 的 SAC 和 CPU PyTorch。FastAPI/Pydantic 用于任务协议和文档，NumPy/SciPy 用于几何计算，trimesh 用于点云/网格读写。各依赖保持各自许可证；运动仿真验收不构成喷涂质量或跨零件泛化能力验证。
