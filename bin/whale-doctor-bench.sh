#!/usr/bin/env bash
set -euo pipefail

ULTRA=/home/dev/whale/bin/whale
STOCK=/home/dev/whale-stock/bin/whale
RUNS=20
WARMUP=5

echo "=== DOCTOR BENCHMARK (${RUNS} runs, ${WARMUP} warmup) ==="
echo ""

bench() {
  local bin=$1 label=$2
  echo "${label}:"
  
  for i in $(seq 1 ${WARMUP}); do
    ${bin} doctor 2>/dev/null >/dev/null
  done
  
  local times=()
  for i in $(seq 1 ${RUNS}); do
    local start_ns=$(date +%s%N)
    ${bin} doctor 2>/dev/null >/dev/null
    local end_ns=$(date +%s%N)
    times+=($(( (end_ns - start_ns) / 1000000 )))
  done
  
  IFS=$'\n' sorted=($(sort -n <<<"${times[*]}"))
  local sum=0
  for t in "${sorted[@]}"; do sum=$((sum + t)); done
  
  local avg=$((sum / RUNS))
  local p50=${sorted[$((RUNS/2))]}
  local p95=${sorted[$((RUNS*95/100))]}
  local p99=${sorted[$((RUNS*99/100))]}
  
  printf "  avg=%-4sms  p50=%-4sms  p95=%-4sms  p99=%-4sms  min=%-4sms  max=%-4sms\n" \
    "$avg" "$p50" "$p95" "$p99" "${sorted[0]}" "${sorted[$((RUNS-1))]}"
}

bench "${ULTRA}" "ULTRA"
bench "${STOCK}" "STOCK"

echo ""
echo "=== BINARY METRICS ==="
echo ""

U_SIZE=$(wc -c < ${ULTRA})
S_SIZE=$(wc -c < ${STOCK})
U_SYMS=$(nm ${ULTRA} 2>/dev/null | wc -l)
S_SYMS=$(nm ${STOCK} 2>/dev/null | wc -l)
U_TEXT=$(size ${ULTRA} | tail -1 | awk '{print $1}')
S_TEXT=$(size ${STOCK} | tail -1 | awk '{print $1}')
SIZE_DELTA=$(echo "scale=1; (1 - ${U_SIZE} / ${S_SIZE}) * 100" | bc)

# ISA counts
U_FMA=$(objdump -d ${ULTRA} 2>/dev/null | grep -cE 'vfmadd|vfmsub|vfnmadd|vfnmsub' || echo 0)
S_FMA=$(objdump -d ${STOCK} 2>/dev/null | grep -cE 'vfmadd|vfmsub|vfnmadd|vfnmsub' || echo 0)
U_BMI=$(objdump -d ${ULTRA} 2>/dev/null | grep -cE 'blsr|blsmsk|blsi|bzhi|pdep|pext|rorx|sarx|shlx|shrx' || echo 0)
S_BMI=$(objdump -d ${STOCK} 2>/dev/null | grep -cE 'blsr|blsmsk|blsi|bzhi|pdep|pext|rorx|sarx|shlx|shrx' || echo 0)
U_AVX2=$(objdump -d ${ULTRA} 2>/dev/null | grep -cE 'vpbroadcast|vperm2i128|vpgather' || echo 0)
S_AVX2=$(objdump -d ${STOCK} 2>/dev/null | grep -cE 'vpbroadcast|vperm2i128|vpgather' || echo 0)

printf "%-25s %10s %10s %10s\n" "Metric" "ULTRA" "STOCK" "Delta"
echo   "---------------------------------------------------------------"
printf "%-25s %10s %10s %10s\n" "Binary size" "$(du -h ${ULTRA} | cut -f1)" "$(du -h ${STOCK} | cut -f1)" "-${SIZE_DELTA}%"
printf "%-25s %10d %10d %10s\n" "Symbols" "${U_SYMS}" "${S_SYMS}" "-100%"
printf "%-25s %10s %10s %10s\n" ".text bytes" "${U_TEXT}" "${S_TEXT}" "-$((S_TEXT - U_TEXT))"
echo ""
printf "%-25s %10d %10d %10s\n" "FMA instructions" "${U_FMA}" "${S_FMA}" "$(echo "scale=1; ${U_FMA} / ${S_FMA}" | bc)x"
printf "%-25s %10d %10d %10s\n" "BMI2 instructions" "${U_BMI}" "${S_BMI}" "$(echo "scale=1; ${U_BMI} / ${S_BMI}" | bc)x"
printf "%-25s %10d %10d %10s\n" "AVX2 instructions" "${U_AVX2}" "${S_AVX2}" "$(echo "scale=1; ${U_AVX2} / ${S_AVX2}" | bc)x"

echo ""
echo "Done."
