# 日麻出牌提示助手

一个本地开发的四人立直麻将规则型出牌助手。开发顺序是先跑通 mjai 模拟，再逐步实现规则引擎、评估和界面；好友房数据接入留到最后。

## 当前状态

- **阶段 1 已完成**：mjai Docker 冒烟模拟、结果解析和按 bot 名称聚合。
- **阶段 2 已完成（CPU 路径）**：用户指定的 v3 模型已校验；官方 Mortal CPU 容器构建、mjai 对局和 Docker NVIDIA 直通验证均已完成。官方推理入口固定使用 CPU。
- **阶段 3 基线已实现**：只依据向听数和有效进张选牌，支持打成 mjai bot zip。
- **阶段 4.1 已完成**：加入赤五牌表示、一般形/七对子/国士无双向听数和有效进张核心；纯效率 bot 已改用该核心。
- **阶段 4.2 已完成**：加入效率弃牌排序和自动立直；使用 mjai 官方状态机判断立直是否合法。

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

`--rotate` 会跑四场，每场在 `experiment.json` 记录座位、bot 映射和种子。四场轮换使用同一个 mjai 种子元组；默认是 `(10000, 2000)`，也可用 `--seed` 改第二个分量。这样只改变 bot 所在座位，不会为每个座位轮换另选种子。

基线的固定策略如下：

- 只在自己的摸牌后出牌；不立直，也不吃、碰或杠。其他时机一律回复 `none`。
- 对每种不同牌计算弃牌后的向听数，先选向听数最低的牌；并列时选能带来最多「严格降低向听数」有效进张的牌。
- 有效进张剩余数按 `4 - 已公开可见数 - 弃牌后自己持有数` 计算；仍并列时按牌索引排序。
- 不评估役种、打点、防守、赤牌价值或局况。相同牌种的赤五与普通五不作价值区分。

当前固定种子的冒烟结果：4 场中基线平均顺位 1.0、一位率 100%；摸切组 12 个座位样本平均顺位 3.0、一位率 0%、四位率 33.3%。**样本很小且对手是摸切 bot，不代表真实强度或统计显著性。**

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

CPU 推理会占用 bot 容器的 CPU，并可能降低批量模拟吞吐；`mjai` 默认每次动作超时为 2 秒。最新 50 局基准记录了 **22,274 次推理：平均 19.29 ms、中位数 17.57 ms、P95 27.87 ms、最大 215.72 ms**（Mortal 日志中的 `eval_time_ns`，非整局耗时）。这些数据仅适用于当前容器和所选 v3 模型。

可从日志重新计算推理耗时：

```powershell
.\.venv\Scripts\python.exe tools\report_mortal_latency.py logs\efficiency-vs-mortal
```

### 吞吐量基准

`tools\benchmark_throughput.py` 可运行「1 个效率基线 + 3 个 Mortal」，并分别测试不同并发数。每局使用递增的可复现种子、独立端口和日志目录；输出 `games.csv`（逐局耗时、Mortal 推理次数、有效性及顺位）与 `benchmark.json`（吞吐量、Docker CPU 和峰值内存）。例如：

```powershell
.\.venv\Scripts\python.exe tools\benchmark_throughput.py `
  --efficiency-submission build\efficiency-bot.zip `
  --mortal-submission build\mortal-bot.zip `
  --logs-dir logs\throughput\concurrency-1 `
  --games 50 --concurrency 1 --seed 3000 --port-base 28100
```

用新的 `--logs-dir` 分别重跑 `--concurrency 2`、`4` 或 `8`；端口范围不能与其他正在运行的模拟重叠。失败局会保留在 CSV 中并标记为无效，不计入有效局吞吐量。Docker CPU 是本次新建 bot 容器的聚合用量，不包含基准开始前已运行的容器。

本机实测（Mortal CPU 镜像，Docker 主机 16 核、总内存约 7,868 MiB）：

| 并发 | 样本 | 有效局 | 有效局/小时 | 平均单局耗时 | 平均 Docker CPU | 峰值内存 |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 50 | 50 | 106.9 | 33.61 秒 | 3.43 核（主机 21.4%） | 1,019 MiB |
| 2 | 8 | 8 | 141.3 | 46.58 秒 | 7.32 核（主机 45.8%） | 2,014 MiB |
| 4 | 8 | 2 | 16.9 | 194.69 秒 | 10.08 核（主机 63.0%） | 3,875 MiB |

并发 1 的 50 局记录了 22,274 次 Mortal 推理，平均 19.29 ms；按并发 2 的短样本吞吐外推，10,000 局东南战约需 **70.8 小时**，远超几小时。东风战没有直接测量；用这 50 局的东场局数和耗时作粗略代理，再按并发 2 吞吐缩放，10,000 局约 **51 小时**，不能视为东风战实测。并发 4 的 6 个失败局在日志中出现 2 秒动作超时及后续协议错误；并发 8 未运行，因为按峰值内存线性估算会接近 Docker 内存上限。并发 2/4 的上述数字来自端口槽独占修复后的测量；修复前的并发数据已弃用。

**东风战限制：**当前安装的 `mjai.Simulator` 没有东风/东南模式参数，运行日志明确记录为 `hanchang game`。因此上述命令跑的是东南战（hanchan），不能当作东风战基准；如需东风战，必须先更换或扩展模拟器。

### 核心牌型分析（阶段 4.1）

`src\mahjong_advisor\core.py` 提供统一的 34 种牌索引、保留赤五身份的 `Tile`、手牌计数、三种和牌形的向听数，以及按可见牌数量折算的有效进张。副露手牌不计算七对子和国士无双。纯效率 bot 复用这些分析函数。

运行核心与基线回归测试：

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_core tests.test_efficiency_bot -v
```

预期 11 项通过。核心 bot 与改造前的效率基线做了 4 场同种子座位轮换：核心平均顺位 **2.50**，基线平均顺位 **2.50**；配对平均顺位差 **0.00**，按轮换计算的 95% t 区间 **[-2.74, 2.74]**。四场只有一个独立种子组，因此该区间仅作描述，不能估计种子间差异或据此判断强弱。

### 牌效率选牌与立直（阶段 4.2）

`src\mahjong_advisor\efficiency_strategy.py` 按「弃牌后向听数最低、再按有效进张最多」排序。mjai 适配器使用官方 `can_riichi` 状态，仅在规则允许时自动立直，并先保存最优听牌弃牌，再响应 `reach`；可和牌时接受自摸/荣和。该阶段不做吃碰杠，也未加入打点、役种或局况判断。

打包并运行四座同种子轮换：

```powershell
.\.venv\Scripts\python.exe tools\package_bot.py --entrypoint bot_efficiency.py --output build\efficiency-bot.zip
.\.venv\Scripts\python.exe tools\package_bot.py --entrypoint bot_strategy.py --output build\efficiency-riichi.zip
.\.venv\Scripts\python.exe tools\run_experiment.py `
  --submission build\efficiency-riichi.zip --bot-name riichi `
  --submission build\efficiency-bot.zip --bot-name baseline `
  --submission build\efficiency-bot.zip --bot-name baseline `
  --submission build\efficiency-bot.zip --bot-name baseline `
  --logs-dir logs\strategy-riichi-vs-baseline\sample-002 --rotate --seed 8100 --port-base 29100
.\.venv\Scripts\python.exe tools\summarize_results.py `
  logs\strategy-riichi-vs-baseline\sample-002 `
  --csv logs\strategy-riichi-vs-baseline\sample-002\results.csv
```

该样本 4 场均有效，29 次立直均被接受；立直 bot 平均顺位 **1.00**，基线 **3.00**，四场配对差均为 **-2.00**。按轮换计算的 95% t 区间退化为 `[1.00, 1.00]`（配对差 `[-2.00, -2.00]`），但这四场使用同一牌山种子，独立种子组只有 1 个，种子层级的置信区间不可估。结果仅为协议与策略冒烟样本，不代表强度结论。

## 项目结构

```text
bot.py                             mjai 容器入口
bot_efficiency.py                  纯牌效率基线入口
src\mahjong_advisor\bot.py         mjai 摸切协议 bot
src\mahjong_advisor\efficiency_bot.py  牌效率基线策略
src\mahjong_advisor\core.py        牌表示、向听数和有效进张
src\mahjong_advisor\efficiency_strategy.py  效率弃牌和立直判断
bot_strategy.py                    mjai 效率/立直适配器入口
tools\package_bot.py               将 bot 和包代码打成提交 zip
tools\run_first_game.py            调用 mjai.Simulator 跑一局
tools\run_experiment.py             运行四家 bot 并可轮换座位
tools\summarize_results.py          解析顺位并写 CSV
tools\benchmark_throughput.py       并发吞吐量、Docker CPU/内存及逐局推理计数
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
4. **Mortal 对照（CPU 基础链路已跑通）**：完成 50 局并发 1 吞吐测量和并发 2/4 小样本；后续再增加轮换强度评估及出牌一致率。
5. **规则助手**：核心牌型分析、效率弃牌和立直判断已完成；下一步实现防守，再实现役种/打点和局况权重配置。
6. **自动调参**：参数配置化，先小样本筛选，再对候选方案进行大样本验证并报告置信区间。
7. **提示窗**：置顶 Tkinter 小窗，仅显示一个当前推荐。
8. **好友房数据接入**：最后实现，并仅用于所有参与者知情同意的好友房。

每个阶段都应有独立的运行命令和针对性测试。Mortal 模型文件由使用者自行选择和核实；下载工具检查 SHA-256、安全加载及版本兼容。NVIDIA/Docker GPU 直通已在本机实际验证，但官方 Mortal 推理当前仍使用 CPU。

## 当前限制

- 当前摸切和纯牌效率 bot 仅用于模拟与基线对比，不是完整出牌提示助手。
- `mjai` 模拟器调用 Docker，首次启动需要拉取镜像和可用的网络连接。
- 吞吐测试中的 50 局固定座位，不能用于评价策略强度；目前对 Mortal 的座位轮换仍是小样本。
- 尚未实现防守、役种/打点、局况权重、自动调参或客户端通信解析。
