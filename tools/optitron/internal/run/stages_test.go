package run
import (
	"context"
	"os/exec"
	"testing"
	"github.com/peterlodri-sec/vaked-base/tools/optitron/internal/gate"
)
func TestRunBenchRealCompile(t *testing.T) {
	if _, err := exec.LookPath("cc"); err != nil {
		t.Skip("cc not available")
	}
	const prog = `#include <stdio.h>
int main(void){
  /* a deterministic, fixed sentinel: optimized is 20% faster than baseline */
  printf("OPTITRON_BENCH baseline=1000 optimized=800\n");
  return 0;
}`
	res, err := RunBench(context.Background(), gate.BenchSpec{Lang: "c", Source: prog}, true)
	if err != nil {
		t.Fatalf("RunBench: %v", err)
	}
	if res == nil {
		t.Fatal("expected a measured result")
	}
	if res.Delta < 0.19 || res.Delta > 0.21 {
		t.Errorf("delta = %v, want ~0.20", res.Delta)
	}
}
func TestRunBenchDisabled(t *testing.T) {
	res, err := RunBench(context.Background(), gate.BenchSpec{Lang: "c", Source: "int main(){}"}, false)
	if err != nil || res != nil {
		t.Fatalf("disabled bench must return (nil,nil), got (%v,%v)", res, err)
	}
}
func TestBudgetGuard(t *testing.T) {
	b := NewBudget(1.0)
	if b.Over() {
		t.Fatal("fresh budget should not be over")
	}
	b.Spend(0.6)
	if b.Over() {
		t.Fatal("0.6/1.0 should not be over")
	}
	b.Spend(0.5)
	if !b.Over() {
		t.Fatal("1.1/1.0 should be over")
	}
}