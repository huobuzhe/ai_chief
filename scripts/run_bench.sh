#!/usr/bin/env bash
# =============================================================================
# scripts/run_bench.sh —— 阶段 10 压测编排脚本（Git Bash 版）
# =============================================================================
# 这个脚本干什么：
#   把"压测"这件很啰嗦的事收成一条命令——自动对每个目标、每个并发档位各跑一轮
#   Locust，每轮的 CSV 分开存放，最后汇总成一张表。
#   手敲 6~8 次 locust 命令既容易漏参数，又容易忘记清配额，结果前后两轮数据不可比。
#
# 怎么用（都在项目根目录 F:\pycharm_aiprogram\ai_chief 下执行）：
#   bash scripts/run_bench.sh                     # 默认：两个目标 × 单档 20 用户 × 60 秒
#   bash scripts/run_bench.sh gateway             # 只压网关
#   bash scripts/run_bench.sh all "10,20,40,60" 30   # 两个目标 × 4 个并发档 × 每档 30 秒（找拐点用）
#
# 为什么参数是"逗号分隔的档位列表"而不是单一并发数：
#   要回答"错误率拐点在哪"，就必须一路加压，直到 P99 明显变差或出现失败。
#   一档一档跑，才能把拐点画出来；只跑一档只能得到"某个并发下还行"，写不进报告。
#
# 🔴 跑之前必须已经满足的条件（否则测出来的是"限流值"，不是"架构容量"）：
#   ① 服务端 MOCK_LLM=true 启动（不真调大模型）
#   ② 服务端 RATE_LIMIT_PER_MINUTE / RATE_LIMIT_USER_PER_MINUTE 调高
#   ③ 当天租户配额已清（free 套餐 chat_daily 只有 50 次）
#   ④ Kong 网关 rate-limiting 已调高
#   ⑤ 5 个服务都健康（9002 / 9121 / 9122 / 9123 / 9124）
#   这五条在操作手册里都有对应步骤和验证命令。
# =============================================================================

set -euo pipefail

# ---------- 参数 ----------
TARGET_SCOPE="${1:-all}"                                  # all | monolith | gateway
USERS_LIST="${2:-20}"                                     # 逗号分隔，如 "10,20,40,60"
RUN_SECONDS="${3:-60}"                                    # 每档跑多少秒

# ---------- 路径与解释器 ----------
cd "$(dirname "$0")/.."                                     # 切到项目根目录（不管从哪调都能跑）

# 解释器允许用环境变量覆盖：PY=/path/to/python.exe bash scripts/run_bench.sh
# 默认用项目自己的虚拟环境。**绝不能写裸 python**——Windows 上会先命中 Anaconda 3.6，
# 那个环境的 pytest/库版本太老，读 UTF-8 配置时按 GBK 解，直接 UnicodeDecodeError。
PY="${PY:-./.venv3/Scripts/python.exe}"

# 🔴 这一步检查不能省。少了它，"解释器路径不存在"这条错误会被后面的
#    `... | grep ... || true` 整个吞掉：屏幕上只看到"目标=monolith 并发=5"
#    然后一行结果都没有、reports 目录空着，人会以为是自己哪里写错了，
#    实际上压测压根没启动（阶段 10 第一版脚本就踩了这个坑）。
if [ ! -f "$PY" ]; then
  echo "[中止] 找不到虚拟环境解释器: $PY"
  echo "       · 确认你是在项目根目录（含 .venv3 的那个）执行的"
  echo "       · 或者显式指定：PY=/绝对路径/python.exe bash scripts/run_bench.sh"
  exit 1
fi

LOCUSTFILE="benchmarks/locustfile.py"
if [ ! -f "$LOCUSTFILE" ]; then
  echo "[中止] 找不到压测脚本: $LOCUSTFILE（当前目录 $(pwd)）"
  exit 1
fi

REPORT_DIR="reports/bench_$(date +%Y%m%d_%H%M%S)"         # 按时间戳分目录，避免覆盖上一轮
mkdir -p "$REPORT_DIR"

# ---------- 目标表：名字 → 地址 ----------
# monolith = 阶段 8 之前的单体，所有接口在一个进程里
# gateway  = 阶段 9 拆成 4 个服务后、经 Kong 网关的入口（用户真正访问的那个地址）
declare -A HOSTS=(
  [monolith]="http://127.0.0.1:9002"
  [gateway]="http://127.0.0.1:9100"
)
ORDER=(monolith gateway)                                   # 固定顺序，压测顺序一致才不会互相干扰

# ---------- 前置检查：服务必须先活着 ----------
echo "=============================================================="
echo " 阶段 10 压测开始  $(date '+%Y-%m-%d %H:%M:%S')"
echo " 输出目录: $REPORT_DIR"
echo "=============================================================="

for p in 9002 9121 9122 9123 9124; do
  if ! curl -s -m 3 "http://127.0.0.1:$p/health" > /dev/null; then
    echo "[中止] 端口 $p 不通。按操作手册先把 5 个服务起好再压测。"
    exit 1
  fi
done
echo "[前置检查] 5 个服务 health 全部通过"

# 清当天配额：free 套餐 chat_daily 上限 50 次，压测几十秒就会打满，
# 之后所有 chat 请求返回 429，报告里就变成"一堆 429"，看不出真实容量。
docker exec ai_chief_redis redis-cli --scan --pattern "quota:*" 2>/dev/null | while read -r k; do
  [ -n "$k" ] && docker exec ai_chief_redis redis-cli DEL "$k" > /dev/null
done
echo "[前置检查] 已清空当天租户配额计数"

# ---------- 主循环 ----------
IFS=',' read -r -a USER_ARRAY <<< "$USERS_LIST"

for target in "${ORDER[@]}"; do
  if [ "$TARGET_SCOPE" != "all" ] && [ "$TARGET_SCOPE" != "$target" ]; then
    continue
  fi
  host="${HOSTS[$target]}"
  for users in "${USER_ARRAY[@]}"; do
    csv="$REPORT_DIR/${target}_u${users}"
    echo ""
    echo "--------------------------------------------------------------"
    echo " 目标=$target  地址=$host  并发=$users  时长=${RUN_SECONDS}s"
    echo "--------------------------------------------------------------"
    # --headless        不开网页界面，直接命令行跑（CI/脚本里必须加）
    # --spawn-rate      每秒启动多少个虚拟用户。这里取"3 秒内把本档用户全起完"，
    #                    而不是一秒全上：一秒全上时，头几秒全是冷启动（连接池要新建、
    #                    Milvus/Neo4j 要重连），这些慢请求会把平均值和 P99 整体拉高，
    #                    测出来的不是"稳态容量"。留 3 秒爬坡，这 3 秒在 45 秒的一轮里
    #                    只占 7%，对结果的影响可以忽略。
    # --csv             输出 CSV：_stats.csv（分场景明细）/ _stats_history.csv（时间序列，找拐点用）/ _failures.csv
    # 🔴 这里**故意不接 `| grep` 过滤**：一接管道，locust 自己报的任何错（找不到文件、
    #    参数写错、解释器起不来）都会被过滤掉，只剩一行安静的分隔线，
    #    排查时完全看不出发生了什么。让它原样打出来，乱一点但可追溯。
    spawn=$(( users / 3 ))
    [ "$spawn" -lt 1 ] && spawn=1
    "$PY" -m locust -f "$LOCUSTFILE" \
      --headless \
      --host "$host" \
      --users "$users" \
      --spawn-rate "$spawn" \
      --run-time "${RUN_SECONDS}s" \
      --csv "$csv" \
      --csv-full-history \
      --only-summary
  done
done

echo ""
echo "=============================================================="
echo " 压测结束，结果 CSV 在: $REPORT_DIR"
echo " 下一步：用报告脚本把它汇总成一张对比表"
echo "   $PY scripts/locust_report.py --dir \"$REPORT_DIR\""
echo "=============================================================="