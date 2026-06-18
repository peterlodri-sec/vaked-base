package run
import (
	"fmt"
	"github.com/peterlodri-sec/vaked-base/tools/optitron/internal/ledger"
)
func Events(cfg *Config, replay bool) error {
	entries, err := ledger.Load(cfg.EventsPath)
	if err != nil {
		return err
	}
	ok := ledger.VerifyChain(entries)
	var found []map[string]any
	for _, e := range entries {
		if ev, _ := e.Payload["event"].(string); ev == "found" {
			found = append(found, e.Payload)
		}
	}
	status := "OK"
	if !ok {
		status = "BROKEN"
	}
	fmt.Printf("events: %d · chain %s · findings: %d\n", len(entries), status, len(found))
	if replay {
		for _, p := range found {
			delta, _ := p["delta"].(float64)
			fmt.Printf("  - %v (%v, %.0f%%) %v\n", p["title"], p["area"], delta*100, p["issue"])
		}
	}
	if !ok {
		return fmt.Errorf("chain broken")
	}
	return nil
}