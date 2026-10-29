# 2026-10-29 多曲面SAC实验包

完整说明见[实验报告](../../docs/EXPERIMENT_20261029.md)和[复现入口](../../docs/MULTISURFACE_DEMO.md)。

- `dataset.json`：45组训练、6组验证、10种测试和E350回归配置；路径相对本目录。
- `assets/`：47个几何的曲面和来源元数据；原始PCD不重复分发。
- `models/sac_multisurface_gpu_v2.zip`：验证集180,000步选中、可CPU推理的70维权重。
- `models/training_checkpoint_python312.zip`：原Python3.12训练检查点，含优化器状态。
- `results/`：三种当前策略90次测试、图表、E12成功与失败记录。
- `checksums.json`：固定数据和权重的SHA256。

真实扫描为经尺度扩展的研究用小物体，E350保留实车尺度。沉积为未标定的相对量，不是实际膜厚或气压。第三方来源条件见[说明](../../docs/THIRD_PARTY.md)。
