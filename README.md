# 日麻出牌提示助手

一个本地开发的四人立直麻将规则型出牌助手。开发顺序是先跑通 mjai 模拟，再逐步实现规则引擎、评估和界面；好友房数据接入留到最后。

## 当前状态

- **阶段 1 已完成**：mjai Docker 冒烟模拟、结果解析和按 bot 名称聚合。
- **阶段 2 已完成（CPU 路径）**：用户指定的 v3 模型已校验；官方 Mortal CPU 容器构建、mjai 对局和 Docker NVIDIA 直通验证均已完成。官方推理入口固定使用 CPU。
- **阶段 3 基线已实现**：只依据向听数和有效进张选牌，支持打成 mjai bot zip。

基线和摸切 bot 都是实验工具，不是实战提示助手。

## 环境

- Windows 10/11、Python 3.12（`mjai` 的 PyPI 分类器列出 3.10–3.12）
- Docker Desktop 已安装并启动
- PowerShell

在项目目录运行：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m pip install -r requirements-simulation.txt
```

所有命令直接使用虚拟环境中的 Python，不需要激活环境或调整 PowerShell 执行策略。

运行全部本地测试：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

在 PowerShell 中，标准输入自检可用下面的方式：

```powershell
'[{"type":"tsumo","actor":0,"pai":"5mr"}]' | .\.venv\Scripts\python.exe bot.py 0
```

输出应为一条 `dahai` JSON。模拟器的首次运行会下载所需 Docker 镜像：

```powershell
.\.venv\Scripts\python.exe tools\run_first_game.py
```

默认使用四个同一摸切 bot，日志写入 `logs\first_game`。解析这场模拟：

```powershell
.\.venv\Scripts\python.exe tools\summarize_results.py logs\first_game `
  --default-bots tsumogiri,tsumogiri,tsumogiri,tsumogiri `
  --csv logs\first_game\results.csv
```

`summary.json` 的 `rank` 是按座位排列；脚本根据每场的 `experiment.json` 将顺位归到 bot 名称，输出每个 bot 的平均顺位、一位率、四位率、出现的对局数和座位样本数，并生成每局一行的 CSV。第一场四家是同一个摸切 bot，所以预期为 1 场、4 个座位样本、平均顺位 2.5、一位率 25%、四位率 25%。

## 纯牌效率基线与座位轮换

基线在每个候选弃牌后计算向听数，再统计能降低向听数的有效进张数。可单独打包并本地检查：

```powershell
.\.venv\Scripts\python.exe tools\package_bot.py `
  --entrypoint bot_efficiency.py `
  --output build\efficiency-bot.zip
```

与摸切示例 bot 对照，并让基线轮换到四个座位：

```powershell
.\.venv\Scripts\python.exe tools\package_bot.py --output build\tsumogiri-bot.zip
.\.venv\Scripts\python.exe tools\run_experiment.py `
  --submission build\efficiency-bot.zip `
  --submission build\tsumogiri-bot.zip `
  --submission build\tsumogiri-bot.zip `
  --submission build\tsumogiri-bot.zip `
  --bot-name efficiency --bot-name tsumogiri --bot-name tsumogiri --bot-name tsumogiri `
  --logs-dir logs\efficiency-vs-tsumogiri --rotate
.\.venv\Scripts\python.exe tools\summarize_results.py `
  logs\efficiency-vs-tsumogiri --csv logs\efficiency-vs-tsumogiri\results.csv
```

`--rotate` 会跑四场，每场在 `experiment.json` 记录座位与 bot 映射。当前固定种子的冒烟结果：4 场中基线平均顺位 1.0、一位率 100%；摸切组 12 个座位样本平均顺位 3.0、一位率 0%、四位率 33.3%。**样本很小且对手是摸切 bot，不代表真实强度或统计显著性。**

## Mortal 模型与 GPU 状态

下载脚本不会替你选择模型来源；只有在你提供 HTTPS URL、SHA-256、模型版本和该运行时明确支持的版本集合后才会下载到指定目录。它先核对 SHA-256，再通过 `torch.load(..., weights_only=True)` 读取 `config.control.version`，并确认 checkpoint 的 v3/v4 版本在运行时支持集合中：

```powershell
.\.venv\Scripts\python.exe tools\download_mortal_model.py `
  --url <你选定的HTTPS地址> --sha256 <64位SHA256> `
  --model-version v3 --runtime-supported-versions v3,v4 --output-dir models
```

下载前需安装与选定 Mortal 运行时匹配的 PyTorch。本机 CPU 校验可用：

```powershell
.\.venv\Scripts\python.exe -m pip install "torch>=2.6,<3" --index-url https://download.pytorch.org/whl/cpu
```

没有指定来源和校验值时，脚本不会运行下载。

已经下载并验证了你指定的 v3 checkpoint（SHA-256 匹配）。可以构建 CPU Mortal 容器并打包模型：

```powershell
docker build -f Dockerfile.mortal -t majang-mortal:cpu .
.\.venv\Scripts\python.exe tools\package_mortal_bot.py
```

容器基于官方 mjai 客户端镜像，固定 Mortal 源码 commit，并将评估设备设为 CPU。运行一场基线对三家 Mortal：

```powershell
.\.venv\Scripts\python.exe tools\run_experiment.py `
  --submission build\efficiency-bot.zip `
  --submission build\mortal-bot.zip `
  --submission build\mortal-bot.zip `
  --submission build\mortal-bot.zip `
  --bot-name efficiency --bot-name mortal --bot-name mortal --bot-name mortal `
  --docker-image majang-mortal:cpu --logs-dir logs\efficiency-vs-mortal --rotate
```

此命令会跑四场轮换。当前小样本输出：纯效率基线 4 场平均顺位 4.0；Mortal 12 个座位样本平均顺位 2.0、一位率 33.3%。样本太少，仅验证接线与统计格式，不代表强度结论。自定义镜像保留 mjai HTTP 启动器；Mortal 适配器会把批量 mjai 输入逐事件交给官方 `libriichi` bot，并在没有动作时返回 `none`，避免 HTTP 行协议等待超时。

已在本机 RTX 3060 验证 Docker 的 NVIDIA 直通：

```powershell
docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi
```

容器内成功识别 RTX 3060。**这证明 Docker GPU 运行时可用，但不等于 Mortal 推理已使用 GPU。**核对的 [官方 Mortal 推理入口](https://github.com/Equim-chan/Mortal/blob/main/mortal/mortal.py)将 `device` 固定为 CPU；同时，当前 `mjai.Simulator` 启动 bot 容器时没有加 `--gpus all`。因此当前官方推理路径不会使用 GPU。若改为 GPU 推理，需要调整 Mortal 推理代码和 PyTorch CUDA 镜像，并修改模拟器启动容器的 GPU 参数，再用你选定的 checkpoint 做实际验证。

CPU 推理会占用 bot 容器的 CPU，并可能降低批量模拟吞吐；`mjai` 默认每次动作超时为 2 秒。所选 v3 模型已在四场座位轮换对局中实测 **1,873 次推理：平均 20.35 ms、中位数 18.57 ms、P95 28.24 ms、最大 136.49 ms**（Mortal 日志中的 `eval_time_ns`，非整局耗时）。这些数据仅适用于当前容器、模型和一批小样本对局。

可从日志重新计算推理耗时：

```powershell
.\.venv\Scripts\python.exe tools\report_mortal_latency.py logs\efficiency-vs-mortal
```

## 项目结构

```text
bot.py                             mjai 容器入口
bot_efficiency.py                  纯牌效率基线入口
src\mahjong_advisor\bot.py         mjai 摸切协议 bot
src\mahjong_advisor\efficiency_bot.py  牌效率基线策略
tools\package_bot.py               将 bot 和包代码打成提交 zip
tools\run_first_game.py            调用 mjai.Simulator 跑一局
tools\run_experiment.py             运行四家 bot 并可轮换座位
tools\summarize_results.py          解析顺位并写 CSV
tools\download_mortal_model.py      按用户指定来源下载并校验模型
tools\package_mortal_bot.py         打包 Mortal 模型与 mjai 适配器
tools\report_mortal_latency.py      汇总 Mortal 推理耗时
bot_mortal.py                       Mortal 到 mjai 行协议的适配器
Dockerfile.mortal                   固定源码版本的 CPU Mortal 镜像
tests\                              本地单元测试
config\                            后续策略参数与实验配置
logs\                              模拟器日志（运行时生成）
```

后续模块按职责放入 `src\mahjong_advisor\`：统一局面状态、牌效率和役种分析、打点估计、防守与押退、局况调整、决策引擎、mjai 适配、Tkinter 提示窗。统计、基线对战和自动调参工具放在 `tools\`。引擎只接收统一状态；模拟器事件和将来的好友房事件解析器分别负责转换状态。

## 开发路线

1. **环境与协议冒烟测试（已完成）**：打包 bot，用 mjai/Docker 跑首局。
2. **评估基础（已完成）**：保存每局结果，输出平均顺位、一位率、四位率和 CSV。
3. **纯牌效率基线（已完成）**：仅按向听数和有效进张选牌，支持座位轮换。
4. **Mortal 对照（CPU 基础链路已跑通）**：扩大样本；之后统计与 Mortal 的出牌一致率。
5. **规则助手**：实现役种与打点、防守安全度、押退及顺位/局况调整；完善模拟器输入适配。
6. **自动调参**：参数配置化，先小样本筛选，再对候选方案进行大样本验证并报告置信区间。
7. **提示窗**：置顶 Tkinter 小窗，仅显示一个当前推荐。
8. **好友房数据接入**：最后实现，并仅用于所有参与者知情同意的好友房。

每个阶段都应有独立的运行命令和针对性测试。Mortal 模型文件由使用者自行选择和核实；下载工具检查 SHA-256、安全加载及版本兼容。NVIDIA/Docker GPU 直通已在本机实际验证，但官方 Mortal 推理当前仍使用 CPU。

## 当前限制

- 当前摸切和纯牌效率 bot 仅用于模拟与基线对比，不是完整出牌提示助手。
- `mjai` 模拟器调用 Docker，首次启动需要拉取镜像和可用的网络连接。
- 当前 Mortal 对照只有四场座位轮换，小样本不足以评价策略强度。
- 尚未实现完整策略引擎、自动调参或客户端通信解析。
