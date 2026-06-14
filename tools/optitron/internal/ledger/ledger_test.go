package ledger

import (
	"path/filepath"
	"sync"
	"testing"
)

func TestChainAppendVerify(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "events.jsonl")
	w, err := Open(path)
	if err != nil {
		t.Fatal(err)
	}
	for i := 0; i < 5; i++ {
		if _, err := w.Append(map[string]any{"event": "crawl", "n": i}); err != nil {
			t.Fatal(err)
		}
	}
	entries, err := Load(path)
	if err != nil {
		t.Fatal(err)
	}
	if len(entries) != 5 {
		t.Fatalf("want 5 entries, got %d", len(entries))
	}
	if !VerifyChain(entries) {
		t.Fatal("freshly written chain should verify")
	}
}

func TestTornTailRecovery(t *testing.T) {
	entries := make([]Entry, 0)
	prev := GenesisHash
	for i := 0; i < 3; i++ {
		e, _ := MakeEntry(prev, i, map[string]any{"i": i})
		entries = append(entries, e)
		prev = e.Hash
	}
	// Tamper the last entry's payload — chain must now fail, prefix is the first 2.
	entries[2].Payload = map[string]any{"i": 999}
	if VerifyChain(entries) {
		t.Fatal("tampered chain must not verify")
	}
	if got := LongestValidPrefix(entries); len(got) != 2 {
		t.Fatalf("want valid prefix of 2, got %d", len(got))
	}
}

// TestConcurrentAppend asserts the single-writer invariant holds under
// concurrency: N goroutines append and the resulting chain still verifies.
func TestConcurrentAppend(t *testing.T) {
	path := filepath.Join(t.TempDir(), "events.jsonl")
	w, err := Open(path)
	if err != nil {
		t.Fatal(err)
	}
	var wg sync.WaitGroup
	for i := 0; i < 50; i++ {
		wg.Add(1)
		go func(n int) {
			defer wg.Done()
			if _, err := w.Append(map[string]any{"event": "rejected", "n": n}); err != nil {
				t.Error(err)
			}
		}(i)
	}
	wg.Wait()
	entries, err := Load(path)
	if err != nil {
		t.Fatal(err)
	}
	if len(entries) != 50 {
		t.Fatalf("want 50 entries, got %d", len(entries))
	}
	if !VerifyChain(entries) {
		t.Fatal("concurrent appends produced an invalid chain")
	}
}
