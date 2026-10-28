# 验收记录

验证环境：Python 3.11、RoboDK 5.9.0.25042、官方 Han's E12 模型。

| 项目 | 实际检查 |
|---|---|
| 大脑 HTTP → SAC → E12 | 客户端提交 JSON，真实加载 SAC，135 段路径全部校验并执行；119 层覆盖随运动显示 |
| 仿真轨迹一致性 | 最大 TCP 位置误差小于 0.1 mm；具体记录见 evidence/robodk_acceptance.json |
| 新点云导入 | 新建 1,271 点解析曲面文件，通过上传 API 注册，raster 规划出 60 段 E12 可执行轨迹；未修改业务代码 |
| 仿真中取消 | 在真实运动阶段发送 cancel，任务到 cancelled，检查机器人 Busy 为 false |
| mock | 不调用机器人，不冒充可达性或碰撞已通过，返回 validation.executable=false |
| 自动检查 | 请求/响应规范、错误参数、未知字段、单位/刚体矩阵、幂等冲突、取消、token、状态持久化、PCD 字段读取、m→mm、参数实际生效、未知区域不跨越 |

真实 HTTP 验收数据在 `docs/evidence/`。`demo/evidence/` 是原始完整演示的训练/几何来源记录，不与新接口的验收混淆。截图 `api_demo_preview.png` 来自新 HTTP 接口的真实仿真。

验收范围为接口协议、几何规划和 RoboDK 运动仿真。真实机械臂驱动、真实漆膜标定、任意点云分割、多机械臂及整车覆盖未纳入验证，SAC 与规则基线的性能差异需另行评估。
