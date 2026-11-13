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

`summary.json` 的 `rank` 是按座位排列；脚本根据每场的 `experiment.json` 将顺位归到 bot 名称，输出平均顺位、一位率、四位率、样本数、完整轮换牌山组数和按组 bootstrap 的 95% 区间，并生成每局一行的 CSV。无效对局会保留在 CSV、标记原因并排除于指标外。第一场四家是同一个摸切 bot，所以预期为 1 场、4 个座位样本、平均顺位 2.5、一位率 25%、四位率 25%；它没有完整四座轮换组，因此区间显示为不可估。

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

当前固定种子的一组四座轮换：基线平均顺位 1.0、一位率 100%；摸切组 12 个座位样本平均顺位 3.0、一位率 0%、四位率 33.3%。只有 1 个牌山组，平均顺位 95% 区间不可估。**样本很小且对手是摸切 bot，不代表真实强度或统计显著性。**

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

容器基于官方 mjai 客户端镜像，固定 Mortal 源码 commit，并将评估设备设为 CPU；容器设置 `OMP_NUM_THREADS=1`，适配器也调用 `torch.set_num_threads(1)`。运行一场基线对三家 Mortal：

```powershell
.\.venv\Scripts\python.exe tools\run_experiment.py `
  --submission build\efficiency-bot.zip `
  --submission build\mortal-bot.zip `
  --submission build\mortal-bot.zip `
  --submission build\mortal-bot.zip `
  --bot-name efficiency --bot-name mortal --bot-name mortal --bot-name mortal `
  --docker-image majang-mortal:cpu --logs-dir logs\efficiency-vs-mortal --rotate
```

此命令会跑四场轮换。当前小样本输出：纯效率基线平均顺位 4.0；Mortal 12 个座位样本平均顺位 2.0、一位率 33.3%。这是 1 个牌山组，种子层级 95% 区间不可估；样本太少，仅验证接线与统计格式，不代表强度结论。自定义镜像保留 mjai HTTP 启动器；Mortal 适配器会把批量 mjai 输入逐事件交给官方 `libriichi` bot，并在没有动作时返回 `none`，避免 HTTP 行协议等待超时。

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

这个工具按单次推理汇总延迟，可能包含无效对局留下的部分推理记录；输出会另列有效/无效对局、完整四座轮换牌山组数和来源对局的顺位区间。策略胜负统计仍排除所有无效对局。

### 性能剖析与吞吐量基准

`tools\profile_game_timing.py` 解析 `runner.log` 和 bot 日志，把每局墙钟时间分成 Mortal 推理、助手选牌、容器启动/清理、协议/适配器剩余时间，以及模拟器剩余时间；它会输出逐局 CSV 和汇总 JSON，并报告各部分占墙钟时间比例。推理时间来自 Mortal 的 `eval_time_ns`；助手计时包围被测 bot 的基线选牌或阶段 4.2 策略决策。协议残差含容器请求、MJAI 适配器和日志开销，模拟器残差由墙钟时间扣除上述部分估算。

`tools\benchmark_throughput.py` 可运行「1 个效率基线 + 3 个 Mortal」，并分别测试不同并发数。每局使用递增的可复现种子、独立端口和日志目录；输出 `games.csv`（逐局耗时、Mortal 推理次数、有效性及顺位）与 `benchmark.json`（吞吐量、Docker CPU、峰值内存、无效率和来源对局顺位背景）。此吞吐工具固定座位，不做四座轮换，因此顺位均值仅作描述，组级置信区间不可估。

```powershell
.\.venv\Scripts\python.exe tools\benchmark_throughput.py `
  --efficiency-submission build\efficiency-bot.zip `
  --mortal-submission build\mortal-bot.zip `
  --logs-dir logs\throughput\concurrency-1 `
  --games 50 --concurrency 1 --seed 3000 --port-base 28100
```

用新的 `--logs-dir` 分别重跑 `--concurrency 2`、`4` 或 `8`；端口范围不能与其他正在运行的模拟重叠。失败局会保留在 CSV 中并标记为无效，不计入有效局吞吐量。Docker CPU 是本次新建 bot 容器的聚合用量，不包含基准开始前已运行的容器。镜像限制 PyTorch intra-op 线程数为 1；决策计时仅写入 bot stderr，不改变推荐动作。并发 8 未运行：先依据并发 4 的峰值内存评估风险，不在 Docker 内存余量不足时继续压测。

线程限制前的历史基准（Mortal CPU 镜像默认 PyTorch intra-op 8 线程；Docker 主机 16 核、总内存约 7,868 MiB）：

| 并发 | 样本 | 有效局 | 有效局/小时 | 平均单局耗时 | 平均 Docker CPU | 峰值内存 |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 50 | 50 | 106.9 | 33.61 秒 | 3.43 核（主机 21.4%） | 1,019 MiB |
| 2 | 8 | 8 | 141.3 | 46.58 秒 | 7.32 核（主机 45.8%） | 2,014 MiB |
| 4 | 8 | 2 | 16.9 | 194.69 秒 | 10.08 核（主机 63.0%） | 3,875 MiB |

历史并发 4 的失败日志中，Mortal 玩家收到自身摸牌事件后未及时回复，约 2 秒后动作超时并出现协议错误。旧容器默认 8 个 intra-op 线程、单容器 CPU 配额 4 核；并发 4 时过量线程竞争是合理假设，但超时请求没有 `eval_time_ns`，日志无法证明这是根因。

单线程限制复测结果（`OMP_NUM_THREADS=1` 且真实模型加载后 `torch.get_num_threads()==1`；Docker 主机 16 核、约 7,868 MiB 内存）：

| 并发 | 对局数 | 有效局/无效率 | 完整轮换牌山组 | 有效局/小时 | 平均单局耗时 | 平均 Mortal 推理/局 | Docker CPU 均值 | 峰值内存 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 50 | 50/50，0% | 0 | 105.5 | 34.08 秒 | 411.2 | 0.62 核（3.9%） | 1,039 MiB |
| 2 | 8 | 8/8，0% | 0 | 180.6 | 36.14 秒 | 403.9 | 1.15 核（7.2%） | 1,983 MiB |
| 4 | 8 | 8/8，0% | 0 | 305.9 | 41.28 秒 | 405.9 | 2.70 核（16.9%） | 3,888 MiB |

吞吐量最高的已测并发为 4；并发 1/2/4 全部有效。按每局容器启动和清理、请求协议、模拟器残差等拆分：

| 并发 | Mortal 推理 | 助手决策 | 容器与协议（启动/清理/协议残差） | 模拟器残差 |
|---:|---:|---:|---:|---:|
| 1 | 9.01 秒（26.4%） | 3.30 秒（9.7%） | 20.65 秒（60.6%；9.04/1.67/9.94） | 1.12 秒（3.3%） |
| 2 | 10.08 秒（27.9%） | 3.98 秒（11.0%） | 20.87 秒（57.7%；9.02/1.82/10.03） | 1.21 秒（3.3%） |
| 4 | 13.81 秒（33.5%） | 4.88 秒（11.8%） | 21.02 秒（50.9%；10.18/2.14/8.70） | 1.57 秒（3.8%） |

推理延迟随并发增加：并发 1/2/4 的均值分别为 21.91/24.97/34.03 ms，P95 分别为 27.31/38.13/58.78 ms。并发 4 新样本 8/8 有效且没有 2 秒超时；相较旧样本 2/8，有力支持线程过量竞争假设，但因为超时日志没有失败推理的内部计时，根因仍不能完全确认。新并发 4 平均 CPU 2.70 核、峰值内存约 3.9 GiB；并发 8 估算将接近 Docker 内存上限，因此未运行。

阶段 4.2 策略另测 4 局（4/4 有效、0 个完整轮换组）：平均助手决策 3.01 秒/局（8.6%）、Mortal 推理 9.16 秒/局（26.3%）；仅用于性能测量。另一个单局样本为 31 次助手决策，单样本不足以描述尾延迟。

按已测最佳并发 4，10,000 局东南战（hanchan）约需 **32.7 小时**。东风战无法由当前模拟器直接运行；若假设专用东风引擎只需一半非启动/清理耗时，粗略估计约 26.8 秒/局、10,000 局 **18.6 小时**，但这不是实测。如果只是从东南战中截取东场结果，仍须跑完整东南战，约需 32.7 小时。推理占比按并发 4 为 33.5%；ONNX 若让推理快 2 倍/4 倍，Amdahl 估算端到端吞吐提升约 20.1%/33.5%，理论上推理时间归零的上限约 50.4%。这些是 CPU 情景估计，不是 ONNX/GPU 实测。

ONNX CPU 改造属于中等工作量：导出所选 v3 模型、处理算子兼容、校验输出一致性并重测吞吐。GPU 改造工作量较高，因为当前 Mortal 推理固定使用 CPU，还需 CUDA PyTorch 镜像、容器 GPU 参数和驱动/显存验证。实际 GPU 加速倍数未知，因此这里只给条件式估算，不保证收益。两项改造均未开始，等待你决定。

**东风战限制：**当前安装的 `mjai.Simulator` 没有东风/东南模式参数，运行日志明确记录为 `hanchang game`。因此上述命令跑的是东南战（hanchan），不能当作东风战基准；如需东风战，必须先更换或扩展模拟器。

替代方案仅做过接口评估，尚未改造：安装版的 Rust `Match.py_match` 接受四个实现 `react_batch/start_game/end_kyoku/end_game` 的 agent 对象，理论上可在 Linux 容器里用本地 agent 绕过 Docker HTTP 层；并发 4 时容器/协议占 50.9%，全部消除的理论上限约为 2.04 倍，但真实收益会更低，且需要自行编写调度/状态适配并处理 Mortal 模型与进程生命周期，属于中高工作量。当前固定 Mortal 源码只有推理/数据加载组件，没有现成对局模拟器。另一种做法是从东南战牌谱中截取东场结束时的分数做东风代理；这只减少统计范围、不减少模拟耗时，而且 agari-yame 等终局语义可能不同。真正东风模拟仍需扩展或替换引擎。

### 评估规范与离线一致率

- 一个牌山组由同一 seed 元组下的四个座位轮换组成；先在组内汇总，再以组为独立样本计算 95% bootstrap 区间。缺少任一轮换的 seed 不算完整组，只能给出描述性均值，区间标为不可估。
- 超时、协议错误或模拟器错误的对局必须标为无效、从策略指标中排除，并同时报告尝试数、有效数、无效率和有效牌山组数。
- 每份评估报告都要给出样本量、完整轮换牌山组数、平均顺位及 95% 组级区间；没有完整组时区间标为不可估，均值只作描述。样本太少时只作冒烟验证，不下强弱结论。性能/离线报告中的平均顺位若来自原始对局，会明确标注为来源对局背景，不会当作新策略结果。
- 评估分层：第 0 层是离线出牌一致率；第 1 层是助手对 3 个基线 bot 的数百局粗筛；第 2 层是助手对 3 个 Mortal 的至少 1,000–2,000 局终验。

第 0 层可直接使用 Mortal 对局的 `mjai_log.json`。工具会为每个 Mortal 座位重放同一事件流，并把他家起手牌/摸牌替换为未知牌、移除模型 meta，再比较弃牌：

```powershell
.\.venv\Scripts\python.exe tools\evaluate_action_consistency.py logs\throughput\threads1-concurrency-1
```

报告包含精确物理牌一致率（保留赤五身份）和牌种一致率，并按早巡（第 1–6 次自摸）、中盘（7–12）、终盘（13 次起）、他家已立直、助手/原 Mortal 弃牌后是否听牌分组。置信区间按完整四座轮换牌山组 bootstrap；不完整轮换的数据只报描述均值、不计算区间。工具已在 1 场真实 Mortal 牌谱上验证：1/1 局有效、0 无效、421 个弃牌决策；精确牌一致率 52.0%、牌种一致率 52.3%，但只有 0 个完整轮换组，区间不可估。**出牌一致率只是代理指标，不等于胜率或策略强度**；报告也展示来源对局的平均顺位区间，且与离线回放结果分开标注。决策点逐个重放；如果助手选了立直，则清除该分支暂存的立直弃牌，以免把助手分支错误带入后续 Mortal 实际牌局。

### 核心牌型分析（阶段 4.1）

`src\mahjong_advisor\core.py` 提供统一的 34 种牌索引、保留赤五身份的 `Tile`、手牌计数、三种和牌形的向听数，以及按可见牌数量折算的有效进张。副露手牌不计算七对子和国士无双。纯效率 bot 复用这些分析函数。

运行核心与基线回归测试：

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_core tests.test_efficiency_bot -v
```

预期 11 项通过。核心 bot 与改造前的效率基线做了 4 场同种子座位轮换：核心平均顺位 **2.50**，基线平均顺位 **2.50**；配对平均顺位差 **0.00**。四场属于 **1 个牌山组**，种子层级 95% 区间不可估，结果仅作协议与策略冒烟验证，不能据此判断强弱。

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

该样本 4 场均有效，29 次立直均被接受；立直 bot 平均顺位 **1.00**，基线 **3.00**，四场配对差均为 **-2.00**。四场使用同一牌山种子，仅为 **1 个牌山组**，所以种子层级置信区间不可估。结果仅为协议与策略冒烟样本，不代表强度结论。

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
tools\profile_game_timing.py        分解单局推理、决策、容器/协议和模拟器耗时
tools\evaluate_action_consistency.py 离线重放 Mortal 局面并统计弃牌一致率
tools\evaluation_stats.py           按牌山组计算 bootstrap 区间
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
4. **Mortal 对照与性能评估**：CPU 并发 1/2/4 基准及离线一致率工具已完成；真实效能比较仍需使用完整四座轮换和规定样本量。
5. **规则助手**：核心牌型分析、效率弃牌和立直判断已完成；下一模块为防守策略，再实现役种/打点和局况权重配置。
6. **自动调参**：参数配置化，先小样本筛选，再对候选方案进行大样本验证并报告置信区间。
7. **提示窗**：置顶 Tkinter 小窗，仅显示一个当前推荐。
8. **好友房数据接入**：最后实现，并仅用于所有参与者知情同意的好友房。

每个阶段都应有独立的运行命令和针对性测试。Mortal 模型文件由使用者自行选择和核实；下载工具检查 SHA-256、安全加载及版本兼容。NVIDIA/Docker GPU 直通已在本机实际验证，但官方 Mortal 推理当前仍使用 CPU。

## 当前限制

- 当前摸切和纯牌效率 bot 仅用于模拟与基线对比，不是完整出牌提示助手。
- `mjai` 模拟器调用 Docker，首次启动需要拉取镜像和可用的网络连接。
- 吞吐测试中的 50 局固定座位，不能用于评价策略强度；目前对 Mortal 的座位轮换仍是小样本。
- 尚未实现防守、役种/打点、局况权重、自动调参或客户端通信解析。
