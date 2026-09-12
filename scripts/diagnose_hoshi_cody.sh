#!/usr/bin/env bash
# ============================================================================
#  diagnose_hoshi_cody.sh  —  在 cody_pc (192.168.31.53, Ubuntu 24.04) 上运行
#  目的：查清 hoshi 定时任务"为什么没了 / 为什么没正常运行"，并可选修复。
#
#  用法：
#     bash diagnose_hoshi_cody.sh            # 只做只读诊断（安全）
#     bash diagnose_hoshi_cody.sh --fix      # 诊断 + 重新安装 cron（会先展示将要做什么）
#
#  说明：本脚本默认只读。--fix 也只在你确认后才写 crontab。
#        所有路径/账号可用环境变量覆盖（见下方变量）。
# ============================================================================
set -u

# ---- 可覆盖的配置（按需修改） --------------------------------------------
PROJECT_DIR="${PROJECT_DIR:-/home/cody/projects/quant-trader}"
VENV_PY="${VENV_PY:-$PROJECT_DIR/.venv/bin/python}"
RUNNER="${RUNNER:-$PROJECT_DIR/scripts/run_hoshi_pg.py}"
LIVE_SH="${LIVE_SH:-$PROJECT_DIR/scripts/run_hoshi_live_cody.sh}"
PG_DB="${PG_DB:-quant_minute}"
PG_USER="${PG_USER:-postgres}"
LOG_DIR="${LOG_DIR:-/home/cody/logs}"
# hoshi 实盘决策：A股收盘 15:00 北京时间，建议 15:30 后跑（工作日）
RUN_HOUR="${RUN_HOUR:-15}"
RUN_MIN="${RUN_MIN:-30}"

echo "============================================================"
echo " 0. 运行环境"
echo "============================================================"
whoami; hostname; date
echo "PROJECT_DIR=$PROJECT_DIR"
echo "server TZ: $(cat /etc/timezone 2>/dev/null || timedatectl show --property=Timezone 2>/dev/null)"
echo

echo "============================================================"
echo " 1. 当前 crontab（找 hoshi / daily_update / quant_bridge）"
echo "============================================================"
if crontab -l >/tmp/crontab_now 2>/tmp/crontab_err; then
  grep -nE "hoshi|daily_update|quant_bridge|cody" /tmp/crontab_now || echo "  (crontab 中没有匹配 hoshi 的行 —— 任务确实'没了')"
else
  echo "  crontab -l 失败: $(cat /tmp/crontab_err)"
fi
echo

echo "============================================================"
echo " 2. fail2ban：本机 IP 是否被封？（SSH 握手被掐的常见原因）"
echo "============================================================"
if command -v fail2ban-client >/dev/null 2>&1; then
  sudo fail2ban-client status sshd 2>&1 | head -20
  echo "  -- 已封 IP --"
  sudo fail2ban-client get sshd bannedip 2>&1 | head
else
  echo "  fail2ban-client 不存在（可能用了其他方式限流）"
fi
echo "  -- 本机出口 IP --"
ip route get 1.1.1.1 2>/dev/null | head -1
hostname -I 2>/dev/null
echo

echo "============================================================"
echo " 3. hoshi 运行脚本是否存在 / 可执行"
echo "============================================================"
ls -l "$LIVE_SH" 2>&1
ls -l "$RUNNER" 2>&1
ls -l "$VENV_PY" 2>&1
echo

echo "============================================================"
echo " 4. PostgreSQL：库与表是否就绪（run_hoshi_pg.py 依赖它们）"
echo "============================================================"
sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='$PG_DB'" 2>&1 | sed 's/^/  db_exists: /'
sudo -u postgres psql -d "$PG_DB" -tAc "SELECT 'daily_kline='||count(*) FROM daily_kline" 2>&1 | sed 's/^/  /' || true
sudo -u postgres psql -d "$PG_DB" -tAc "SELECT 'stock_info='||count(*) FROM stock_info" 2>&1 | sed 's/^/  /' || true
echo

echo "============================================================"
echo " 5. 历史日志：cron / mail 里有没有 hoshi 的报错"
echo "============================================================"
( grep -i hoshi /var/log/syslog /var/log/cron.log 2>/dev/null | tail -20 ) || echo "  无 syslog/cron.log 匹配"
echo "  -- 最近一次 cron 投递邮件（若有）--"
( grep -i hoshi /var/mail/$USER 2>/dev/null | tail -20 ) || echo "  无 mail 匹配"
echo

echo "============================================================"
echo " 6. 手动试跑 hoshi（用 venv python，看真实报错）"
echo "============================================================"
mkdir -p "$LOG_DIR"
cd "$PROJECT_DIR" || { echo "  无法 cd $PROJECT_DIR"; exit 1; }
"$VENV_PY" "$RUNNER" --top 5 --min-score 4.0 2>&1 | tail -40
echo

if [ "${1:-}" != "--fix" ]; then
  echo "============================================================"
  echo " 诊断完成（只读）。如需自动修复（重新安装 cron），运行："
  echo "   bash $0 --fix"
  echo "============================================================"
  exit 0
fi

echo "============================================================"
echo " 7. [--fix] 将要执行的修复"
echo "============================================================"
SERVER_TZ="$(cat /etc/timezone 2>/dev/null)"
# 计算 UTC 等价时间（仅展示用）
python3 - <<PY 2>/dev/null || true
import datetime
try:
    import zoneinfo
    tz=zoneinfo.ZoneInfo("${SERVER_TZ:-Asia/Shanghai}")
    lt=datetime.time($RUN_HOUR,$RUN_MIN)
    utc=(datetime.datetime.combine(datetime.date(2000,1,1),lt,tzinfo=tz)).astimezone(zoneinfo.ZoneInfo("UTC"))
    print(f"  服务器时区={tz}  本地 {RUN_HOUR}:{RUN_MIN}  ≈  UTC {utc.hour:02d}:{utc.minute:02d}")
except Exception as e:
    print("  (无法换算时区，请人工确认)")
PY

CRON_LINE="$RUN_MIN $RUN_HOUR * * 1-5 cd $PROJECT_DIR && $VENV_PY $RUNNER --mode confirmation --top 30 --min-score 4.0 >> $LOG_DIR/hoshi_live.log 2>&1"
echo "  将写入 crontab 的行（工作日 $RUN_HOUR:$RUN_MIN 本地时间）："
echo "    $CRON_LINE"
echo
read -r -p "  确认写入？[y/N] " ANS
if [ "${ANS:-N}" != "y" ] && [ "${ANS:-N}" != "Y" ]; then
  echo "  已取消，未修改 crontab。"
  exit 0
fi

# 去掉旧的 hoshi 行（幂等），再追加新的
crontab -l 2>/dev/null | grep -vE "run_hoshi_pg|hoshi_live" > /tmp/crontab_new
echo "$CRON_LINE" >> /tmp/crontab_new
crontab /tmp/crontab_new
echo "  已更新 crontab。当前 hoshi 相关行："
crontab -l | grep -nE "hoshi"
echo "  日志将写入：$LOG_DIR/hoshi_live.log"
echo "  解除 fail2ban 封禁（若本机 IP 被封）： sudo fail2ban-client set sshd unbanip <本机IP>"
